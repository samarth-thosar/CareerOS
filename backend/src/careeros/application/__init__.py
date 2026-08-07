"""The application layer: use-case services, the ports they depend on, and cross-layer DTOs.

Services depend only on domain types and the ports declared under `application.ports` -- never on concrete
infrastructure. See docs/architecture/00-overview.md.
"""
