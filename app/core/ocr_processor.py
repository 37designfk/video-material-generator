"""OCR processing module using EasyOCR."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OCRResult:
    """OCR result for a single image."""

    image_path: str
    timestamp: float
    text: str
    confidence: float = 0.0
    text_lines: list[str] = None

    def __post_init__(self):
        if self.text_lines is None:
            self.text_lines = []

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "image_path": self.image_path,
            "timestamp": self.timestamp,
            "text": self.text,
            "confidence": self.confidence,
            "text_lines": self.text_lines,
        }


@dataclass
class BatchOCRResult:
    """Result of batch OCR processing."""

    results: list[OCRResult]
    total_images: int
    processed_images: int
    failed_images: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total_images": self.total_images,
            "processed_images": self.processed_images,
            "failed_images": self.failed_images,
        }


class OCRProcessor:
    """
    OCR processing using EasyOCR.

    Processes extracted keyframe images in batches to extract
    on-screen text (slides, presentations, etc.).
    """

    _reader = None

    def __init__(
        self,
        languages: Optional[list[str]] = None,
        gpu: bool = False,
        batch_size: int = 4,
    ):
        """
        Initialize OCRProcessor.

        Args:
            languages: List of language codes (e.g., ["ja", "en"]).
            gpu: Whether to use GPU acceleration.
            batch_size: Number of images to process in each batch.
        """
        self.settings = get_settings()
        self.languages = languages or ["ja", "en"]
        self.gpu = gpu
        self.batch_size = batch_size

    def _get_reader(self):
        """
        Get or create EasyOCR reader instance.

        Uses lazy loading to avoid loading models until needed.
        Reader is cached as a class variable to reuse across instances.

        Returns:
            EasyOCR Reader instance.
        """
        if OCRProcessor._reader is None:
            logger.info(
                "loading_easyocr_models",
                languages=self.languages,
                gpu=self.gpu,
            )

            import easyocr

            OCRProcessor._reader = easyocr.Reader(
                self.languages,
                gpu=self.gpu,
                verbose=False,
            )

            logger.info("easyocr_models_loaded")

        return OCRProcessor._reader

    def process_image(
        self,
        image_path: Path,
        timestamp: float = 0.0,
    ) -> OCRResult:
        """
        Process a single image for OCR.

        Args:
            image_path: Path to the image file.
            timestamp: Timestamp associated with this image.

        Returns:
            OCRResult with extracted text.

        Raises:
            FileNotFoundError: If image file doesn't exist.
            RuntimeError: If OCR processing fails.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        try:
            reader = self._get_reader()

            # Run OCR
            results = reader.readtext(str(image_path))

            # Extract text and confidence
            text_lines = []
            total_confidence = 0.0

            for bbox, text, confidence in results:
                text_lines.append(text)
                total_confidence += confidence

            avg_confidence = (
                total_confidence / len(results) if results else 0.0
            )
            full_text = "\n".join(text_lines)

            return OCRResult(
                image_path=str(image_path),
                timestamp=timestamp,
                text=full_text,
                confidence=avg_confidence,
                text_lines=text_lines,
            )

        except Exception as e:
            logger.error(
                "ocr_processing_failed",
                image_path=str(image_path),
                error=str(e),
            )
            raise RuntimeError(f"OCR processing failed: {e}")

    def process_batch(
        self,
        image_paths: list[Path],
        timestamps: Optional[list[float]] = None,
    ) -> BatchOCRResult:
        """
        Process multiple images.

        Args:
            image_paths: List of image file paths.
            timestamps: List of timestamps for each image.

        Returns:
            BatchOCRResult with all OCR results.
        """
        if not image_paths:
            return BatchOCRResult(
                results=[],
                total_images=0,
                processed_images=0,
                failed_images=0,
            )

        if timestamps is None:
            timestamps = [0.0] * len(image_paths)

        logger.info(
            "starting_batch_ocr",
            total_images=len(image_paths),
            languages=self.languages,
        )

        # Ensure reader is loaded
        self._get_reader()

        results: list[OCRResult] = []
        failed_count = 0

        for i, (path, ts) in enumerate(zip(image_paths, timestamps)):
            logger.debug(
                "processing_image",
                index=i + 1,
                total=len(image_paths),
                path=str(path),
            )

            try:
                result = self.process_image(path, ts)
                results.append(result)
            except Exception as e:
                logger.warning(
                    "image_processing_failed",
                    path=str(path),
                    error=str(e),
                )
                failed_count += 1
                results.append(
                    OCRResult(
                        image_path=str(path),
                        timestamp=ts,
                        text="",
                        confidence=0.0,
                        text_lines=[],
                    )
                )

        # Sort results by timestamp
        results.sort(key=lambda r: r.timestamp)

        batch_result = BatchOCRResult(
            results=results,
            total_images=len(image_paths),
            processed_images=len(image_paths) - failed_count,
            failed_images=failed_count,
        )

        logger.info(
            "batch_ocr_complete",
            total=batch_result.total_images,
            processed=batch_result.processed_images,
            failed=batch_result.failed_images,
        )

        return batch_result

    def process_frames(
        self,
        frames: list,
    ) -> BatchOCRResult:
        """
        Process ExtractedFrame objects from video_processor.

        Args:
            frames: List of ExtractedFrame objects (from video_processor).

        Returns:
            BatchOCRResult with all OCR results.
        """
        image_paths = [f.path for f in frames]
        timestamps = [f.timestamp for f in frames]

        return self.process_batch(
            image_paths=image_paths,
            timestamps=timestamps,
        )

    def process_and_save(
        self,
        image_paths: list[Path],
        output_path: Path,
        timestamps: Optional[list[float]] = None,
    ) -> BatchOCRResult:
        """
        Process images and save results to JSON file.

        Args:
            image_paths: List of image file paths.
            output_path: Path for output JSON file.
            timestamps: List of timestamps for each image.

        Returns:
            BatchOCRResult object.
        """
        result = self.process_batch(
            image_paths=image_paths,
            timestamps=timestamps,
        )

        # Save to JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info("ocr_results_saved", output_path=str(output_path))

        return result
