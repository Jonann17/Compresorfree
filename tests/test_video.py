"""Integracion con FFmpeg real (videos sinteticos generados en el test)."""
import io
import os
import subprocess
import sys
import threading
import time

import pytest

import compresor_video
from conftest import FFMPEG, RAIZ, generar_video, leer, requiere_ffmpeg, temporales

pytestmark = requiere_ffmpeg

try:
    import nucleo
    DestinoExistente = nucleo.DestinoExistente
except ImportError:  # permite correr las regresiones contra main
    DestinoExistente = FileExistsError


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(RAIZ, "app.py"), *args],
                          capture_output=True, text=True)


def test_c1_lote_no_destruye_otra_entrada(tmp_path):
    """C1: con a.avi y a_comprimido_media.mp4 en el lote, la segunda no se toca."""
    a = generar_video(str(tmp_path / "a.avi"))
    b = str(tmp_path / "a_comprimido_media.mp4")
    generar_video(b)
    original_b = leer(b)
    cli(a, b, "-n", "media")
    assert leer(b) == original_b


def test_c2_destino_existente_no_se_pisa(video, tmp_path):
    """C2: un archivo que ya existe con el nombre de salida queda intacto."""
    destino = compresor_video.ruta_salida_por_defecto(video, "media")
    with open(destino, "wb") as f:
        f.write(b"dato importante")
    with pytest.raises(DestinoExistente):
        compresor_video.comprimir(video, destino, "media")
    assert leer(destino) == b"dato importante"


def test_c2_cli_crea_nombre_unico(video, tmp_path):
    destino = compresor_video.ruta_salida_por_defecto(video, "media")
    with open(destino, "wb") as f:
        f.write(b"dato importante")
    r = cli(video, "-n", "media")
    assert r.returncode == 0, r.stderr
    assert leer(destino) == b"dato importante"
    assert os.path.exists(destino.replace(".mp4", " (2).mp4"))


def test_cli_o_existente_es_error(video, tmp_path):
    destino = str(tmp_path / "ya.mp4")
    with open(destino, "wb") as f:
        f.write(b"no tocar")
    r = cli(video, "-o", destino)
    assert r.returncode == 1 and "ya existe" in r.stderr
    assert leer(destino) == b"no tocar"


def test_c4_fallo_de_ffmpeg_no_deja_salida(video, tmp_path, monkeypatch):
    """C4: si FFmpeg escribe algo y falla, no queda archivo final ni temporal."""
    real = subprocess.Popen

    class PopenFalso:
        """Solo la codificacion (la llamada con -progress) es falsa."""
        def __new__(cls, cmd, **kw):
            if "-progress" not in cmd:
                return real(cmd, **kw)
            return super().__new__(cls)

        def __init__(self, cmd, **kw):
            with open(cmd[-1], "wb") as f:
                f.write(b"\x00" * 4096)  # salida parcial
            self.stdout = io.StringIO("progress=continue\n")
            self.stderr = io.StringIO("error simulado\n")
            self.returncode = 1

        def wait(self, *a, **k):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", PopenFalso)
    salida = str(tmp_path / "resultado.mp4")
    with pytest.raises(RuntimeError):
        compresor_video.comprimir(video, salida, "media")
    monkeypatch.undo()
    assert not os.path.exists(salida)
    assert temporales(tmp_path) == []


def test_cancelar_no_deja_salida(video, tmp_path):
    cancelar = threading.Event()
    cancelar.set()
    salida = str(tmp_path / "cancelado.mp4")
    with pytest.raises(RuntimeError):
        compresor_video.comprimir(video, salida, "media", cancelar=cancelar)
    assert not os.path.exists(salida) and temporales(tmp_path) == []


def test_resultado_valido_h264_aac_dimensiones_pares(tmp_path):
    entrada = generar_video(str(tmp_path / "impar.avi"), tamano="321x241")
    salida = compresor_video.comprimir(entrada, None, "baja")
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", salida],
                          capture_output=True, text=True).stderr
    assert "h264" in info and "aac" in info and "320x240" in info
    decod = subprocess.run([FFMPEG, "-v", "error", "-i", salida, "-f", "null", "-"],
                           capture_output=True, text=True)
    assert decod.returncode == 0 and decod.stderr == ""
    assert temporales(tmp_path) == []


def test_validacion_rechaza_video_truncado(video, tmp_path):
    salida = compresor_video.comprimir(video, str(tmp_path / "ok.mp4"), "media")
    truncado = str(tmp_path / "truncado.mp4")
    with open(truncado, "wb") as f:
        f.write(leer(salida)[: os.path.getsize(salida) // 3])
    with pytest.raises(RuntimeError):
        compresor_video.validar_salida(FFMPEG, truncado, 2.0)


def test_cancelar_a_mitad_de_la_codificacion(tmp_path):
    """Cancelar con la codificacion en marcha: RuntimeError rapido, sin salida ni temporales."""
    import procesos
    entrada = generar_video(str(tmp_path / "largo.avi"), 20, "640x480")
    salida = str(tmp_path / "largo_out.mp4")
    cancelar = threading.Event()
    marca = []

    def progreso(p):
        if p > 0 and not cancelar.is_set():
            marca.append(time.monotonic())
            cancelar.set()

    with pytest.raises(RuntimeError):
        compresor_video.comprimir(entrada, salida, "media", progreso, cancelar)
    assert marca, "la codificacion no llego a informar progreso"
    assert time.monotonic() - marca[0] < 2
    assert not os.path.exists(salida)
    assert temporales(tmp_path) == []
    assert procesos.procesos_vivos() == []


def test_estimar_cancelado_devuelve_none_rapido(tmp_path):
    import procesos
    entrada = generar_video(str(tmp_path / "largo.avi"), 20, "640x480")
    cancelar = threading.Event()
    marca = []

    def disparar():
        marca.append(time.monotonic())
        cancelar.set()

    timer = threading.Timer(0.2, disparar)
    timer.start()
    assert compresor_video.estimar(entrada, "media", cancelar) is None
    fin = time.monotonic()
    timer.join()
    assert marca and fin - marca[0] < 2
    assert procesos.procesos_vivos() == []
