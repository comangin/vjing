"""Compat shim providing a legacy-like `AudioVisualizer` API.

This lightweight shim composes the new `AudioAnalyzer` + `VisualGUI` so
older callers can use a similar pattern: instantiate then call `run()`.
"""
from typing import Optional
from .core import AudioAnalyzer
from .gui import VisualGUI


class AudioVisualizer:
    def __init__(self, device: Optional[int] = None, blocksize: int = 1024,
                 samplerate: Optional[int] = None):
        self.device = device
        self.blocksize = blocksize
        self.samplerate = samplerate

        self.analyzer = AudioAnalyzer(blocksize=self.blocksize, samplerate=self.samplerate, device=self.device)
        self.gui = VisualGUI(self.analyzer)

    def run(self):
        try:
            self.analyzer.start()
        except Exception as e:
            print("Erreur démarrage analyser:", e)
            return
        try:
            self.gui.run()
        finally:
            self.analyzer.stop()
