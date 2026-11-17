"""Publicacion sin sobrescritura, temporales y planificacion de destinos."""
import os
import sys

import pytest

import nucleo
from conftest import leer, temporales


def _escribir(ruta, contenido):
    with open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


def test_capacidad_primitiva_no_sobrescribe_en_este_disco(tmp_path):
    """Prueba de capacidad del sistema de archivos del runner (NTFS/APFS/ext4)."""
    destino = _escribir(str(tmp_path / "existente.mp4"), b"ORIGINAL")
    tmp = nucleo.crear_temporal(destino)
    _escribir(tmp, b"NUEVO")
    with pytest.raises(nucleo.DestinoExistente):
        nucleo.publicar(tmp, destino)
    assert leer(destino) == b"ORIGINAL"
    assert os.path.exists(tmp), "el temporal debe quedar intacto si no se publico"
    # Y a un destino libre si publica, de forma atomica.
    libre = str(tmp_path / "libre.mp4")
    assert nucleo.publicar(tmp, libre) == libre
    assert leer(libre) == b"NUEVO" and not os.path.exists(tmp)


def test_publicar_con_nombre_libre_agrega_numero(tmp_path):
    destino = _escribir(str(tmp_path / "v.mp4"), b"A")
    _escribir(str(tmp_path / "v (2).mp4"), b"B")
    tmp = _escribir(nucleo.crear_temporal(destino), b"C")
    final = nucleo.publicar_con_nombre_libre(tmp, destino)
    assert os.path.basename(final) == "v (3).mp4"
    assert leer(destino) == b"A" and leer(str(tmp_path / "v (2).mp4")) == b"B"


def test_sin_primitiva_segura_falla_sin_escribir(tmp_path, monkeypatch):
    monkeypatch.setattr(nucleo, "_renombrar_exclusivo", lambda a, b: False)
    monkeypatch.setattr(nucleo, "_enlazar_exclusivo", lambda a, b: False)
    destino = str(tmp_path / "salida.mp4")
    tmp = _escribir(nucleo.crear_temporal(destino), b"X")
    with pytest.raises(nucleo.PublicacionNoSegura):
        nucleo.publicar(tmp, destino)
    assert not os.path.exists(destino)


def test_temporales_son_exclusivos_y_ocultos(tmp_path):
    destino = str(tmp_path / "doc.pdf")
    a, b = nucleo.crear_temporal(destino), nucleo.crear_temporal(destino)
    assert a != b
    for t in (a, b):
        nombre = os.path.basename(t)
        assert nombre.startswith(".doc.parcial-") and nombre.endswith(".pdf")


def test_salida_temporal_limpia_ante_error(tmp_path):
    destino = str(tmp_path / "x.mp4")
    with pytest.raises(RuntimeError):
        with nucleo.salida_temporal(destino) as tmp:
            _escribir(tmp, b"parcial")
            raise RuntimeError("fallo simulado")
    assert temporales(tmp_path) == [] and not os.path.exists(destino)


def test_planificar_no_elige_otra_entrada_del_lote(tmp_path):
    """C1: la salida de a.avi no puede ser la entrada a_comprimido.mp4."""
    a = _escribir(str(tmp_path / "a.avi"), b"1")
    b = _escribir(str(tmp_path / "a_comprimido.mp4"), b"2")
    salidas = nucleo.planificar_lote([a, b], lambda e: os.path.splitext(e)[0] + "_comprimido.mp4")
    assert not any(nucleo.es_misma_ruta(s, e) for s in salidas for e in (a, b))
    assert len({nucleo.clave_ruta(s) for s in salidas}) == 2


def test_planificar_evita_existentes_y_duplicados(tmp_path):
    """C2 + nombres repetidos desde carpetas distintas hacia una sola carpeta."""
    (tmp_path / "uno").mkdir(); (tmp_path / "dos").mkdir(); (tmp_path / "out").mkdir()
    e1 = _escribir(str(tmp_path / "uno" / "v.avi"), b"1")
    e2 = _escribir(str(tmp_path / "dos" / "v.avi"), b"2")
    _escribir(str(tmp_path / "out" / "v_c.mp4"), b"ya existia")
    salidas = nucleo.planificar_lote(
        [e1, e2], lambda e: os.path.splitext(e)[0] + "_c.mp4", str(tmp_path / "out"))
    assert [os.path.basename(s) for s in salidas] == ["v_c (2).mp4", "v_c (3).mp4"]


def test_misma_ruta_con_hardlink_y_mayusculas(tmp_path):
    a = _escribir(str(tmp_path / "Video.avi"), b"1")
    enlace = str(tmp_path / "otro_nombre.avi")
    os.link(a, enlace)
    assert nucleo.es_misma_ruta(a, enlace)
    assert nucleo.clave_ruta(str(tmp_path / "VIDEO.AVI")) == nucleo.clave_ruta(a)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks requieren permisos en Windows")
def test_misma_ruta_con_symlink(tmp_path):
    a = _escribir(str(tmp_path / "v.avi"), b"1")
    s = str(tmp_path / "atajo.avi")
    os.symlink(a, s)
    assert nucleo.es_misma_ruta(a, s)


def test_destino_igual_a_entrada_se_rechaza(tmp_path):
    a = _escribir(str(tmp_path / "a.mp4"), b"1")
    with pytest.raises(ValueError):
        nucleo.comprobar_destino(a, str(tmp_path / "A.MP4") if os.name == "nt" else a, "renombrar")
