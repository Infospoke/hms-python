import os
import logging
from datetime import datetime
from app.core import config
from groq import Groq, AsyncGroq
import base64
import io
import asyncio
from app.utils import timezone_utils

logger = logging.getLogger(__name__)


# --- SPEECH TO TEXT SERVICE ---


class SpeechToText:

    def __init__(self):
        self.api_key = config.GROQ_API_KEY
        self.model_name = config.WHISPER_MODEL_NAME or "whisper-large-v3"
        if not self.api_key:
            logger.warning(
                "GROQ_API_KEY not found in environment variables - STT will not work"
            )
            self.client = None
            self.async_client = None
        else:
            self.client = Groq(api_key=self.api_key)
            self.async_client = AsyncGroq(api_key=self.api_key)
            logger.info(f"Groq client initialized with model: {self.model_name}")

    def transcribe(self, audio_file):
        if not self.client:
            return None, 0
        if not os.path.exists(audio_file):
            logger.error(f"Audio file not found: {audio_file}")
            return None, 0
        try:
            start = timezone_utils.get_ist_now()
            with open(audio_file, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_file), file.read()),
                    model=self.model_name,
                    response_format="json",
                    language="en",
                )
            end = timezone_utils.get_ist_now()
            time_taken = (end - start).total_seconds()
            return transcription.text.strip(), time_taken
        except Exception as e:
            logger.error(f"Error transcribing audio file: {e}")
            return None, 0

    def transcribe_base64(self, base64_string, filename="audio.m4a"):
        if not self.client:
            return None, 0
        try:
            start = timezone_utils.get_ist_now()
            audio_bytes = base64.b64decode(base64_string)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            transcription = self.client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model=self.model_name,
                response_format="json",
                language="en",
            )
            end = timezone_utils.get_ist_now()
            time_taken = (end - start).total_seconds()
            return transcription.text.strip(), time_taken
        except Exception as e:
            logger.error(f"Error transcribing base64 audio: {e}")
            return None, 0

    def transcribe_answers(self, answers_dict: dict):
        transcriptions = {}
        logger.info(f"Starting batch transcription for {len(answers_dict)} answers")
        for q_id, base64_audio in answers_dict.items():
            logger.debug(f"Transcribing answer ID: {q_id}")
            text, time_taken = self.transcribe_base64(
                base64_audio, filename=f"answer_{q_id}.m4a"
            )
            if text:
                transcriptions[q_id] = text
                logger.debug(f"Answer ID {q_id} transcribed in {time_taken:.2f}s")
            else:
                transcriptions[q_id] = ""
                logger.warning(f"Failed to transcribe answer ID: {q_id}")
        return transcriptions

    async def transcribe_base64_async(self, base64_string, filename="audio.m4a"):
        if not self.async_client:
            logger.error("Groq async client not initialized - check API key")
            return None, 0
        try:
            start = timezone_utils.get_ist_now()
            audio_bytes = base64.b64decode(base64_string)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            transcription = await self.async_client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model=self.model_name,
                response_format="json",
                language="en",
            )
            end = timezone_utils.get_ist_now()
            time_taken = (end - start).total_seconds()
            return transcription.text.strip(), time_taken
        except Exception as e:
            logger.error(f"Error transcribing base64 audio (async): {e}")
            return None, 0

    async def transcribe_answers_async(self, answers_dict: dict):
        transcriptions = {}
        logger.info(
            f"Starting async batch transcription for {len(answers_dict)} answers"
        )

        async def process_answer(q_id, base64_audio):
            logger.debug(f"Transcribing answer ID: {q_id}")
            text, time_taken = await self.transcribe_base64_async(
                base64_audio, filename=f"answer_{q_id}.m4a"
            )
            if text:
                logger.debug(f"Answer ID {q_id} transcribed in {time_taken:.2f}s")
                return q_id, text
            else:
                logger.warning(f"Failed to transcribe answer ID: {q_id}")
                return q_id, ""

        tasks = [
            process_answer(q_id, base64_audio)
            for q_id, base64_audio in answers_dict.items()
        ]
        results = await asyncio.gather(*tasks)
        for q_id, text in results:
            transcriptions[q_id] = text
        return transcriptions
