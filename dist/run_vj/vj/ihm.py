"""IHM de sélection des paramètres audio pour le visualizer VJ.

Affiche une fenêtre pour choisir la source (fichier ou micro), le périphérique,
le blocksize, la fréquence d'échantillonnage, etc. Retourne un dict de config.
"""
import os
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog, simpledialog, messagebox, colorchooser
except ImportError:
    tk = None

def select_config(devices, default_blocksize=1024, default_samplerate=None):
    """Affiche une IHM tkinter pour choisir les paramètres. Retourne un dict."""
    if tk is None:
        raise RuntimeError("tkinter requis pour l'IHM de configuration")

    root = tk.Tk()
    root.title("Configuration VJ Visualizer (Entrée Live)")
    # Slightly larger so all controls are visible on smaller screens
    root.geometry("460x340")
    root.resizable(False, False)
    root.lift()
    root.focus_force()

    result = {
        'device': None,
        'blocksize': default_blocksize,
        'samplerate': default_samplerate,
        'primary_color': (0, 255, 0),
        'secondary_color': (255, 0, 0),
        'bg_color': (0, 0, 0),
        'glitch_enabled': True,
    }

    # Périphérique
    tk.Label(root, text="Périphérique d'entrée audio :").pack(anchor='w', padx=10, pady=(18,0))
    dev_var = tk.StringVar(value='default')
    dev_names = [f"{i}: {d['name']} (in={d['max_input_channels']}, out={d['max_output_channels']})" for i, d in enumerate(devices)]
    dev_menu = tk.OptionMenu(root, dev_var, 'default', *dev_names)
    dev_menu.pack(anchor='w', padx=10)


    # Blocksize
    tk.Label(root, text="Blocksize (FFT):").pack(anchor='w', padx=10, pady=(10,0))
    block_var = tk.StringVar(value=str(default_blocksize))
    tk.Entry(root, textvariable=block_var, width=8).pack(anchor='w', padx=10)

    # Samplerate
    tk.Label(root, text="Samplerate (Hz, optionnel):").pack(anchor='w', padx=10, pady=(10,0))
    sr_var = tk.StringVar(value='' if default_samplerate is None else str(default_samplerate))
    tk.Entry(root, textvariable=sr_var, width=10).pack(anchor='w', padx=10)

    # Color pickers: primary, secondary, background
    tk.Label(root, text="Couleurs dominantes (primary / secondary / background):").pack(anchor='w', padx=10, pady=(12,0))
    # helper to create a small button showing color and opening chooser
    def make_color_button(init_color):
        b = tk.Button(root, relief='raised', width=4, height=1)
        b._rgb = init_color
        b.configure(bg='#%02x%02x%02x' % init_color)
        def pick():
            col = colorchooser.askcolor(color=b._rgb, title='Choisir une couleur')
            if col and col[0]:
                r,g,bg = int(col[0][0]), int(col[0][1]), int(col[0][2])
                b._rgb = (r, g, bg)
                b.configure(bg='#%02x%02x%02x' % b._rgb)
        b.configure(command=pick)
        return b

    frame_cols = tk.Frame(root)
    frame_cols.pack(anchor='w', padx=10, pady=(8,0), fill='x')
    btn_primary = make_color_button(result['primary_color'])
    btn_primary.pack(side='left')
    tk.Label(frame_cols, text='Primary').pack(side='left', padx=(6,12))
    btn_secondary = make_color_button(result['secondary_color'])
    btn_secondary.pack(side='left')
    tk.Label(frame_cols, text='Secondary').pack(side='left', padx=(6,12))
    btn_bg = make_color_button(result['bg_color'])
    btn_bg.pack(side='left')
    tk.Label(frame_cols, text='Background').pack(side='left', padx=(6,6))

    # Glitch/random shapes toggle
    glitch_var = tk.BooleanVar(value=True)
    tk.Checkbutton(root, text='Activer effets glitch aléatoires', variable=glitch_var).pack(anchor='w', padx=10, pady=(10,0))

    # Validation
    def valider():
        dev = dev_var.get()
        if dev == 'default':
            result['device'] = None
        else:
            try:
                idx = int(dev.split(':')[0])
                result['device'] = idx
            except Exception:
                result['device'] = None
        try:
            result['blocksize'] = int(block_var.get())
        except Exception:
            result['blocksize'] = default_blocksize
        try:
            sr = sr_var.get().strip()
            result['samplerate'] = int(sr) if sr else None
        except Exception:
            result['samplerate'] = default_samplerate
        # read colors from buttons
        result['primary_color'] = getattr(btn_primary, '_rgb', result['primary_color'])
        result['secondary_color'] = getattr(btn_secondary, '_rgb', result['secondary_color'])
        result['bg_color'] = getattr(btn_bg, '_rgb', result['bg_color'])
        result['glitch_enabled'] = bool(glitch_var.get())
        root.destroy()

    tk.Button(root, text="Valider", command=valider, bg='#2ecc40', fg='white', height=2, width=20).pack(pady=18)
    root.mainloop()
    return result
