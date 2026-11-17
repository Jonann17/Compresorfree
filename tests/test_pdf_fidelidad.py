"""PDF: motor por defecto, imagenes conservadoras, huella estructural y cifrado."""
import os

import pikepdf
import pytest
from PIL import Image

import compresor_pdf
import nucleo
from conftest import temporales


def _foto(modo, tam=(300, 300)):
    import numpy as np
    rng = np.random.default_rng(3)
    canales = {"RGB": 3, "L": 1, "CMYK": 4}[modo]
    forma = (tam[1], tam[0], canales) if canales > 1 else (tam[1], tam[0])
    return Image.fromarray((rng.random(forma) * 255).astype("uint8"), modo)


def _pdf_con_imagen(ruta, **kw):
    """PDF de una pagina con una imagen cruda (Flate) segun kw."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(300, 300))
    ancho = alto = 300
    cs, bpc, datos = kw["cs"], kw["bpc"], kw["datos"]
    if callable(cs):
        cs = cs(pdf)
    img = pikepdf.Stream(pdf, datos)
    img.Type, img.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
    img.Width, img.Height, img.ColorSpace, img.BitsPerComponent = ancho, alto, cs, bpc
    pdf.pages[0].Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
    pdf.pages[0].Contents = pdf.make_stream(b"q 300 0 0 300 0 0 cm /Im0 Do Q")
    pdf.save(ruta)
    return ruta


def _bytes_imagen(ruta):
    with pikepdf.open(ruta) as pdf:
        return pdf.pages[0].Resources.XObject.Im0.read_raw_bytes()


@pytest.fixture
def pdf_estructura(tmp_path, pdf_fotos):
    """Fotos + enlace, campo de formulario, adjunto y marcador."""
    ruta = str(tmp_path / "estructura.pdf")
    with pikepdf.open(pdf_fotos) as pdf:
        link = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=[0, 0, 50, 50],
            A=pikepdf.Dictionary(S=pikepdf.Name.URI, URI=pikepdf.String("https://ejemplo.org"))))
        campo = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget, FT=pikepdf.Name.Tx,
            T=pikepdf.String("nombre"), V=pikepdf.String("Ana"), Rect=[0, 60, 50, 90]))
        pdf.pages[0].Annots = pikepdf.Array([link, campo])
        pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([campo])))
        pdf.attachments["nota.txt"] = pikepdf.AttachedFileSpec(pdf, b"hola adjunto")
        with pdf.open_outline() as of:
            of.root.append(pikepdf.OutlineItem("Inicio", 0))
        pdf.save(ruta)
    return ruta


def _firmas(ruta):
    with pikepdf.open(ruta) as pdf:
        return compresor_pdf.huella(pdf)


# ------------------------------------------------------------- motor

def test_motor_por_defecto_no_llama_a_ghostscript(pdf_fotos, tmp_path, monkeypatch):
    monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: "gs-falso")

    def prohibido(*a, **k):
        raise AssertionError("no debe usarse Ghostscript")

    monkeypatch.setattr(compresor_pdf, "_comprimir_ghostscript", prohibido)
    salida = compresor_pdf.comprimir(pdf_fotos, str(tmp_path / "out.pdf"), "media")
    assert os.path.getsize(salida) <= os.path.getsize(pdf_fotos)


def test_motor_ghostscript_sin_gs_da_error(pdf_fotos, tmp_path, monkeypatch):
    monkeypatch.setattr(compresor_pdf, "buscar_ghostscript", lambda: None)
    salida = str(tmp_path / "out.pdf")
    with pytest.raises(RuntimeError, match="Ghostscript"):
        compresor_pdf.comprimir(pdf_fotos, salida, "media", motor="ghostscript")
    assert not os.path.exists(salida) and temporales(tmp_path) == []


def test_motor_invalido(pdf_fotos, tmp_path):
    with pytest.raises(ValueError):
        compresor_pdf.comprimir(pdf_fotos, str(tmp_path / "o.pdf"), motor="otro")


def test_estimar_pasa_el_motor(pdf_fotos, monkeypatch):
    vistos = []
    real = compresor_pdf.comprimir

    def espia(*a, **k):
        vistos.append(k.get("motor"))
        return real(*a, **k)

    monkeypatch.setattr(compresor_pdf, "comprimir", espia)
    compresor_pdf.estimar(pdf_fotos, "media")
    assert vistos == ["pikepdf"]


def test_no_se_llama_remove_unreferenced(pdf_fotos, tmp_path, monkeypatch):
    def prohibido(self, *a, **k):
        raise AssertionError("remove_unreferenced_resources no debe llamarse")

    monkeypatch.setattr(pikepdf.Pdf, "remove_unreferenced_resources", prohibido)
    compresor_pdf.comprimir(pdf_fotos, str(tmp_path / "out.pdf"), "media")


# ------------------------------------------------------------- imagenes

def _comprimir_y_comparar(tmp_path, entrada):
    antes = _bytes_imagen(entrada)
    try:
        salida = compresor_pdf.comprimir(entrada, str(tmp_path / "out.pdf"), "alta")
    except nucleo.SinMejora:  # nada que recomprimir: no se crea salida, el original queda
        assert not (tmp_path / "out.pdf").exists()
        return antes, antes
    return antes, _bytes_imagen(salida)


@pytest.mark.parametrize("caso", ["cmyk", "indexed", "16bits", "icc"])
def test_imagen_no_conservadora_queda_intacta(tmp_path, caso):
    if caso == "cmyk":
        cs, bpc, datos = pikepdf.Name.DeviceCMYK, 8, _foto("CMYK").tobytes()
    elif caso == "indexed":
        paleta = bytes(range(256)) * 3
        cs = pikepdf.Array([pikepdf.Name.Indexed, pikepdf.Name.DeviceRGB, 255, pikepdf.String(paleta)])
        bpc, datos = 8, _foto("L").tobytes()
    elif caso == "16bits":
        cs, bpc, datos = pikepdf.Name.DeviceRGB, 16, os.urandom(300 * 300 * 6)
    else:
        def cs(pdf):
            icc = pikepdf.Stream(pdf, b"\x00" * 128)
            icc.N = 3
            return pikepdf.Array([pikepdf.Name.ICCBased, icc])
        bpc, datos = 8, _foto("RGB").tobytes()
    ruta = _pdf_con_imagen(str(tmp_path / "e.pdf"), cs=cs, bpc=bpc, datos=datos)
    antes, despues = _comprimir_y_comparar(tmp_path, ruta)
    assert antes == despues


def test_imagen_devicergb_8bits_si_se_recomprime(tmp_path):
    ruta = _pdf_con_imagen(str(tmp_path / "e.pdf"), cs=pikepdf.Name.DeviceRGB, bpc=8,
                           datos=_foto("RGB").tobytes())
    antes, despues = _comprimir_y_comparar(tmp_path, ruta)
    assert len(despues) < len(antes)


# ------------------------------------------------------------- huella

def test_conserva_enlace_formulario_adjunto_y_marcador(pdf_estructura, tmp_path):
    salida = compresor_pdf.comprimir(pdf_estructura, str(tmp_path / "out.pdf"), "media")
    assert _firmas(salida) == _firmas(pdf_estructura)
    h = _firmas(salida)
    assert h["marcadores"] >= 2 and h["campos"] == [("nombre", "Ana")]
    assert [n for n, _ in h["adjuntos"]] == ["nota.txt"]


@pytest.mark.parametrize("alteracion", ["anotacion", "adjunto"])
def test_huella_distinta_no_publica(pdf_estructura, tmp_path, monkeypatch, alteracion):
    real = compresor_pdf._comprimir_pikepdf

    def alterado(entrada, tmp, cfg, progreso, cancelar):
        real(entrada, tmp, cfg, progreso, cancelar)
        with pikepdf.open(tmp, allow_overwriting_input=True) as pdf:
            if alteracion == "anotacion":
                del pdf.pages[0].Annots[0]
            else:
                pdf.attachments["nota.txt"] = pikepdf.AttachedFileSpec(pdf, b"otro")
            pdf.save(tmp)

    monkeypatch.setattr(compresor_pdf, "_comprimir_pikepdf", alterado)
    salida = str(tmp_path / "out.pdf")
    with pytest.raises(RuntimeError, match="sin alterar el documento"):
        compresor_pdf.comprimir(pdf_estructura, salida, "media")
    assert not os.path.exists(salida) and temporales(tmp_path) == []


# ------------------------------------------------------------- cifrado

@pytest.mark.parametrize("R", [4, 6])
def test_cifrado_solo_owner_se_comprime_conservando_cifrado(pdf_fotos, tmp_path, R):
    entrada = str(tmp_path / "cifrado.pdf")
    perms = pikepdf.Permissions(extract=False, print_lowres=True)
    with pikepdf.open(pdf_fotos) as pdf:
        pdf.save(entrada, encryption=pikepdf.Encryption(owner="dueno", user="", R=R,
                                                        allow=perms))
    salida = compresor_pdf.comprimir(entrada, str(tmp_path / "out.pdf"), "media")
    with pikepdf.open(entrada) as a, pikepdf.open(salida) as b:
        assert b.is_encrypted and b.encryption.R == R
        assert tuple(b.allow) == tuple(a.allow)
        assert not b.allow.extract
        assert len(b.pages) == 2
    assert temporales(tmp_path) == []


def test_cifrado_con_user_password_se_omite(pdf_fotos, tmp_path):
    entrada = str(tmp_path / "clave.pdf")
    with pikepdf.open(pdf_fotos) as pdf:
        pdf.save(entrada, encryption=pikepdf.Encryption(owner="dueno", user="clave", R=6))
    with pytest.raises(nucleo.ArchivoOmitido):
        compresor_pdf.comprimir(entrada, str(tmp_path / "out.pdf"), "media")
