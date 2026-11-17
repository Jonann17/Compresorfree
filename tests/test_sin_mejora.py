"""Politica "sin mejora": no se publica un resultado que no pesa menos."""
import os
import subprocess
import sys

import pikepdf
import pytest

import compresor_pdf
import compresor_video
import nucleo
from conftest import FFMPEG, RAIZ, requiere_ffmpeg, temporales


def _video(ruta, codec_args):
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", *codec_args, ruta],
        check=True, capture_output=True)
    return ruta


def _h264_pobre(tmp_path):
    return _video(str(tmp_path / "pobre.mp4"),
                  ["-c:v", "libx264", "-crf", "51", "-preset", "ultrafast",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "16k"])


def _mpeg4_pobre(tmp_path):
    return _video(str(tmp_path / "pobre.avi"),
                  ["-c:v", "mpeg4", "-q:v", "31", "-c:a", "aac", "-b:a", "16k"])


def _pdf_vacio(tmp_path):
    pdf = pikepdf.new()
    pdf.add_blank_page()
    ruta = str(tmp_path / "vacio.pdf")
    pdf.save(ruta)
    return ruta


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(RAIZ, "app.py"), *args],
                          capture_output=True, text=True)


@requiere_ffmpeg
def test_video_compatible_que_crece_es_sin_mejora(tmp_path):
    entrada = _h264_pobre(tmp_path)
    destino = str(tmp_path / "salida.mp4")
    with pytest.raises(nucleo.SinMejora):
        compresor_video.comprimir(entrada, destino, "baja")
    assert sorted(os.listdir(tmp_path)) == ["pobre.mp4"]
    assert not os.path.exists(destino) and temporales(tmp_path) == []


@requiere_ffmpeg
def test_video_no_compatible_que_crece_se_publica(tmp_path):
    entrada = _mpeg4_pobre(tmp_path)
    salida = compresor_video.comprimir(entrada, None, "baja")
    assert os.path.exists(salida)
    assert os.path.getsize(salida) > os.path.getsize(entrada)


@requiere_ffmpeg
def test_deteccion_de_compatibilidad(tmp_path):
    ff = compresor_video.buscar_ffmpeg()
    for ruta, esperado in ((_h264_pobre(tmp_path), True), (_mpeg4_pobre(tmp_path), False)):
        info = compresor_video._info_ffmpeg(ff, ruta)
        assert compresor_video.es_compatible(ruta, info) is esperado


def test_sin_mejora_es_archivo_omitido():
    assert issubclass(nucleo.SinMejora, nucleo.ArchivoOmitido)


def test_pdf_que_no_se_reduce_es_sin_mejora(tmp_path, monkeypatch):
    monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: None)
    entrada = _pdf_vacio(tmp_path)
    with pytest.raises(nucleo.SinMejora):
        compresor_pdf.comprimir(entrada, None, "alta")
    assert sorted(os.listdir(tmp_path)) == ["vacio.pdf"]


def test_cli_sin_mejora_devuelve_cero(tmp_path):
    entrada = _pdf_vacio(tmp_path)
    r = cli(entrada, "-n", "alta")
    assert r.returncode == 0, r.stderr
    assert "No se redujo" in r.stdout
    assert sorted(os.listdir(tmp_path)) == ["vacio.pdf"]


def _lineas(nombre):
    with open(os.path.join(RAIZ, nombre)) as f:
        return [li.strip() for li in f if li.strip() and not li.startswith("#")]


def test_lock_existen_y_fijan_requirements():
    for n in ("requirements.lock", "requirements-build.lock", "requirements-dev.lock"):
        assert _lineas(n), n
    fijados = {li.split("==")[0].lower().replace("_", "-")
               for li in _lineas("requirements.lock")}
    for req in _lineas("requirements.txt"):
        assert req.lower().replace("_", "-") in fijados, req
    for n in ("requirements.lock", "requirements-build.lock", "requirements-dev.lock"):
        assert all("==" in li for li in _lineas(n)), n
