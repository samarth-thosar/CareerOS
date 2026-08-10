"""Layered configuration: environment variables > YAML file > code defaults, via pydantic-settings.

This is the only module (outside the composition root) that touches configuration loading directly --
domain and application code receive narrow typed slices instead. See
docs/architecture/decisions/0004-layered-yaml-plus-env-configuration.md.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3].parent / "config" / "default.yaml"


class ScoringWeights(BaseModel):
    resume_match: float = 0.30
    skill_area_fit: float = 0.25
    career_progression_fit: float = 0.15
    remote_fit: float = 0.10
    salary_fit: float = 0.10
    company_quality: float = 0.10


class LLMSettings(BaseModel):
    provider: str = "ollama"
    model: str = "qwen3:8b"
    base_url: str = "http://localhost:11434"
    # A scoring call measured ~60s on a 4GB-VRAM laptop GPU, so the ceiling is generous.
    # Generous because a single local call can take minutes, and far more under contention: background
    # scoring and an interactive tailoring request share one Ollama instance, which serialises them.
    timeout_seconds: float = 900.0
    # Keeps the model resident between calls; reloading dominates when draining a backlog one job at a time.
    keep_alive: str = "10m"
    max_output_tokens: int = 800
    # Qwen3 and other reasoning models emit chain-of-thought by default. CareerOS stores the model's own
    # narrative instead, and disabling thought measured ~35% faster.
    disable_thinking: bool = True


class SchedulerSettings(BaseModel):
    """Background work.

    Turn this off while working interactively. One local Ollama instance serialises generation, so a scheduled
    20-job scoring batch will queue ahead of a tailoring request and time it out -- the batch is not urgent, the
    thing you are waiting on is.
    """

    enabled: bool = True


class ScoringSettings(BaseModel):
    """How the scoring backlog is drained.

    Concurrency stays at 1 by default: a single local Ollama instance serializes generation, so parallel
    requests mostly just contend for VRAM.
    """

    batch_size: int = 20
    interval_seconds: int = 900
    run_on_startup: bool = False


class ResumeSettings(BaseModel):
    """Resume tailoring and rendering.

    `latex_engine` empty means "use whichever of tectonic/pdflatex/xelatex/lualatex is on PATH". With none
    installed, tailoring still produces .tex and artifacts; only the PDF step is skipped.
    """

    latex_engine: str = ""


class ProfileSettings(BaseModel):
    # Load config/profile.yaml into the database on boot. Off by default so a running system's profile -- which
    # Memory may have adjusted -- is never silently overwritten by a stale file.
    seed_on_startup: bool = False


class FeatureFlags(BaseModel):
    auto_apply_enabled: bool = False
    auto_tailor_resume: bool = True
    notification_batching_window_minutes: int = 60


class GreenhouseSettings(BaseModel):
    """Greenhouse has no cross-company search API, so discovery is driven by an explicit board list.

    A board token is the slug in `boards.greenhouse.io/<token>` for a company you want to watch.
    """

    enabled: bool = True
    board_tokens: list[str] = []


class LeverSettings(BaseModel):
    """Lever's public postings API. A slug is the company name in `jobs.lever.co/<slug>`."""

    enabled: bool = True
    company_slugs: list[str] = []


class AshbySettings(BaseModel):
    """Ashby's public job-board API. A slug is the company name in `jobs.ashbyhq.com/<slug>`."""

    enabled: bool = True
    company_slugs: list[str] = []


class JobSourceSettings(BaseModel):
    greenhouse: GreenhouseSettings = GreenhouseSettings()
    lever: LeverSettings = LeverSettings()
    ashby: AshbySettings = AshbySettings()


class DiscoverySettings(BaseModel):
    """What discovery looks for, and how often.

    Prefer `title_keywords` for narrowing: every kept job later costs one local LLM call to score, so a loose
    description-wide filter turns straight into hours of inference. See `SearchCriteria` for the tradeoff.
    """

    title_keywords: list[str] = []
    keywords: list[str] = []
    remote_only: bool = False
    # Places the candidate is authorised to work. A posting naming only regions outside this list is dropped at
    # the source: it is a legal constraint, not a preference, so it filters rather than lowering a score.
    # Empty disables the check entirely.
    eligible_locations: list[str] = []
    interval_seconds: int = 21_600  # 6 hours; ATS boards do not change minute to minute.
    run_on_startup: bool = False


class TrackerSettings(BaseModel):
    # Below this score an Application stays at Found rather than being promoted to Interested.
    auto_interested_threshold: int = 70


def _yaml_config_source(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class Settings(BaseSettings):
    """Root settings object. Precedence: environment variables > `.env` > YAML file > these defaults."""

    model_config = SettingsConfigDict(
        env_prefix="CAREEROS_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./careeros.db"
    log_level: str = "INFO"

    scoring_weights: ScoringWeights = ScoringWeights()
    scoring: ScoringSettings = ScoringSettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    llm: LLMSettings = LLMSettings()
    feature_flags: FeatureFlags = FeatureFlags()
    job_sources: JobSourceSettings = JobSourceSettings()
    discovery: DiscoverySettings = DiscoverySettings()
    tracker: TrackerSettings = TrackerSettings()
    profile: ProfileSettings = ProfileSettings()
    resume: ResumeSettings = ResumeSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_values = _yaml_config_source(_DEFAULT_CONFIG_PATH)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            lambda: yaml_values,
            file_secret_settings,
        )


def load_settings() -> Settings:
    return Settings()
