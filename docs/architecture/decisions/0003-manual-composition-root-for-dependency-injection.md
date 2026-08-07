# 0003 — Manual Composition Root for Dependency Injection

## Context

The project explicitly requires dependency injection and no global state, so services can be constructed
with fakes in tests and adapters can be swapped without touching business logic. A choice was needed between
a DI framework (e.g. `dependency-injector`, with containers/providers/wiring) and a plain, hand-written
composition root.

## Decision

Use a single, explicit bootstrap module (`infrastructure/bootstrap.py`) that constructs every adapter and
service via plain constructor injection, in dependency order, with no DI framework, decorators, or wiring
magic.

## Consequences

- The entire object graph is visible by reading one file top to bottom — there is no framework-managed
  container to inspect at runtime to answer "what is this service actually wired to."
- Adding a new service means adding a few lines to the composition root, not learning a framework's provider
  API. This favors a project maintained mostly by one person.
- There is slightly more boilerplate than a framework would auto-generate, but it stays proportional to the
  number of services rather than growing with framework complexity.
- Tests build their own small composition roots (or construct services directly) using fakes, exercising the
  exact same constructor-injection pattern as production code — there is no separate "test mode" wiring
  mechanism to keep in sync with the real one.

## Alternatives considered

**A DI framework (`dependency-injector` or similar).** Offers scopes, factories, and declarative wiring out
of the box. Rejected because it adds a layer of indirection (container lookups, provider declarations) that
is rarely worth it below a certain team size, and because the manual approach already satisfies every actual
requirement (constructor injection, no global state, swappable adapters) without the extra dependency or
learning curve.
