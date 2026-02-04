"""HTML material generator using Jinja2 templates."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings
from app.core.integrator import UnifiedTranscript
from app.utils.logger import get_logger

logger = get_logger(__name__)


class HTMLGenerator:
    """
    Generates HTML learning materials from unified transcripts.

    Creates single-file HTML with embedded images, table of contents,
    and collapsible transcript sections.
    """

    def __init__(self, template_dir: Optional[Path] = None):
        """
        Initialize HTMLGenerator.

        Args:
            template_dir: Directory containing Jinja2 templates.
                         Defaults to app/templates.
        """
        self.settings = get_settings()

        if template_dir is None:
            # Default to app/templates
            template_dir = Path(__file__).parent.parent / "templates"

        template_dir.mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Register custom filters
        self.env.filters["format_duration"] = self._format_duration

    def _format_duration(self, seconds: float) -> str:
        """
        Format seconds as human-readable duration.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted duration string (e.g., "1:23:45").
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def generate(
        self,
        unified: UnifiedTranscript,
        title: Optional[str] = None,
        overall_summary: Optional[str] = None,
    ) -> str:
        """
        Generate HTML from unified transcript.

        Args:
            unified: UnifiedTranscript to convert.
            title: Optional title for the material.
            overall_summary: Optional overall summary text.

        Returns:
            Generated HTML string.
        """
        if title is None:
            title = Path(unified.metadata.source_file).stem

        # Calculate statistics
        total_word_count = sum(
            len(c.speech_text) for c in unified.chapters
        )
        chapters_with_content = sum(
            1 for c in unified.chapters
            if c.speech_text or c.ocr_text
        )

        template = self.env.get_template("material.html")

        html = template.render(
            title=title,
            unified=unified,
            overall_summary=overall_summary,
            total_word_count=total_word_count,
            chapters_with_content=chapters_with_content,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        logger.info(
            "html_generated",
            title=title,
            chapters=len(unified.chapters),
            word_count=total_word_count,
        )

        return html

    def generate_and_save(
        self,
        unified: UnifiedTranscript,
        output_path: Path,
        title: Optional[str] = None,
        overall_summary: Optional[str] = None,
    ) -> Path:
        """
        Generate HTML and save to file.

        Args:
            unified: UnifiedTranscript to convert.
            output_path: Output file path.
            title: Optional title for the material.
            overall_summary: Optional overall summary text.

        Returns:
            Path to saved HTML file.
        """
        html = self.generate(unified, title, overall_summary)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

        logger.info("html_saved", output_path=str(output_path))

        return output_path
