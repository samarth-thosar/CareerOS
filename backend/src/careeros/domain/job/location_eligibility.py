"""Deciding whether the candidate could actually take a job, given where it is and where they can work.

This is a work-authorization question, not a geography one, and it is deliberately separate from "do I like this
location". Two properties of real postings drive the design:

1. **A posting has zero or more locations, not one.** Greenhouse routinely writes
   "New York, San Francisco, Seattle, or Remote (US/Canada)" in a single field. Extracting one city/country pair
   from that produces nonsense -- an earlier version of this code turned that exact string into
   city="San Francisco", country="WA", and "N/A" into city="N", country="A".
2. **"Remote" is usually region-locked.** "US Remote", "Remote in the US", "Remote (US/Canada)" are all remote
   and all unavailable to someone without US authorization. Treating `remote_type == REMOTE` as "anyone may
   apply" is the single most expensive mistake this module exists to prevent, because it silently fills the
   shortlist with jobs the candidate cannot legally take.

So eligibility is decided from the raw location text, by looking for evidence either way, and the outcome is
three-valued: eligible, not eligible, or unknown. Unknown is kept rather than discarded -- a posting that says
only "Remote" may well be open worldwide, and throwing those away would hide real opportunities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Eligibility(StrEnum):
    ELIGIBLE = "eligible"
    """Mentions somewhere the candidate can work."""

    NOT_ELIGIBLE = "not_eligible"
    """Mentions only regions the candidate cannot work in."""

    UNKNOWN = "unknown"
    """No location signal at all, or bare "Remote" with no region named."""


# Regions the candidate is authorised for, as the substrings that appear in posting text. Aliases matter:
# Bengaluru and Bangalore are the same place and postings use both.
DEFAULT_ELIGIBLE_TERMS: tuple[str, ...] = (
    "india", "pune", "bangalore", "bengaluru", "mumbai", "hyderabad", "delhi", "gurgaon", "gurugram",
    "noida", "chennai", "kolkata", "ahmedabad", "apac", "asia",
)

_WORLDWIDE = re.compile(r"\b(?:worldwide|anywhere|global(?:ly)?|any location|remote[- ]first)\b")


@dataclass(frozen=True, slots=True)
class EligibilityRules:
    """The places the candidate may work, as terms to match.

    Only an allowlist: there is deliberately no list of ineligible regions, because any such list is incomplete
    the moment a company posts in a country nobody thought of.
    """

    eligible_terms: tuple[str, ...] = DEFAULT_ELIGIBLE_TERMS

    @classmethod
    def from_locations(cls, locations: list[str]) -> "EligibilityRules":
        """Build rules from a plain list of places the candidate may work in."""
        terms = tuple(term.strip().lower() for term in locations if term.strip())
        return cls(eligible_terms=terms or DEFAULT_ELIGIBLE_TERMS)


def _contains_any(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(term in haystack for term in terms)


def assess(location_text: str | None, rules: EligibilityRules | None = None) -> Eligibility:
    """Judge one posting's location text.

    Allowlist, not blocklist. An earlier version enumerated ineligible countries and let anything unrecognised
    through as UNKNOWN -- which quietly admitted Norway, Greece and Romania roles, because no hand-written list
    of the world's countries is ever complete. Inverting it means the question is "does this name a place I can
    work in?", so an unfamiliar location fails closed instead of open.

    An eligible mention always wins: "Pune, India or Remote (US)" is available to the candidate, so another
    location in the same string must not veto it.
    """
    active = rules or EligibilityRules()
    if not location_text or not location_text.strip():
        return Eligibility.UNKNOWN

    # Pad so " us " style boundary terms can match at the string edges too.
    text = f" {location_text.lower().strip()} "

    if _contains_any(text, active.eligible_terms):
        return Eligibility.ELIGIBLE
    if _WORLDWIDE.search(text):
        return Eligibility.ELIGIBLE

    # Whatever remains once work-arrangement words and punctuation are removed is a place name -- and since no
    # eligible term matched, it is somewhere the candidate cannot work.
    if _names_a_place(text):
        return Eligibility.NOT_ELIGIBLE

    # Nothing but "Remote", "N/A" or similar: genuinely unknown, so keep it rather than hide a real opening.
    return Eligibility.UNKNOWN


# Words that describe the arrangement rather than the place. Stripping these is what distinguishes "Remote"
# (no location named) from "Remote - Greece" (a location named).
_ARRANGEMENT_WORDS = re.compile(
    r"\b(?:fully|partially|100%?|remote|hybrid|onsite|on-site|in-office|office|based|friendly|flexible|"
    r"anywhere|distributed|work\s+from\s+home|wfh|any|location|multiple|locations|or|and|either|various|"
    r"n\s*/?\s*a|tbd|unspecified|travel|required|optional|global|worldwide)\b",
    re.IGNORECASE,
)


def _names_a_place(text: str) -> bool:
    """Whether anything place-like survives once arrangement words and punctuation are stripped."""
    residue = _ARRANGEMENT_WORDS.sub(" ", text)
    residue = re.sub(r"[^a-z]+", " ", residue).strip()
    # Two letters or more, to ignore stray fragments left behind by punctuation removal.
    return len(residue) >= 2


def is_worth_keeping(location_text: str | None, rules: EligibilityRules | None = None) -> bool:
    """Whether discovery should store this posting.

    Keeps UNKNOWN as well as ELIGIBLE: a bare "Remote" might be open worldwide, and discarding it would hide
    real opportunities. Only an explicit mismatch is dropped.
    """
    return assess(location_text, rules) is not Eligibility.NOT_ELIGIBLE
