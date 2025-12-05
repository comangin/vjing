#!/usr/bin/env python3
"""Runner pour le visualiseur VJ."""
import argparse
try:
    # preferred imports when running from project root or installed package
    from vj.config import format_devices, Config
    from vj.core import AudioAnalyzer
    from vj.gui import VisualGUI
except ModuleNotFoundError:
    # fallback when running the runner directly from the folder that contains `vj/`
    from vj.config import format_devices, Config
    from vj.core import AudioAnalyzer
    from vj.gui import VisualGUI


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--blocksize", type=int, default=1024)
    p.add_argument("--samplerate", type=int, default=None)
    p.add_argument("--device", type=int, default=None, help="Index PortAudio du périphérique à utiliser (voir --list-devices)")
    p.add_argument("--list-devices", action="store_true", help="Lister les périphériques audio (PortAudio) et quitter")
    return p.parse_args()


def main():
    args = parse_args()
    if getattr(args, 'list_devices', False):
        try:
            for line in format_devices():
                print(line)
            return
        except Exception as e:
            print('Impossible de lister les périphériques audio via PortAudio:', e)
            print('\nSur Linux installez les bibliothèques système puis réessayez:')
            print('  Debian/Ubuntu: sudo apt install libportaudio2 portaudio19-dev libsndfile1')
            print('  Fedora: sudo dnf install portaudio portaudio-devel libsndfile')
            return
    # IHM de sélection si demandé (aucun argument passé)
    # Correction : l'IHM ne doit être appelée que si AUCUN argument pertinent n'est fourni
    has_arg = any([
        args.device is not None,
        args.blocksize != 1024,
        args.samplerate is not None
    ])
    if not has_arg:
        try:
            from vj.ihm import select_config
            from vj.config import list_devices
            user_cfg = select_config(list_devices())
            cfg = Config(**user_cfg)
        except Exception as e:
            print("Erreur IHM de configuration:", e)
            return
    else:
        cfg = Config(device=args.device, blocksize=args.blocksize, samplerate=args.samplerate)

    analyzer = AudioAnalyzer(blocksize=cfg.blocksize, samplerate=cfg.samplerate, device=cfg.device)

    try:
        analyzer.start()
    except Exception as e:
        print("Impossible d'initialiser la capture audio:", e)
        return

    # pass color choices from configuration into the GUI
    gui = VisualGUI(
        analyzer,
        title="VJ Visualizer — Argile-City",
        primary_color=cfg.primary_color,
        secondary_color=cfg.secondary_color,
        bg_color=cfg.bg_color,
        glitch_enabled=cfg.glitch_enabled,
    )
    try:
        gui.run()
    finally:
        analyzer.stop()


if __name__ == '__main__':
    main()
