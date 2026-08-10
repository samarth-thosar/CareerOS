"""ResumeManagerService -- produces a tailored resume for one job.

Sequence: read the master template and achievement bank, ask the model to *select* content, validate that
selection against what the candidate can actually claim, assemble the .tex deterministically, attempt a PDF,
and write a self-contained artifact folder.

Two guarantees this service is built around:

* **Never invent.** The model only chooses achievement ids and reworded versions of existing bullets, and
  `validate_plan` rejects the whole selection if anything is unsupported. A rejected plan raises rather than
  being partially applied -- a selection that tried to fabricate once is not trustworthy for its other picks.
* **Never overwrite.** Each run creates a new ResumeVersion and a new artifact directory, so every version the
  candidate ever generated stays inspectable.

Gaps the bank cannot support become ResumeGapFlags for the candidate to resolve, which is one of the decisions
the user explicitly keeps for themselves.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from careeros.application.ports.artifact_store import ArtifactStore
from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.application.ports.resume_assembler import ResumeAssembler
from careeros.application.ports.resume_renderer import ResumeRenderer
from careeros.application.ports.resume_source import ResumeSource
from careeros.application.prompts.tailoring_prompt import (
    TAILORING_STRATEGY_VERSION,
    build_tailoring_prompt,
)
from careeros.domain.events import ResumeGapFlagged, ResumeGenerated
from careeros.domain.repositories import (
    CandidateProfileRepository,
    CompanyRepository,
    JobRepository,
    ResumeRepository,
)
from careeros.domain.resume.achievement import AchievementBank
from careeros.domain.resume.resume_version import GapFlagStatus, ResumeGapFlag, ResumeVersion
from careeros.domain.resume.tailoring import (
    AchievementSelection,
    BulletSelection,
    TailoringPlan,
    validate_plan,
)

logger = logging.getLogger(__name__)


class TailoringResponseError(ValueError):
    """Raised when the model's tailoring response is structurally unusable."""




@dataclass(frozen=True, slots=True)
class TailoringOutcome:
    resume_version_id: str
    artifact_directory: Path
    pdf_rendered: bool
    pdf_unavailable: bool
    gap_count: int


class ResumeManagerService:
    def __init__(
        self,
        resume_repository: ResumeRepository,
        job_repository: JobRepository,
        company_repository: CompanyRepository,
        candidate_profile_repository: CandidateProfileRepository,
        resume_source: ResumeSource,
        achievement_bank: AchievementBank,
        renderer: ResumeRenderer,
        artifact_store: ArtifactStore,
        assembler: ResumeAssembler,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._resume_repository = resume_repository
        self._job_repository = job_repository
        self._company_repository = company_repository
        self._candidate_profile_repository = candidate_profile_repository
        self._resume_source = resume_source
        self._achievement_bank = achievement_bank
        self._renderer = renderer
        self._artifact_store = artifact_store
        self._assembler = assembler
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def tailor_for_job(self, job_id: str, application_id: str | None = None) -> TailoringOutcome:
        job = await self._job_repository.get_by_id(job_id)
        if job is None:
            raise LookupError(f"Job {job_id} does not exist")

        profile = await self._candidate_profile_repository.get()
        if profile is None:
            raise RuntimeError("No candidate profile seeded; load config/profile.yaml before tailoring")

        company = await self._company_repository.get_by_id(job.company_id)
        company_name = company.name if company else "unknown"

        master = await self._resume_source.fetch_master()
        self._warn_about_template(master.content)
        prompt = build_tailoring_prompt(job, company_name, profile, self._achievement_bank)
        response = await self._llm_provider.complete(prompt)
        if response.parsed is None:
            raise TailoringResponseError(f"Model returned no parseable JSON when tailoring for job {job_id}")

        plan, dropped_skills = _drop_unclaimable_skills(
            _plan_from(response.parsed), self._achievement_bank, profile.skills
        )
        # Raises on any unsupported id, bullet index or invented figure. Skills were sanitised just above rather
        # than left to raise: an over-eager skills line is fixable by removing it, whereas a fabricated
        # achievement or metric means the whole selection is untrustworthy.
        validate_plan(plan, self._achievement_bank, profile.skills)

        tailored_tex = self._assembler.assemble(master.content, plan, self._achievement_bank)

        now = self._clock.now()
        directory = self._artifact_store.allocate(
            company_name=company_name, job_title=job.title, at=now
        )
        render = await self._renderer.render(tailored_tex, directory, "resume")
        if not render.succeeded and not render.unavailable:
            logger.warning("PDF render failed for job %s; the .tex is still available", job_id)

        resume_version = ResumeVersion(
            id=self._id_generator.new_id(),
            source_master_version_ref=master.version_ref,
            content=tailored_tex,
            created_at=now,
            job_id=job_id,
            diff_summary=_diff_summary(plan, self._achievement_bank),
            has_gaps=bool(plan.gaps),
        )
        if render.succeeded and render.pdf_path is not None:
            resume_version.mark_rendered(str(render.pdf_path))
        await self._resume_repository.add_resume_version(resume_version)

        self._write_artifacts(directory, job, company_name, plan, tailored_tex, resume_version)

        gap_flags = await self._record_gaps(plan, resume_version.id, job_id)
        await self._event_bus.publish(
            ResumeGenerated(
                resume_version_id=resume_version.id,
                job_id=job_id,
                application_id=application_id or "",
                has_gaps=bool(plan.gaps),
            )
        )
        for flag in gap_flags:
            await self._event_bus.publish(
                ResumeGapFlagged(
                    gap_flag_id=flag.id,
                    resume_version_id=resume_version.id,
                    missing_item=flag.missing_skill_or_requirement,
                )
            )

        logger.info(
            "Tailored resume %s for job %s (%d gaps, pdf=%s)",
            resume_version.id,
            job_id,
            len(plan.gaps),
            "yes" if render.succeeded else ("unavailable" if render.unavailable else "failed"),
        )
        return TailoringOutcome(
            resume_version_id=resume_version.id,
            artifact_directory=directory,
            pdf_rendered=render.succeeded,
            pdf_unavailable=render.unavailable,
            gap_count=len(plan.gaps),
        )

    def _warn_about_template(self, master_tex: str) -> None:
        """Report a misconfigured master template instead of silently producing a wrong document.

        A missing marker just leaves that section empty; a duplicated one fills both occurrences, which for a
        multi-line block escapes any surrounding LaTeX comment and injects a stray copy of the section.
        """
        issues = self._assembler.check_template(master_tex)
        if issues.missing:
            logger.warning("Master resume has no %s marker(s); those sections will be empty", issues.missing)
        if issues.duplicated:
            logger.warning(
                "Master resume repeats %s marker(s); content will be duplicated in the output",
                issues.duplicated,
            )

    async def list_pending_gaps(self) -> list[ResumeGapFlag]:
        """Gaps awaiting the candidate's decision -- content the bank could not support for some job."""
        return await self._resume_repository.list_pending_gap_flags()

    async def versions_for_job(self, job_id: str) -> list[ResumeVersion]:
        """Every resume version generated for a job, newest first. Nothing is ever replaced."""
        return await self._resume_repository.list_versions_for_job(job_id)

    async def _record_gaps(
        self, plan: TailoringPlan, resume_version_id: str, job_id: str
    ) -> list[ResumeGapFlag]:
        flags = [
            ResumeGapFlag(
                id=self._id_generator.new_id(),
                resume_version_id=resume_version_id,
                job_id=job_id,
                missing_skill_or_requirement=gap,
                suggested_language=None,
                status=GapFlagStatus.PENDING_APPROVAL,
            )
            for gap in plan.gaps
        ]
        for flag in flags:
            await self._resume_repository.add_gap_flag(flag)
        return flags

    def _write_artifacts(
        self,
        directory: Path,
        job,
        company_name: str,
        plan: TailoringPlan,
        tailored_tex: str,
        resume_version: ResumeVersion,
    ) -> None:
        """Snapshot everything needed to explain this application later."""
        self._artifact_store.write_json(
            directory,
            "job-listing.json",
            {
                "job_id": job.id,
                "title": job.title,
                "company": company_name,
                "url": job.url,
                "source": job.source.value,
                "location": {
                    "city": job.location.city,
                    "country": job.location.country,
                    "remote_type": job.location.remote_type.value,
                },
                "skills": job.skills,
                "posting_date": job.posting_date,
                "discovered_at": job.discovered_at,
                "description": job.description,
            },
        )
        self._artifact_store.write_json(
            directory,
            "selection.json",
            {
                "strategy_version": TAILORING_STRATEGY_VERSION,
                "master_version_ref": resume_version.source_master_version_ref,
                "summary": plan.summary,
                "skills": plan.skills,
                "achievements": [
                    {
                        "id": selection.achievement_id,
                        "bullets": [
                            {"source_index": bullet.source_index, "rephrased": bullet.rephrased}
                            for bullet in selection.bullets
                        ],
                    }
                    for selection in plan.achievements
                ],
                "gaps": plan.gaps,
            },
        )
        self._artifact_store.write_text(directory, "resume.tex", tailored_tex)
        self._artifact_store.write_text(
            directory, "diff.md", _diff_markdown(plan, self._achievement_bank, company_name, job.title)
        )
        if plan.gaps:
            gaps_markdown = "\n".join(f"- {gap}" for gap in plan.gaps)
            self._artifact_store.write_text(
                directory,
                "gaps.md",
                "# Requirements the achievement bank could not support\n\n"
                f"{gaps_markdown}\n\n"
                "Add these to data/master/achievements.yaml if you can genuinely claim them.\n",
            )


def _drop_unclaimable_skills(
    plan: TailoringPlan, bank: AchievementBank, claimable_skills: list[str]
) -> tuple[TailoringPlan, list[str]]:
    """Remove skills the candidate cannot claim, returning them so they become gap flags.

    A hard refusal here would be disproportionate: the achievement selection may be perfectly good and only the
    "most relevant skills" line over-reached. Dropping the skill keeps the unsupported claim off the document --
    the guarantee that matters -- while still telling the candidate what the job wanted that they cannot yet
    back up, which is exactly what a gap flag is for.
    """
    claimable = {skill.lower() for skill in claimable_skills} | {
        technology.lower() for technology in bank.all_technologies()
    }
    kept = [skill for skill in plan.skills if skill.lower() in claimable]
    dropped = [skill for skill in plan.skills if skill.lower() not in claimable]
    if not dropped:
        return plan, []

    logger.info("Dropped unclaimable skills from the tailored resume: %s", dropped)
    gap_notes = [
        f"Job asks for {skill}, which nothing in your achievement bank supports" for skill in dropped
    ]
    return (
        TailoringPlan(
            achievements=plan.achievements,
            skills=kept,
            summary=plan.summary,
            gaps=[*plan.gaps, *gap_notes],
        ),
        dropped,
    )


def _plan_from(parsed: dict) -> TailoringPlan:
    """Convert the model's JSON into a TailoringPlan. Structural problems only; semantics are validated later."""
    raw_achievements = parsed.get("achievements")
    if not isinstance(raw_achievements, list):
        raise TailoringResponseError("Tailoring response is missing an 'achievements' list")

    selections: list[AchievementSelection] = []
    for entry in raw_achievements:
        if not isinstance(entry, dict) or "id" not in entry:
            raise TailoringResponseError(f"Malformed achievement selection: {entry!r}")
        raw_bullets = entry.get("bullets")
        if not isinstance(raw_bullets, list):
            raise TailoringResponseError(f"Achievement {entry['id']!r} has no bullets list")

        bullets: list[BulletSelection] = []
        for bullet in raw_bullets:
            if not isinstance(bullet, dict) or "source_index" not in bullet:
                raise TailoringResponseError(f"Malformed bullet selection: {bullet!r}")
            try:
                index = int(bullet["source_index"])
            except (TypeError, ValueError) as error:
                raise TailoringResponseError(f"Bullet source_index is not an integer: {bullet!r}") from error
            rephrased = str(bullet.get("rephrased") or "").strip() or None
            bullets.append(BulletSelection(source_index=index, rephrased=rephrased))

        selections.append(AchievementSelection(achievement_id=str(entry["id"]).strip(), bullets=bullets))

    skills = _dedupe_preserving_order(
        str(skill).strip() for skill in (parsed.get("skills") or []) if str(skill).strip()
    )
    gaps = _dedupe_preserving_order(
        str(gap).strip() for gap in (parsed.get("gaps") or []) if str(gap).strip()
    )
    summary = str(parsed.get("summary") or "").strip() or None
    return TailoringPlan(
        achievements=_merge_duplicate_selections(selections),
        skills=skills,
        summary=summary,
        gaps=gaps,
    )


def _dedupe_preserving_order(values) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def _merge_duplicate_selections(selections: list[AchievementSelection]) -> list[AchievementSelection]:
    """Fold repeated selections of the same achievement into one, unioning their bullets.

    Models do this routinely -- naming a role twice to attach different bullets to each mention. It is a
    structural slip, not a fabrication attempt: the content is all still from the bank, it would just appear
    twice on the page. Treating it as fabrication would throw away an otherwise valid tailoring, so it is
    normalised here instead, while `validate_plan` stays strict about claims that genuinely are unsupported.

    Bullet order and first-seen achievement order are preserved. Where the same bullet appears twice, a version
    with a rewording wins over one without, since the model chose to adapt it.
    """
    merged: dict[str, dict[int, BulletSelection]] = {}
    for selection in selections:
        bullets = merged.setdefault(selection.achievement_id, {})
        for bullet in selection.bullets:
            existing = bullets.get(bullet.source_index)
            if existing is None or (existing.rephrased is None and bullet.rephrased is not None):
                bullets[bullet.source_index] = bullet

    if len(merged) < len(selections):
        logger.info("Merged %d duplicate achievement selections", len(selections) - len(merged))

    return [
        AchievementSelection(achievement_id=achievement_id, bullets=list(bullets.values()))
        for achievement_id, bullets in merged.items()
    ]


def _diff_summary(plan: TailoringPlan, bank: AchievementBank) -> str:
    reworded = sum(
        1
        for selection in plan.achievements
        for bullet in selection.bullets
        if bullet.is_rewording(bank.get(selection.achievement_id).bullet(bullet.source_index))
    )
    included = ", ".join(bank.get(s.achievement_id).title for s in plan.achievements)
    return (
        f"Included {len(plan.achievements)} achievements ({included}); "
        f"reworded {reworded} bullets; {len(plan.gaps)} gaps flagged"
    )


def _diff_markdown(plan: TailoringPlan, bank: AchievementBank, company_name: str, job_title: str) -> str:
    lines = [f"# Tailoring for {job_title} at {company_name}", ""]
    if plan.summary:
        lines += ["## Summary used", "", plan.summary, ""]
    if plan.skills:
        lines += ["## Skills, in the order shown", "", ", ".join(plan.skills), ""]

    lines += ["## Content selected", ""]
    for selection in plan.achievements:
        achievement = bank.get(selection.achievement_id)
        lines.append(f"### {achievement.title}  \n`{achievement.id}`")
        lines.append("")
        for bullet in selection.bullets:
            original = achievement.bullet(bullet.source_index)
            if bullet.is_rewording(original):
                lines.append(f"- **reworded** [{bullet.source_index}]")
                lines.append(f"  - from: {original}")
                lines.append(f"  - to:   {bullet.rephrased}")
            else:
                lines.append(f"- unchanged [{bullet.source_index}]: {original}")
        lines.append("")

    omitted = sorted(bank.ids - {selection.achievement_id for selection in plan.achievements})
    if omitted:
        lines += ["## Left out for this role", "", ", ".join(f"`{id_}`" for id_ in omitted), ""]
    if plan.gaps:
        lines += ["## Gaps flagged", "", *[f"- {gap}" for gap in plan.gaps], ""]
    return "\n".join(lines)
