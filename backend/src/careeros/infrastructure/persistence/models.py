"""SQLAlchemy ORM models mirroring the domain aggregates.

These are persistence-shape only -- the domain layer never imports from this module. Repository
implementations in `infrastructure/persistence/repositories/` translate between ORM rows and domain
entities. See docs/architecture/01-domain-model.md for the aggregates these mirror.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyModel(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Derived from `name` by the repository via domain.company.normalize_company_name; unique so the same
    # employer seen through two job sources cannot become two Company rows.
    normalized_name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    careers_page_url: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    size_estimate: Mapped[str | None] = mapped_column(String, nullable=True)
    tech_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    engineering_blog_url: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[list[dict]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=0)


class RecruiterContactModel(Base):
    __tablename__ = "recruiter_contacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    first_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str | None] = mapped_column(String, nullable=True)


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "source_job_id", name="uq_job_source_source_job_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_job_id: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    location_city: Mapped[str | None] = mapped_column(String, nullable=True)
    location_country: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_type: Mapped[str] = mapped_column(String, nullable=False)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    posting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ScoreModel(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_match: Mapped[float] = mapped_column(Float, nullable=False)
    skill_area_fit: Mapped[float] = mapped_column(Float, nullable=False)
    career_progression_fit: Mapped[float] = mapped_column(Float, nullable=False)
    remote_fit: Mapped[float] = mapped_column(Float, nullable=False)
    salary_fit: Mapped[float] = mapped_column(Float, nullable=False)
    company_quality: Mapped[float] = mapped_column(Float, nullable=False)
    narrative: Mapped[str] = mapped_column(String, nullable=False)
    scoring_strategy_version: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationStatusEventModel(Base):
    __tablename__ = "application_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(String, ForeignKey("applications.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String, nullable=True)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, default="system")


class ApplicationModel(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    current_resume_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_cover_letter_id: Mapped[str | None] = mapped_column(String, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)

    status_history: Mapped[list[ApplicationStatusEventModel]] = relationship(
        "ApplicationStatusEventModel", order_by=ApplicationStatusEventModel.changed_at, lazy="selectin"
    )


class ResumeVersionModel(Base):
    __tablename__ = "resume_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_master_version_ref: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String, ForeignKey("jobs.id"), nullable=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    render_status: Mapped[str] = mapped_column(String, default="draft")
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    has_gaps: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CoverLetterModel(Base):
    __tablename__ = "cover_letters"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), nullable=False)
    resume_version_id: Mapped[str] = mapped_column(String, ForeignKey("resume_versions.id"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    render_status: Mapped[str] = mapped_column(String, default="draft")
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResumeGapFlagModel(Base):
    __tablename__ = "resume_gap_flags"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(String, ForeignKey("resume_versions.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), nullable=False)
    missing_skill_or_requirement: Mapped[str] = mapped_column(String, nullable=False)
    suggested_language: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending_approval")


class EmailMessageModel(Base):
    __tablename__ = "email_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    from_address: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    classification: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    linked_company_id: Mapped[str | None] = mapped_column(String, ForeignKey("companies.id"), nullable=True)
    linked_application_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("applications.id"), nullable=True
    )
    draft_reply_id: Mapped[str | None] = mapped_column(String, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateProfileModel(Base):
    __tablename__ = "candidate_profile"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    headline: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    master_resume_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    # [{"title": ..., "priority": 1-5}]; kept as JSON because it is only ever read as a whole with the profile.
    role_interests: Mapped[list[dict]] = mapped_column(JSON, default=list)
    remote_preference: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_floor: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_skill_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    do_not_apply_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_tailor_resume_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
