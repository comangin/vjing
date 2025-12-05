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


def list_devices(outputs_only: bool = True) -> List[Dict]:
    """Retourne la liste des périphériques audio.

    Par défaut (outputs_only=True) on renvoie les périphériques qui fournissent
    des canaux de sortie (max_output_channels > 0) afin de permettre la
    sélection des périphériques de lecture. Passez outputs_only=False pour
    obtenir la liste complète.
    """
    if sd is None:
        raise RuntimeError(f"sounddevice non disponible: {_sd_import_err}")
    devs = sd.query_devices()
    if not outputs_only:
        # annotate with their PortAudio index for callers that expect it
        for i, d in enumerate(devs):
            d['_pa_index'] = i
        return devs
    out = []
    for i, d in enumerate(devs):
        if d.get('max_output_channels', 0) > 0:
            # keep the original PortAudio index so UI can map back
            d['_pa_index'] = i
            out.append(d)
    return out


def format_devices(outputs_only: bool = True) -> List[str]:
    """Helper: liste des noms + indices formatés pour affichage.

    Par défaut, n'affiche que les périphériques de sortie. Passer
    `outputs_only=False` pour lister tous les périphériques.
    """
    devs = list_devices(outputs_only=outputs_only)
    lines = []
    for i, d in enumerate(devs):
        pa_idx = d.get('_pa_index', i)
        lines.append(f"{pa_idx}: {d['name']}  in={d['max_input_channels']} out={d['max_output_channels']}")
    return lines
