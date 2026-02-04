"""Video processing module using ffmpeg for audio extraction and keyframe extraction."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import imagehash
from PIL import Image

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedFrame:
    """Represents an extracted video frame."""

    path: Path
    timestamp: float
    phash: Optional[str] = None


@dataclass
class VideoInfo:
    """Video metadata."""

    duration: float
    width: int
    height: int
    fps: float
    codec: str


class VideoProcessor:
    """
    Handles video processing using ffmpeg.

    Provides methods for:
    - Extracting audio from video
    - Extracting keyframes using scene detection
    - Removing duplicate frames using perceptual hashing
    """

    def __init__(self, input_path: Path, output_dir: Path):
        """
        Initialize VideoProcessor.

        Args:
            input_path: Path to the input video file.
            output_dir: Directory for output files.
        """
        self.input_path = input_path
        self.output_dir = output_dir
        self.frames_dir = output_dir / "frames"
        self.settings = get_settings()

        # Ensure output directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    def get_video_info(self) -> VideoInfo:
        """
        Get video metadata using ffprobe.

        Returns:
            VideoInfo with duration, dimensions, fps, and codec.

        Raises:
            RuntimeError: If ffprobe fails.
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(self.input_path),
        ]

        logger.debug("running_ffprobe", command=" ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                raise RuntimeError("No video stream found")

            # Parse FPS (e.g., "30/1" or "29.97")
            fps_str = video_stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den)
            else:
                fps = float(fps_str)

            duration = float(data.get("format", {}).get("duration", 0))

            return VideoInfo(
                duration=duration,
                width=int(video_stream.get("width", 0)),
                height=int(video_stream.get("height", 0)),
                fps=fps,
                codec=video_stream.get("codec_name", "unknown"),
            )

        except subprocess.CalledProcessError as e:
            logger.error("ffprobe_failed", error=e.stderr)
            raise RuntimeError(f"ffprobe failed: {e.stderr}")
        except json.JSONDecodeError as e:
            logger.error("ffprobe_parse_failed", error=str(e))
            raise RuntimeError(f"Failed to parse ffprobe output: {e}")

    def extract_audio(self, output_path: Optional[Path] = None) -> Path:
        """
        Extract audio from video as 16kHz mono WAV.

        Args:
            output_path: Optional custom output path. Defaults to output_dir/audio.wav.

        Returns:
            Path to the extracted audio file.

        Raises:
            RuntimeError: If audio extraction fails.
        """
        if output_path is None:
            output_path = self.output_dir / "audio.wav"

        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", str(self.input_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            str(output_path),
        ]

        logger.info(
            "extracting_audio",
            input=str(self.input_path),
            output=str(output_path),
        )

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("audio_extracted", output=str(output_path))
            return output_path

        except subprocess.CalledProcessError as e:
            logger.error("audio_extraction_failed", error=e.stderr)
            raise RuntimeError(f"Audio extraction failed: {e.stderr}")

    def extract_keyframes(
        self,
        scene_threshold: Optional[float] = None,
    ) -> list[ExtractedFrame]:
        """
        Extract keyframes using scene detection.

        Extracts frames where significant scene changes occur based on
        the scene detection threshold.

        Args:
            scene_threshold: Scene change detection threshold (0.0-1.0).
                            Lower values = more sensitive. Defaults to config value.

        Returns:
            List of ExtractedFrame objects with paths and timestamps.

        Raises:
            RuntimeError: If frame extraction fails.
        """
        if scene_threshold is None:
            scene_threshold = self.settings.scene_detect_threshold

        # First, detect scene changes and get timestamps
        # Using select filter with scene detection
        cmd = [
            "ffmpeg",
            "-i", str(self.input_path),
            "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
            "-vsync", "vfr",
            "-frame_pts", "1",
            "-f", "null",
            "-",
        ]

        logger.info(
            "detecting_scenes",
            input=str(self.input_path),
            threshold=scene_threshold,
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

            # Parse showinfo output to get timestamps
            # Format: [Parsed_showinfo_1 @ ...] n: 0 pts: 12345 pts_time:1.234567 ...
            timestamps: list[float] = []
            for line in result.stderr.split("\n"):
                if "pts_time:" in line:
                    match = re.search(r"pts_time:(\d+\.?\d*)", line)
                    if match:
                        timestamps.append(float(match.group(1)))

            logger.info("scenes_detected", count=len(timestamps))

            # If no scenes detected, extract frames at regular intervals
            if not timestamps:
                logger.warning("no_scenes_detected, using interval extraction")
                return self._extract_frames_by_interval()

            # Now extract the actual frames at detected timestamps
            return self._extract_frames_at_timestamps(timestamps)

        except subprocess.CalledProcessError as e:
            logger.error("scene_detection_failed", error=e.stderr)
            raise RuntimeError(f"Scene detection failed: {e.stderr}")

    def _extract_frames_at_timestamps(
        self,
        timestamps: list[float],
    ) -> list[ExtractedFrame]:
        """
        Extract frames at specific timestamps.

        Args:
            timestamps: List of timestamps in seconds.

        Returns:
            List of ExtractedFrame objects.
        """
        frames: list[ExtractedFrame] = []

        for i, ts in enumerate(timestamps):
            # Format timestamp for filename (e.g., 00_03_25 for 3:25)
            hours = int(ts // 3600)
            minutes = int((ts % 3600) // 60)
            seconds = int(ts % 60)
            ts_str = f"{hours:02d}_{minutes:02d}_{seconds:02d}"

            output_path = self.frames_dir / f"frame_{ts_str}_{i:04d}.jpg"

            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(ts),  # Seek to timestamp
                "-i", str(self.input_path),
                "-frames:v", "1",  # Extract 1 frame
                "-q:v", "2",  # High quality JPEG
                str(output_path),
            ]

            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                frames.append(ExtractedFrame(path=output_path, timestamp=ts))

            except subprocess.CalledProcessError as e:
                logger.warning(
                    "frame_extraction_failed",
                    timestamp=ts,
                    error=e.stderr,
                )
                continue

        logger.info("frames_extracted", count=len(frames))
        return frames

    def _extract_frames_by_interval(
        self,
        interval_seconds: float = 30.0,
    ) -> list[ExtractedFrame]:
        """
        Extract frames at regular intervals (fallback method).

        Args:
            interval_seconds: Interval between frames in seconds.

        Returns:
            List of ExtractedFrame objects.
        """
        video_info = self.get_video_info()
        timestamps = []
        current = 0.0

        while current < video_info.duration:
            timestamps.append(current)
            current += interval_seconds

        return self._extract_frames_at_timestamps(timestamps)

    def remove_duplicate_frames(
        self,
        frames: list[ExtractedFrame],
        threshold: Optional[int] = None,
    ) -> list[ExtractedFrame]:
        """
        Remove duplicate frames using perceptual hashing.

        Compares frames using pHash (perceptual hash) and removes
        frames that are too similar to previous frames.

        Args:
            frames: List of extracted frames.
            threshold: Hamming distance threshold. Frames with distance < threshold
                      are considered duplicates. Defaults to config value.

        Returns:
            Filtered list of unique frames.
        """
        if threshold is None:
            threshold = self.settings.phash_threshold

        if not frames:
            return []

        logger.info(
            "removing_duplicates",
            input_count=len(frames),
            threshold=threshold,
        )

        unique_frames: list[ExtractedFrame] = []
        prev_hash: Optional[imagehash.ImageHash] = None

        for frame in frames:
            try:
                # Calculate perceptual hash
                with Image.open(frame.path) as img:
                    current_hash = imagehash.phash(img)

                frame.phash = str(current_hash)

                # Check if this frame is a duplicate
                if prev_hash is not None:
                    distance = current_hash - prev_hash
                    if distance < threshold:
                        logger.debug(
                            "duplicate_frame_removed",
                            path=str(frame.path),
                            distance=distance,
                        )
                        # Remove the duplicate file
                        frame.path.unlink(missing_ok=True)
                        continue

                unique_frames.append(frame)
                prev_hash = current_hash

            except Exception as e:
                logger.warning(
                    "hash_calculation_failed",
                    path=str(frame.path),
                    error=str(e),
                )
                # Keep the frame if hashing fails
                unique_frames.append(frame)

        logger.info(
            "duplicates_removed",
            input_count=len(frames),
            output_count=len(unique_frames),
            removed=len(frames) - len(unique_frames),
        )

        return unique_frames

    def process(self) -> tuple[Path, list[ExtractedFrame]]:
        """
        Run the complete video processing pipeline.

        1. Extract audio
        2. Extract keyframes using scene detection
        3. Remove duplicate frames

        Returns:
            Tuple of (audio_path, list of unique frames).
        """
        logger.info("starting_video_processing", input=str(self.input_path))

        # Get video info
        video_info = self.get_video_info()
        logger.info(
            "video_info",
            duration=video_info.duration,
            resolution=f"{video_info.width}x{video_info.height}",
            fps=video_info.fps,
        )

        # Extract audio
        audio_path = self.extract_audio()

        # Extract keyframes
        frames = self.extract_keyframes()

        # Remove duplicates
        unique_frames = self.remove_duplicate_frames(frames)

        logger.info(
            "video_processing_complete",
            audio_path=str(audio_path),
            frame_count=len(unique_frames),
        )

        return audio_path, unique_frames
