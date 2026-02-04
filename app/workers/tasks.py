"""Celery tasks for video processing pipeline."""

from datetime import datetime
from pathlib import Path

from celery import current_task

from app.config import get_settings
from app.core.html_generator import HTMLGenerator
from app.core.integrator import Integrator
from app.core.ocr_processor import OCRProcessor
from app.core.summarizer import Summarizer
from app.core.transcriber import Transcriber
from app.core.video_processor import VideoProcessor
from app.models.job import (
    Job,
    JobStatus,
    StepStatus,
    get_job,
    update_job,
)
from app.utils.file_manager import FileManager
from app.utils.logger import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


def update_step(job_id: str, step: str, status: StepStatus, progress: int = None):
    """Update job step status and progress."""
    updates = {
        f"step_{step}": status,
        "current_step": step if status == StepStatus.PROCESSING else None,
    }
    if progress is not None:
        updates["progress"] = progress

    update_job(job_id, **updates)

    # Update Celery task state
    if current_task:
        current_task.update_state(
            state="PROGRESS",
            meta={"step": step, "status": status.value, "progress": progress},
        )


@celery_app.task(bind=True, name="app.workers.tasks.process_video")
def process_video(self, job_id: str, input_filename: str):
    """
    Process a video through the complete pipeline.

    Args:
        job_id: Unique job identifier.
        input_filename: Name of the uploaded video file.

    Returns:
        dict with job result information.
    """
    logger.info("task_started", job_id=job_id, filename=input_filename)

    # Update job with Celery task ID
    update_job(
        job_id,
        status=JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    file_manager = FileManager(job_id)
    input_path = file_manager.job_dir / input_filename

    try:
        # ============================================================
        # Step 1: Extract Audio
        # ============================================================
        update_step(job_id, "extract_audio", StepStatus.PROCESSING, 5)
        logger.info("step_extract_audio", job_id=job_id)

        video_processor = VideoProcessor(input_path, file_manager.job_dir)
        video_info = video_processor.get_video_info()
        audio_path = video_processor.extract_audio()

        update_step(job_id, "extract_audio", StepStatus.COMPLETED, 10)

        # ============================================================
        # Step 2: Extract Frames
        # ============================================================
        update_step(job_id, "extract_frames", StepStatus.PROCESSING, 15)
        logger.info("step_extract_frames", job_id=job_id)

        frames = video_processor.extract_keyframes()
        unique_frames = video_processor.remove_duplicate_frames(frames)

        update_job(job_id, total_frames=len(unique_frames), duration=video_info.duration)
        update_step(job_id, "extract_frames", StepStatus.COMPLETED, 25)

        # ============================================================
        # Step 3: Transcribe Audio
        # ============================================================
        update_step(job_id, "transcribe", StepStatus.PROCESSING, 30)
        logger.info("step_transcribe", job_id=job_id)

        transcriber = Transcriber()
        transcription = transcriber.transcribe(
            audio_path=audio_path,
            language=settings.whisper_language,
            vad_filter=True,
        )

        update_step(job_id, "transcribe", StepStatus.COMPLETED, 50)

        # ============================================================
        # Step 4: OCR Processing
        # ============================================================
        update_step(job_id, "ocr", StepStatus.PROCESSING, 55)
        logger.info("step_ocr", job_id=job_id)

        ocr_processor = OCRProcessor(languages=["ja", "en"], gpu=False)
        ocr_results = ocr_processor.process_frames(unique_frames)

        update_step(job_id, "ocr", StepStatus.COMPLETED, 70)

        # ============================================================
        # Step 5: Integration
        # ============================================================
        update_step(job_id, "integrate", StepStatus.PROCESSING, 75)
        logger.info("step_integrate", job_id=job_id)

        integrator = Integrator(embed_images=True)
        unified = integrator.integrate(
            transcription=transcription,
            ocr_results=ocr_results,
            source_file=input_filename,
        )

        update_step(job_id, "integrate", StepStatus.COMPLETED, 80)

        # ============================================================
        # Step 6: Summarization
        # ============================================================
        update_step(job_id, "summarize", StepStatus.PROCESSING, 82)
        logger.info("step_summarize", job_id=job_id)

        overall_summary = ""
        if settings.anthropic_api_key and settings.anthropic_api_key != "sk-ant-xxxxx":
            summarizer = Summarizer()
            unified, overall_summary = summarizer.summarize_transcript(unified)
        else:
            logger.warning("skipping_summarization_no_api_key", job_id=job_id)

        update_step(job_id, "summarize", StepStatus.COMPLETED, 90)

        # ============================================================
        # Step 7: Generate HTML
        # ============================================================
        update_step(job_id, "generate_html", StepStatus.PROCESSING, 92)
        logger.info("step_generate_html", job_id=job_id)

        html_generator = HTMLGenerator()
        output_path = file_manager.output_html_path

        html_generator.generate_and_save(
            unified=unified,
            output_path=output_path,
            title=Path(input_filename).stem,
            overall_summary=overall_summary,
        )

        # Calculate word count
        word_count = sum(len(c.speech_text) for c in unified.chapters)

        update_step(job_id, "generate_html", StepStatus.COMPLETED, 100)

        # ============================================================
        # Complete
        # ============================================================
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            current_step=None,
            word_count=word_count,
            completed_at=datetime.utcnow(),
        )

        logger.info(
            "task_completed",
            job_id=job_id,
            output_path=str(output_path),
            duration=video_info.duration,
            frames=len(unique_frames),
            word_count=word_count,
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "output_path": str(output_path),
            "metadata": {
                "duration": video_info.duration,
                "total_frames": len(unique_frames),
                "word_count": word_count,
            },
        }

    except Exception as e:
        logger.error("task_failed", job_id=job_id, error=str(e))

        update_job(
            job_id,
            status=JobStatus.FAILED,
            error_message=str(e),
            completed_at=datetime.utcnow(),
        )

        raise
