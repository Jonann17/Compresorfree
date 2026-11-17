"""Compresor de PDF con tres niveles: baja, media o alta.

Por defecto se recomprimen las imagenes con pikepdf + Pillow (conservador:
conserva enlaces, formularios, adjuntos, marcadores y cifrado). Ghostscript es
opcional (motor="ghostscript", compresion agresiva); su resultado tambien pasa
por la huella estructural y se rechaza si altera el documento.
"""

import errno
import hashlib
import io
import os
import re
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

MOTORES = ("pikepdf", "ghostscript")


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
    # Ghostscript trata %d, %03d... de la salida como plantillas de pagina.
    salida = salida.replace("%", "%%")
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
        if "No space left on device" in r.stderr:
            raise nucleo.EspacioInsuficiente(nucleo.MENSAJE_DISCO_LLENO)
        raise RuntimeError(f"Ghostscript fallo:\n{r.stderr[-1500:]}")


def _recomprimir_imagen(pikepdf, Image, obj, cfg):
    """Reemplaza la imagen por un JPEG mas liviano. Devuelve True si cambio.

    Solo toca imagenes /DeviceRGB o /DeviceGray directas de 8 bits, sin /Decode
    ni /Mask en array; el resto (ICC, Indexed, CMYK, 16 bits...) queda intacto."""
    if obj.get("/ImageMask", False) or isinstance(obj.get("/Mask"), pikepdf.Array):
        return False  # mascaras: no se pueden pasar a JPEG sin romperlas
    if obj.get("/ColorSpace") not in (pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray):
        return False
    if int(obj.get("/BitsPerComponent", 0)) != 8 or "/Decode" in obj:
        return False

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

        _comprobar_cancelacion(cancelar)  # pdf.save no se puede interrumpir
        pdf.save(
            salida, compress_streams=True, recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            encryption=True if pdf.is_encrypted else None,  # conserva cifrado y permisos
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
    - Con contrasena de usuario: no se puede abrir sin ella.
      (Cifrado solo con contrasena de propietario si se comprime, conservando el cifrado.)
    Ante la duda se omite (mejor no comprimir que alterar un documento)."""
    pikepdf = _importar_pikepdf()
    try:
        pdf = pikepdf.open(entrada)
    except pikepdf.PasswordError:
        return "protegido con contrasena"
    except pikepdf.PdfError:
        return None  # PDF danado: el error real lo dara la compresion
    with pdf:
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


def _heredado(pagina, clave):
    nodo = pagina.obj
    for _ in range(64):
        if clave in nodo:
            return nodo[clave]
        nodo = nodo.get("/Parent")
        if nodo is None:
            return None
    return None


def _caja(valor):
    return None if valor is None else [round(float(x), 3) for x in valor]


def _texto(valor):
    try:
        if isinstance(valor, (int, float, bool)) or valor is None:
            return repr(valor)
        return str(valor)
    except Exception:
        return "<ilegible>"



def huella(pdf):
    """Resumen estructural comparable antes/despues (filtro de publicacion, no prueba total)."""
    pikepdf = _importar_pikepdf()
    raiz = pdf.Root
    h = {"paginas": len(pdf.pages), "cifrado": bool(pdf.is_encrypted)}
    if pdf.is_encrypted:
        h["permisos"] = _texto(tuple(pdf.allow))
    orden = {p.objgen: i for i, p in enumerate(pdf.pages)}
    paginas = []
    for pagina in pdf.pages:
        anots = []
        for a in pagina.obj.get("/Annots", []):
            if not isinstance(a, pikepdf.Dictionary):
                continue
            accion = a.get("/A")
            uri = accion.get("/URI") if isinstance(accion, pikepdf.Dictionary) else None
            dest = a.get("/Dest")
            if dest is None and isinstance(accion, pikepdf.Dictionary):
                dest = accion.get("/D")
            if isinstance(dest, pikepdf.Array) and len(dest) and dest[0].is_indirect:
                dest = ("pag", orden.get(dest[0].objgen))
            elif dest is not None:
                dest = _texto(dest)
            anots.append((_texto(a.get("/Subtype")), _texto(uri) if uri is not None else None, dest))
        paginas.append((_caja(_heredado(pagina, "/MediaBox")), _caja(_heredado(pagina, "/CropBox")),
                        _texto(_heredado(pagina, "/Rotate")), anots))
    h["paginas_info"] = paginas

    formulario = raiz.get("/AcroForm")
    campos = []
    if isinstance(formulario, pikepdf.Dictionary):
        for campo, _ft in _campos(pikepdf, formulario.get("/Fields", [])):
            campos.append((_texto(campo.get("/T")), _texto(campo.get("/V"))))
    h["campos"] = campos

    n, vistos = 0, set()
    pila = [raiz.get("/Outlines")]
    while pila and n < 10000:
        nodo = pila.pop()
        if not isinstance(nodo, pikepdf.Dictionary):
            continue
        clave = nodo.objgen if nodo.is_indirect else id(nodo)
        if clave in vistos:
            continue
        vistos.add(clave)
        n += 1
        pila.append(nodo.get("/First"))
        pila.append(nodo.get("/Next"))
    h["marcadores"] = n

    adjuntos = {}
    try:
        for nombre, spec in pdf.attachments.items():
            adjuntos[nombre] = hashlib.sha256(spec.get_file().read_bytes()).hexdigest()
    except Exception:
        adjuntos = {"<ilegible>": None}
    h["adjuntos"] = sorted(adjuntos.items())

    nombres = raiz.get("/Names")
    h["accion_inicial"] = "/OpenAction" in raiz
    h["javascript"] = isinstance(nombres, pikepdf.Dictionary) and "/JavaScript" in nombres
    h["capas"] = "/OCProperties" in raiz
    pdfa = []
    meta = raiz.get("/Metadata")
    if isinstance(meta, pikepdf.Stream):
        try:
            pdfa = re.findall(rb"pdfaid:(\w+)\s*[>=]\s*[\"']?([^<\"'\s]+)", meta.read_bytes())
        except Exception:
            pdfa = ["<ilegible>"]
    h["pdfaid"] = sorted(pdfa)
    return h


def _huella_de(ruta):
    pikepdf = _importar_pikepdf()
    with pikepdf.open(ruta) as pdf:
        return huella(pdf)


def _contar_paginas(ruta):
    pikepdf = _importar_pikepdf()
    with pikepdf.open(ruta) as pdf:
        return len(pdf.pages)


def comprimir(entrada, salida=None, nivel="media", progreso=None, cancelar=None,
              si_existe="error", motor="pikepdf"):
    """Comprime un PDF. Devuelve la ruta del archivo generado.

    si_existe: 'error' (no toca un destino existente y lanza DestinoExistente)
               o 'renombrar' (guarda como "nombre (2).pdf", "(3)"...).
    motor: 'pikepdf' (por defecto) o 'ghostscript' (agresivo; RuntimeError si no esta).
    Lanza nucleo.ArchivoOmitido si el PDF esta firmado o tiene contrasena de usuario.
    Si la huella estructural del resultado difiere de la del original, no se publica.
    Nunca sobrescribe nada: escribe en un temporal y lo publica al final.
    """
    if nivel not in NIVELES:
        raise ValueError(f"Nivel invalido: {nivel}. Usa: {', '.join(NIVELES)}")
    if motor not in MOTORES:
        raise ValueError(f"Motor invalido: {motor}. Usa: {', '.join(MOTORES)}")
    if not os.path.isfile(entrada):
        raise FileNotFoundError(f"No existe el archivo: {entrada}")
    gs = None
    if motor == "ghostscript":
        gs = buscar_ghostscript()
        if gs is None:
            raise RuntimeError("Ghostscript no esta instalado: usa el motor pikepdf.")

    cfg = NIVELES[nivel]
    salida = salida or ruta_salida_por_defecto(entrada, nivel)
    nucleo.comprobar_destino(entrada, salida, si_existe)

    motivo = motivo_omision(entrada)
    if motivo:
        raise nucleo.ArchivoOmitido(f"Se omitio: PDF {motivo}.")
    huella_original = _huella_de(entrada)
    paginas = huella_original["paginas"]

    # Si el resultado no pesa menos que la entrada, no se publica (SinMejora).
    nucleo.comprobar_espacio(os.path.dirname(os.path.abspath(salida)),
                             os.path.getsize(entrada) + nucleo.MARGEN_ESPACIO)

    with nucleo.salida_temporal(salida) as tmp:
        try:
            if gs:
                _comprimir_ghostscript(gs, entrada, tmp, cfg, cancelar)
            else:
                _comprimir_pikepdf(entrada, tmp, cfg, progreso, cancelar)
        except OSError as e:
            if e.errno == errno.ENOSPC:
                raise nucleo.EspacioInsuficiente(nucleo.MENSAJE_DISCO_LLENO) from e
            raise

        if os.path.getsize(tmp) >= os.path.getsize(entrada):
            raise nucleo.SinMejora(
                "No se redujo: el PDF ya esta optimizado; no se creo ningun archivo.")

        try:
            paginas_salida = _contar_paginas(tmp)
        except Exception as e:
            raise RuntimeError(f"El resultado no es un PDF valido: {e}")
        if paginas_salida != paginas:
            raise RuntimeError(
                f"El resultado tiene {paginas_salida} paginas y el original {paginas}; "
                "no se guardo.")
        try:
            if _huella_de(tmp) != huella_original:
                raise RuntimeError("no se pudo comprimir sin alterar el documento")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"no se pudo comprimir sin alterar el documento ({e})")
        _comprobar_cancelacion(cancelar)  # nada se publica despues de cancelar
        final = nucleo.finalizar(tmp, salida, si_existe)

    if progreso:
        progreso(100.0)
    return final


def estimar(entrada, nivel="media", cancelar=None, motor="pikepdf"):
    """Tamano final en bytes: comprime el PDF en un archivo temporal y lo mide."""
    with tempfile.TemporaryDirectory(prefix="compresorfree_") as tmp:
        try:
            salida = comprimir(entrada, os.path.join(tmp, "estimado.pdf"), nivel,
                               cancelar=cancelar, motor=motor)
        except nucleo.SinMejora:
            return os.path.getsize(entrada)
        except RuntimeError:
            if cancelar is not None and cancelar.is_set():
                return None
            raise
        return os.path.getsize(salida)
