"""Preferencias del usuario (tipo, nivel, carpeta de salida) en un JSON. Sin GUI."""
import json
import os
import sys
import tempfile

TIPOS_VALIDOS = ("video", "pdf")
NIVELES_VALIDOS = ("baja", "media", "alta")
DEFECTO = {"tipo": "video", "nivel": "media", "carpeta": ""}


def directorio_config():
    if os.environ.get("COMPRESORFREE_CONFIG"):  # p. ej. pruebas o instalacion portable
        return os.environ["COMPRESORFREE_CONFIG"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "Compresorfree")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "Compresorfree")
    return os.path.join(os.path.expanduser("~"), ".config", "compresorfree")


def ruta_config():
    return os.path.join(directorio_config(), "preferencias.json")


def cargar(ruta=None):
    """Preferencias validadas; archivo ausente/corrupto o valores raros -> defecto."""
    prefs = dict(DEFECTO)
    try:
        with open(ruta or ruta_config(), encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return prefs
    if not isinstance(datos, dict):
        return prefs
    if datos.get("tipo") in TIPOS_VALIDOS:
        prefs["tipo"] = datos["tipo"]
    if datos.get("nivel") in NIVELES_VALIDOS:
        prefs["nivel"] = datos["nivel"]
    carpeta = datos.get("carpeta")
    if isinstance(carpeta, str) and carpeta and os.path.isdir(carpeta):
        prefs["carpeta"] = carpeta
    return prefs


def guardar(prefs, ruta=None):
    """Escritura atomica (temporal + os.replace). Devuelve False si no se pudo."""
    ruta = ruta or ruta_config()
    tmp = None
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ruta), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({k: prefs.get(k, DEFECTO[k]) for k in DEFECTO}, f, indent=2)
        os.replace(tmp, ruta)
        return True
    except OSError:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False
