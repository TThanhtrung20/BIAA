"""Bộ NGHE (STT) offline: thu mic (sounddevice) + nhận dạng (faster-whisper).

Thu tới khi im lặng một lúc (VAD đơn giản theo mức năng lượng), rồi phiên âm.
Model whisper được nạp MỘT LẦN.
"""
from __future__ import annotations

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


class Stt:
    def __init__(self, model_size: str = "small", sample_rate: int = 16000):
        self.sr = sample_rate
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def record(self, max_seconds: float = 8.0, silence_ms: int = 900,
               threshold: float = 0.02, warmup_ms: int = 400) -> "np.ndarray":
        """Thu từ mic; dừng khi im lặng ~silence_ms sau khi đã có tiếng, hoặc hết max_seconds."""
        block = int(self.sr * 0.05)               # khối 50ms
        max_blocks = int(max_seconds / 0.05)
        silence_blocks = int(silence_ms / 50)
        warmup_blocks = int(warmup_ms / 50)
        chunks = []
        started = False
        silent = 0
        with sd.InputStream(samplerate=self.sr, channels=1,
                            dtype="float32", blocksize=block) as stream:
            for i in range(max_blocks):
                data, _ = stream.read(block)
                d = data.reshape(-1)
                chunks.append(d.copy())
                rms = float(np.sqrt(np.mean(d * d))) if d.size else 0.0
                if i < warmup_blocks:
                    continue
                if rms > threshold:
                    started = True
                    silent = 0
                elif started:
                    silent += 1
                    if silent >= silence_blocks:
                        break
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")

    def wait_for_utterance(self, stop_event, manual_event, threshold: float = 0.02,
                           max_seconds: float = 8.0, silence_ms: int = 800):
        """Nghe nền: canh mic tới khi CÓ tiếng nói rồi thu trọn câu.

        Rẻ khi im lặng (chỉ tính năng lượng mỗi 50ms), chỉ tốn CPU khi có tiếng.
        Trả (status, audio):
          - ("audio", ndarray): đã thu được một câu nói.
          - ("manual", None):   người dùng bấm gọi (double-click/menu).
          - ("stop", None):     yêu cầu dừng.
        """
        block = int(self.sr * 0.05)               # khối 50ms
        silence_blocks = int(silence_ms / 50)
        with sd.InputStream(samplerate=self.sr, channels=1,
                            dtype="float32", blocksize=block) as stream:
            # Giai đoạn 1: chờ có tiếng (kiểm tra stop/manual mỗi ~50ms)
            chunks = None
            while True:
                if stop_event.is_set():
                    return ("stop", None)
                if manual_event is not None and manual_event.is_set():
                    return ("manual", None)
                data, _ = stream.read(block)
                d = data.reshape(-1)
                rms = float(np.sqrt(np.mean(d * d))) if d.size else 0.0
                if rms > threshold:
                    chunks = [d.copy()]
                    break
            # Giai đoạn 2: thu tiếp tới khi im lặng đủ lâu
            silent = 0
            max_blocks = int(max_seconds / 0.05)
            for _ in range(max_blocks):
                if stop_event.is_set():
                    break
                data, _ = stream.read(block)
                d = data.reshape(-1)
                chunks.append(d.copy())
                rms = float(np.sqrt(np.mean(d * d))) if d.size else 0.0
                if rms > threshold:
                    silent = 0
                else:
                    silent += 1
                    if silent >= silence_blocks:
                        break
        return ("audio", np.concatenate(chunks))

    def transcribe(self, audio: "np.ndarray") -> str:
        if audio is None or audio.size == 0:
            return ""
        segments, _ = self.model.transcribe(audio, language="vi", beam_size=5)
        return "".join(seg.text for seg in segments).strip()

    def listen(self, max_seconds: float = 8.0) -> str:
        return self.transcribe(self.record(max_seconds=max_seconds))
