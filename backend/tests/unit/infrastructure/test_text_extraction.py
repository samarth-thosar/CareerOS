"""Tests for the deterministic parsing helpers job-source providers rely on.

The negative cases matter most here: a wrong salary or a phantom skill silently corrupts every downstream
scoring decision, so these assert that the parsers stay quiet when they aren't sure.
"""
from __future__ import annotations

import pytest

from careeros.domain.job.job import RemoteType
from careeros.infrastructure.job_sources.text_extraction import (
    extract_skills,
    html_to_text,
    matches_keyword,
    parse_location,
    parse_salary,
)


class TestMatchesKeyword:
    """Regressions from a live Greenhouse run, where substring matching let junk titles through."""

    @pytest.mark.parametrize(
        ("keyword", "title"),
        [
            ("ai", "Research Engineer, Pre-training"),
            ("ai", "Enterprise Account Executive, Retail"),
            ("ai", "Thailand Compliance Officer"),
            ("ml", "SDC Operations Manager, Financial Crimes (AML)"),
            ("ai", "Senior Aid Programme Lead"),
        ],
    )
    def test_keyword_inside_a_larger_word_does_not_match(self, keyword: str, title: str) -> None:
        assert matches_keyword(title, keyword) is False

    @pytest.mark.parametrize(
        ("keyword", "title"),
        [
            ("ai", "Technical Program Manager, AI Performance"),
            ("ml", "Staff Engineer, ML Platform"),
            ("machine learning", "Machine Learning Engineer"),
            ("software engineer", "Senior Software Engineer"),
            ("backend", "Backend Engineer (Payments)"),
        ],
    )
    def test_whole_word_matches(self, keyword: str, title: str) -> None:
        assert matches_keyword(title, keyword) is True

    def test_simple_plurals_still_match(self) -> None:
        assert matches_keyword("Software Engineers, Platform", "software engineer") is True

    def test_matching_is_case_insensitive(self) -> None:
        assert matches_keyword("SENIOR PYTHON DEVELOPER", "python") is True

    def test_empty_text_never_matches(self) -> None:
        assert matches_keyword("", "python") is False


class TestHtmlToText:
    def test_unescapes_entities_and_strips_tags(self) -> None:
        raw = "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;"

        assert html_to_text(raw) == "Build & ship"

    def test_handles_empty_content(self) -> None:
        assert html_to_text("") == ""


class TestParseLocation:
    def test_detects_remote(self) -> None:
        location = parse_location("Remote - United States")

        assert location.remote_type is RemoteType.REMOTE

    def test_detects_hybrid(self) -> None:
        assert parse_location("Hybrid - Berlin").remote_type is RemoteType.HYBRID

    def test_treats_plain_city_as_onsite_and_splits_parts(self) -> None:
        location = parse_location("Bengaluru, India")

        assert location.remote_type is RemoteType.ONSITE
        assert location.city == "Bengaluru"
        assert location.country == "India"

    def test_missing_location_is_unknown_not_onsite(self) -> None:
        assert parse_location(None).remote_type is RemoteType.UNKNOWN
        assert parse_location("   ").remote_type is RemoteType.UNKNOWN

    def test_raw_text_is_always_preserved(self) -> None:
        # The raw string is the source of truth: eligibility is decided from it, not from city/country.
        assert parse_location("San Francisco, CA • United States").raw == "San Francisco, CA • United States"

    def test_single_place_populates_city_and_country(self) -> None:
        location = parse_location("Bengaluru, India")

        assert (location.city, location.country) == ("Bengaluru", "India")

    def test_abstains_on_multi_location_postings(self) -> None:
        # Regression: three-plus fragments mean a *list* of places, not one. The old code took parts[0] and
        # parts[-1], turning this into city="San Francisco", country="WA" -- a wrong city reads as fact, which
        # is worse than none, and it now matters because location drives a work-authorisation filter.
        location = parse_location("New York, San Francisco, Seattle, or Remote (US/Canada)")

        assert location.city is None
        assert location.country is None
        assert location.raw is not None, "the full text must survive for eligibility to read"

    def test_na_does_not_become_a_place(self) -> None:
        # "N/A" split on "/" used to yield city="N", country="A".
        location = parse_location("N/A")

        assert location.city is None and location.country is None

    def test_display_prefers_the_postings_own_words(self) -> None:
        assert parse_location("Remote (US/Canada)").display == "Remote (US/Canada)"


class TestParseSalary:
    def test_parses_currency_range_and_flags_it_estimated(self) -> None:
        salary = parse_salary("The base range is $120,000 - $160,000 per year.")

        assert (salary.minimum, salary.maximum) == (120_000, 160_000)
        assert salary.currency == "USD"
        assert salary.is_estimated is True

    def test_parses_k_suffix_notation(self) -> None:
        salary = parse_salary("Compensation: $120k to $160k")

        assert (salary.minimum, salary.maximum) == (120_000, 160_000)

    def test_normalizes_reversed_range(self) -> None:
        salary = parse_salary("$160,000 - $120,000")

        assert (salary.minimum, salary.maximum) == (120_000, 160_000)

    def test_returns_empty_when_no_range_present(self) -> None:
        salary = parse_salary("We offer competitive compensation and a 401k match.")

        assert salary.minimum is None and salary.maximum is None

    def test_ignores_non_salary_numbers(self) -> None:
        assert parse_salary("Join the top 100 engineers among 5,000 applicants").minimum is None


class TestExtractSkills:
    def test_finds_vocabulary_terms(self) -> None:
        skills = extract_skills("We use Python, FastAPI and PostgreSQL on AWS.")

        assert set(skills) >= {"python", "fastapi", "postgresql", "aws"}

    def test_respects_word_boundaries(self) -> None:
        # "go" must not match "going"; "rust" must not match "trust".
        skills = extract_skills("We are going to build trust with customers.")

        assert "go" not in skills
        assert "rust" not in skills

    @pytest.mark.parametrize(
        "prose",
        [
            "Own the go to market strategy for the platform.",
            "Drive our go-to-market motion end to end.",
            "Let's go build something great.",
            "This is a go-getter role on a growing team.",
        ],
    )
    def test_english_go_does_not_register_as_the_go_language(self, prose: str) -> None:
        # Regression: a "Voice of the Customer Program Manager" posting was tagged with Go because plain
        # word-boundary matching accepted "go to market".
        assert "go" not in extract_skills(prose)

    @pytest.mark.parametrize(
        "prose",
        [
            "Experience with Golang required.",
            "You will be a Go engineer on the payments team.",
            "Services are written in Go.",
            "Comfortable writing Go and Python.",
        ],
    )
    def test_genuine_go_references_are_still_detected(self, prose: str) -> None:
        assert "go" in extract_skills(prose)

    def test_rest_requires_an_api_qualifier(self) -> None:
        assert "rest" not in extract_skills("You will own the rest of the onboarding flow.")
        assert "rest" in extract_skills("Design REST APIs for internal consumers.")

    def test_java_does_not_match_javascript(self) -> None:
        skills = extract_skills("Strong JavaScript and TypeScript skills.")

        assert "java" not in skills
        assert "javascript" in skills

    def test_matches_dotted_and_plus_terms(self) -> None:
        skills = extract_skills("Stack is Next.js with some C++ services and Node.js workers.")

        assert {"next.js", "c++", "node.js"} <= set(skills)

    def test_returns_empty_for_no_matches(self) -> None:
        assert extract_skills("We sell artisanal cheese.") == []
