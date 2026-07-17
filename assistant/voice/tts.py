"""Bộ NÓI (TTS) offline: piper tổng hợp giọng tiếng Việt -> WAV -> phát bằng aplay.

Model piper (.onnx) được nạp MỘT LẦN rồi dùng lại cho mọi câu.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import wave

from piper import PiperVoice


class Tts:
    def __init__(self, model_path: str, config_path: str | None = None):
        model_path = os.path.expanduser(model_path)
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"Không thấy model giọng piper: {model_path}")
        if config_path is None:
            candidate = model_path + ".json"
            config_path = candidate if os.path.exists(candidate) else None
        self.voice = PiperVoice.load(model_path, config_path=config_path)

    def synth(self, text: str, out_path: str) -> None:
        with wave.open(out_path, "wb") as wav_file:
            self.voice.synthesize_wav(text, wav_file)

    def speak(self, text: str) -> None:
        """Tổng hợp và phát (chặn cho tới khi phát xong). Nên gọi trong thread nền."""
        text = (text or "").strip()
        if not text:
            return
        path = os.path.join(tempfile.gettempdir(), "biaa_tts.wav")
        self.synth(text, path)
        subprocess.run(
            ["aplay", "-q", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
