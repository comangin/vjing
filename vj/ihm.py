"""IHM de sélection des paramètres audio pour le visualizer VJ.

Affiche une fenêtre pour choisir la source (fichier ou micro), le périphérique,
le blocksize, la fréquence d'échantillonnage, etc. Retourne un dict de config.
"""
import os
from typing import Optional
import queue
import threading
import math
import time

try:
    import tkinter as tk
    from tkinter import filedialog, simpledialog, messagebox, colorchooser
except ImportError:
    tk = None

try:
    import sounddevice as sd
except Exception:
    sd = None

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

    # Périphérique (affiche par défaut les périphériques de sortie)
    tk.Label(root, text="Périphérique de sortie audio :").pack(anchor='w', padx=10, pady=(18,0))
    dev_var = tk.StringVar(value='default')
    # devices may be a filtered list; use the original PortAudio index if present
    dev_names = []
    for i, d in enumerate(devices):
        pa_idx = d.get('_pa_index', i)
        dev_names.append(f"{pa_idx}: {d['name']} (in={d['max_input_channels']}, out={d['max_output_channels']})")
    dev_menu = tk.OptionMenu(root, dev_var, 'default', *dev_names)
    dev_menu.pack(anchor='w', padx=10)
    
    # Small live level meter (shows input level for the selected device)
    meter_frame = tk.Frame(root)
    meter_frame.pack(anchor='w', padx=10, pady=(8,0))
    tk.Label(meter_frame, text='Niveau (entrée):').pack(side='left')
    meter_canvas = tk.Canvas(meter_frame, width=220, height=20, bg='#222222', highlightthickness=0)
    meter_canvas.pack(side='left', padx=(8,0))
    meter_bar = meter_canvas.create_rectangle(0, 0, 0, 20, fill='#2ecc40', width=0)
    meter_text = tk.Label(meter_frame, text='—', width=6)
    meter_text.pack(side='left', padx=(8,0))

    # meter internals
    meter_q = queue.Queue()
    meter_stream = {'obj': None}
    meter_after_id = {'id': None}
    meter_sim = {'thread': None, 'running': False}

    def audio_callback(indata, frames, time_info, status):
        # compute RMS of first channel, push to queue
        try:
            # prefer numpy if available for speed
            import numpy as _np
            data = _np.asarray(indata[:, 0], dtype=_np.float32)
            rms = float(_np.sqrt((_np.square(data)).mean()))
        except Exception:
            try:
                # fallback: Python loop
                arr = [float(x[0]) for x in indata]
                s = 0.0
                for v in arr:
                    s += v * v
                rms = math.sqrt(s / max(1, len(arr)))
            except Exception:
                return
        try:
            # keep only the latest value
            while not meter_q.empty():
                meter_q.get_nowait()
            meter_q.put_nowait(rms)
        except Exception:
            pass

    def start_meter_for_device(dev_idx):
        # stop existing
        stop_meter()
        if sd is None:
            meter_text.config(text='no sounddevice')
            return
        try:
            device = None if dev_idx is None else int(dev_idx)
            # choose 1 channel for meter; let sounddevice pick samplerate
            stream = sd.InputStream(device=device, channels=1, callback=audio_callback)
            stream.start()
            meter_stream['obj'] = stream
            meter_text.config(text='0.00')
        except Exception:
            meter_text.config(text='err')
            meter_stream['obj'] = None

    def start_simulator():
        # simple simulator to feed the meter when sounddevice is not available
        if meter_sim['running']:
            return
        meter_sim['running'] = True

        def run_sim():
            import random
            while meter_sim['running']:
                # produce a varying RMS-like value
                v = random.random() * 0.12
                try:
                    while not meter_q.empty():
                        meter_q.get_nowait()
                    meter_q.put_nowait(v)
                except Exception:
                    pass
                time.sleep(0.06)

        t = threading.Thread(target=run_sim, daemon=True)
        meter_sim['thread'] = t
        t.start()

    def stop_simulator():
        meter_sim['running'] = False
        t = meter_sim.get('thread')
        if t is not None and t.is_alive():
            try:
                t.join(timeout=0.1)
            except Exception:
                pass
        meter_sim['thread'] = None

    def stop_meter():
        s = meter_stream.get('obj')
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        meter_stream['obj'] = None
        # cancel after callback if scheduled
        aid = meter_after_id.get('id')
        if aid is not None:
            try:
                root.after_cancel(aid)
            except Exception:
                pass
            meter_after_id['id'] = None

    def update_meter():
        # poll queue for latest rms
        val = None
        try:
            while True:
                val = meter_q.get_nowait()
        except Exception:
            pass
        if val is not None:
            # scale: assume val in [0..1], map to canvas width
            w = int(min(1.0, val / 0.1) * 220)  # 0.1 RMS maps to full
            meter_canvas.coords(meter_bar, 0, 0, w, 20)
            meter_text.config(text=f"{val:.3f}")
        # schedule next poll
        meter_after_id['id'] = root.after(60, update_meter)

    # when device selection changes, restart meter
    def on_device_change(*args):
        sel = dev_var.get()
        if sel == 'default':
            # default -> let system choose (no specific device)
            stop_meter()
            meter_text.config(text='—')
            return
        try:
            pa_idx = int(sel.split(':')[0])
        except Exception:
            pa_idx = None
        # find the selected device entry in the provided devices list
        sel_dev = None
        for d in devices:
            if d.get('_pa_index', None) == pa_idx:
                sel_dev = d
                break
        # if the selected output device also exposes input channels (monitor/loopback), start meter
        if sel_dev is not None and sel_dev.get('max_input_channels', 0) > 0:
            start_meter_for_device(pa_idx)
        else:
            stop_meter()
            meter_text.config(text='no capture')

    dev_var.trace_add('write', on_device_change)
    # start meter for default selection
    on_device_change()
    # start simulator if no sounddevice available (allows visual testing)
    if sd is None:
        start_simulator()
    # start the periodic meter update loop
    update_meter()


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
            except Exception:
                idx = None
            # Map selected output device to an input capture device when possible.
            # If the selected output exposes input channels (monitor), use it.
            # Otherwise try to find a "monitor" device matching the output name.
            chosen_idx = idx
            try:
                if idx is not None:
                    # find selected device entry from provided list
                    sel_dev = None
                    for d in devices:
                        if d.get('_pa_index', None) == idx:
                            sel_dev = d
                            break
                    # if selected output has input channels, use it
                    if sel_dev is not None and sel_dev.get('max_input_channels', 0) > 0:
                        chosen_idx = idx
                    else:
                        # try to find monitor/input device by name
                        if sd is not None:
                            all_devs = sd.query_devices()
                            name_lower = (sel_dev.get('name','') if sel_dev else '').lower()
                            monitor_idx = None
                            # heuristics: look for devices that contain 'monitor' and the output name
                            for j, dd in enumerate(all_devs):
                                nm = (dd.get('name') or '').lower()
                                if 'monitor' in nm and (name_lower in nm or name_lower.split()[0] in nm):
                                    monitor_idx = j
                                    break
                            # fallback: any device that is an input and whose name contains the output name
                            if monitor_idx is None:
                                for j, dd in enumerate(all_devs):
                                    nm = (dd.get('name') or '').lower()
                                    if dd.get('max_input_channels', 0) > 0 and name_lower in nm:
                                        monitor_idx = j
                                        break
                            if monitor_idx is not None:
                                chosen_idx = monitor_idx
            except Exception:
                # best-effort mapping: if anything fails, keep chosen_idx as idx
                chosen_idx = idx
            result['device'] = chosen_idx
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
        # stop meter stream before closing
        try:
            stop_meter()
        except Exception:
            pass
        root.destroy()

    tk.Button(root, text="Valider", command=valider, bg='#2ecc40', fg='white', height=2, width=20).pack(pady=18)
    root.mainloop()
    return result
