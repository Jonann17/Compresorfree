"""Ayudas de prueba para firmas en formato minisign, generadas con `cryptography`
(sin necesitar el binario minisign, asi corren igual en Windows y macOS).

Formato (minisign 0.11):
- clave publica: base64(b"Ed" + key_id(8) + pk(32)); el id se muestra en hex
  mayusculas invertido (little-endian).
- .minisig: 4 lineas; firma = b"ED" + key_id + Ed25519(BLAKE2b-512(datos));
  firma global = Ed25519(firma(64) + trusted_comment_utf8).
"""
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def b64(datos):
    return base64.b64encode(datos).decode("ascii")


class Par:
    """Par Ed25519 con su identidad minisign."""

    def __init__(self, key_id=None):
        self.priv = Ed25519PrivateKey.generate()
        self.pk = self.priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = key_id if key_id is not None else os.urandom(8)

    @property
    def id(self):
        """Id como lo muestra minisign: hex mayusculas, bytes invertidos."""
        return self.key_id[::-1].hex().upper()

    @property
    def publica(self):
        return b64(b"Ed" + self.key_id + self.pk)

    def entrada(self, rol="principal"):
        """Entrada para claves_confianza.CLAVES."""
        return {"id": self.id, "rol": rol, "publica": self.publica}


def firmar(par, datos, comentario, *, algoritmo=b"ED", key_id=None,
           prehash=True, firma_global_sobre=None, comentario_sin_firmar="firma de prueba"):
    """Devuelve el texto de un .minisig.

    algoritmo / key_id: para fabricar casos invalidos (b"Ed", id falso...).
    prehash=False: firma los datos directamente (como el algoritmo legacy).
    firma_global_sobre: bytes alternativos para la firma global.
    """
    mensaje = hashlib.blake2b(datos, digest_size=64).digest() if prehash else datos
    firma = par.priv.sign(mensaje)
    kid = key_id if key_id is not None else par.key_id
    global_ = par.priv.sign(firma_global_sobre if firma_global_sobre is not None
                            else firma + comentario.encode("utf-8"))
    return "\n".join([
        f"untrusted comment: {comentario_sin_firmar}",
        b64(algoritmo + kid + firma),
        f"trusted comment: {comentario}",
        b64(global_),
    ]) + "\n"


def comentario_de(manifiesto):
    return f"compresorfree tipo={manifiesto['tipo']} version={manifiesto['version']}"


def nombre_asset(version, os_="windows", arch="x64", formato="zip"):
    return f"Compresorfree-{version}-{os_}-{arch}.{formato}"


def manifiesto_valido(version="1.2.0", **cambios):
    m = {
        "schema": 1, "app": "Compresorfree", "canal": "estable", "tipo": "release",
        "version": version, "tag": f"v{version}", "commit": "a" * 40,
        "creado": "2026-11-16T12:00:00Z",
        "assets": [{"os": "windows", "arch": "x64", "formato": "zip",
                    "nombre": nombre_asset(version),
                    "sha256": "b" * 64, "tamano": 61234567,
                    "tamano_expandido_max": 250000000}],
    }
    m.update(cambios)
    return m


def manifiesto_rotacion(par_nueva, version="1.2.0"):
    return manifiesto_valido(version, tipo="rotacion", assets=[],
                             claves=[{"id": par_nueva.id, "rol": "principal",
                                      "publica": par_nueva.publica}])


def serializar(manifiesto):
    """Mismo formato que escribe preparar_release.py."""
    return (json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")


def firmar_manifiesto(par, manifiesto, **kw):
    """Devuelve (bytes_del_manifiesto, minisig) con el trusted comment correcto."""
    datos = serializar(manifiesto)
    return datos, firmar(par, datos, kw.pop("comentario", comentario_de(manifiesto)), **kw)
