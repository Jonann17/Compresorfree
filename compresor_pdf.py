"""Compresor de PDF con tres niveles: baja, media o alta.

Si Ghostscript esta instalado se usa (mejor resultado). Si no, se recomprimen
las imagenes del PDF con pikepdf + Pillow (pip install pikepdf pillow).
"""

import io
import os
import shutil
import tempfile

import nucleo
import procesos

NIVELES = {
    # calidad JPEG, lado maximo de imagen en pixeles, ajuste de Ghostscript
    "baja": {"calidad": 85, "lado_max": 2500, "gs": "/printer"},
    "media": {"calidad": 70, "lado_max": 1600, "gs": "/ebook"},
    "alta": {"calidad": 50, "lado_max": 1000, "gs": "/screen"},
}


def ruta_salida_por_defecto(entrada, nivel):
    base, _ = os.path.splitext(entrada)
    return f"{base}_comprimido_{nivel}.pdf"


def buscar_ghostscript():
    for nombre in ("gs", "gswin64c", "gswin32c"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def _comando_ghostscript(gs, entrada, salida, cfg):
    return [
        gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={cfg['gs']}", "-dNOPAUSE", "-dQUIET", "-dBATCH",
        f"-sOutputFile={salida}", entrada,
    ]


def _comprimir_ghostscript(gs, entrada, salida, cfg, cancelar=None):
    # Ghostscript deja archivos gs_* de cientos de MB en TEMP si se le corta a
    # mitad; se le da una carpeta propia que se borra siempre, tambien al cancelar.
    with tempfile.TemporaryDirectory(prefix="compresorfree_gs_") as tmp:
        env = dict(os.environ, TMPDIR=tmp, TEMP=tmp, TMP=tmp)
        r = procesos.ejecutar(_comando_ghostscript(gs, entrada, salida, cfg), cancelar, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"Ghostscript fallo:\n{r.stderr[-1500:]}")


def _recomprimir_imagen(pikepdf, Image, obj, cfg):
    """Reemplaza la imagen por un JPEG mas liviano. Devuelve True si cambio."""
    if obj.get("/ImageMask", False) or isinstance(obj.get("/Mask"), pikepdf.Array):
        return False  # mascaras: no se pueden pasar a JPEG sin romperlas
    if int(obj.get("/BitsPerComponent", 8)) < 8:
        return False  # imagenes de 1 bit (escaneos B/N) ya son muy livianas

    try:
        img = pikepdf.PdfImage(obj).as_pil_image()
    except Exception:
        return False  # formato no soportado: se deja igual

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > cfg["lado_max"]:
        img.thumbnail((cfg["lado_max"], cfg["lado_max"]), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=cfg["calidad"], optimize=True)
    datos = buf.getvalue()
    if len(datos) >= len(obj.read_raw_bytes()):
        return False  # no gana nada

    obj.write(datos, filter=pikepdf.Name.DCTDecode)
    obj.Width, obj.Height = img.size
    obj.ColorSpace = pikepdf.Name.DeviceGray if img.mode == "L" else pikepdf.Name.DeviceRGB
    obj.BitsPerComponent = 8
    for clave in ("/DecodeParms", "/Decode"):
        if clave in obj:
            del obj[clave]
    return True


def _comprimir_pikepdf(entrada, salida, cfg, progreso, cancelar):
    try:
        import pikepdf
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Para comprimir PDF instala Ghostscript o ejecuta:\n"
            "    pip install pikepdf pillow"
        )

    with pikepdf.open(entrada) as pdf:
        imagenes = [o for o in pdf.objects
                    if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image"]
        for i, obj in enumerate(imagenes, 1):
            _comprobar_cancelacion(cancelar)
            _recomprimir_imagen(pikepdf, Image, obj, cfg)
            if progreso:
                progreso(i / len(imagenes) * 90)

        pdf.remove_unreferenced_resources()
        _comprobar_cancelacion(cancelar)  # pdf.save no se puede interrumpir
        pdf.save(
            salida, compress_streams=True, recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )


def _comprobar_cancelacion(cancelar):
    if cancelar is not None and cancelar.is_set():
        raise procesos.Cancelado()


def _importar_pikepdf():
    try:
        import pikepdf
    except ImportError:
        raise RuntimeError("Para comprimir PDF hace falta pikepdf:\n    pip install pikepdf pillow")
    return pikepdf


def _campos(pikepdf, campos, ft_heredado=None, vistos=None):
    """Recorre el arbol de campos de formulario (con /Kids y /FT heredado)."""
    vistos = set() if vistos is None else vistos
    for campo in campos:
        if not isinstance(campo, pikepdf.Dictionary):
            continue
        clave = campo.objgen if campo.is_indirect else id(campo)
        if clave in vistos:
            continue
        vistos.add(clave)
        ft = campo.get("/FT", ft_heredado)
        yield campo, ft
        yield from _campos(pikepdf, campo.get("/Kids", []), ft, vistos)


def motivo_omision(entrada):
    """Motivo por el que un PDF no debe tocarse, o None si se puede comprimir.

    - Firmado o certificado: reescribirlo invalidaria la firma.
    - Cifrado o con contrasena: no se quita su proteccion en silencio.
    Ante la duda se omite (mejor no comprimir que alterar un documento)."""
    pikepdf = _importar_pikepdf()
    try:
        pdf = pikepdf.open(entrada)
    except pikepdf.PasswordError:
        return "protegido con contrasena"
    except pikepdf.PdfError:
        return None  # PDF danado: el error real lo dara la compresion
    with pdf:
        if pdf.is_encrypted:
            return "cifrado (no se quita su proteccion)"
        firmado = "firmado digitalmente (comprimirlo invalidaria la firma)"
        raiz = pdf.Root
        if "/Perms" in raiz:
            return firmado
        formulario = raiz.get("/AcroForm")
        if isinstance(formulario, pikepdf.Dictionary):
            if int(formulario.get("/SigFlags", 0)) & 3:
                return firmado
            for campo, ft in _campos(pikepdf, formulario.get("/Fields", [])):
                if ft == "/Sig" and "/V" in campo:
                    return firmado
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Dictionary) and obj.get("/Type") == "/Sig":
                return firmado
    return None


def _contar_paginas(ruta):
    pikepdf = _importar_pikepdf()
    with pikepdf.open(ruta) as pdf:
        return len(pdf.pages)


def comprimir(entrada, salida=None, nivel="media", progreso=None, cancelar=None,
              si_existe="error"):
    """Comprime un PDF. Devuelve la ruta del archivo generado.

    si_existe: 'error' (no toca un destino existente y lanza DestinoExistente)
               o 'renombrar' (guarda como "nombre (2).pdf", "(3)"...).
    Lanza nucleo.ArchivoOmitido si el PDF esta firmado o cifrado.
    Nunca sobrescribe nada: escribe en un temporal y lo publica al final.
    """
    if nivel not in NIVELES:
        raise ValueError(f"Nivel invalido: {nivel}. Usa: {', '.join(NIVELES)}")
    if not os.path.isfile(entrada):
        raise FileNotFoundError(f"No existe el archivo: {entrada}")

    cfg = NIVELES[nivel]
    salida = salida or ruta_salida_por_defecto(entrada, nivel)
    nucleo.comprobar_destino(entrada, salida, si_existe)

    motivo = motivo_omision(entrada)
    if motivo:
        raise nucleo.ArchivoOmitido(f"Se omitio: PDF {motivo}.")
    paginas = _contar_paginas(entrada)

    with nucleo.salida_temporal(salida) as tmp:
        gs = buscar_ghostscript()
        if gs:
            _comprimir_ghostscript(gs, entrada, tmp, cfg, cancelar)
        else:
            _comprimir_pikepdf(entrada, tmp, cfg, progreso, cancelar)

        # Si el PDF ya estaba optimizado y el resultado pesa mas, se conserva el original.
        if os.path.getsize(tmp) > os.path.getsize(entrada):
            shutil.copyfile(entrada, tmp)

        try:
            paginas_salida = _contar_paginas(tmp)
        except Exception as e:
            raise RuntimeError(f"El resultado no es un PDF valido: {e}")
        if paginas_salida != paginas:
            raise RuntimeError(
                f"El resultado tiene {paginas_salida} paginas y el original {paginas}; "
                "no se guardo.")
        _comprobar_cancelacion(cancelar)  # nada se publica despues de cancelar
        final = nucleo.finalizar(tmp, salida, si_existe)

    if progreso:
        progreso(100.0)
    return final


def estimar(entrada, nivel="media", cancelar=None):
    """Tamano final en bytes: comprime el PDF en un archivo temporal y lo mide."""
    with tempfile.TemporaryDirectory(prefix="compresorfree_") as tmp:
        try:
            salida = comprimir(entrada, os.path.join(tmp, "estimado.pdf"), nivel,
                               cancelar=cancelar)
        except RuntimeError:
            if cancelar is not None and cancelar.is_set():
                return None
            raise
        return os.path.getsize(salida)
