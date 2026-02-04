"""Integration module for combining transcription and OCR results."""

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.ocr_processor import BatchOCRResult, OCRResult
from app.core.transcriber import TranscriptionResult, TranscriptSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SpeechSegment:
    """A speech segment within a chapter."""

    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }


@dataclass
class Chapter:
    """A chapter combining frame, OCR, and speech data."""

    index: int
    timestamp_start: float
    timestamp_end: float
    timestamp_display: str
    frame_image: str
    frame_image_base64: str
    ocr_text: str
    speech_segments: list[SpeechSegment]
    speech_text: str
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "index": self.index,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "timestamp_display": self.timestamp_display,
            "frame_image": self.frame_image,
            "frame_image_base64": self.frame_image_base64,
            "ocr_text": self.ocr_text,
            "speech_segments": [s.to_dict() for s in self.speech_segments],
            "speech_text": self.speech_text,
            "summary": self.summary,
        }


@dataclass
class UnifiedTranscriptMetadata:
    """Metadata for the unified transcript."""

    source_file: str
    duration: float
    total_frames_extracted: int
    processing_time: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source_file": self.source_file,
            "duration": self.duration,
            "total_frames_extracted": self.total_frames_extracted,
            "processing_time": self.processing_time,
        }


@dataclass
class UnifiedTranscript:
    """Complete unified transcript with metadata and chapters."""

    metadata: UnifiedTranscriptMetadata
    chapters: list[Chapter]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": self.metadata.to_dict(),
            "chapters": [c.to_dict() for c in self.chapters],
        }

    def get_total_word_count(self) -> int:
        """Get total word count across all chapters."""
        return sum(len(c.speech_text) for c in self.chapters)


class Integrator:
    """
    Integrates transcription and OCR results by timestamp.

    Combines speech segments with frame OCR data to create
    a unified transcript organized by chapters (frames).
    """

    def __init__(self, embed_images: bool = True):
        """
        Initialize Integrator.

        Args:
            embed_images: Whether to embed images as Base64 in output.
        """
        self.embed_images = embed_images

    def _format_timestamp(self, seconds: float) -> str:
        """
        Format seconds as HH:MM:SS timestamp.

        Args:
            seconds: Time in seconds.

        Returns:
            Formatted timestamp string.
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _image_to_base64(self, image_path: Path) -> str:
        """
        Convert image file to Base64 data URI.

        Args:
            image_path: Path to image file.

        Returns:
            Base64 data URI string.
        """
        if not image_path.exists():
            return ""

        try:
            with open(image_path, "rb") as f:
                data = f.read()

            # Determine MIME type
            suffix = image_path.suffix.lower()
            mime_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_types.get(suffix, "image/jpeg")

            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:{mime_type};base64,{encoded}"

        except Exception as e:
            logger.warning(
                "image_base64_failed",
                path=str(image_path),
                error=str(e),
            )
            return ""

    def _find_speech_segments_in_range(
        self,
        transcript_segments: list[TranscriptSegment],
        start_time: float,
        end_time: float,
    ) -> list[SpeechSegment]:
        """
        Find speech segments that fall within a time range.

        Args:
            transcript_segments: List of transcript segments.
            start_time: Start of time range.
            end_time: End of time range.

        Returns:
            List of SpeechSegment objects within the range.
        """
        segments = []

        for seg in transcript_segments:
            # Check if segment overlaps with the time range
            # Segment overlaps if it starts before end_time and ends after start_time
            if seg.start < end_time and seg.end > start_time:
                segments.append(
                    SpeechSegment(
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                    )
                )

        return segments

    def integrate(
        self,
        transcription: TranscriptionResult,
        ocr_results: BatchOCRResult,
        source_file: str,
        processing_start_time: Optional[float] = None,
    ) -> UnifiedTranscript:
        """
        Integrate transcription and OCR results.

        Each OCR result (frame) becomes a chapter. Speech segments
        are assigned to chapters based on timestamp overlap.

        Args:
            transcription: Transcription result from Transcriber.
            ocr_results: OCR results from OCRProcessor.
            source_file: Original video filename.
            processing_start_time: Start time for processing duration calc.

        Returns:
            UnifiedTranscript with integrated data.
        """
        logger.info(
            "starting_integration",
            transcript_segments=len(transcription.segments),
            ocr_frames=len(ocr_results.results),
        )

        start_time = processing_start_time or time.time()
        chapters: list[Chapter] = []

        # Sort OCR results by timestamp
        sorted_ocr = sorted(ocr_results.results, key=lambda x: x.timestamp)

        for i, ocr_result in enumerate(sorted_ocr):
            # Determine chapter time range
            chapter_start = ocr_result.timestamp

            # End time is the start of next frame, or video duration
            if i < len(sorted_ocr) - 1:
                chapter_end = sorted_ocr[i + 1].timestamp
            else:
                # For last chapter, use transcript duration or add buffer
                chapter_end = max(
                    transcription.duration,
                    chapter_start + 60.0,  # At least 60 seconds
                )

            # Find speech segments in this time range
            speech_segments = self._find_speech_segments_in_range(
                transcription.segments,
                chapter_start,
                chapter_end,
            )

            # Combine speech text
            speech_text = " ".join(seg.text for seg in speech_segments)

            # Convert image to Base64 if enabled
            image_path = Path(ocr_result.image_path)
            if self.embed_images:
                image_base64 = self._image_to_base64(image_path)
            else:
                image_base64 = ""

            chapter = Chapter(
                index=i,
                timestamp_start=chapter_start,
                timestamp_end=chapter_end,
                timestamp_display=self._format_timestamp(chapter_start),
                frame_image=str(image_path),
                frame_image_base64=image_base64,
                ocr_text=ocr_result.text,
                speech_segments=speech_segments,
                speech_text=speech_text,
                summary="",  # To be filled by summarizer
            )

            chapters.append(chapter)

        # Calculate processing time
        processing_time = time.time() - start_time

        # Create metadata
        metadata = UnifiedTranscriptMetadata(
            source_file=source_file,
            duration=transcription.duration,
            total_frames_extracted=len(ocr_results.results),
            processing_time=processing_time,
        )

        unified = UnifiedTranscript(
            metadata=metadata,
            chapters=chapters,
        )

        logger.info(
            "integration_complete",
            chapters=len(chapters),
            total_speech_segments=sum(
                len(c.speech_segments) for c in chapters
            ),
        )

        return unified

    def integrate_from_files(
        self,
        transcript_path: Path,
        ocr_path: Path,
        source_file: str,
    ) -> UnifiedTranscript:
        """
        Integrate from JSON files.

        Args:
            transcript_path: Path to transcript JSON file.
            ocr_path: Path to OCR results JSON file.
            source_file: Original video filename.

        Returns:
            UnifiedTranscript with integrated data.
        """
        # Load transcript
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_data = json.load(f)

        transcription = TranscriptionResult(
            segments=[
                TranscriptSegment(**seg) for seg in transcript_data["segments"]
            ],
            language=transcript_data["language"],
            language_probability=transcript_data["language_probability"],
            duration=transcript_data["duration"],
        )

        # Load OCR results
        with open(ocr_path, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)

        ocr_results = BatchOCRResult(
            results=[OCRResult(**r) for r in ocr_data["results"]],
            total_images=ocr_data["total_images"],
            processed_images=ocr_data["processed_images"],
            failed_images=ocr_data["failed_images"],
        )

        return self.integrate(
            transcription=transcription,
            ocr_results=ocr_results,
            source_file=source_file,
        )

    def save(self, unified: UnifiedTranscript, output_path: Path) -> None:
        """
        Save unified transcript to JSON file.

        Args:
            unified: UnifiedTranscript to save.
            output_path: Output file path.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(unified.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info("unified_transcript_saved", output_path=str(output_path))

    def integrate_and_save(
        self,
        transcription: TranscriptionResult,
        ocr_results: BatchOCRResult,
        output_path: Path,
        source_file: str,
    ) -> UnifiedTranscript:
        """
        Integrate and save in one step.

        Args:
            transcription: Transcription result.
            ocr_results: OCR results.
            output_path: Output file path.
            source_file: Original video filename.

        Returns:
            UnifiedTranscript object.
        """
        unified = self.integrate(
            transcription=transcription,
            ocr_results=ocr_results,
            source_file=source_file,
        )

        self.save(unified, output_path)

        return unified
