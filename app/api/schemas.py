"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job processing status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Individual step status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingSteps(BaseModel):
    """Status of each processing step."""

    extract_audio: StepStatus = StepStatus.PENDING
    extract_frames: StepStatus = StepStatus.PENDING
    transcribe: StepStatus = StepStatus.PENDING
    ocr: StepStatus = StepStatus.PENDING
    integrate: StepStatus = StepStatus.PENDING
    summarize: StepStatus = StepStatus.PENDING
    generate_html: StepStatus = StepStatus.PENDING


class UploadResponse(BaseModel):
    """Response for video upload."""

    job_id: str
    status: JobStatus
    created_at: datetime


class JobStatusResponse(BaseModel):
    """Response for job status query."""

    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    step: Optional[str] = None
    steps: ProcessingSteps
    created_at: datetime
    error_message: Optional[str] = None


class JobMetadata(BaseModel):
    """Metadata about the processed video."""

    title: str
    duration: str
    chapters: int
    total_frames: int
    word_count: int


class JobResultResponse(BaseModel):
    """Response for completed job result."""

    job_id: str
    status: JobStatus
    html_url: str
    metadata: JobMetadata


class JobListItem(BaseModel):
    """Item in job list response."""

    job_id: str
    status: JobStatus
    progress: int
    created_at: datetime
    filename: Optional[str] = None


class JobListResponse(BaseModel):
    """Response for job list."""

    jobs: list[JobListItem]
    total: int


class HealthResponse(BaseModel):
    """Response for health check."""

    status: str
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[str] = None
