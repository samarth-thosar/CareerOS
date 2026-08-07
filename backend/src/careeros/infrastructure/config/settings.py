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


class FeatureFlags(BaseModel):
    auto_apply_enabled: bool = False
    auto_tailor_resume: bool = True
    notification_batching_window_minutes: int = 60


class EnabledProviders(BaseModel):
    wellfound: bool = True
    greenhouse: bool = False
    lever: bool = False
    ashby: bool = False
    generic: bool = False
    linkedin: bool = False


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
    llm: LLMSettings = LLMSettings()
    feature_flags: FeatureFlags = FeatureFlags()
    enabled_providers: EnabledProviders = EnabledProviders()

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
