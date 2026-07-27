#!/usr/bin/env python3
"""
Wyoming STT server that uses xAI Grok Speech-to-Text API.
Collects full audio utterance, converts it to WAV, and sends it to the REST endpoint.
"""
import asyncio
import logging
import os
import io
import wave
from functools import partial

import httpx
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.asr import Transcribe, Transcript

_LOGGER = logging.getLogger("wyoming-grok-stt")

# ====================== DEFAULT ENVS ======================
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_STT_URL = os.getenv("XAI_STT_URL", "https://api.x.ai/v1/stt")
DEFAULT_LANGUAGE = os.getenv("LANGUAGE", "en")
URI = os.getenv("WYOMING_URI", "tcp://0.0.0.0:10300")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


class GrokSttHandler(AsyncEventHandler):
    def __init__(self, *args, language: str = "en", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self._audio = bytearray()
        self._is_recording = False
        self._sample_rate = 16000
        self._sample_width = 2
        self._channels = 1
        self._client = httpx.AsyncClient(timeout=60.0)

    async def handle_event(self, event: Event) -> bool:
        # Advertise supported models and languages
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    asr=[
                        AsrProgram(
                            name="grok-stt",
                            description="Grok Speech-to-Text (xAI)",
                            attribution=Attribution(name="xAI", url="https://x.ai"),
                            installed=True,
                            version="1.0.0",
                            models=[
                                AsrModel(
                                    name="grok-stt",
                                    description="xAI Grok STT",
                                    attribution=Attribution(
                                        name="xAI", url="https://x.ai"
                                    ),
                                    installed=True,
                                    version="1.0.0",
                                    languages=[
                                        "ar",
                                        "cs",
                                        "da",
                                        "nl",
                                        "en",
                                        "fil",
                                        "fr",
                                        "de",
                                        "hi",
                                        "id",
                                        "it",
                                        "ja",
                                        "ko",
                                        "mk",
                                        "ms",
                                        "fa",
                                        "pl",
                                        "pt",
                                        "ro",
                                        "ru",
                                        "es",
                                        "sv",
                                        "th",
                                        "tr",
                                        "vi",
                                    ],
                                )
                            ],
                        )
                    ]
                ).event()
            )
            return True
        # Allow language override per request
        if Transcribe.is_type(event.type):
            data = Transcribe.from_event(event)
            if data.language:
                self.language = data.language
            return True
        # Start of utterance – reset buffer and store audio format
        if AudioStart.is_type(event.type):
            start = AudioStart.from_event(event)
            self._sample_rate = start.rate
            self._sample_width = start.width
            self._channels = start.channels
            self._audio.clear()
            self._is_recording = True
            _LOGGER.debug("AudioStart: %s Hz, %s ch", self._sample_rate, self._channels)
            return True
        # Collect audio chunks
        if AudioChunk.is_type(event.type) and self._is_recording:
            chunk = AudioChunk.from_event(event)
            self._audio.extend(chunk.audio)
            return True
        # End of utterance – send full audio to xAI and return transcript
        if AudioStop.is_type(event.type) and self._is_recording:
            self._is_recording = False
            audio_data = bytes(self._audio)
            _LOGGER.info(
                "AudioStop: %d bytes, language=%s", len(audio_data), self.language
            )

            text = await self._transcribe(audio_data)
            await self.write_event(Transcript(text=text or "").event())
            return True

        return True

    async def _transcribe(self, audio: bytes) -> str:
        """Convert raw PCM to WAV and send it to xAI STT API."""
        if not XAI_API_KEY:
            _LOGGER.error("XAI_API_KEY is not set")
            return ""

        if not audio:
            return ""

        try:
            # Wrap raw PCM into a proper WAV container
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(self._channels)
                wav_file.setsampwidth(self._sample_width)
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(audio)

            wav_data = wav_buffer.getvalue()

            files = {"file": ("audio.wav", wav_data, "audio/wav")}

            data = {}
            if self.language:
                data["language"] = self.language
                data["format"] = (
                    "true"  # for number and currency formats, e.g. "1,000" instead of "one thousand"
                )

            headers = {"Authorization": f"Bearer {XAI_API_KEY}"}

            resp = await self._client.post(
                XAI_STT_URL,
                headers=headers,
                files=files,
                data=data,
            )

            if resp.status_code != 200:
                _LOGGER.error("xAI STT error %s: %s", resp.status_code, resp.text[:500])
                return ""

            result = resp.json()
            text = (result.get("text") or "").strip()
            if text:
                _LOGGER.debug("Raw transcript: %s", text)
                # Remove common quote characters (keep apostrophes)
                text = text.replace("«", "").replace("»", "").replace('"', "")
                _LOGGER.info("Cleaned transcript: %s", text)
            return text

        except Exception:
            _LOGGER.exception("Failed to call xAI STT")
            return ""


async def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _LOGGER.info("Starting wyoming-grok-stt")
    _LOGGER.info("URI: %s", URI)
    _LOGGER.info("Default language: %s", DEFAULT_LANGUAGE)

    server = AsyncServer.from_uri(URI)
    await server.run(partial(GrokSttHandler, language=DEFAULT_LANGUAGE))


if __name__ == "__main__":
    asyncio.run(main())
