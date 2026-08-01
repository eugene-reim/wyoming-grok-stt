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

import httpx
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.asr import Transcribe, Transcript

_LOGGER = logging.getLogger("wyoming-grok-stt")

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_STT_URL = os.getenv("XAI_STT_URL", "https://api.x.ai/v1/stt")
URI = os.getenv("WYOMING_URI", "tcp://0.0.0.0:10500")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


class GrokSttHandler(AsyncEventHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.language = None
        self._audio = bytearray()
        self._is_recording = False
        self._sample_rate = 16000
        self._sample_width = 2
        self._channels = 1
        self._client = httpx.AsyncClient(timeout=60.0)
        _LOGGER.debug("Client connected")

    async def handle_event(self, event: Event) -> bool:
        try:
            return await self._handle_event(event)
        except Exception:
            _LOGGER.exception("Error while handling event type=%s", event.type)
            return False

    async def _handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    asr=[
                        AsrProgram(
                            name="grok-stt",
                            description="Grok Speech-to-Text (xAI)",
                            attribution=Attribution(name="xAI", url="https://x.ai"),
                            installed=True,
                            version="1.5.0",
                            models=[
                                AsrModel(
                                    name="grok-stt",
                                    description="xAI Grok STT",
                                    attribution=Attribution(
                                        name="xAI", url="https://x.ai"
                                    ),
                                    installed=True,
                                    version="1.5.0",
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
            _LOGGER.debug("Sent info")
            return True

        if Transcribe.is_type(event.type):
            data = Transcribe.from_event(event)
            if data.language:
                self.language = data.language
            _LOGGER.debug("Transcribe language=%s", self.language)
            return True

        if AudioStart.is_type(event.type):
            start = AudioStart.from_event(event)
            self._sample_rate = start.rate
            self._sample_width = start.width
            self._channels = start.channels
            self._audio.clear()
            self._is_recording = True
            _LOGGER.debug(
                "AudioStart: %s Hz, %s ch, width=%s",
                self._sample_rate,
                self._channels,
                self._sample_width,
            )
            return True

        if AudioChunk.is_type(event.type) and self._is_recording:
            chunk = AudioChunk.from_event(event)
            self._audio.extend(chunk.audio)
            return True

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
        if not XAI_API_KEY:
            _LOGGER.error("XAI_API_KEY is not set")
            return ""

        if not audio:
            return ""

        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(self._channels)
                wav_file.setsampwidth(self._sample_width)
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(audio)

            wav_data = wav_buffer.getvalue()

            files = {"file": ("audio.wav", wav_data, "audio/wav")}
            lang = self.language or "auto"
            data = {"language": lang}
            if self.language:
                data["format"] = "true"

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
                text = text.replace("«", "").replace("»", "").replace('"', "")
                _LOGGER.info("Cleaned transcript: %s", text)
            return text

        except Exception:
            _LOGGER.exception("Failed to call xAI STT")
            return ""

    async def disconnect(self) -> None:
        _LOGGER.debug("Client disconnected")
        await self._client.aclose()


async def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _LOGGER.info("Starting wyoming-grok-stt")
    _LOGGER.info("URI: %s", URI)
    if not XAI_API_KEY:
        _LOGGER.warning("XAI_API_KEY is not set — transcriptions will fail")

    server = AsyncServer.from_uri(URI)
    await server.run(GrokSttHandler)


if __name__ == "__main__":
    asyncio.run(main())
