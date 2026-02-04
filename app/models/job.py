"""SQLAlchemy models for job management."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

Base = declarative_base()


class JobStatus(str, PyEnum):
    """Job processing status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, PyEnum):
    """Individual step status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """Job model for tracking video processing jobs."""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    filename = Column(String(255), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    progress = Column(Integer, default=0)
    current_step = Column(String(50), nullable=True)

    # Step statuses
    step_extract_audio = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_extract_frames = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_transcribe = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_ocr = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_integrate = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_summarize = Column(Enum(StepStatus), default=StepStatus.PENDING)
    step_generate_html = Column(Enum(StepStatus), default=StepStatus.PENDING)

    # Metadata
    duration = Column(Float, nullable=True)
    total_frames = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Celery task ID
    celery_task_id = Column(String(36), nullable=True)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "job_id": self.id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": self.progress,
            "step": self.current_step,
            "steps": {
                "extract_audio": self.step_extract_audio.value,
                "extract_frames": self.step_extract_frames.value,
                "transcribe": self.step_transcribe.value,
                "ocr": self.step_ocr.value,
                "integrate": self.step_integrate.value,
                "summarize": self.step_summarize.value,
                "generate_html": self.step_generate_html.value,
            },
            "metadata": {
                "duration": self.duration,
                "total_frames": self.total_frames,
                "word_count": self.word_count,
            },
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# Database session management
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session():
    """Get database session."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_job(job_id: str) -> Optional[Job]:
    """Get job by ID."""
    session = get_session()
    try:
        return session.query(Job).filter(Job.id == job_id).first()
    finally:
        session.close()


def create_job(job_id: str, filename: str) -> Job:
    """Create a new job."""
    session = get_session()
    try:
        job = Job(id=job_id, filename=filename)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()


def update_job(job_id: str, **kwargs) -> Optional[Job]:
    """Update job fields."""
    session = get_session()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if job:
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            session.commit()
            session.refresh(job)
        return job
    finally:
        session.close()


def list_jobs(limit: int = 100, offset: int = 0) -> list[Job]:
    """List all jobs."""
    session = get_session()
    try:
        return (
            session.query(Job)
            .order_by(Job.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def delete_job(job_id: str) -> bool:
    """Delete a job."""
    session = get_session()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if job:
            session.delete(job)
            session.commit()
            return True
        return False
    finally:
        session.close()
