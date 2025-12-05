"""Simple VJ-style audio visualizer.

Features:
- Two input modes: audio file or microphone (live).
- Uses sounddevice + soundfile for audio I/O and numpy FFT for analysis.
- Displays a responsive visualization with pygame.

Notes:
- Install dependencies in `requirements.txt`.
- Run with the runner `env_ia/run_vj.py`.
"""
import argparse
import threading
import queue
import math
import time
from typing import Optional

import numpy as np

# sounddevice / soundfile may raise on import if PortAudio or libsndfile
# system libraries are missing (common in minimal containers). Import them
# lazily and capture import errors so the module can still be imported for
# argument parsing or help output.
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

import pygame


class AudioVisualizer:
    """Audio visualizer that can use a file or live microphone.

    Typical usage:
        v = AudioVisualizer(source='path/to/file.wav')
        v.run()
    Or for mic:
        v = AudioVisualizer(mic=True)
        v.run()
    """

    def __init__(self, source: Optional[str] = None, mic: bool = False,
                 device: Optional[int] = None, blocksize: int = 1024,
                 samplerate: Optional[int] = None):
        self.source = source
        self.mic = mic
        self.device = device
        self.blocksize = blocksize
        self.samplerate = samplerate

        self._spec_lock = threading.Lock()
        self.latest_spectrum = np.zeros(blocksize // 2)
        self.latest_rms = 0.0

        # queue for audio frames when using file mode (producer -> callback)
        # avoid using subscripted types like `queue.Queue[np.ndarray]` which
        # require newer Python/typing features; use a plain annotation so the
        # module can run in older interpreters inside the user's virtualenv.
        self._file_q: queue.Queue = queue.Queue(maxsize=8)

        # flag to stop threads/streams
        self._stop = threading.Event()

    def _analyze_frame(self, frame: np.ndarray):
        # frame: shape (n, channels) or (n,) mono
        if frame.ndim > 1:
            frame = np.mean(frame, axis=1)
        # apply window
        win = np.hanning(len(frame))
        frame_win = frame * win
        # FFT
        spec = np.abs(np.fft.rfft(frame_win))
        # normalize
        spec = spec / (np.max(spec) + 1e-6)
        rms = float(np.sqrt(np.mean(frame ** 2)))
        with self._spec_lock:
            # keep spectrum length consistent with blocksize/2
            target_len = self.blocksize // 2
            if len(spec) != target_len:
                spec = np.resize(spec, target_len)
            self.latest_spectrum = spec
            self.latest_rms = rms

    # ---------- File playback mode ----------
    def _file_playback_worker(self):
        """Read audio file and play it, while posting frames to analysis queue."""
        if sf is None or sd is None:
            print("Audio libraries not available (soundfile/sounddevice).\n"
                  "Install system libs (PortAudio, libsndfile) and Python packages to use file playback.")
            self._stop.set()
            return
        assert self.source
        try:
            with sf.SoundFile(self.source, "r") as f:
                samplerate = self.samplerate or f.samplerate

                def callback(outdata, frames, time_info, status):
                    try:
                        data = f.read(frames, dtype="float32")
                        if len(data) == 0:
                            raise sd.CallbackStop()
                        # if mono -> make sure outdata shape fits
                        if data.ndim == 1:
                            out = np.expand_dims(data, axis=1)
                        else:
                            out = data
                        # if fewer frames than requested, pad
                        if out.shape[0] < frames:
                            pad = np.zeros((frames - out.shape[0], out.shape[1]), dtype="float32")
                            out = np.vstack((out, pad))
                        outdata[:] = out
                        # also analyze chunk (use copy to avoid mutation)
                        try:
                            self._file_q.put_nowait(out.copy())
                        except queue.Full:
                            pass
                    except sd.CallbackStop:
                        raise
                    except Exception:
                        raise

                with sd.OutputStream(samplerate=samplerate, blocksize=self.blocksize,
                                      device=self.device, channels=f.channels,
                                      callback=callback):
                    # keep the stream alive until playback finishes
                    while not self._stop.is_set():
                        time.sleep(0.1)
        except Exception as e:
            print("Erreur playback fichier:", e)
            self._stop.set()

    def _file_analyzer_worker(self):
        # consume from queue and analyze
        while not self._stop.is_set():
            try:
                frame = self._file_q.get(timeout=0.2)
            except queue.Empty:
                continue
            # convert to mono and analyze
            if frame.ndim > 1:
                mono = np.mean(frame, axis=1)
            else:
                mono = frame
            # if length mismatch, resample/truncate/pad
            if len(mono) != self.blocksize:
                if len(mono) > self.blocksize:
                    mono = mono[: self.blocksize]
                else:
                    mono = np.pad(mono, (0, self.blocksize - len(mono)))
            self._analyze_frame(mono)

    # ---------- Microphone mode ----------
    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            # print(status)
            pass
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

    # ---------- Visuals (pygame) ----------
    def _draw(self, screen, width, height):
        # get a copy of spectrum
        with self._spec_lock:
            spec = np.copy(self.latest_spectrum)
            rms = float(self.latest_rms)

        screen.fill((8, 8, 12))
        # draw radial bands based on spectrum
        n = len(spec)
        center = (width // 2, height // 2)
        max_radius = min(width, height) // 2 - 20
        # draw a pulsating background circle based on rms
        pulse = int(30 + min(200, rms * 2000))
        pygame.draw.circle(screen, (pulse, pulse // 2, pulse // 4), center, 40)

        # draw frequency bars in a circular layout
        for i in range(n):
            angle = 2 * math.pi * i / n
            mag = float(spec[i])
            inner = int(60 + (max_radius * 0.2))
            outer = int(inner + mag * (max_radius - inner))
            x1 = center[0] + int(inner * math.cos(angle))
            y1 = center[1] + int(inner * math.sin(angle))
            x2 = center[0] + int(outer * math.cos(angle))
            y2 = center[1] + int(outer * math.sin(angle))
            # color gradient
            col = (min(255, int(100 + mag * 155)), min(255, int(30 + mag * 120)), 200)
            pygame.draw.line(screen, col, (x1, y1), (x2, y2), 2)

        # small HUD
        font = pygame.font.SysFont(None, 20)
        txt = font.render(f"Source: {self.source or 'mic'}  RMS: {rms:.4f}", True, (200, 200, 200))
        screen.blit(txt, (10, 10))

        pygame.display.flip()

    def run(self):
        # Start audio threads/streams then run pygame loop
        # if file mode -> playback + analyzer thread
        threads = []

        if self.source and not self.mic:
            t_play = threading.Thread(target=self._file_playback_worker, daemon=True)
            t_play.start()
            threads.append(t_play)
            t_anal = threading.Thread(target=self._file_analyzer_worker, daemon=True)
            t_anal.start()
            threads.append(t_anal)
        else:
            # mic input
            samplerate = self.samplerate or sd.query_devices(self.device, 'input')['default_samplerate']
            try:
                stream = sd.InputStream(samplerate=int(samplerate), blocksize=self.blocksize,
                                        device=self.device, channels=1,
                                        callback=self._mic_callback)
                stream.start()
            except Exception as e:
                print("Impossible d'ouvrir le micro:", e)
                return

        # pygame init
        pygame.init()
        width, height = 800, 600
        screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("VJ Visualizer — Argile-City")
        clock = pygame.time.Clock()

        try:
            while not self._stop.is_set():
                for evt in pygame.event.get():
                    if evt.type == pygame.QUIT:
                        self._stop.set()
                        break
                    if evt.type == pygame.KEYDOWN:
                        if evt.key == pygame.K_q:
                            self._stop.set()
                            break

                self._draw(screen, width, height)
                clock.tick(30)

        finally:
            self._stop.set()
            pygame.quit()


def parse_args():
    p = argparse.ArgumentParser(description="VJ audio visualizer (file or mic).")
    p.add_argument("--source", type=str, default=None, help="Chemin vers un fichier audio (wav/flac/mp3 si soundfile supporte)")
    p.add_argument("--mic", action="store_true", help="Utiliser le microphone comme source audio")
    p.add_argument("--blocksize", type=int, default=1024, help="Taille des blocs audio pour FFT")
    p.add_argument("--samplerate", type=int, default=None, help="Forcer la fréquence d'échantillonnage")
    return p.parse_args()


def main():
    args = parse_args()
    v = AudioVisualizer(source=args.source, mic=args.mic, blocksize=args.blocksize, samplerate=args.samplerate)
    v.run()


if __name__ == "__main__":
    main()
