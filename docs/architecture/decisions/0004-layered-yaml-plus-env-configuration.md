# 0004 — Layered YAML + Environment Configuration

## Context

CareerOS has two kinds of configuration with very different lifecycles: frequently-tweaked domain tunables
(scoring weights, which job providers are enabled, which LLM model to use, feature flags) and secrets
(API tokens, base URLs) that must never be committed to version control. A single flat `.env` file handles
secrets well but is awkward for structured, frequently-edited domain settings.

## Decision

Load configuration through `pydantic-settings` with precedence **environment variables > YAML file > code
defaults**. YAML (`backend/config/default.yaml`) holds domain tunables. `.env` / real environment variables
hold secrets. The composition root is the only module that touches the raw `Settings` object; it hands
narrow, typed slices (e.g. a `ScoringWeights` value object) to the services that need them.

## Consequences

- Scoring weights and provider toggles can be edited in a readable YAML file without redeploying or touching
  code, while secrets stay out of version control via `.env` (gitignored, with `.env.example` documented).
- Domain and application code never import `pydantic-settings` or know how configuration is loaded — they
  receive already-typed value objects, which keeps the dependency-direction rule intact (Settings loading is
  an infrastructure concern).
- A new tunable requires adding a field to the appropriate settings model and, if relevant, to
  `default.yaml` — a small, consistent, well-understood change.

## Alternatives considered

**Env-only configuration** (every setting, including domain tuning values, in `.env`/environment variables).
Simpler — one mechanism, no YAML parsing. Rejected because it makes frequently-tweaked structured settings
like per-skill scoring weights awkward to express and review (flat env vars don't nest well), and the
project's own requirements explicitly call for configuration files.
