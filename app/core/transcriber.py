"""Audio transcription module using faster-whisper."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TranscriptSegment:
    """A single transcription segment with timing."""

    start: float
    end: float
    text: str
    confidence: float = 0.0


@dataclass
class TranscriptionResult:
    """Complete transcription result."""

    segments: list[TranscriptSegment]
    language: str
    language_probability: float
    duration: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "segments": [asdict(s) for s in self.segments],
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
        }

    def get_full_text(self) -> str:
        """Get the complete transcription as a single string."""
        return " ".join(s.text.strip() for s in self.segments)


class Transcriber:
    """
    Audio transcription using faster-whisper.

    Uses the large-v3 model with VAD filtering for accurate
    Japanese speech transcription with timestamps.
    """

    _model: Optional[WhisperModel] = None

    def __init__(
        self,
        model_size: Optional[str] = None,
        compute_type: Optional[str] = None,
        device: str = "auto",
    ):
        """
        Initialize Transcriber.

        Args:
            model_size: Whisper model size (e.g., "large-v3"). Defaults to config.
            compute_type: Computation type (e.g., "float16"). Defaults to config.
            device: Device to use ("auto", "cuda", "cpu"). Defaults to "auto".
        """
        self.settings = get_settings()
        self.model_size = model_size or self.settings.whisper_model
        self.compute_type = compute_type or self.settings.whisper_compute_type
        self.device = device

    def _get_model(self) -> WhisperModel:
        """
        Get or create the Whisper model instance.

        Uses lazy loading to avoid loading the model until needed.
        Model is cached as a class variable to reuse across instances.

        Returns:
            Loaded WhisperModel instance.
        """
        if Transcriber._model is None:
            logger.info(
                "loading_whisper_model",
                model_size=self.model_size,
                compute_type=self.compute_type,
                device=self.device,
            )

            Transcriber._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )

            logger.info("whisper_model_loaded")

        return Transcriber._model

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        vad_filter: bool = True,
        vad_parameters: Optional[dict] = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio file to text with timestamps.

        Args:
            audio_path: Path to the audio file (WAV, MP3, etc.).
            language: Language code (e.g., "ja"). Defaults to config.
                     Set to None for auto-detection.
            vad_filter: Enable Voice Activity Detection to skip silence.
            vad_parameters: Optional VAD parameters dict.

        Returns:
            TranscriptionResult with segments and metadata.

        Raises:
            FileNotFoundError: If audio file doesn't exist.
            RuntimeError: If transcription fails.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if language is None:
            language = self.settings.whisper_language

        logger.info(
            "starting_transcription",
            audio_path=str(audio_path),
            language=language,
            vad_filter=vad_filter,
        )

        model = self._get_model()

        # Default VAD parameters optimized for speech
        if vad_parameters is None:
            vad_parameters = {
                "threshold": 0.5,
                "min_speech_duration_ms": 250,
                "min_silence_duration_ms": 100,
                "speech_pad_ms": 30,
            }

        try:
            segments_generator, info = model.transcribe(
                str(audio_path),
                language=language,
                vad_filter=vad_filter,
                vad_parameters=vad_parameters,
                beam_size=5,
                best_of=5,
                word_timestamps=False,
            )

            # Convert generator to list of segments
            segments: list[TranscriptSegment] = []
            for segment in segments_generator:
                segments.append(
                    TranscriptSegment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text,
                        confidence=segment.avg_logprob,
                    )
                )

            result = TranscriptionResult(
                segments=segments,
                language=info.language,
                language_probability=info.language_probability,
                duration=info.duration,
            )

            logger.info(
                "transcription_complete",
                segments_count=len(segments),
                duration=info.duration,
                language=info.language,
                language_probability=info.language_probability,
            )

            return result

        except Exception as e:
            logger.error("transcription_failed", error=str(e))
            raise RuntimeError(f"Transcription failed: {e}")

    def transcribe_and_save(
        self,
        audio_path: Path,
        output_path: Path,
        language: Optional[str] = None,
        vad_filter: bool = True,
    ) -> TranscriptionResult:
        """
        Transcribe audio and save result to JSON file.

        Args:
            audio_path: Path to the audio file.
            output_path: Path for output JSON file.
            language: Language code (e.g., "ja").
            vad_filter: Enable VAD filtering.

        Returns:
            TranscriptionResult object.
        """
        result = self.transcribe(
            audio_path=audio_path,
            language=language,
            vad_filter=vad_filter,
        )

        # Save to JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info("transcription_saved", output_path=str(output_path))

        return result


def format_timestamp(seconds: float) -> str:
    """
    Format seconds as HH:MM:SS.mmm timestamp.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"
