"""PDF: publicacion segura y barrera para PDF firmados o cifrados."""
import os

import pikepdf
import pytest

import compresor_pdf
from conftest import leer, temporales

try:
    import nucleo
    DestinoExistente, ArchivoOmitido = nucleo.DestinoExistente, nucleo.ArchivoOmitido
except ImportError:  # permite correr las regresiones contra main
    DestinoExistente = ArchivoOmitido = Exception


@pytest.fixture(params=["pikepdf", "ghostscript"])
def motor(request, monkeypatch):
    if request.param == "pikepdf":
        monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: None)
    elif compresor_pdf.buscar_ghostscript() is None:
        pytest.skip("Ghostscript no instalado")
    return request.param


def test_comprime_y_conserva_paginas(pdf_fotos, tmp_path, motor):
    salida = compresor_pdf.comprimir(pdf_fotos, str(tmp_path / "out.pdf"), "media")
    with pikepdf.open(salida) as pdf:
        assert len(pdf.pages) == 2
    assert os.path.getsize(salida) <= os.path.getsize(pdf_fotos)
    assert temporales(tmp_path) == []


def test_c2_pdf_destino_existente_no_se_pisa(pdf_fotos, tmp_path, motor):
    destino = str(tmp_path / "existente.pdf")
    with open(destino, "wb") as f:
        f.write(b"dato importante")
    with pytest.raises(DestinoExistente):
        compresor_pdf.comprimir(pdf_fotos, destino, "media")
    assert leer(destino) == b"dato importante"


def test_pdf_sin_mejora_se_publica_identico(tmp_path, monkeypatch):
    monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: None)
    pdf = pikepdf.new()
    pdf.add_blank_page()
    entrada = str(tmp_path / "vacio.pdf")
    pdf.save(entrada)
    salida = compresor_pdf.comprimir(entrada, None, "alta")
    assert os.path.getsize(salida) <= os.path.getsize(entrada)
    assert temporales(tmp_path) == []


def _guardar_cifrado(origen, destino, user=""):
    with pikepdf.open(origen) as pdf:
        pdf.save(destino, encryption=pikepdf.Encryption(owner="dueno", user=user, R=6))
    return destino


def _guardar_firmado(origen, destino, con_sigflags=True):
    """Firma simulada a nivel de estructura (la firma criptografica real es PR2-A)."""
    with pikepdf.open(origen) as pdf:
        sig = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Sig, Filter=pikepdf.Name("/Adobe.PPKLite"),
            Contents=pikepdf.String(b"\x00" * 16)))
        campo = pdf.make_indirect(pikepdf.Dictionary(
            FT=pikepdf.Name.Sig, T=pikepdf.String("Firma1"), V=sig,
            Subtype=pikepdf.Name.Widget, Rect=[0, 0, 0, 0]))
        acro = pikepdf.Dictionary(Fields=pikepdf.Array([campo]))
        if con_sigflags:
            acro.SigFlags = 3
        pdf.Root.AcroForm = pdf.make_indirect(acro)
        pdf.save(destino)
    return destino


@pytest.mark.parametrize("caso", ["cifrado", "contrasena", "firmado", "firmado_sin_sigflags"])
def test_pdf_especiales_se_omiten_sin_tocar(pdf_fotos, tmp_path, caso):
    entrada = str(tmp_path / f"{caso}.pdf")
    if caso == "cifrado":
        _guardar_cifrado(pdf_fotos, entrada)
    elif caso == "contrasena":
        _guardar_cifrado(pdf_fotos, entrada, user="clave")
    else:
        _guardar_firmado(pdf_fotos, entrada, con_sigflags=(caso == "firmado"))
    original = leer(entrada)
    salida = str(tmp_path / "salida.pdf")
    with pytest.raises(ArchivoOmitido):
        compresor_pdf.comprimir(entrada, salida, "media")
    assert leer(entrada) == original
    assert not os.path.exists(salida) and temporales(tmp_path) == []
