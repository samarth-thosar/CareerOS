"""Deterministic text helpers shared by job-source providers.

Everything here is plain parsing -- no LLM. Providers use these to turn an ATS's HTML blob into the
normalized fields `RawJobPosting` requires. Skill and salary extraction are intentionally conservative:
a missed field is harmless (Scoring re-reads the full description later), whereas a wrong field would
silently corrupt the data every downstream decision is made from.
"""
from __future__ import annotations

import html
import re

from careeros.domain.job.job import Location, RemoteType, SalaryRange

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t]*\n\s*\n\s*")

# Conservative: only currency-prefixed ranges with thousands separators or explicit 'k' suffixes, so prose
# like "top 100 engineers" or "401k" can never be read as pay.
_SALARY_RANGE = re.compile(
    r"(?P<currency>[$€£₹])\s?(?P<min>\d{2,3}(?:,\d{3})+|\d{2,3}k)\s*(?:-|–|to)\s*"
    r"(?:[$€£₹]\s?)?(?P<max>\d{2,3}(?:,\d{3})+|\d{2,3}k)",
    re.IGNORECASE,
)

_CURRENCY_CODES = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}

# Separators ATS location strings use. Greenhouse in particular writes "San Francisco, CA • United States".
_LOCATION_SEPARATOR = re.compile(r"[,/|•·;]|\s[-–]\s")

# Words that join a list of places rather than naming one ("New York, San Francisco, or Remote").
_MULTI_LOCATION_JOINER = re.compile(r"(?:or|and|either|n\s*/?\s*a)", re.IGNORECASE)

# Skills whose names are also ordinary English words. Plain word-boundary matching produces false positives
# ("go to market" tagging a Program Manager role as a Go developer), so these require a qualifier that only
# appears in a technical context. Precision matters more than recall here: a phantom skill misleads scoring,
# whereas a missed one is recoverable because the LLM re-reads the full description anyway.
_AMBIGUOUS_SKILL_PATTERNS: dict[str, str] = {
    "go": r"\bgolang\b|\bgo\s+(?:developer|engineer|programmer|programming|routines?|modules?)\b"
    r"|(?:^|[^a-z])(?:in|using|with|write|writing|written)\s+go(?:$|[^a-z])",
    "rest": r"\brest(?:ful)?\s+(?:apis?|services?|endpoints?|web\s+services?)\b|\bapi\s+rest\b",
    "express": r"\bexpress(?:\.js|js)\b|\bexpress\s+(?:framework|server|middleware)\b",
    "dart": r"\bdart\s+(?:language|programming|code)\b|\b(?:flutter|dart)\s*/\s*(?:dart|flutter)\b",
    "java": r"\bjava\b(?!script)",
}

DEFAULT_SKILL_VOCABULARY: tuple[str, ...] = (
    "python", "typescript", "javascript", "java", "go", "rust", "c++", "sql",
    "fastapi", "django", "flask", "node.js", "express", "nest.js",
    "react", "next.js", "react native", "flutter", "dart", "vue", "svelte", "tailwind",
    "mongodb", "postgresql", "mysql", "redis", "elasticsearch",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "llm", "langchain", "rag", "pytorch", "tensorflow", "hugging face", "openai",
    "machine learning", "nlp", "computer vision", "mlops",
    "kafka", "rabbitmq", "graphql", "rest", "grpc", "microservices", "ci/cd",
)


def matches_keyword(text: str, keyword: str) -> bool:
    """Whole-word (or simple plural) keyword match.

    Naive substring matching is actively wrong for short keywords: "ai" would match "Pre-training",
    "Retail" and "Thailand"; "ml" would match "AML". Requiring a word boundary on both sides fixes that,
    while an optional trailing "s" keeps legitimate plurals ("Software Engineers") matching.
    """
    pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}s?(?![a-z0-9])"
    return re.search(pattern, (text or "").lower()) is not None


def html_to_text(raw_html: str) -> str:
    """Unescape and strip an ATS content blob down to readable plain text."""
    unescaped = html.unescape(raw_html or "")
    without_tags = _HTML_TAG.sub("\n", unescaped)
    collapsed = _WHITESPACE.sub("\n\n", html.unescape(without_tags))
    return collapsed.strip()


def parse_location(raw_location: str | None) -> Location:
    """Interpret a free-text ATS location string (e.g. "Remote - US", "Bengaluru, India").

    The raw text is always preserved and is what eligibility is decided from. `city`/`country` are filled in
    only when the text names a *single* place: postings frequently list several, and an earlier version of this
    function forced them into one pair, turning "New York, San Francisco, Seattle, or Remote (US/Canada)" into
    city="San Francisco", country="WA" and "N/A" into city="N", country="A". A wrong city is worse than none,
    because it reads as fact.
    """
    if not raw_location or not raw_location.strip():
        return Location(city=None, country=None, remote_type=RemoteType.UNKNOWN, raw=None)

    text = raw_location.strip()
    lowered = text.lower()
    if "hybrid" in lowered:
        remote_type = RemoteType.HYBRID
    elif "remote" in lowered or "anywhere" in lowered or "distributed" in lowered:
        remote_type = RemoteType.REMOTE
    else:
        remote_type = RemoteType.ONSITE

    # Drop the remote/hybrid qualifier so only place names remain, then read "City, Country".
    place = re.sub(r"\b(fully\s+)?(remote|hybrid|onsite|on-site|anywhere)\b", "", text, flags=re.IGNORECASE)
    parts = [part.strip(" -–—/|") for part in _LOCATION_SEPARATOR.split(place)]
    parts = [part for part in parts if len(part) > 1 and not _MULTI_LOCATION_JOINER.fullmatch(part)]

    # "City, Country" is one place; three or more fragments means a list, and guessing is worse than abstaining.
    city = parts[0] if len(parts) in (1, 2) else None
    country = parts[1] if len(parts) == 2 else None
    return Location(city=city, country=country, remote_type=remote_type, raw=text)


def _to_amount(token: str) -> float:
    token = token.lower().replace(",", "")
    if token.endswith("k"):
        return float(token[:-1]) * 1_000
    return float(token)


def parse_salary(description: str) -> SalaryRange:
    """Look for an explicit pay range in the description.

    Anything found here is flagged `is_estimated=True`, because prose is not a structured salary field --
    downstream consumers must be able to tell a parsed guess from an ATS-provided number.
    """
    match = _SALARY_RANGE.search(description or "")
    if match is None:
        return SalaryRange(minimum=None, maximum=None, currency=None, period=None)

    minimum = _to_amount(match.group("min"))
    maximum = _to_amount(match.group("max"))
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    return SalaryRange(
        minimum=minimum,
        maximum=maximum,
        currency=_CURRENCY_CODES.get(match.group("currency")),
        period="year",
        is_estimated=True,
    )


def extract_skills(text: str, vocabulary: tuple[str, ...] = DEFAULT_SKILL_VOCABULARY) -> list[str]:
    """Match a known skill vocabulary against the posting text, preserving vocabulary order.

    Unambiguous terms match on word boundaries (so "rust" does not match "trust"). Terms that are also
    ordinary English words use the stricter patterns in `_AMBIGUOUS_SKILL_PATTERNS`, which require a
    technical qualifier before the skill is claimed.
    """
    lowered = (text or "").lower()
    found = []
    for skill in vocabulary:
        pattern = _AMBIGUOUS_SKILL_PATTERNS.get(skill)
        if pattern is None:
            pattern = rf"(?<![a-z0-9+#.]){re.escape(skill)}(?![a-z0-9+#])"
        if re.search(pattern, lowered):
            found.append(skill)
    return found
