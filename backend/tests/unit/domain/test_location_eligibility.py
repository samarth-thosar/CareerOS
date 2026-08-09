"""Tests for work-authorisation eligibility.

This is the filter standing between the candidate and a shortlist full of jobs they cannot legally take, so the
cases below are drawn from real Greenhouse location strings rather than invented ones.
"""
from __future__ import annotations

import pytest

from careeros.domain.job.location_eligibility import (
    Eligibility,
    EligibilityRules,
    assess,
    is_worth_keeping,
)

INDIA = EligibilityRules.from_locations(
    ["india", "pune", "bangalore", "bengaluru", "mumbai", "hyderabad"]
)


class TestEligible:
    @pytest.mark.parametrize(
        "text",
        [
            "Bengaluru, India",
            "Pune, India",
            "Mumbai",
            "Hyderabad, Telangana, India",
            "Bangalore or Remote (India)",
            "BENGALURU",  # matching is case-insensitive
        ],
    )
    def test_indian_locations_are_eligible(self, text: str) -> None:
        assert assess(text, INDIA) is Eligibility.ELIGIBLE

    def test_aliases_both_work(self) -> None:
        assert assess("Bangalore", INDIA) is Eligibility.ELIGIBLE
        assert assess("Bengaluru", INDIA) is Eligibility.ELIGIBLE

    @pytest.mark.parametrize("text", ["Remote - Worldwide", "Remote, anywhere", "Global - remote first"])
    def test_genuinely_worldwide_postings_are_eligible(self, text: str) -> None:
        assert assess(text, INDIA) is Eligibility.ELIGIBLE

    def test_an_eligible_mention_beats_an_ineligible_one(self) -> None:
        # The candidate can take this job in Pune; the US option simply isn't the one they'd use.
        assert assess("Pune, India or Remote (US)", INDIA) is Eligibility.ELIGIBLE


class TestNotEligible:
    @pytest.mark.parametrize(
        "text",
        [
            "US Remote",
            "Remote in the US, Remote in Canada",
            "US-Remote, Chicago, Seattle, San Francisco",
            "Remote, CA",
            "New York, San Francisco, Seattle, or Remote (US/Canada)",
        ],
    )
    def test_region_locked_remote_is_rejected(self, text: str) -> None:
        # The costliest mistake this module prevents: these are all `remote`, and all unavailable without US
        # authorisation. Treating remote as "anyone may apply" fills the shortlist with unusable jobs.
        assert assess(text, INDIA) is Eligibility.NOT_ELIGIBLE

    @pytest.mark.parametrize(
        "text",
        ["Norway", "Greece", "Remote - Romania", "Singapore", "Berlin, Germany", "London, UK", "Toronto"],
    )
    def test_unlisted_countries_fail_closed(self, text: str) -> None:
        # Regression: an earlier blocklist implementation let Norway, Greece and Romania through as UNKNOWN,
        # because no hand-written list of countries is ever complete. The allowlist inverts that failure.
        assert assess(text, INDIA) is Eligibility.NOT_ELIGIBLE

    def test_a_country_nobody_would_think_to_blocklist_still_fails(self) -> None:
        assert assess("Ulaanbaatar, Mongolia", INDIA) is Eligibility.NOT_ELIGIBLE


class TestUnknown:
    @pytest.mark.parametrize("text", ["Remote", "", "   ", "N/A", "TBD", None])
    def test_no_location_named_is_unknown_not_rejected(self, text: str | None) -> None:
        assert assess(text, INDIA) is Eligibility.UNKNOWN

    def test_arrangement_only_text_is_unknown(self) -> None:
        assert assess("Remote-Friendly (Travel-Required)", INDIA) is Eligibility.UNKNOWN


class TestKeepDecision:
    def test_eligible_and_unknown_are_kept(self) -> None:
        # Unknown is kept deliberately: a bare "Remote" may be open worldwide, and dropping it would hide a real
        # opening. Only an explicit mismatch is discarded.
        assert is_worth_keeping("Pune, India", INDIA) is True
        assert is_worth_keeping("Remote", INDIA) is True

    def test_ineligible_is_dropped(self) -> None:
        assert is_worth_keeping("US Remote", INDIA) is False

    def test_custom_rules_change_the_verdict(self) -> None:
        germany = EligibilityRules.from_locations(["germany", "berlin"])

        assert assess("Berlin, Germany", germany) is Eligibility.ELIGIBLE
        assert assess("Pune, India", germany) is Eligibility.NOT_ELIGIBLE

    def test_empty_rule_list_falls_back_to_defaults_rather_than_rejecting_everything(self) -> None:
        # A misconfigured empty list must not silently make every job ineligible.
        assert assess("Pune, India", EligibilityRules.from_locations([])) is Eligibility.ELIGIBLE
