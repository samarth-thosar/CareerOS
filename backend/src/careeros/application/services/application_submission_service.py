"""ApplicationSubmissionService -- turns an approved selection into a submitted application.

The user's model is: CareerOS lists, the user picks, CareerOS applies. So approval is an explicit act on specific
job ids, never a threshold the system crosses on its own. `feature_flags.auto_apply_enabled` exists but only
governs whether an *approved* batch may submit without a second confirmation -- it never selects jobs.

Three guards, all of which must pass before anything is sent:

1. **Never apply twice.** Re-checked here immediately before submission even though `Application.apply()` and a
   unique constraint also enforce it, because this is the last moment before an irreversible outward action.
2. **Never submit an incomplete form.** If any required application answer is still a placeholder, the batch
   refuses. Sending an invented notice period or salary to a real employer is worse than not applying.
3. **Never submit without a resume.** A submission with no tailored resume attached is not an application worth
   making, so it is refused rather than sent bare.

Actual form-filling is per-source and gated on `JobSourceProvider.supports_auto_submit`. No source supports it
yet, so this service prepares and records the submission and reports `manual_url` for the ones that need a
human to press the final button -- which is the honest state of things rather than a pretence of automation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.form_filler import (
    BatchFormFillResult,
    FormFillRequest,
    FormFillResult,
    FormFiller,
)
from careeros.application.ports.job_source_provider import JobSourceProvider
from careeros.domain.application.application import AlreadyAppliedError, ApplicationStatus
from careeros.domain.candidate.application_answers import ApplicationAnswers
from careeros.domain.events import ApplicationStatusChanged, ApplicationSubmitted
from careeros.domain.repositories import (
    ApplicationRepository,
    CompanyRepository,
    JobRepository,
    ResumeRepository,
)

logger = logging.getLogger(__name__)


class AnswersIncompleteError(RuntimeError):
    """Raised when required application answers are still placeholders."""


@dataclass(slots=True)
class SubmissionResult:
    job_id: str
    submitted: bool
    needs_manual_step: bool = False
    manual_url: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class BatchSubmissionResult:
    submitted: list[SubmissionResult] = field(default_factory=list)
    skipped: list[SubmissionResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {"submitted": len(self.submitted), "skipped": len(self.skipped)}


class ApplicationSubmissionService:
    def __init__(
        self,
        application_repository: ApplicationRepository,
        job_repository: JobRepository,
        resume_repository: ResumeRepository,
        company_repository: CompanyRepository,
        providers: list[JobSourceProvider],
        answers: ApplicationAnswers,
        event_bus: EventBus,
        clock: Clock,
        form_filler: FormFiller | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._job_repository = job_repository
        self._resume_repository = resume_repository
        self._company_repository = company_repository
        self._providers = {provider.name: provider for provider in providers}
        self._answers = answers
        self._event_bus = event_bus
        self._clock = clock
        self._form_filler = form_filler

    async def submit_selected(self, job_ids: list[str]) -> BatchSubmissionResult:
        """Apply to exactly the jobs the user picked.

        Fails the whole batch up front when answers are incomplete -- that is a single fixable cause, and
        reporting it once beats the same message repeated per job.
        """
        missing = self._answers.missing_fields()
        if missing:
            raise AnswersIncompleteError(
                "These application answers still need you before anything can be submitted: "
                + ", ".join(missing)
            )

        result = BatchSubmissionResult()
        for job_id in job_ids:
            outcome = await self._submit_one(job_id)
            (result.submitted if outcome.submitted else result.skipped).append(outcome)
        logger.info("Submission batch: %s", result.counts)
        return result

    async def _submit_one(self, job_id: str) -> SubmissionResult:
        job = await self._job_repository.get_by_id(job_id)
        if job is None:
            return SubmissionResult(job_id=job_id, submitted=False, reason="job no longer exists")

        application = await self._application_repository.get_by_job_id(job_id)
        if application is None:
            return SubmissionResult(job_id=job_id, submitted=False, reason="not tracked")

        # Guard 1, re-checked at the last moment before an irreversible outward action.
        if application.applied_at is not None:
            return SubmissionResult(
                job_id=job_id, submitted=False, reason=f"already applied on {application.applied_at:%Y-%m-%d}"
            )

        # Guard 3: a bare application is not worth making.
        versions = await self._resume_repository.list_versions_for_job(job_id)
        if not versions:
            return SubmissionResult(
                job_id=job_id, submitted=False, reason="no tailored resume yet — tailor one first"
            )

        provider = self._providers.get(job.source.value)
        if provider is None or not provider.supports_auto_submit:
            # Honest reporting rather than pretending: the form still needs a human.
            return SubmissionResult(
                job_id=job_id,
                submitted=False,
                needs_manual_step=True,
                manual_url=job.url,
                reason=f"{job.source.value} forms are not automatable yet",
            )

        return await self._record_submission(application, job, method=f"{job.source.value}:auto")

    async def _record_submission(self, application, job, *, method: str) -> SubmissionResult:
        now = self._clock.now()
        try:
            application.apply(at=now)
        except AlreadyAppliedError as error:
            return SubmissionResult(job_id=job.id, submitted=False, reason=str(error))

        await self._application_repository.save(application)
        await self._event_bus.publish(
            ApplicationSubmitted(application_id=application.id, job_id=job.id, method=method)
        )
        await self._event_bus.publish(
            ApplicationStatusChanged(
                application_id=application.id,
                job_id=job.id,
                from_status=ApplicationStatus.RESUME_GENERATED.value,
                to_status=ApplicationStatus.APPLIED.value,
                reason=f"submitted via {method}",
                actor="user-approved",
            )
        )
        return SubmissionResult(job_id=job.id, submitted=True)

    async def prepare_forms(self, job_ids: list[str]) -> BatchFormFillResult:
        """Open one tab per selected job, each with the form already drafted, and leave them for review.

        Batched because the workflow is "queue several, come back, review them together" -- one browser with N
        tabs, not N browsers. Per-job refusals are reported rather than raised so one unready job does not
        abandon the rest of the batch; incomplete answers are the exception, since that blocks everything and
        saying so once is clearer than repeating it per job.
        """
        if self._form_filler is None or not self._form_filler.is_available():
            return BatchFormFillResult(
                skipped=[
                    FormFillResult(job_id=job_id, error="Browser automation unavailable (Playwright missing)")
                    for job_id in job_ids
                ]
            )

        missing = self._answers.missing_fields()
        if missing:
            raise AnswersIncompleteError(
                "These answers still need you before any form can be drafted: " + ", ".join(missing)
            )

        requests: list[FormFillRequest] = []
        upfront_skips: list[FormFillResult] = []
        for job_id in job_ids:
            request, reason = await self._build_request(job_id)
            if request is None:
                upfront_skips.append(FormFillResult(job_id=job_id, error=reason))
            else:
                requests.append(request)

        batch = await self._form_filler.prepare(requests)
        batch.skipped = [*upfront_skips, *batch.skipped]
        return batch

    async def _build_request(self, job_id: str) -> tuple[FormFillRequest | None, str | None]:
        """Assemble one form-fill request, or explain why this job is not ready for one."""
        job = await self._job_repository.get_by_id(job_id)
        application = await self._application_repository.get_by_job_id(job_id)
        if job is None or application is None:
            return None, "job is not tracked"
        if application.applied_at is not None:
            return None, f"already applied on {application.applied_at:%Y-%m-%d}"

        versions = await self._resume_repository.list_versions_for_job(job_id)
        rendered = next((version for version in versions if version.pdf_path), None)
        if rendered is None:
            return None, "no tailored resume PDF yet — tailor one first"

        letter = None
        if application.current_cover_letter_id:
            stored = await self._resume_repository.get_cover_letter(application.current_cover_letter_id)
            letter = stored.content if stored else None

        # Company name is for the review report, so the candidate can tell the tabs apart at a glance.
        company = await self._company_repository.get_by_id(job.company_id)
        return (
            FormFillRequest(
                job_id=job_id,
                job_title=job.title,
                company_name=company.name if company else "unknown",
                job_url=job.url,
                answers=_form_answers(self._answers),
                resume_pdf_path=rendered.pdf_path,
                cover_letter=letter,
            ),
            None,
        )

    async def confirm_manual_submission(self, job_id: str) -> SubmissionResult:
        """Record that the user submitted a form themselves.

        Needed because most ATS forms are not automatable, and an application that happened but is not recorded
        breaks both the never-apply-twice guard and every downstream outcome metric.
        """
        job = await self._job_repository.get_by_id(job_id)
        application = await self._application_repository.get_by_job_id(job_id)
        if job is None or application is None:
            return SubmissionResult(job_id=job_id, submitted=False, reason="not tracked")
        if application.applied_at is not None:
            return SubmissionResult(job_id=job_id, submitted=False, reason="already recorded")
        return await self._record_submission(application, job, method="manual")


def _form_answers(answers: ApplicationAnswers) -> dict[str, str]:
    """Flatten answers into the keys a form filler looks for.

    First/last name are derived rather than stored separately: forms disagree on whether they want one field or
    two, and asking the candidate for both spellings of the same fact would be busywork.
    """
    parts = answers.full_name.split()
    return {
        "full_name": answers.full_name,
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
        "email": answers.email,
        "phone": answers.phone,
        "current_location": answers.current_location,
        "linkedin_url": answers.linkedin_url,
        "github_url": answers.github_url,
        "portfolio_url": answers.portfolio_url,
    }
