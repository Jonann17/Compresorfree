"""Aviso, descarga e instalacion de versiones nuevas desde GitHub Releases.

Modelo de confianza (como SIG-FT): la release oficial publica un manifest.json con
el SHA-256 y el tamano exactos de cada paquete.
- Con claves en claves_confianza.CLAVES, solo una firma minisign valida del manifiesto
  da `verificada=True` y `auto=True`. Sin firma (o con una invalida) nunca hay
  autoinstalacion: solo se ofrece la pagina de descarga.
- Con CLAVES vacia se confia en el SHA-256 del canal oficial: `verificada=False`,
  `auto=True`.
La descarga solo acepta URLs https del asset de la release consultada, con nombre
exacto, y comprueba tamano y SHA-256 antes de entregar el archivo.
"""

import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import claves_confianza
import instalador_constantes
import preferencias
import verificacion
from version import VERSION

REPO = "Jonann17/Compresorfree"
URL_API = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO}/releases/latest"
MANIFIESTO = "manifest.json"
FIRMA = "manifest.json.minisig"
MAX_DESCARGA = 256 * 1024
MAX_API = 1024 * 1024  # respuesta de la API de GitHub
MIN_PAQUETE = 1024 * 1024  # un instalador real pesa mas: menos es una pagina de error
ESPERA_SINAL = 600  # segundos que se espera a que el instalador avise que arranco
MAX_LOG = 256 * 1024
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
ERROR_ELEVACION = 740


class Cancelado(Exception):
    pass


class InstaladorNoArranco(Exception):
    pass


# ------------------------------------------------------------------ Registro (log)

def ruta_log():
    return os.path.join(preferencias.directorio_config(), "logs", "actualizacion.log")


def _log(mensaje):
    """Registro simple con rotacion; nunca interrumpe la actualizacion."""
    try:
        ruta = ruta_log()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        try:
            if os.path.getsize(ruta) > MAX_LOG:
                os.replace(ruta, ruta + ".1")
        except OSError:
            pass
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {mensaje}\n")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Red

def _contexto_ssl():
    # La app compilada no siempre encuentra los certificados del sistema (macOS).
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class _SoloHttps(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("redireccion a una URL que no es https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _abrir(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Compresorfree"})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_contexto_ssl()), _SoloHttps)
    return opener.open(req, timeout=timeout)


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


def _url_asset(tag, nombre):
    return f"https://github.com/{REPO}/releases/download/{tag}/{nombre}"


def _asset_con_url(asset, assets_release, tag):
    """Copia del asset del manifiesto con la URL https tomada de la release, por nombre
    exacto. None si la release no lo trae o la URL no es la oficial de esa release."""
    if asset is None:
        return None
    entrada = assets_release.get(asset["nombre"])
    url = entrada.get("browser_download_url") if entrada else None
    if not isinstance(url, str) or url != _url_asset(tag, asset["nombre"]):
        return None
    return dict(asset, url=url)


def buscar_actualizacion():
    """Devuelve {'version', 'notas', 'fecha', 'url_pagina', 'verificada', 'auto', 'asset'}
    si hay una version mas nueva, o None. `asset` es el paquete de este sistema (con su
    `url`) o None. Sin manifiesto no se anuncia nada."""
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
    cuerpo_notas = release.get("body") if isinstance(release.get("body"), str) else ""
    publicada = release.get("published_at")
    fecha = publicada[:10] if isinstance(publicada, str) else ""
    assets = {a.get("name"): a for a in release.get("assets") or [] if isinstance(a, dict)}
    if MANIFIESTO not in assets:
        return None
    claves = claves_confianza.CLAVES
    manifiesto = None
    try:
        datos = _descargar_pequeno(assets[MANIFIESTO].get("browser_download_url"))
        if claves:
            if FIRMA not in assets:
                raise verificacion.VerificacionFallida("la release no trae firma")
            firma = _descargar_pequeno(assets[FIRMA].get("browser_download_url"))
            manifiesto = verificacion.verificar_manifiesto(datos, firma, claves)
        else:
            manifiesto = verificacion.cargar_manifiesto(datos)
        if manifiesto["tipo"] != "release" or manifiesto["tag"] != tag:
            raise verificacion.VerificacionFallida("el manifiesto no es de esta release")
    except verificacion.VerificacionFallida as e:
        _log(f"manifiesto no aceptado: {e}")
        manifiesto = None
    if manifiesto is None:
        version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
        if not verificacion.es_mas_nueva(version, VERSION):
            return None
        return {"version": version, "notas": cuerpo_notas, "fecha": fecha,
                "url_pagina": url_pagina(version), "verificada": False, "auto": False,
                "asset": None}
    if not verificacion.es_mas_nueva(manifiesto["version"], VERSION):
        return None
    asset = _asset_con_url(verificacion.asset_para_sistema(manifiesto), assets, tag)
    return {"version": manifiesto["version"], "notas": manifiesto.get("notas") or cuerpo_notas,
            "fecha": manifiesto["creado"][:10] or fecha,
            "url_pagina": url_pagina(manifiesto["version"]),
            "verificada": bool(claves), "auto": asset is not None, "asset": asset}


# ------------------------------------------------------------------ Descarga

def dir_descargas():
    return os.path.join(tempfile.gettempdir(), "Compresorfree_Update")


def limpiar_descargas():
    """Borra instaladores y parciales de actualizaciones anteriores."""
    carpeta = dir_descargas()
    try:
        nombres = os.listdir(carpeta)
    except OSError:
        return
    for nombre in nombres:
        ruta = os.path.join(carpeta, nombre)
        try:
            if os.path.isfile(ruta) or os.path.islink(ruta):
                os.remove(ruta)
        except OSError:
            pass


def descargar(asset, destino_dir, progreso=None, cancelar=None):
    """Descarga `asset` (con `url`) a `destino_dir` y devuelve la ruta final.

    Comprueba https, nombre exacto, tamano y SHA-256. `progreso(leidos, total)`;
    `cancelar` es un threading.Event. Ante cualquier fallo no queda archivo parcial."""
    nombre = asset.get("nombre")
    url = asset.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise verificacion.VerificacionFallida("URL de descarga no valida")
    if not isinstance(nombre, str) or not nombre or nombre != os.path.basename(nombre) \
            or nombre in (".", "..") or "\\" in nombre or url.rsplit("/", 1)[-1] != nombre:
        raise verificacion.VerificacionFallida("nombre de asset no valido")
    total = asset.get("tamano")
    if not isinstance(total, int) or isinstance(total, bool) or total < MIN_PAQUETE:
        raise verificacion.VerificacionFallida("tamano del paquete no plausible")
    esperado = asset.get("sha256")
    os.makedirs(destino_dir, exist_ok=True)
    final = os.path.join(destino_dir, nombre)
    parcial = final + ".part"
    _log(f"descargando {nombre} ({total} bytes)")
    try:
        h = hashlib.sha256()
        leidos = 0
        with _abrir(url, timeout=30) as resp, open(parcial, "wb") as f:
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado()
                bloque = resp.read(256 * 1024)
                if not bloque:
                    break
                leidos += len(bloque)
                if leidos > total:
                    raise verificacion.VerificacionFallida(
                        "el archivo es mas grande de lo esperado")
                h.update(bloque)
                f.write(bloque)
                if progreso:
                    progreso(leidos, total)
        if leidos != total:
            raise verificacion.VerificacionFallida("el tamano del archivo no coincide")
        if h.hexdigest() != esperado:
            raise verificacion.VerificacionFallida("el SHA-256 del archivo no coincide")
        os.replace(parcial, final)
    except BaseException as e:
        try:
            os.remove(parcial)
        except OSError:
            pass
        _log(f"descarga fallida: {type(e).__name__}: {e}")
        raise
    _log(f"descarga verificada: {final}")
    return final


# ------------------------------------------------------------------ Instalacion

def _clave_registro_existe():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, instalador_constantes.CLAVE_REGISTRO):
            return True
    except (ImportError, OSError):
        return False


def puede_autoinstalar():
    """Windows instalado con el instalador, o macOS compilado (descarga y abre el dmg)."""
    if not getattr(sys, "frozen", False):
        return False
    if sys.platform == "win32":
        return _clave_registro_existe()
    return sys.platform == "darwin"


def _shell_execute_runas(ruta, parametros):
    import ctypes
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", ruta, parametros, None, 1)


def instalar_windows(ruta_exe, sinal=None, espera=ESPERA_SINAL, dormir=time.sleep,
                     relogio=time.monotonic):
    """Lanza el instalador desacoplado y espera a que cree el archivo SINAL.

    Bloquea: llamar desde un hilo. Vuelve cuando el instalador ya arranco (la app puede
    cerrarse). Lanza InstaladorNoArranco si muere antes o no responde."""
    ruta_exe = str(ruta_exe)
    if sinal is None:
        sinal = os.path.join(os.path.dirname(ruta_exe), "instalador_listo.txt")
    try:
        os.remove(sinal)
    except OSError:
        pass
    args = instalador_constantes.flags_instalador(sinal)
    proceso = None
    _log(f"lanzando instalador {os.path.basename(ruta_exe)}")
    try:
        proceso = subprocess.Popen([ruta_exe, *args], close_fds=True,
                                   creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
    except OSError as e:
        if getattr(e, "winerror", None) != ERROR_ELEVACION:
            raise
        _log("el instalador exige elevacion: ShellExecute runas")
        rc = _shell_execute_runas(ruta_exe, subprocess.list2cmdline(args))
        if rc <= 32:  # <= 32 es error; 5 = el usuario rechazo el UAC
            raise InstaladorNoArranco(
                f"No se pudo iniciar el instalador con permisos de administrador (codigo {rc}).")
    inicio = relogio()
    while not os.path.exists(sinal):
        if proceso is not None and (codigo := proceso.poll()) is not None:
            _log(f"el instalador termino antes de arrancar (codigo {codigo})")
            raise InstaladorNoArranco(
                f"El instalador termino antes de comenzar (codigo {codigo}). "
                f"Puedes ejecutarlo a mano: {ruta_exe}")
        if relogio() - inicio >= espera:
            _log("el instalador no respondio a tiempo")
            raise InstaladorNoArranco("El instalador no respondio a tiempo.")
        dormir(0.2)
    _log("instalador listo (sinal recibido)")


def instalar_macos(ruta_dmg):
    """Abre el dmg; el usuario arrastra Compresorfree a Aplicaciones."""
    _log(f"abriendo {os.path.basename(str(ruta_dmg))}")
    subprocess.run(["open", str(ruta_dmg)], check=True)


def instalar(ruta):
    """Instala segun la plataforma. Devuelve "cerrar" (Windows: la app debe cerrarse para que
    el instalador la reemplace) o "manual" (macOS: el usuario arrastra la app desde el dmg)."""
    if sys.platform == "win32":
        instalar_windows(ruta)
        return "cerrar"
    if sys.platform == "darwin":
        instalar_macos(ruta)
        return "manual"
    raise InstaladorNoArranco("Este sistema no admite la instalacion automatica.")
