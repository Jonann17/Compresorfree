"""Compresor de PDF con tres niveles: baja, media o alta.

Si Ghostscript esta instalado se usa (mejor resultado). Si no, se recomprimen
las imagenes del PDF con pikepdf + Pillow (pip install pikepdf pillow).
"""

import io
import os
import shutil
import subprocess
import tempfile

from compresor_video import SIN_CONSOLA

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


def _comprimir_ghostscript(gs, entrada, salida, cfg):
    cmd = [
        gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={cfg['gs']}", "-dNOPAUSE", "-dQUIET", "-dBATCH",
        f"-sOutputFile={salida}", entrada,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                          creationflags=SIN_CONSOLA)
    if proc.returncode != 0:
        raise RuntimeError(f"Ghostscript fallo:\n{proc.stderr[-1500:]}")


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
            if cancelar is not None and cancelar.is_set():
                raise RuntimeError("Compresion cancelada.")
            _recomprimir_imagen(pikepdf, Image, obj, cfg)
            if progreso:
                progreso(i / len(imagenes) * 90)

        pdf.remove_unreferenced_resources()
        pdf.save(
            salida, compress_streams=True, recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )


def comprimir(entrada, salida=None, nivel="media", progreso=None, cancelar=None):
    """Comprime un PDF. Devuelve la ruta del archivo generado."""
    if nivel not in NIVELES:
        raise ValueError(f"Nivel invalido: {nivel}. Usa: {', '.join(NIVELES)}")
    if not os.path.isfile(entrada):
        raise FileNotFoundError(f"No existe el archivo: {entrada}")

    cfg = NIVELES[nivel]
    salida = salida or ruta_salida_por_defecto(entrada, nivel)
    if os.path.abspath(salida) == os.path.abspath(entrada):
        raise ValueError("El archivo de salida no puede ser el mismo que el de entrada.")

    gs = buscar_ghostscript()
    if gs:
        _comprimir_ghostscript(gs, entrada, salida, cfg)
    else:
        _comprimir_pikepdf(entrada, salida, cfg, progreso, cancelar)

    # Si el PDF ya estaba optimizado y el resultado pesa mas, se conserva el original.
    if os.path.getsize(salida) > os.path.getsize(entrada):
        shutil.copyfile(entrada, salida)

    if progreso:
        progreso(100.0)
    return salida


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
