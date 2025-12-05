VJ audio visualizer — guide rapide

Dépendances

Installer les dépendances dans votre environnement (recommandé dans un venv) :

```bash
pip install -r requirements.txt
```

Usage

- Visualiser un fichier audio (lecture + visualisation) :

```bash
python3 env_ia/run_vj.py --source /chemin/vers/fichier.wav
```

- Visualiser depuis le microphone (live) :

```bash
python3 env_ia/run_vj.py --mic
```

Options:
- `--blocksize` : taille du bloc FFT (défaut 1024). Plus grand = meilleure résolution fréquentielle mais moins réactif.
- `--samplerate` : forcer la fréquence d'échantillonnage (optionnel).

Notes:
- Sous Linux, si vous utilisez le microphone, vérifiez vos devices avec `python -c "import sounddevice as sd; print(sd.query_devices())"`.
- Le visualiseur est une base simple : tu peux modifier `env_ia/vj/visualizer.py` pour créer d'autres effets (formes, couleurs, réactivité).