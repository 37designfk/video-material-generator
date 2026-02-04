"""API route definitions."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.schemas import (
    ErrorResponse,
    HealthResponse,
    JobListItem,
    JobListResponse,
    JobMetadata,
    JobResultResponse,
    JobStatus,
    JobStatusResponse,
    ProcessingSteps,
    StepStatus,
    UploadResponse,
)
from app.config import get_settings
from app.models.job import (
    JobStatus as DBJobStatus,
    StepStatus as DBStepStatus,
    create_job,
    delete_job as db_delete_job,
    get_job,
    list_jobs as db_list_jobs,
)
from app.utils.file_manager import FileManager
from app.utils.logger import get_logger
from app.workers.tasks import process_video

router = APIRouter()
logger = get_logger(__name__)

# Application version
APP_VERSION = "0.2.0"

# Allowed video extensions
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _convert_step_status(db_status: DBStepStatus) -> StepStatus:
    """Convert database step status to API schema."""
    return StepStatus(db_status.value)


def _convert_job_status(db_status: DBJobStatus) -> JobStatus:
    """Convert database job status to API schema."""
    return JobStatus(db_status.value)


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

        # Create job in database
        job = create_job(job_id, file.filename)

        # Queue Celery task for processing
        process_video.delay(job_id, file.filename)

        logger.info("job_queued", job_id=job_id)

        return UploadResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=job.created_at,
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
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return JobStatusResponse(
        job_id=job.id,
        status=_convert_job_status(job.status),
        progress=job.progress,
        step=job.current_step,
        steps=ProcessingSteps(
            extract_audio=_convert_step_status(job.step_extract_audio),
            extract_frames=_convert_step_status(job.step_extract_frames),
            transcribe=_convert_step_status(job.step_transcribe),
            ocr=_convert_step_status(job.step_ocr),
            integrate=_convert_step_status(job.step_integrate),
            summarize=_convert_step_status(job.step_summarize),
            generate_html=_convert_step_status(job.step_generate_html),
        ),
        created_at=job.created_at,
        error_message=job.error_message,
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
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != DBJobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job.status.value}",
        )

    file_manager = FileManager(job_id)

    return JobResultResponse(
        job_id=job.id,
        status=JobStatus.COMPLETED,
        html_url=f"/api/jobs/{job_id}/download/html",
        metadata=JobMetadata(
            title=Path(job.filename).stem,
            duration=f"{int(job.duration // 60):02d}:{int(job.duration % 60):02d}" if job.duration else "00:00",
            chapters=job.total_frames or 0,
            total_frames=job.total_frames or 0,
            word_count=job.word_count or 0,
        ),
    )


@router.get(
    "/jobs/{job_id}/download/html",
    summary="Download HTML",
    description="Download the generated HTML material.",
    responses={
        404: {"model": ErrorResponse, "description": "Job or file not found"},
    },
)
async def download_html(job_id: str):
    """
    Download the generated HTML file.

    Args:
        job_id: The job identifier.

    Returns:
        HTML file as download.
    """
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    file_manager = FileManager(job_id)
    html_path = file_manager.output_html_path

    if not html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HTML file not found",
        )

    return FileResponse(
        path=html_path,
        filename=f"{Path(job.filename).stem}_material.html",
        media_type="text/html",
    )


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List jobs",
    description="Get a list of all jobs.",
)
async def list_jobs(limit: int = 100, offset: int = 0) -> JobListResponse:
    """
    List all processing jobs.

    Args:
        limit: Maximum number of jobs to return.
        offset: Number of jobs to skip.

    Returns:
        List of jobs with their status.
    """
    jobs = db_list_jobs(limit=limit, offset=offset)

    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=job.id,
                status=_convert_job_status(job.status),
                progress=job.progress,
                created_at=job.created_at,
                filename=job.filename,
            )
            for job in jobs
        ],
        total=len(jobs),
    )


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
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    try:
        # Delete files
        file_manager = FileManager(job_id)
        file_manager.cleanup()

        # Delete from database
        db_delete_job(job_id)

        logger.info("job_deleted", job_id=job_id)

    except Exception as e:
        logger.error("job_delete_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(e)}",
        )
