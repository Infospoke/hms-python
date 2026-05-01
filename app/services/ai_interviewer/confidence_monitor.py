import os
import time
import logging

import json
import asyncio
import io
import base64

from app.core import config
from .confidence_analysis.audio_signal_analyzer import AudioSignalAnalyzer
from .confidence_analysis.comprehensive_analyzer import (
    ComprehensiveAnalyzer,
)
from .speech_to_text import SpeechToText
from .proctoring import ProctoringEngine

logger = logging.getLogger(__name__)


class ConfidenceMonitor:
    def __init__(self):
        self.proctoring_engine = ProctoringEngine()
        self.audio_analyzer = AudioSignalAnalyzer()
        self.llm_analyzer = ComprehensiveAnalyzer()
        self.stt_engine = SpeechToText()
        self.micro_expression_count = 0

    async def generate_comprehensive_report(
        self, audio_file_path: str = None, base64_audio: str = None
    ) -> dict:
        logger.info("Generating comprehensive confidence report...")

        voice_data = None
        text_data = None
        transcription = ""

        if audio_file_path or base64_audio:
            temp_audio_path = None
            try:
                if base64_audio:
                    audio_bytes = base64.b64decode(base64_audio)
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as temp_file:
                        temp_file.write(audio_bytes)
                        temp_audio_path = temp_file.name

                    transcription, _ = await self.stt_engine.transcribe_base64_async(
                        base64_audio
                    )

                    voice_data = await asyncio.to_thread(
                        self.audio_analyzer.analyze, temp_audio_path
                    )

                elif audio_file_path:
                    transcription, _ = self.stt_engine.transcribe(audio_file_path)
                    voice_data = await asyncio.to_thread(
                        self.audio_analyzer.analyze, audio_file_path
                    )

                if self.llm_analyzer and transcription:
                    logger.info("Starting LLM text analysis (threaded)...")
                    text_data = await asyncio.to_thread(
                        self.llm_analyzer.analyze, transcription
                    )
                    logger.info("LLM text analysis completed.")

                if voice_data and transcription:
                    duration_min = (
                        voice_data["metrics"].get("total_duration_sec", 0) / 60
                    )
                    word_count = len(transcription.split())
                    if duration_min > 0:
                        true_wpm = int(word_count / duration_min)
                        voice_data["metrics"]["speech_rate_wpm"] = true_wpm

            except Exception as e:
                logger.error(f"Error processing audio in confidence monitor: {e}")
                voice_data = None

            finally:
                if temp_audio_path and os.path.exists(temp_audio_path):
                    try:
                        os.remove(temp_audio_path)
                    except Exception as cleanup_err:
                        logger.warning(
                            f"Failed to delete temp audio file {temp_audio_path}: {cleanup_err}"
                        )

        a_score = voice_data["score"] if voice_data else 0
        t_score = text_data["assertiveness_score"] if text_data else 0

        denominator = 0
        score_sum = 0

        if voice_data:
            score_sum += a_score * 0.5
            denominator += 0.5
        if text_data:
            score_sum += t_score * 0.5
            denominator += 0.5

        if denominator > 0:
            final_score = int(score_sum / denominator)
        else:
            final_score = 0

        return {
            "final_confidence_score": final_score,
            "confidence_level": self._get_label(final_score),
            "metrics": {
                "audio": voice_data["metrics"] if voice_data else None,
                "linguistic": text_data,
            },
            "transcript": transcription,
        }

    def _calculate_visual_metrics(self):
        return None

    def _get_label(self, score):
        if score >= 85:
            return "High Confidence"
        if score >= 65:
            return "Normal"
        return "Low Confidence"
