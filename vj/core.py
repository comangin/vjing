"""Core audio: capture (file or mic) + analyse FFT.

Expose an `AudioAnalyzer` class with a minimal API:
- start(source=None, mic=False)
- stop()
- attributes: latest_spectrum, latest_rms

This module intentionally keeps audio I/O separate from rendering.
"""
from typing import Optional
import threading
import queue
import time
try:
    import numpy as np
except Exception as e:
    np = None
    _np_import_err = e

_sd_import_err = None
_sf_import_err = None
try:
    import sounddevice as sd
except Exception as e:
    sd = None
    _sd_import_err = e
try:
    import soundfile as sf
except Exception as e:
    sf = None
    _sf_import_err = e



class AudioAnalyzer:
    """Capture live du périphérique audio (entrée micro) et calcul FFT."""
    def __init__(self, blocksize: int = 1024, samplerate: Optional[int] = None, device: Optional[int] = None):
        self.blocksize = blocksize
        self.samplerate = samplerate
        self.device = device
        self._spec_lock = threading.Lock()
        self.latest_spectrum = np.zeros(blocksize // 2)
        self.latest_rms = 0.0
        self._stop = threading.Event()
        self._stream = None

    def _analyze_frame(self, frame):
        if frame.ndim > 1:
            frame = np.mean(frame, axis=1)
        win = np.hanning(len(frame))
        frame_win = frame * win
        spec = np.abs(np.fft.rfft(frame_win))
        spec = spec / (np.max(spec) + 1e-6)
        rms = float(np.sqrt(np.mean(frame ** 2)))
        with self._spec_lock:
            target_len = self.blocksize // 2
            if len(spec) != target_len:
                spec = np.resize(spec, target_len)
            self.latest_spectrum = spec
            self.latest_rms = rms

    def _mic_callback(self, indata, frames, time_info, status):
        try:
            if indata.ndim > 1:
                mono = np.mean(indata, axis=1)
            else:
                mono = indata
            if len(mono) != self.blocksize:
                if len(mono) > self.blocksize:
                    mono = mono[: self.blocksize]
                else:
                    mono = np.pad(mono, (0, self.blocksize - len(mono)))
            self._analyze_frame(mono)
        except Exception:
            pass

    def start(self):
        """Démarre la capture live (entrée micro/périphérique)."""
        self._stop.clear()
        if sd is None:
            raise RuntimeError(f"sounddevice non disponible: {_sd_import_err}")
        samplerate = self.samplerate or sd.query_devices(self.device, 'input')['default_samplerate']
        try:
            self._stream = sd.InputStream(samplerate=int(samplerate), blocksize=self.blocksize,
                                          device=self.device, channels=1,
                                          callback=self._mic_callback)
            self._stream.start()
        except Exception as e:
            raise

    def stop(self):
        self._stop.set()
        try:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
        finally:
            pass
