"""Actualizaciones automaticas desde GitHub Releases.

Cada vez que se publica un tag vX.Y.Z, GitHub Actions compila la app y la sube
a Releases. La app compara su VERSION con la ultima release y, si hay una mas
nueva, descarga el paquete de su sistema, reemplaza la app y la vuelve a abrir.
"""

import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from version import VERSION

REPO = "Jonann17/Compresorfree"
URL_API = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO}/releases/latest"


def _contexto_ssl():
    # La app compilada no siempre encuentra los certificados del sistema (macOS).
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _abrir(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Compresorfree"})
    return urllib.request.urlopen(req, timeout=timeout, context=_contexto_ssl())


def _a_tupla(version):
    partes = []
    for p in version.lstrip("vV").split("."):
        num = "".join(c for c in p if c.isdigit())
        partes.append(int(num) if num else 0)
    return tuple(partes)


def es_app_compilada():
    return getattr(sys, "frozen", False)


def nombre_paquete():
    """Nombre del archivo de la release que corresponde a este sistema."""
    if sys.platform == "win32":
        return "Compresorfree-Windows.zip"
    if sys.platform == "darwin":
        chip = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
        return f"Compresorfree-macOS-{chip}.dmg"
    return None


def buscar_actualizacion():
    """Devuelve {'version', 'url', 'notas'} si hay una version mas nueva, o None."""
    try:
        with _abrir(URL_API) as resp:
            release = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # todavia no hay ninguna release publicada
            return None
        raise
    nueva = release.get("tag_name", "")
    if _a_tupla(nueva) <= _a_tupla(VERSION):
        return None
    paquete = nombre_paquete()
    url = next((a["browser_download_url"] for a in release.get("assets", [])
                if a["name"] == paquete), None)
    return {"version": nueva.lstrip("vV"), "url": url, "notas": release.get("body") or ""}


def descargar(url, progreso=None):
    destino = os.path.join(tempfile.mkdtemp(prefix="compresorfree_"), url.rsplit("/", 1)[-1])
    with _abrir(url, timeout=60) as resp, open(destino, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        leidos = 0
        while True:
            bloque = resp.read(256 * 1024)
            if not bloque:
                break
            f.write(bloque)
            leidos += len(bloque)
            if progreso and total:
                progreso(leidos / total * 100)
    return destino


def instalar(paquete):
    """Prepara el reemplazo de la app. Despues hay que cerrar la app:
    un script espera a que se cierre, copia la version nueva y la vuelve a abrir."""
    trabajo = os.path.dirname(paquete)
    pid = os.getpid()

    if sys.platform == "win32":
        carpeta_app = os.path.dirname(sys.executable)
        with zipfile.ZipFile(paquete) as z:
            z.extractall(trabajo)
        nueva = os.path.join(trabajo, "Compresorfree")
        script = os.path.join(trabajo, "actualizar.bat")
        with open(script, "w", encoding="utf-8") as f:
            f.write(f"""@echo off
:esperar
tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto esperar)
robocopy "{nueva}" "{carpeta_app}" /E /NFL /NDL /NJH /NJS /R:5 /W:1 >nul
start "" "{sys.executable}"
""")
        subprocess.Popen(
            ["cmd", "/c", script],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )

    elif sys.platform == "darwin":
        # sys.executable = .../Compresorfree.app/Contents/MacOS/Compresorfree
        app = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
        montaje = os.path.join(trabajo, "montaje")
        nueva = os.path.join(trabajo, "Compresorfree.app")
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly",
                        "-mountpoint", montaje, paquete], check=True, capture_output=True)
        try:
            subprocess.run(["ditto", os.path.join(montaje, "Compresorfree.app"), nueva],
                           check=True, capture_output=True)
        finally:
            subprocess.run(["hdiutil", "detach", montaje, "-quiet"], capture_output=True)
        script = os.path.join(trabajo, "actualizar.sh")
        with open(script, "w") as f:
            f.write(f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 1; done
rm -rf "{app}.anterior"
mv "{app}" "{app}.anterior"
if ditto "{nueva}" "{app}"; then
    rm -rf "{app}.anterior"
    xattr -cr "{app}" 2>/dev/null
else
    rm -rf "{app}"; mv "{app}.anterior" "{app}"  # si falla, se restaura la version anterior
fi
open "{app}"
""")
        subprocess.Popen(["/bin/sh", script], start_new_session=True, close_fds=True)

    else:
        raise RuntimeError("Actualizacion automatica no disponible en este sistema.")
