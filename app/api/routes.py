"""API route definitions."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.schemas import (
    ErrorResponse,
    HealthResponse,
    JobListResponse,
    JobResultResponse,
    JobStatus,
    JobStatusResponse,
    ProcessingSteps,
    UploadResponse,
)
from app.config import get_settings
from app.utils.file_manager import FileManager
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Application version
APP_VERSION = "0.1.0"

# Allowed video extensions
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the API server is running.",
)
async def health_check() -> HealthResponse:
    """
    Perform health check.

    Returns:
        Health status with version and timestamp.
    """
    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload video",
    description="Upload a video file for processing.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file type"},
        500: {"model": ErrorResponse, "description": "Upload failed"},
    },
)
async def upload_video(
    file: Annotated[UploadFile, File(description="Video file to process")],
) -> UploadResponse:
    """
    Upload a video file for processing.

    Args:
        file: The video file to upload.

    Returns:
        Job ID and initial status.

    Raises:
        HTTPException: If file type is invalid or upload fails.
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Generate job ID and set up file manager
    job_id = str(uuid.uuid4())
    file_manager = FileManager(job_id)

    try:
        # Ensure directories exist
        settings = get_settings()
        settings.ensure_directories()
        file_manager.ensure_directories()

        # Save uploaded file
        input_path = file_manager.job_dir / file.filename
        content = await file.read()
        input_path.write_bytes(content)

        logger.info(
            "video_uploaded",
            job_id=job_id,
            filename=file.filename,
            size_bytes=len(content),
        )

        # TODO: Queue Celery task for processing
        # For now, just return the job ID

        return UploadResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error("upload_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Get the processing status of a job.",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the status of a processing job.

    Args:
        job_id: The job identifier.

    Returns:
        Current job status and progress.

    Raises:
        HTTPException: If job is not found.
    """
    file_manager = FileManager(job_id)

    if not file_manager.job_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # TODO: Get actual status from database/Celery
    # For now, return a placeholder response
    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        progress=0,
        step=None,
        steps=ProcessingSteps(),
        created_at=datetime.now(timezone.utc),
    )


@router.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Get the result of a completed job.",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        400: {"model": ErrorResponse, "description": "Job not completed"},
    },
)
async def get_job_result(job_id: str) -> JobResultResponse:
    """
    Get the result of a completed job.

    Args:
        job_id: The job identifier.

    Returns:
        Result with HTML URL and metadata.

    Raises:
        HTTPException: If job is not found or not completed.
    """
    file_manager = FileManager(job_id)

    if not file_manager.job_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # TODO: Check if job is completed and return actual result
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Job is not completed yet",
    )


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List jobs",
    description="Get a list of all jobs.",
)
async def list_jobs() -> JobListResponse:
    """
    List all processing jobs.

    Returns:
        List of jobs with their status.
    """
    # TODO: Get actual job list from database
    return JobListResponse(jobs=[], total=0)


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete job",
    description="Delete a job and its files.",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def delete_job(job_id: str) -> None:
    """
    Delete a job and all associated files.

    Args:
        job_id: The job identifier.

    Raises:
        HTTPException: If job is not found.
    """
    file_manager = FileManager(job_id)

    if not file_manager.job_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    try:
        file_manager.cleanup()
        logger.info("job_deleted", job_id=job_id)
    except Exception as e:
        logger.error("job_delete_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(e)}",
        )
