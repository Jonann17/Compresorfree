"""Genera la aplicacion de escritorio con PyInstaller.

    python compilar.py

- Windows: dist/Compresorfree/Compresorfree.exe
- macOS:   dist/Compresorfree.app
FFmpeg se incluye dentro de la app (paquete imageio-ffmpeg).
"""

import importlib.util

import PyInstaller.__main__

opcionales = (["--collect-all", "tkinterdnd2"]
              if importlib.util.find_spec("tkinterdnd2") else [])

PyInstaller.__main__.run([
    "app.py",
    "--name", "Compresorfree",
    "--windowed",            # sin ventana de consola
    "--noconfirm",
    "--clean",
    "--collect-all", "imageio_ffmpeg",   # incluye el binario de FFmpeg
    "--collect-all", "pikepdf",
    "--osx-bundle-identifier", "com.compresorfree.app",
    *opcionales,             # arrastrar y soltar (opcional)
])
