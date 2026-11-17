"""Verificacion de releases firmadas con minisign (Ed25519).

Cada release publicada lleva un manifest.json (version, commit y SHA-256 de cada
paquete) firmado sin red por el propietario con minisign. La app solo da por buena
una version si la firma corresponde a una de las claves de claves_confianza.py.

Formato minisign (algoritmo "ED", con prehash):
- clave publica: base64 de b"Ed" + key_id (8) + clave Ed25519 (32)
- .minisig: "untrusted comment: ...", base64 de b"ED" + key_id (8) + firma (64)
  sobre BLAKE2b-512 del archivo, "trusted comment: <texto>" y base64 de la firma
  global (64) sobre firma + texto.
"""

import base64
import binascii
import datetime
import hashlib
import json
import platform
import re
import stat
import sys
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROLES = ("principal", "respaldo")
TIPOS = ("release", "rotacion")
ASSETS_ESPERADOS = (("windows", "x64", "zip"), ("macos", "arm64", "dmg"), ("macos", "x64", "dmg"))
MAX_ENTRADAS_ZIP = 20000
RAIZ_ZIP = "Compresorfree"

_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ID_CLAVE = re.compile(r"[0-9A-F]{1,16}")
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

_CAMPOS = {"schema", "app", "canal", "tipo", "version", "tag", "commit", "creado", "assets"}
_CAMPOS_ASSET = {"os", "arch", "formato", "nombre", "sha256", "tamano", "tamano_expandido_max"}
_CAMPOS_CLAVE = {"id", "rol", "publica"}


class VerificacionFallida(Exception):
    pass


# ------------------------------------------------------------------ Firma minisign

def _b64(texto, longitud, que):
    try:
        datos = base64.b64decode(texto.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise VerificacionFallida(f"{que}: base64 invalido") from None
    if len(datos) != longitud:
        raise VerificacionFallida(f"{que}: longitud incorrecta")
    return datos


def id_de_bytes(key_id):
    """key_id (8 bytes little-endian) como lo muestra minisign: hex mayusculas."""
    return key_id[::-1].hex().upper()


def normalizar_id(id_clave):
    """Id en 16 hex mayusculas. minisign omite los ceros a la izquierda al mostrarlo."""
    if not isinstance(id_clave, str) or not id_clave.isascii() \
            or not _ID_CLAVE.fullmatch(id_clave.upper()):
        return None
    return id_clave.upper().zfill(16)


def leer_clave_publica(publica):
    """Linea base64 de una clave publica minisign -> (id, bytes Ed25519)."""
    if not isinstance(publica, str):
        raise VerificacionFallida("clave publica: formato invalido")
    datos = _b64(publica, 42, "clave publica")
    if datos[:2] != b"Ed":
        raise VerificacionFallida("clave publica: algoritmo no soportado")
    return id_de_bytes(datos[2:10]), datos[10:]


def _leer_minisig(minisig):
    if isinstance(minisig, bytes):
        try:
            minisig = minisig.decode("utf-8")
        except UnicodeDecodeError:
            raise VerificacionFallida("firma: no es UTF-8") from None
    if not isinstance(minisig, str):
        raise VerificacionFallida("firma: formato invalido")
    if minisig.endswith("\n"):
        minisig = minisig[:-1]
    # minisign quita el \r final de cada linea al leer.
    lineas = [linea[:-1] if linea.endswith("\r") else linea for linea in minisig.split("\n")]
    if len(lineas) != 4:
        raise VerificacionFallida("firma: deben ser exactamente 4 lineas")
    if not lineas[0].startswith("untrusted comment: "):
        raise VerificacionFallida("firma: falta el comentario no confiable")
    if not lineas[2].startswith("trusted comment: "):
        raise VerificacionFallida("firma: falta el comentario confiable")
    firma = _b64(lineas[1], 74, "firma")
    if firma[:2] != b"ED":
        raise VerificacionFallida("firma: algoritmo no soportado (solo ED)")
    comentario = lineas[2][len("trusted comment: "):]
    global_ = _b64(lineas[3], 64, "firma global")
    return firma[2:10], firma[10:], comentario, global_


def verificar_firma(datos, minisig, claves):
    """Verifica `minisig` sobre `datos` con alguna de `claves`.

    Devuelve {"clave": <entrada de claves>, "comentario": <trusted comment>}.
    """
    key_id, firma, comentario, global_ = _leer_minisig(minisig)
    if not claves:
        raise VerificacionFallida("no hay claves de confianza")
    id_firma = id_de_bytes(key_id)
    digesto = hashlib.blake2b(bytes(datos), digest_size=64).digest()
    texto = comentario.encode("utf-8")
    for clave in claves:
        try:
            id_clave, publica = leer_clave_publica(clave.get("publica"))
        except (VerificacionFallida, AttributeError):
            continue
        # El id solo sirve para elegir candidatas; la firma decide.
        if id_clave != id_firma or normalizar_id(clave.get("id")) != id_clave:
            continue
        pk = Ed25519PublicKey.from_public_bytes(publica)
        try:
            pk.verify(firma, digesto)
            pk.verify(global_, firma + texto)
        except InvalidSignature:
            continue
        return {"clave": clave, "comentario": comentario}
    raise VerificacionFallida("firma no valida o de una clave desconocida")


# ------------------------------------------------------------------ Manifiesto

def es_semver(version):
    return isinstance(version, str) and _SEMVER.fullmatch(version) is not None


def _tupla(version):
    return tuple(int(p) for p in _SEMVER.fullmatch(version).groups())


def es_mas_nueva(version, actual):
    if not es_semver(version):
        return False
    base = _tupla(actual) if es_semver(actual) else (0, 0, 0)
    return _tupla(version) > base


def nombre_asset(version, os_, arch, formato):
    return f"Compresorfree-{version}-{os_}-{arch}.{formato}"


def _sin_duplicados(pares):
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise VerificacionFallida(f"manifiesto: clave duplicada {clave!r}")
        resultado[clave] = valor
    return resultado


def _rechazar_constante(nombre):
    raise VerificacionFallida(f"manifiesto: valor no permitido {nombre}")


def _entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _exigir(condicion, mensaje):
    if not condicion:
        raise VerificacionFallida(f"manifiesto: {mensaje}")


def _validar_asset(asset, version):
    _exigir(isinstance(asset, dict) and set(asset) == _CAMPOS_ASSET, "asset con campos incorrectos")
    _exigir(asset["os"] in ("windows", "macos"), "os invalido")
    _exigir(asset["arch"] in ("x64", "arm64"), "arch invalida")
    _exigir(asset["formato"] in ("zip", "dmg"), "formato invalido")
    _exigir(asset["nombre"] == nombre_asset(version, asset["os"], asset["arch"], asset["formato"]),
            "nombre de asset invalido")
    _exigir(isinstance(asset["sha256"], str) and _HEX64.fullmatch(asset["sha256"]), "sha256 invalido")
    _exigir(_entero(asset["tamano"]) and asset["tamano"] > 0, "tamano invalido")
    maximo = asset["tamano_expandido_max"]
    _exigir(_entero(maximo) and maximo >= asset["tamano"], "tamano_expandido_max invalido")
    if asset["formato"] == "dmg":
        _exigir(maximo == asset["tamano"], "tamano_expandido_max de un dmg debe ser su tamano")


def _validar_clave(clave):
    _exigir(isinstance(clave, dict) and set(clave) == _CAMPOS_CLAVE, "clave con campos incorrectos")
    _exigir(isinstance(clave["id"], str) and _ID_CLAVE.fullmatch(clave["id"]), "id de clave invalido")
    clave_id = normalizar_id(clave["id"])
    _exigir(clave["rol"] in ROLES, "rol de clave invalido")
    try:
        id_publica, _ = leer_clave_publica(clave["publica"])
    except VerificacionFallida:
        raise VerificacionFallida("manifiesto: clave publica invalida") from None
    _exigir(id_publica == clave_id, "id de clave no coincide con su clave publica")


def cargar_manifiesto(datos):
    """Interpreta y valida el manifiesto (bytes). No comprueba la firma."""
    try:
        texto = bytes(datos).decode("utf-8")
    except UnicodeDecodeError:
        raise VerificacionFallida("manifiesto: no es UTF-8") from None
    try:
        m = json.loads(texto, object_pairs_hook=_sin_duplicados,
                       parse_constant=_rechazar_constante)
    except ValueError:
        raise VerificacionFallida("manifiesto: JSON invalido") from None

    _exigir(isinstance(m, dict), "no es un objeto")
    tipo = m.get("tipo")
    _exigir(tipo in TIPOS, "tipo invalido")
    esperados = _CAMPOS | {"claves"} if tipo == "rotacion" else _CAMPOS
    _exigir(set(m) == esperados, "campos incorrectos")
    _exigir(_entero(m["schema"]) and m["schema"] == 1, "schema no soportado")
    _exigir(m["app"] == "Compresorfree", "app incorrecta")
    _exigir(m["canal"] == "estable", "canal incorrecto")
    _exigir(es_semver(m["version"]), "version no es X.Y.Z")
    _exigir(m["tag"] == "v" + m["version"], "tag no coincide con la version")
    _exigir(isinstance(m["commit"], str) and _HEX40.fullmatch(m["commit"]), "commit invalido")
    _exigir(isinstance(m["creado"], str) and _FECHA.fullmatch(m["creado"]), "fecha invalida")
    try:
        datetime.datetime.strptime(m["creado"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise VerificacionFallida("manifiesto: fecha invalida") from None

    assets = m["assets"]
    _exigir(isinstance(assets, list), "assets no es una lista")
    if tipo == "release":
        _exigir(assets, "una release necesita assets")
    else:
        # La clave de respaldo firma rotaciones: nunca deben traer paquetes instalables.
        _exigir(assets == [], "una rotacion no puede llevar paquetes")
    for asset in assets:
        _validar_asset(asset, m["version"])
    sistemas = [(a["os"], a["arch"]) for a in assets]
    _exigir(len(sistemas) == len(set(sistemas)), "asset repetido para un mismo sistema")

    if tipo == "rotacion":
        claves = m["claves"]
        _exigir(isinstance(claves, list) and claves, "rotacion sin claves")
        for clave in claves:
            _validar_clave(clave)
        ids = [normalizar_id(c["id"]) for c in claves]
        _exigir(len(ids) == len(set(ids)), "clave repetida")
    return m


def verificar_manifiesto(datos, minisig, claves):
    """Firma primero, despues esquema, rol y trusted comment. Devuelve el manifiesto."""
    resultado = verificar_firma(datos, minisig, claves)
    m = cargar_manifiesto(datos)
    rol = resultado["clave"].get("rol")
    if rol == "principal":
        permitidos = ("release", "rotacion")
    elif rol == "respaldo":
        permitidos = ("rotacion",)
    else:
        permitidos = ()
    if m["tipo"] not in permitidos:
        raise VerificacionFallida(f"la clave {rol!r} no puede firmar tipo={m['tipo']}")
    if resultado["comentario"] != f"compresorfree tipo={m['tipo']} version={m['version']}":
        raise VerificacionFallida("el comentario confiable no coincide con el manifiesto")
    return m


# ------------------------------------------------------------------ Paquetes

def asset_para_sistema(manifiesto, os_=None, arch=None):
    if manifiesto.get("tipo") != "release":
        raise VerificacionFallida("solo una release ofrece paquetes")
    if os_ is None:
        os_ = {"win32": "windows", "darwin": "macos"}.get(sys.platform)
    if arch is None:
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return next((a for a in manifiesto.get("assets", [])
                 if a["os"] == os_ and a["arch"] == arch), None)


def verificar_archivo(ruta, asset):
    """Comprueba tamano y SHA-256 de un paquete descargado."""
    h = hashlib.sha256()
    leidos = 0
    with open(ruta, "rb") as f:
        while bloque := f.read(1024 * 1024):
            leidos += len(bloque)
            if leidos > asset["tamano"]:
                raise VerificacionFallida("el archivo es mas grande de lo esperado")
            h.update(bloque)
    if leidos != asset["tamano"]:
        raise VerificacionFallida("el tamano del archivo no coincide")
    if h.hexdigest() != asset["sha256"]:
        raise VerificacionFallida("el SHA-256 del archivo no coincide")


_RESERVADOS_WINDOWS = {"con", "prn", "aux", "nul",
                       *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _es_reservado_windows(nombre):
    return nombre.split(".")[0].casefold() in _RESERVADOS_WINDOWS


def validar_zip(ruta, asset):
    """Estructura segura del ZIP de Windows antes de extraerlo (para PR3-C)."""
    try:
        with zipfile.ZipFile(ruta) as z:
            entradas = z.infolist()
    except (zipfile.BadZipFile, OSError) as e:
        raise VerificacionFallida(f"zip invalido: {e}") from None
    if not entradas:
        raise VerificacionFallida("zip vacio")
    if len(entradas) > MAX_ENTRADAS_ZIP:
        raise VerificacionFallida("zip con demasiadas entradas")
    total = 0
    vistos, archivos, carpetas_implicitas = set(), set(), set()
    for e in entradas:
        nombre = e.filename.replace("\\", "/")
        if nombre.startswith("/") or ":" in nombre or "\x00" in nombre:
            raise VerificacionFallida(f"zip: ruta no permitida {e.filename!r}")
        es_carpeta = nombre.endswith("/")
        partes = (nombre[:-1] if es_carpeta else nombre).split("/")
        if partes[0] != RAIZ_ZIP:
            raise VerificacionFallida(f"zip: fuera de {RAIZ_ZIP}/: {e.filename!r}")
        if any(p in ("", ".", "..") or p != p.rstrip(". ") or _es_reservado_windows(p)
               for p in partes):
            raise VerificacionFallida(f"zip: ruta no permitida {e.filename!r}")
        if len(partes) == 1 and not es_carpeta:
            raise VerificacionFallida(f"zip: {RAIZ_ZIP} debe ser una carpeta")
        modo = (e.external_attr >> 16) & 0o170000
        if modo == stat.S_IFLNK:
            raise VerificacionFallida(f"zip: enlace simbolico {e.filename!r}")
        if modo not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise VerificacionFallida(f"zip: tipo de archivo no permitido {e.filename!r}")
        ruta_norm = "/".join(partes).casefold()
        if ruta_norm in vistos or ruta_norm in carpetas_implicitas and not es_carpeta:
            raise VerificacionFallida(f"zip: entrada repetida {e.filename!r}")
        if any("/".join(partes[:i]).casefold() in archivos for i in range(1, len(partes))):
            raise VerificacionFallida(f"zip: un archivo se usa como carpeta {e.filename!r}")
        vistos.add(ruta_norm)
        (carpetas_implicitas if es_carpeta else archivos).add(ruta_norm)
        carpetas_implicitas.update("/".join(partes[:i]).casefold() for i in range(1, len(partes)))
        total += e.file_size
    if total > asset["tamano_expandido_max"]:
        raise VerificacionFallida("zip: expandido supera el maximo del manifiesto")
