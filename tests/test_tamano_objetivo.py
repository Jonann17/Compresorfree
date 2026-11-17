"""Compresion de video a un tamano objetivo (FFmpeg real, videos sinteticos)."""
import glob
import os
import subprocess
import sys
import tempfile
import threading

import pytest

import compresor_video
import procesos
from conftest import RAIZ, generar_video, requiere_ffmpeg, temporales

pytestmark = requiere_ffmpeg


@pytest.fixture
def clip(tmp_path):
    return generar_video(str(tmp_path / "clip.avi"), segundos=10, tamano="640x480")


def pasadas_en_temp():
    return glob.glob(os.path.join(tempfile.gettempdir(), "compresorfree_pasadas_*"))


def sin_restos(carpeta):
    assert pasadas_en_temp() == []
    assert temporales(carpeta) == []
    assert not [n for n in os.listdir(carpeta) if "log" in n or "mbtree" in n]


def test_resultado_dentro_del_objetivo(clip, tmp_path):
    salida = str(tmp_path / "out.mp4")
    objetivo = 0.4
    out = compresor_video.comprimir(clip, salida, "media", objetivo_mb=objetivo)
    assert os.path.getsize(out) <= objetivo * 1024 * 1024 * 1.03
    sin_restos(str(tmp_path))


def test_progreso_en_dos_mitades(clip, tmp_path):
    vistos = []
    compresor_video.comprimir(clip, str(tmp_path / "o.mp4"), "media",
                              progreso=vistos.append, objetivo_mb=0.4)
    assert vistos == sorted(vistos) or max(vistos) <= 100
    assert max(v for v in vistos if v < 100) > 50  # la pasada 2 llega a la segunda mitad


def test_estimar_devuelve_objetivo(clip):
    assert compresor_video.estimar(clip, "media", objetivo_mb=2) == 2 * 1024 * 1024


def test_objetivo_imposible(clip, tmp_path):
    salida = str(tmp_path / "out.mp4")
    with pytest.raises(RuntimeError, match="demasiado pequeno para un video de 10 s"):
        compresor_video.comprimir(clip, salida, "media", objetivo_mb=0.01)
    assert not os.path.exists(salida)
    assert sorted(os.listdir(tmp_path)) == ["clip.avi"]
    assert pasadas_en_temp() == []


@pytest.mark.parametrize("pasada", [1, 2])
def test_cancelar_en_cada_pasada(clip, tmp_path, monkeypatch, pasada):
    cancelar = threading.Event()
    original = procesos.ejecutar
    llamadas = []

    def ejecutar(cmd, cancelar_=None, **kw):
        if "-passlogfile" in cmd:
            llamadas.append(cmd[cmd.index("-pass") + 1])
            if len(llamadas) == pasada:
                # cancela poco despues de arrancar la pasada elegida
                threading.Timer(0.05, cancelar.set).start()
        return original(cmd, cancelar_, **kw)

    monkeypatch.setattr(procesos, "ejecutar", ejecutar)
    salida = str(tmp_path / "out.mp4")
    with pytest.raises(procesos.Cancelado):
        compresor_video.comprimir(clip, salida, "alta", cancelar=cancelar, objetivo_mb=0.4)
    assert llamadas[-1] == str(pasada)
    assert not os.path.exists(salida)
    sin_restos(str(tmp_path))


def test_cli_max_mb(clip, tmp_path):
    salida = str(tmp_path / "cli.mp4")
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "app.py"), clip, "--max-mb", "0.4",
                        "-o", salida], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.path.getsize(salida) <= 0.4 * 1024 * 1024 * 1.03
    sin_restos(str(tmp_path))
    r = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "app.py"), clip, "--max-mb", "0.001",
         "-o", str(tmp_path / "x.mp4")], capture_output=True, text=True)
    assert r.returncode == 1 and "demasiado pequeno" in r.stderr
    assert not os.path.exists(tmp_path / "x.mp4")
