"""File path management utilities."""

import uuid
from pathlib import Path
from typing import Optional

from app.config import get_settings


class FileManager:
    """Manages file paths for video processing jobs."""

    def __init__(self, job_id: Optional[str] = None):
        """
        Initialize FileManager.

        Args:
            job_id: Unique job identifier. If None, a new UUID is generated.
        """
        self.settings = get_settings()
        self.job_id = job_id or str(uuid.uuid4())

    @property
    def job_dir(self) -> Path:
        """Get the job's processing directory."""
        return self.settings.processing_dir / self.job_id

    @property
    def frames_dir(self) -> Path:
        """Get the directory for extracted frames."""
        return self.job_dir / "frames"

    @property
    def audio_path(self) -> Path:
        """Get the path for extracted audio file."""
        return self.job_dir / "audio.wav"

    @property
    def transcript_path(self) -> Path:
        """Get the path for transcription JSON."""
        return self.job_dir / "transcript.json"

    @property
    def ocr_path(self) -> Path:
        """Get the path for OCR results JSON."""
        return self.job_dir / "ocr_results.json"

    @property
    def unified_transcript_path(self) -> Path:
        """Get the path for unified transcript JSON."""
        return self.job_dir / "unified_transcript.json"

    @property
    def output_html_path(self) -> Path:
        """Get the path for output HTML file."""
        return self.settings.output_dir / self.job_id / "material.html"

    def ensure_directories(self) -> None:
        """Create all necessary directories for the job."""
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.output_dir / self.job_id).mkdir(parents=True, exist_ok=True)

    def get_input_path(self, filename: str) -> Path:
        """
        Get the full path for an input file.

        Args:
            filename: The input filename.

        Returns:
            Full path to the input file.
        """
        return self.settings.input_dir / filename

    def cleanup(self) -> None:
        """Remove all temporary files for this job."""
        import shutil

        if self.job_dir.exists():
            shutil.rmtree(self.job_dir)
