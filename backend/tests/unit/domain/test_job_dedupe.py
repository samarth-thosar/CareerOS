"""Unit tests for Job's dedupe key -- re-discovering a posting must be a no-op, not a new Job."""
from __future__ import annotations

from datetime import datetime, timezone

from careeros.domain.job.job import Job, JobSource, Location, RemoteType, SalaryRange


def _make_job(source: JobSource, source_job_id: str) -> Job:
    return Job(
        id="job-1",
        source=source,
        source_job_id=source_job_id,
        company_id="company-1",
        title="Senior AI Engineer",
        url="https://example.com/job/1",
        description="Build things.",
        location=Location(city="Remote", country=None, remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=["python", "llm"],
        posting_date=None,
        discovered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_dedupe_key_combines_source_and_source_job_id() -> None:
    job = _make_job(JobSource.WELLFOUND, "abc123")

    assert job.dedupe_key() == (JobSource.WELLFOUND, "abc123")


def test_dedupe_key_differs_across_sources_with_same_native_id() -> None:
    wellfound_job = _make_job(JobSource.WELLFOUND, "abc123")
    greenhouse_job = _make_job(JobSource.GREENHOUSE, "abc123")

    assert wellfound_job.dedupe_key() != greenhouse_job.dedupe_key()
