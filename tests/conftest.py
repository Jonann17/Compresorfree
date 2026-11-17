import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import compresor_video  # noqa: E402


def _ffmpeg():
    try:
        return compresor_video.buscar_ffmpeg()
    except RuntimeError:
        return None


FFMPEG = _ffmpeg()
requiere_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg no disponible")


def generar_video(ruta, segundos=2, tamano="320x240"):
    """Video sintetico (sin datos de usuarios): barras de prueba + tono."""
    subprocess.run(
        [FFMPEG, "-v", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size={tamano}:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440",
         "-t", str(segundos), "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac", ruta],
        check=True, capture_output=True,
    )
    return ruta


@pytest.fixture
def video(tmp_path):
    if FFMPEG is None:
        pytest.skip("FFmpeg no disponible")
    return generar_video(str(tmp_path / "clip.avi"))


@pytest.fixture
def pdf_fotos(tmp_path):
    """PDF de 2 paginas con fotos (ruido), comprimible."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(1)
    paginas = [Image.fromarray((rng.random((500, 700, 3)) * 255).astype("uint8"))
               for _ in range(2)]
    ruta = str(tmp_path / "fotos.pdf")
    paginas[0].save(ruta, save_all=True, append_images=paginas[1:], quality=95)
    return ruta


def leer(ruta):
    with open(ruta, "rb") as f:
        return f.read()


def temporales(carpeta):
    return [n for n in os.listdir(carpeta) if ".parcial-" in n]
