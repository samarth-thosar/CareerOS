"""End-to-end tailoring against real SQLite, the real event bus, and the real filesystem.

Covers the whole flow with a scripted model: selection -> validation -> deterministic assembly -> artifact
folder -> persisted ResumeVersion and gap flags. The refusal cases matter as much as the happy path: a model
that tries to fabricate must produce no resume at all.
"""
from __future__ import annotations

import json

import pytest

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.application.ports.llm_provider import LLMResponse
from careeros.domain.job.job import Location, RemoteType, SalaryRange
from careeros.domain.resume.achievement import UnknownAchievementError, UnknownBulletError
from careeros.domain.resume.resume_version import RenderStatus
from careeros.domain.resume.tailoring import FabricationError
from careeros.infrastructure.bootstrap import Container, build_container, in_session
from careeros.infrastructure.config.profile_loader import load_profile
from careeros.infrastructure.persistence.models import Base
from careeros.infrastructure.resume.artifact_store import ArtifactStore
from tests.fakes.fake_job_source_provider import FakeJobSourceProvider
from tests.fakes.fake_llm_provider import FakeLLMProvider


def _posting() -> RawJobPosting:
    return RawJobPosting(
        source_job_id="1",
        title="Senior Python Engineer",
        company_name="Acme Labs",
        url="https://example.com/jobs/1",
        description="Build APIs in Python with FastAPI and PostgreSQL.",
        location=Location(city=None, country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=["python", "fastapi"],
        posting_date=None,
        raw_payload={},
    )


def _tailoring_response(**overrides) -> FakeLLMProvider:
    """A scripted selection over the shipped placeholder achievement bank."""
    parsed = {
        "summary": "Backend engineer focused on Python services.",
        "skills": ["python", "fastapi", "postgresql"],
        "achievements": [
            {
                "id": "placeholder-current-role",
                "bullets": [
                    {"source_index": 0, "rephrased": "Built and shipped REST APIs end to end."},
                    {"source_index": 1},
                ],
            },
            {"id": "placeholder-ai-project", "bullets": [{"source_index": 0}]},
        ],
        "gaps": ["Kubernetes experience"],
    }
    parsed.update(overrides)
    return FakeLLMProvider(LLMResponse(text="{}", parsed=parsed, model_used="fake-model"))


@pytest.fixture
async def container(tmp_path, monkeypatch) -> Container:
    monkeypatch.setenv("CAREEROS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'tailoring.db'}")
    built = build_container()
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    built.job_source_providers = [FakeJobSourceProvider("greenhouse", [_posting()])]
    # Artifacts go to a temp dir so tests never touch the real data/applications folder.
    built.artifact_store = ArtifactStore(root=tmp_path / "applications")
    built.llm_provider = _tailoring_response()
    await in_session(built, lambda s: s.candidate_profile.replace(load_profile()))
    try:
        yield built
    finally:
        await built.engine.dispose()


async def _discover(container: Container) -> str:
    ids = await in_session(container, lambda s: s.discovery.run_cycle("greenhouse", SearchCriteria()))
    return ids[0]


class TestSuccessfulTailoring:
    async def test_produces_a_resume_version_and_artifact_folder(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        assert outcome.resume_version_id
        assert outcome.artifact_directory.exists()
        assert outcome.gap_count == 1

    async def test_writes_every_artifact_needed_to_explain_the_application(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))
        written = {path.name for path in outcome.artifact_directory.iterdir()}

        assert {"job-listing.json", "selection.json", "resume.tex", "diff.md", "gaps.md"} <= written

    async def test_the_folder_name_identifies_company_and_role(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        assert "acme-labs" in outcome.artifact_directory.name
        assert "senior-python-engineer" in outcome.artifact_directory.name

    async def test_generated_tex_contains_selected_content_only(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))
        tex = (outcome.artifact_directory / "resume.tex").read_text(encoding="utf-8")

        assert "Built and shipped REST APIs end to end." in tex  # reworded bullet
        assert "Retrieval-Augmented Question Answering Tool" in tex  # selected project
        assert "Full-Stack Web Application" not in tex  # not selected
        assert "%%CAREEROS:" not in tex  # every marker substituted
        assert tex.strip().endswith("\\end{document}")

    async def test_selection_json_records_exactly_what_was_chosen(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))
        selection = json.loads((outcome.artifact_directory / "selection.json").read_text(encoding="utf-8"))

        assert [entry["id"] for entry in selection["achievements"]] == [
            "placeholder-current-role",
            "placeholder-ai-project",
        ]
        assert selection["gaps"] == ["Kubernetes experience"]
        assert selection["master_version_ref"].startswith("local:")

    async def test_gap_flags_are_persisted_for_review(self, container: Container) -> None:
        job_id = await _discover(container)
        await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        gaps = await in_session(container, lambda s: s.resume_manager.list_pending_gaps())

        assert [gap.missing_skill_or_requirement for gap in gaps] == ["Kubernetes experience"]

    async def test_pdf_is_skipped_cleanly_without_a_latex_toolchain(self, container: Container) -> None:
        job_id = await _discover(container)

        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        # Whether a toolchain exists is environmental; either way the .tex must exist and the state must be
        # consistent -- never "rendered" without a PDF.
        versions = await in_session(container, lambda s: s.resume_manager.versions_for_job(job_id))
        if outcome.pdf_rendered:
            assert versions[0].render_status is RenderStatus.RENDERED
            assert versions[0].pdf_path is not None
        else:
            assert versions[0].render_status is RenderStatus.DRAFT
            assert versions[0].pdf_path is None
        assert (outcome.artifact_directory / "resume.tex").exists()


class TestNeverOverwrites:
    async def test_a_second_run_adds_a_version_rather_than_replacing_one(self, container: Container) -> None:
        job_id = await _discover(container)

        first = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))
        second = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        assert first.resume_version_id != second.resume_version_id
        assert first.artifact_directory != second.artifact_directory
        assert first.artifact_directory.exists(), "the earlier version's artifacts must survive"

        versions = await in_session(container, lambda s: s.resume_manager.versions_for_job(job_id))
        assert len(versions) == 2


class TestRefusesToFabricate:
    async def test_invented_achievement_id_produces_no_resume(self, container: Container) -> None:
        job_id = await _discover(container)
        container.llm_provider = _tailoring_response(
            achievements=[{"id": "role-i-never-had", "bullets": [{"source_index": 0}]}]
        )

        with pytest.raises(UnknownAchievementError):
            await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        assert await in_session(container, lambda s: s.resume_manager.versions_for_job(job_id)) == []

    async def test_invented_bullet_index_produces_no_resume(self, container: Container) -> None:
        job_id = await _discover(container)
        container.llm_provider = _tailoring_response(
            achievements=[{"id": "placeholder-ai-project", "bullets": [{"source_index": 99}]}]
        )

        with pytest.raises(UnknownBulletError):
            await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

    async def test_invented_metric_produces_no_resume(self, container: Container) -> None:
        job_id = await _discover(container)
        container.llm_provider = _tailoring_response(
            achievements=[
                {
                    "id": "placeholder-current-role",
                    "bullets": [
                        {"source_index": 0, "rephrased": "Built APIs serving 10,000 requests per second."}
                    ],
                }
            ]
        )

        with pytest.raises(FabricationError, match="figures absent"):
            await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

    async def test_unclaimable_skill_produces_no_resume(self, container: Container) -> None:
        job_id = await _discover(container)
        container.llm_provider = _tailoring_response(skills=["python", "kubernetes", "terraform"])

        with pytest.raises(FabricationError, match="kubernetes"):
            await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

    async def test_no_artifacts_are_left_behind_by_a_refused_run(self, container: Container) -> None:
        job_id = await _discover(container)
        container.llm_provider = _tailoring_response(skills=["kubernetes"])

        with pytest.raises(FabricationError):
            await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))

        # Validation happens before any directory is allocated, so a refusal leaves no partial output.
        applications_root = container.artifact_store.root
        assert not applications_root.exists() or not any(applications_root.iterdir())
