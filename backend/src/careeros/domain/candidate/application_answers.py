"""The answers every job application form asks for.

Application forms are boringly repetitive: identity, authorisation, notice period, compensation, links. Storing
them once means a submission can be assembled without asking the candidate again each time.

Two design points that matter:

* **Unanswered is a first-class state, not an empty string.** A blank "expected CTC" and a deliberate "prefer
  not to say" are different facts, and a submission must be able to refuse to proceed when a required field was
  never filled rather than sending "" into a real employer's form. `PLACEHOLDER` marks a field the system wrote
  as a prompt, so the UI can highlight exactly what still needs the candidate.
* **Nothing here is invented.** Same rule as the resume: CareerOS never guesses a notice period or a salary
  expectation. Fields it cannot know ship as placeholders for the candidate to correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum

PLACEHOLDER = "TODO"
"""Marks a value CareerOS wrote as a prompt rather than a fact. Treated as unanswered everywhere."""


class WorkAuthorisation(StrEnum):
    """Whether the candidate may work in a region without sponsorship.

    Drives the discovery filter, so it is data rather than prose: a job needing authorisation the candidate
    lacks is not a lower-scoring job, it is an unavailable one.
    """

    CITIZEN_OR_PERMANENT = "citizen_or_permanent"
    NEEDS_SPONSORSHIP = "needs_sponsorship"
    NOT_AUTHORISED = "not_authorised"


@dataclass(slots=True)
class ApplicationAnswers:
    """Reusable answers for job application forms.

    Field names mirror what forms actually label them, so mapping to a real form stays obvious.
    """

    # --- identity ---
    full_name: str = PLACEHOLDER
    email: str = PLACEHOLDER
    phone: str = PLACEHOLDER
    current_location: str = PLACEHOLDER
    linkedin_url: str = PLACEHOLDER
    github_url: str = PLACEHOLDER
    portfolio_url: str = ""

    # --- authorisation ---
    # Region -> authorisation. Discovery reads this; "india: citizen_or_permanent" plus nothing else means
    # US/UK/EU postings get filtered out rather than scored and shortlisted uselessly.
    work_authorisation: dict[str, str] = field(default_factory=dict)
    requires_visa_sponsorship: bool = True

    # --- availability ---
    notice_period_days: int | None = None
    earliest_start_date: str = PLACEHOLDER
    willing_to_relocate: bool | None = None
    preferred_work_arrangement: str = PLACEHOLDER  # remote | hybrid | onsite | any

    # --- compensation, annual, in the candidate's own currency ---
    current_ctc: str = ""
    expected_ctc: str = PLACEHOLDER
    salary_currency: str = "INR"

    # --- background ---
    total_experience_years: float | None = None
    highest_qualification: str = PLACEHOLDER
    gender: str = ""  # optional on most forms; blank means "prefer not to say"
    ethnicity: str = ""
    disability_status: str = ""
    veteran_status: str = ""

    # --- free text forms commonly ask for ---
    why_this_company_template: str = PLACEHOLDER
    additional_information: str = ""

    def missing_fields(self) -> list[str]:
        """Fields still holding a placeholder or left unset, so the UI can show exactly what is outstanding.

        Deliberately excludes fields that are legitimately optional -- flagging `gender` as "missing" would train
        the candidate to ignore this list, which defeats its purpose.
        """
        optional = {
            "portfolio_url", "current_ctc", "gender", "ethnicity", "disability_status",
            "veteran_status", "additional_information",
        }
        outstanding: list[str] = []
        for spec in fields(self):
            if spec.name in optional:
                continue
            value = getattr(self, spec.name)
            if value == PLACEHOLDER or value is None or value == "" or value == {}:
                outstanding.append(spec.name)
        return outstanding

    @property
    def ready_to_apply(self) -> bool:
        """Whether a submission can proceed without inventing anything on the candidate's behalf."""
        return not self.missing_fields()

    def authorised_regions(self) -> list[str]:
        """Regions the candidate can work in without sponsorship -- the eligible set discovery filters on."""
        return [
            region
            for region, status in self.work_authorisation.items()
            if status == WorkAuthorisation.CITIZEN_OR_PERMANENT.value
        ]
