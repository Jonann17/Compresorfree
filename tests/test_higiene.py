"""PR1-C: higiene (C5 '%' en Ghostscript, C9 texto de resultado, C10 extensiones
desconocidas), aviso de espacio en disco / ENOSPC y rutas Unicode."""
import collections
import errno
import io
import os
import subprocess
import sys

import pikepdf
import pytest

import app
import compresor_pdf
import compresor_video
import nucleo
from conftest import generar_video, leer, requiere_ffmpeg, temporales

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
CFG = compresor_pdf.NIVELES["media"]
requiere_gs = pytest.mark.skipif(compresor_pdf.buscar_ghostscript() is None,
                                 reason="Ghostscript no instalado")
Uso = collections.namedtuple("Uso", "total used free")


def cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, APP, *args], capture_output=True,
                          text=True, encoding="utf-8", env=env)


def poco_espacio(monkeypatch, libre=1024):
    monkeypatch.setattr("shutil.disk_usage", lambda *a, **k: Uso(10**12, 10**12 - libre, libre))


def contenido(carpeta):
    return sorted(os.listdir(carpeta))


# ---------------------------------------------------------------- C5

def test_c5_comando_gs_escapa_porcentaje_en_salida():
    cmd = compresor_pdf._comando_ghostscript(
        "gs", "/x/in 100%.pdf", "/x/carpeta 50%/informe 100%.pdf", CFG)
    assert "-sOutputFile=/x/carpeta 50%%/informe 100%%.pdf" in cmd


def test_c5_comando_gs_no_toca_la_entrada():
    cmd = compresor_pdf._comando_ghostscript("gs", "/x/in 100%.pdf", "/x/out.pdf", CFG)
    assert cmd[-1] == "/x/in 100%.pdf"
    assert "-sOutputFile=/x/out.pdf" in cmd


@requiere_gs
def test_c5_gs_real_nombre_con_porcentaje(pdf_fotos, tmp_path):
    entrada = str(tmp_path / "informe 100%.pdf")
    os.rename(pdf_fotos, entrada)
    original = leer(entrada)
    salida = compresor_pdf.comprimir(entrada, None, "media")
    assert os.path.basename(salida) == "informe 100%_comprimido_media.pdf"
    with pikepdf.open(salida) as pdf:
        assert len(pdf.pages) == 2
    assert leer(entrada) == original and temporales(tmp_path) == []


@requiere_gs
def test_c5_gs_real_carpeta_con_porcentaje(pdf_fotos, tmp_path):
    carpeta = tmp_path / "carpeta 50%"
    carpeta.mkdir()
    entrada = str(carpeta / "doc.pdf")
    os.rename(pdf_fotos, entrada)
    salida = compresor_pdf.comprimir(entrada, None, "media")
    assert os.path.dirname(salida) == str(carpeta)
    assert os.path.basename(salida) == "doc_comprimido_media.pdf"
    with pikepdf.open(salida) as pdf:
        assert len(pdf.pages) == 2
    assert temporales(carpeta) == [] and contenido(tmp_path) == ["carpeta 50%"]


# ---------------------------------------------------------------- C9

def test_c9_texto_reduccion():
    assert app.texto_resultado(1000, 410) == "Listo (-59%)"


def test_c9_texto_sin_cambio():
    assert app.texto_resultado(1000, 1000) == "Listo (sin cambio)"
    assert app.texto_resultado(1000, 1002) == "Listo (sin cambio)"
    assert app.texto_resultado(1000, 998) == "Listo (sin cambio)"


def test_c9_texto_crecimiento():
    texto = app.texto_resultado(1000, 1120)
    assert texto == "Listo (+12%)" and "--" not in texto


def test_c9_texto_antes_cero():
    assert app.texto_resultado(0, 0) == "Listo"
    assert app.texto_resultado(0, 500) == "Listo"


def test_c9_resumen_aumento(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x" * 1000)
    b.write_bytes(b"x" * 1500)
    texto = compresor_video.resumen(str(a), str(b))
    assert "Aumento:    50.0%" in texto
    assert "Reduccion" not in texto and "-50" not in texto


def test_c9_resumen_reduccion(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x" * 1000)
    b.write_bytes(b"x" * 500)
    texto = compresor_video.resumen(str(a), str(b))
    assert "Reduccion:  50.0%" in texto and "Aumento" not in texto


# ---------------------------------------------------------------- C10

@pytest.mark.parametrize("ruta,tipo", [
    ("a.pdf", "pdf"), ("A.PDF", "pdf"), ("x/y/Informe.Pdf", "pdf"),
    ("a.avi", "video"), ("a.MKV", "video"), ("a.mov", "video"), ("a.mp4", "video"),
    ("foto.jpg", None), ("doc.docx", None), ("sin_extension", None),
    ("archivo.pdf.txt", None), ("pdf", None),
])
def test_c10_tipo_por_extension(ruta, tipo):
    assert app.tipo_por_extension(ruta) == tipo


@requiere_ffmpeg
def test_c10_cli_extension_desconocida_no_frena_el_lote(video, tmp_path):
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(b"\xff\xd8no es un video")
    r = cli(str(foto), video)
    assert r.returncode == 1
    assert "formato no soportado" in r.stderr and "foto.jpg" in r.stderr
    assert os.path.exists(str(tmp_path / "clip_comprimido_media.mp4"))
    assert not os.path.exists(str(tmp_path / "foto_comprimido_media.mp4"))
    assert foto.read_bytes() == b"\xff\xd8no es un video"


def test_c10_cli_estimar_extension_desconocida(tmp_path):
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(b"\xff\xd8no es un video")
    r = cli("--estimar", str(foto))
    assert "formato no soportado" in r.stderr and "(.jpg)" in r.stderr
    assert "~" not in r.stdout


# ---------------------------------------------------------------- Espacio

def test_espacio_comprobar_lanza(tmp_path, monkeypatch):
    poco_espacio(monkeypatch, 1024)
    with pytest.raises(nucleo.EspacioInsuficiente) as e:
        nucleo.comprobar_espacio(str(tmp_path), 10 * 1024 * 1024)
    assert isinstance(e.value, OSError) and "No hay espacio suficiente" in str(e.value)


def test_espacio_comprobar_suficiente_no_lanza(tmp_path, monkeypatch):
    poco_espacio(monkeypatch, 2 * 1024 * 1024)
    nucleo.comprobar_espacio(str(tmp_path), 1024 * 1024)
    nucleo.comprobar_espacio(str(tmp_path), 2 * 1024 * 1024)  # justo


def test_espacio_margen_fijo():
    assert nucleo.MARGEN_ESPACIO == 50 * 1024 * 1024


@requiere_ffmpeg
def test_espacio_video_comprimir_falla_antes_de_crear_nada(video, tmp_path, monkeypatch):
    antes = contenido(tmp_path)
    poco_espacio(monkeypatch, 1024)
    salida = str(tmp_path / "out.mp4")
    with pytest.raises(nucleo.EspacioInsuficiente):
        compresor_video.comprimir(video, salida, "media")
    monkeypatch.undo()
    assert not os.path.exists(salida) and temporales(tmp_path) == []
    assert contenido(tmp_path) == antes


def test_espacio_pdf_comprimir_falla_antes_de_crear_nada(pdf_fotos, tmp_path, monkeypatch):
    antes = contenido(tmp_path)
    poco_espacio(monkeypatch, 1024)
    salida = str(tmp_path / "out.pdf")
    with pytest.raises(nucleo.EspacioInsuficiente):
        compresor_pdf.comprimir(pdf_fotos, salida, "media")
    monkeypatch.undo()
    assert not os.path.exists(salida) and temporales(tmp_path) == []
    assert contenido(tmp_path) == antes


def test_espacio_pdf_exige_tamano_entrada_mas_margen(pdf_fotos, tmp_path, monkeypatch):
    """Quedan 'margen + tamano - 1' bytes: falta justo uno."""
    libre = os.path.getsize(pdf_fotos) + nucleo.MARGEN_ESPACIO - 1
    poco_espacio(monkeypatch, libre)
    with pytest.raises(nucleo.EspacioInsuficiente):
        compresor_pdf.comprimir(pdf_fotos, str(tmp_path / "out.pdf"), "media")


@requiere_ffmpeg
def test_espacio_enospc_de_ffmpeg_se_traduce(video, tmp_path, monkeypatch):
    real = subprocess.Popen

    class PopenFalso:
        """Solo la codificacion (la llamada con -progress) es falsa."""
        def __new__(cls, cmd, **kw):
            if "-progress" not in cmd:
                return real(cmd, **kw)
            return super().__new__(cls)

        def __init__(self, cmd, **kw):
            with open(cmd[-1], "wb") as f:
                f.write(b"\x00" * 4096)
            self.stdout = io.StringIO("progress=continue\n")
            self.stderr = io.StringIO("av_interleaved_write_frame(): No space left on device\n")
            self.returncode = 1

        def wait(self, *a, **k):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", PopenFalso)
    salida = str(tmp_path / "resultado.mp4")
    with pytest.raises(nucleo.EspacioInsuficiente):
        compresor_video.comprimir(video, salida, "media")
    monkeypatch.undo()
    assert not os.path.exists(salida) and temporales(tmp_path) == []


def test_espacio_enospc_en_pdf_se_traduce(pdf_fotos, tmp_path, monkeypatch):
    monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: None)

    def falla(entrada, tmp, cfg, progreso, cancelar):
        with open(tmp, "wb") as f:
            f.write(b"parcial")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(compresor_pdf, "_comprimir_pikepdf", falla)
    salida = str(tmp_path / "out.pdf")
    with pytest.raises(nucleo.EspacioInsuficiente):
        compresor_pdf.comprimir(pdf_fotos, salida, "media")
    assert not os.path.exists(salida) and temporales(tmp_path) == []


# ---------------------------------------------------------------- Unicode

@requiere_ffmpeg
def test_unicode_video_api(tmp_path):
    origen = tmp_path / "José"
    origen.mkdir()
    entrada = generar_video(str(origen / "vídeo ñ.avi"))
    original = leer(entrada)
    destino = tmp_path / "salida ü"
    destino.mkdir()
    salida = compresor_video.comprimir(entrada, str(destino / "vídeo ñ.mp4"), "alta")
    assert os.path.basename(salida) == "vídeo ñ.mp4" and os.path.getsize(salida) > 0
    assert leer(entrada) == original
    assert temporales(destino) == [] and temporales(origen) == []


def test_unicode_pdf_api(pdf_fotos, tmp_path):
    origen = tmp_path / "José"
    origen.mkdir()
    entrada = str(origen / "informe ñ 100%.pdf")
    os.rename(pdf_fotos, entrada)
    original = leer(entrada)
    destino = tmp_path / "salida ü"
    destino.mkdir()
    salida = compresor_pdf.comprimir(entrada, str(destino / "informe ñ 100%.pdf"), "alta")
    assert os.path.basename(salida) == "informe ñ 100%.pdf"
    with pikepdf.open(salida) as pdf:
        assert len(pdf.pages) == 2
    assert leer(entrada) == original
    assert temporales(destino) == [] and temporales(origen) == []


@requiere_ffmpeg
def test_unicode_video_cli(tmp_path):
    origen = tmp_path / "José"
    origen.mkdir()
    entrada = generar_video(str(origen / "vídeo ñ.avi"))
    original = leer(entrada)
    destino = tmp_path / "salida ü"
    r = cli(entrada, "-d", str(destino))
    assert r.returncode == 0, r.stderr
    assert os.listdir(destino) == ["vídeo ñ_comprimido_media.mp4"]
    assert leer(entrada) == original and temporales(destino) == []


def test_unicode_pdf_cli(pdf_fotos, tmp_path):
    origen = tmp_path / "José"
    origen.mkdir()
    entrada = str(origen / "informe ñ 100%.pdf")
    os.rename(pdf_fotos, entrada)
    original = leer(entrada)
    destino = tmp_path / "salida ü"
    r = cli(entrada, "-d", str(destino))
    assert r.returncode == 0, r.stderr
    assert os.listdir(destino) == ["informe ñ 100%_comprimido_media.pdf"]
    assert leer(entrada) == original and temporales(destino) == []
