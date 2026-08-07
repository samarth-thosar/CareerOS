"""Use-case orchestration services.

Every service's constructor and public method signatures reflect the design in
docs/architecture/03-event-catalog-and-pipeline.md. Method bodies for features not yet built raise
`NotImplementedError` naming the phase that implements them, rather than faking behavior -- see
docs/architecture/00-overview.md, "Non-goals for this phase".
"""
