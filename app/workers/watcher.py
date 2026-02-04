"""Folder watcher for automatic video processing."""

import shutil
import time
import uuid
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.config import get_settings
from app.models.job import create_job, init_db
from app.utils.file_manager import FileManager
from app.utils.logger import get_logger, setup_logging
from app.workers.tasks import process_video

logger = get_logger(__name__)

# Supported video extensions
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class VideoFileHandler(FileSystemEventHandler):
    """Handles new video files in the watch directory."""

    def __init__(self, watch_dir: Path, processing_dir: Path):
        """
        Initialize handler.

        Args:
            watch_dir: Directory to watch for new videos.
            processing_dir: Directory to move files for processing.
        """
        self.watch_dir = watch_dir
        self.processing_dir = processing_dir
        self._processing_files: set[str] = set()

    def on_created(self, event):
        """Handle file creation event."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if it's a video file
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return

        # Avoid processing the same file multiple times
        if str(file_path) in self._processing_files:
            return

        self._processing_files.add(str(file_path))

        try:
            self._process_video(file_path)
        finally:
            self._processing_files.discard(str(file_path))

    def _wait_for_file_ready(self, file_path: Path, timeout: int = 60) -> bool:
        """
        Wait for file to be fully written.

        Args:
            file_path: Path to the file.
            timeout: Maximum seconds to wait.

        Returns:
            True if file is ready, False if timeout.
        """
        last_size = -1
        stable_count = 0
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                current_size = file_path.stat().st_size
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 3:  # Size stable for 3 checks
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
            except FileNotFoundError:
                return False

            time.sleep(1)

        return False

    def _process_video(self, file_path: Path):
        """
        Process a new video file.

        Args:
            file_path: Path to the video file.
        """
        logger.info("new_video_detected", path=str(file_path))

        # Wait for file to be fully written
        if not self._wait_for_file_ready(file_path):
            logger.warning("file_not_ready_timeout", path=str(file_path))
            return

        # Generate job ID
        job_id = str(uuid.uuid4())
        file_manager = FileManager(job_id)
        file_manager.ensure_directories()

        # Move file to processing directory
        dest_path = file_manager.job_dir / file_path.name
        shutil.move(str(file_path), str(dest_path))

        logger.info(
            "video_moved_to_processing",
            job_id=job_id,
            original=str(file_path),
            dest=str(dest_path),
        )

        # Create job in database
        try:
            create_job(job_id, file_path.name)
        except Exception as e:
            logger.error("job_creation_failed", job_id=job_id, error=str(e))
            return

        # Queue processing task
        try:
            process_video.delay(job_id, file_path.name)
            logger.info("job_queued", job_id=job_id, filename=file_path.name)
        except Exception as e:
            logger.error("task_queue_failed", job_id=job_id, error=str(e))


def run_watcher():
    """Run the folder watcher."""
    setup_logging()

    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    try:
        init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        return

    watch_dir = settings.input_dir
    processing_dir = settings.processing_dir

    logger.info(
        "starting_folder_watcher",
        watch_dir=str(watch_dir),
        extensions=list(SUPPORTED_EXTENSIONS),
    )

    event_handler = VideoFileHandler(watch_dir, processing_dir)
    observer = Observer()
    observer.schedule(event_handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("stopping_folder_watcher")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    run_watcher()
