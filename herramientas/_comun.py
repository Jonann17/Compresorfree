"""Utilidades compartidas por las herramientas de release del propietario.

Ninguna herramienta toca claves privadas: la firma se hace a mano, sin red,
con minisign (ver docs/GUIA_FIRMA.md).
"""

import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import verificacion  # noqa: E402

REPO = "Jonann17/Compresorfree"


def fallar(mensaje):
    print(f"ERROR: {mensaje}", file=sys.stderr)
    sys.exit(1)


def leer_version(texto):
    """'vX.Y.Z' (o 'X.Y.Z') -> 'X.Y.Z'. Sale con error si no es semver estricto."""
    version = texto[1:] if texto.startswith("v") else texto
    if not verificacion.es_semver(version):
        fallar(f"version no valida {texto!r}: debe ser vX.Y.Z")
    return version


def carpeta_release(version):
    return f"release-v{version}"


def nombres_esperados(version):
    """Paquetes de la release (sin manifest.json ni su firma)."""
    return {verificacion.nombre_asset(version, *a) for a in verificacion.ASSETS_ESPERADOS}


def gh(*args, opcional=False):
    """Ejecuta el CLI de GitHub y devuelve su salida (texto). Con opcional, None si falla."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        fallar("no se encontro el comando 'gh' (GitHub CLI). Instalalo e inicia sesion "
               "con 'gh auth login'.")
    if r.returncode != 0:
        if opcional:
            return None
        fallar(f"gh {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout


def ver_release(version, repo):
    """Datos de la release publicada del tag vX.Y.Z."""
    return json.loads(gh("release", "view", f"v{version}", "--repo", repo,
                         "--json", "isDraft,tagName,targetCommitish,assets"))
