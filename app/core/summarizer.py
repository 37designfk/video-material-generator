"""Summarization module using Claude API."""

import json
from typing import Optional

import anthropic

from app.config import get_settings
from app.core.integrator import Chapter, UnifiedTranscript
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Summarizer:
    """
    Generates summaries using Claude API.

    Creates chapter summaries and overall summaries for
    video transcripts using Anthropic's Claude model.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize Summarizer.

        Args:
            api_key: Anthropic API key. Defaults to config.
            model: Model name to use. Defaults to config.
        """
        self.settings = get_settings()
        self.api_key = api_key or self.settings.anthropic_api_key
        self.model = model or self.settings.claude_model

        if not self.api_key or self.api_key == "sk-ant-xxxxx":
            logger.warning("anthropic_api_key_not_configured")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def summarize_chapter(
        self,
        chapter: Chapter,
        context: Optional[str] = None,
    ) -> str:
        """
        Generate summary for a single chapter.

        Args:
            chapter: Chapter to summarize.
            context: Optional context about the video.

        Returns:
            Summary text.
        """
        # Build prompt
        prompt_parts = []

        if context:
            prompt_parts.append(f"動画の概要: {context}\n")

        prompt_parts.append(f"タイムスタンプ: {chapter.timestamp_display}")

        if chapter.ocr_text:
            prompt_parts.append(f"\n画面に表示されているテキスト:\n{chapter.ocr_text}")

        if chapter.speech_text:
            prompt_parts.append(f"\n話されている内容:\n{chapter.speech_text}")

        content = "\n".join(prompt_parts)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": f"""以下の動画チャプターの内容を、2-3文で簡潔に要約してください。
要点を押さえた分かりやすい日本語で書いてください。

{content}

要約:""",
                    }
                ],
            )

            summary = response.content[0].text.strip()

            logger.debug(
                "chapter_summarized",
                chapter_index=chapter.index,
                summary_length=len(summary),
            )

            return summary

        except anthropic.APIError as e:
            logger.error(
                "chapter_summarization_failed",
                chapter_index=chapter.index,
                error=str(e),
            )
            return ""

    def summarize_all_chapters(
        self,
        unified: UnifiedTranscript,
        context: Optional[str] = None,
    ) -> UnifiedTranscript:
        """
        Generate summaries for all chapters in a transcript.

        Args:
            unified: UnifiedTranscript to summarize.
            context: Optional context about the video.

        Returns:
            UnifiedTranscript with summaries filled in.
        """
        logger.info(
            "starting_chapter_summarization",
            total_chapters=len(unified.chapters),
        )

        for chapter in unified.chapters:
            # Skip chapters with no content
            if not chapter.speech_text and not chapter.ocr_text:
                logger.debug(
                    "skipping_empty_chapter",
                    chapter_index=chapter.index,
                )
                continue

            summary = self.summarize_chapter(chapter, context)
            chapter.summary = summary

        summarized_count = sum(1 for c in unified.chapters if c.summary)

        logger.info(
            "chapter_summarization_complete",
            summarized=summarized_count,
            total=len(unified.chapters),
        )

        return unified

    def generate_overall_summary(
        self,
        unified: UnifiedTranscript,
    ) -> str:
        """
        Generate an overall summary of the entire video.

        Args:
            unified: UnifiedTranscript to summarize.

        Returns:
            Overall summary text.
        """
        # Collect all chapter content
        chapter_summaries = []
        for chapter in unified.chapters:
            if chapter.summary:
                chapter_summaries.append(
                    f"[{chapter.timestamp_display}] {chapter.summary}"
                )
            elif chapter.speech_text:
                # Use first 200 chars of speech if no summary
                text = chapter.speech_text[:200]
                chapter_summaries.append(f"[{chapter.timestamp_display}] {text}...")

        if not chapter_summaries:
            return ""

        content = "\n".join(chapter_summaries)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""以下は動画の各チャプターの要約です。
動画全体の概要を3-5文で簡潔にまとめてください。

{content}

全体の概要:""",
                    }
                ],
            )

            summary = response.content[0].text.strip()

            logger.info(
                "overall_summary_generated",
                summary_length=len(summary),
            )

            return summary

        except anthropic.APIError as e:
            logger.error("overall_summarization_failed", error=str(e))
            return ""

    def summarize_transcript(
        self,
        unified: UnifiedTranscript,
        generate_overall: bool = True,
    ) -> tuple[UnifiedTranscript, str]:
        """
        Summarize entire transcript with optional overall summary.

        Args:
            unified: UnifiedTranscript to summarize.
            generate_overall: Whether to generate overall summary.

        Returns:
            Tuple of (updated UnifiedTranscript, overall summary).
        """
        # Summarize chapters
        unified = self.summarize_all_chapters(unified)

        # Generate overall summary
        overall_summary = ""
        if generate_overall:
            overall_summary = self.generate_overall_summary(unified)

        return unified, overall_summary
