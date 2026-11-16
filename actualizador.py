"""Aviso de versiones nuevas desde GitHub Releases.

Cada release publicada lleva un manifest.json firmado con minisign por el
propietario. La app solo anuncia una version como verificada si la firma
corresponde a una clave de claves_confianza.py. No descarga ni instala nada:
solo abre la pagina de descarga.
"""

import json
import ssl
import urllib.error
import urllib.request

import claves_confianza
import verificacion
from version import VERSION

REPO = "Jonann17/Compresorfree"
URL_API = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO}/releases/latest"
MANIFIESTO = "manifest.json"
FIRMA = "manifest.json.minisig"
MAX_DESCARGA = 256 * 1024
MAX_API = 1024 * 1024  # respuesta de la API de GitHub


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


def _descargar_pequeno(url):
    if not isinstance(url, str) or not url.startswith("https://"):
        raise verificacion.VerificacionFallida("URL de descarga no valida")
    with _abrir(url) as resp:
        datos = resp.read(MAX_DESCARGA + 1)
    if len(datos) > MAX_DESCARGA:
        raise verificacion.VerificacionFallida("archivo de firma demasiado grande")
    return datos


def url_pagina(version):
    return f"https://github.com/{REPO}/releases/tag/v{version}"


def buscar_actualizacion():
    """Devuelve {'version', 'notas', 'url_pagina', 'verificada'} si hay una version
    mas nueva, o None. Una release sin manifiesto firmado no se anuncia."""
    try:
        with _abrir(URL_API) as resp:
            cuerpo = resp.read(MAX_API + 1)
        if len(cuerpo) > MAX_API:
            return None
        release = json.loads(cuerpo)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # todavia no hay ninguna release publicada
            return None
        raise
    if not isinstance(release, dict):
        return None
    tag = release.get("tag_name")
    notas = release.get("body") if isinstance(release.get("body"), str) else ""
    assets = {a.get("name"): a for a in release.get("assets") or [] if isinstance(a, dict)}
    if MANIFIESTO not in assets or FIRMA not in assets:
        return None
    try:
        datos = _descargar_pequeno(assets[MANIFIESTO].get("browser_download_url"))
        firma = _descargar_pequeno(assets[FIRMA].get("browser_download_url"))
        manifiesto = verificacion.verificar_manifiesto(datos, firma, claves_confianza.CLAVES)
        if manifiesto["tipo"] != "release" or manifiesto["tag"] != tag:
            raise verificacion.VerificacionFallida("el manifiesto no es de esta release")
    except verificacion.VerificacionFallida:
        version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
        if not verificacion.es_mas_nueva(version, VERSION):
            return None
        return {"version": version, "notas": notas, "url_pagina": url_pagina(version),
                "verificada": False}
    if not verificacion.es_mas_nueva(manifiesto["version"], VERSION):
        return None
    return {"version": manifiesto["version"], "notas": notas,
            "url_pagina": url_pagina(manifiesto["version"]), "verificada": True}
