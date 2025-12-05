"""Gestion de la configuration audio (sélection de périphériques).

Fournit des helpers pour lister les périphériques PortAudio et un petit
dataclass `Config` pour transporter les options courantes.
"""
from typing import Optional, List, Dict

_sd_import_err = None
try:
    import sounddevice as sd
except Exception as e:
    sd = None
    _sd_import_err = e


class Config:
    def __init__(self, device: Optional[int] = None, blocksize: int = 1024,
                 samplerate: Optional[int] = None,
                 primary_color: Optional[tuple] = None,
                 secondary_color: Optional[tuple] = None,
                 bg_color: Optional[tuple] = None,
                 glitch_enabled: bool = True):
        self.device = device
        self.blocksize = blocksize
        self.samplerate = samplerate
        # color controls: RGB tuples, defaults will be handled by the GUI
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.bg_color = bg_color
        self.glitch_enabled = glitch_enabled


def list_devices() -> List[Dict]:
    """Retourne la liste des périphériques audio (ou lève si sd non dispo).

    Chaque entrée est un dict tel que renvoyé par `sounddevice.query_devices()`.
    """
    if sd is None:
        raise RuntimeError(f"sounddevice non disponible: {_sd_import_err}")
    return sd.query_devices()


def format_devices() -> List[str]:
    """Helper: liste des noms + indices formatés pour affichage."""
    devs = list_devices()
    lines = []
    for i, d in enumerate(devs):
        lines.append(f"{i}: {d['name']}  in={d['max_input_channels']} out={d['max_output_channels']}")
    return lines
