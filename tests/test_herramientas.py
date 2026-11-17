"""Herramientas de release (preparar_release / publicar_release --solo-firma) con un `gh` FALSO.

El falso simula una release YA PUBLICADA (con manifest.json) y registra cada llamada, para
comprobar que no se sube la firma cuando alguna comprobacion falla."""
import hashlib
import io
import json
import os
import sys
import zipfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ruta in (RAIZ, os.path.join(RAIZ, "herramientas")):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

import _comun  # noqa: E402
import claves_confianza  # noqa: E402
import preparar_release  # noqa: E402
import publicar_release  # noqa: E402
import verificacion  # noqa: E402
from firma_util import (Par, firmar_manifiesto, manifiesto_rotacion,  # noqa: E402
                        manifiesto_valido, serializar)

VERSION = "1.2.0"
COMMIT = "a" * 40
CARPETA = f"release-v{VERSION}"
NOMBRES = sorted(_comun.nombres_esperados(VERSION))


def zip_valido(extra=b""):
    import io
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Compresorfree/Compresorfree.exe", b"exe" + extra)
    return b.getvalue()


def paquetes(extra=b""):
    return {n: (zip_valido(extra) if n.endswith(".zip") else b"bin " + n.encode() + extra)
            for n in NOMBRES}


class GhFalso:
    def __init__(self, assets, *, draft=False):
        self.assets = dict(assets)          # archivos de la release en GitHub
        self.draft = draft
        self.llamadas = []

    def __call__(self, *args, opcional=False):
        self.llamadas.append(args)
        if args[:2] == ("release", "view"):
            return json.dumps({"isDraft": self.draft, "tagName": args[2],
                               "targetCommitish": COMMIT,
                               "assets": [{"name": n} for n in self.assets]})
        if args[:2] == ("release", "download"):
            destino = args[args.index("--dir") + 1]
            os.makedirs(destino, exist_ok=True)
            nombres = [args[args.index("--pattern") + 1]] if "--pattern" in args \
                else list(self.assets)
            for n in nombres:
                with open(os.path.join(destino, n), "wb") as f:
                    f.write(self.assets[n])
            return ""
        if args[:2] == ("release", "upload"):
            for ruta in args[args.index("--clobber") + 1:]:
                with open(ruta, "rb") as f:
                    self.assets[os.path.basename(ruta)] = f.read()
            return ""
        raise AssertionError(f"llamada a gh no prevista: {args}")

    def hizo(self, *prefijo):
        return any(a[:len(prefijo)] == prefijo for a in self.llamadas)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    par = Par()
    monkeypatch.setattr(claves_confianza, "CLAVES", [par.entrada("principal")])
    return par


def instalar(monkeypatch, falso):
    for modulo in (_comun, publicar_release, preparar_release):
        monkeypatch.setattr(modulo, "gh", falso)
    return falso


def manifiesto_de(contenidos, **cambios):
    assets = []
    for os_, arch, formato in verificacion.ASSETS_ESPERADOS:
        nombre = verificacion.nombre_asset(VERSION, os_, arch, formato)
        datos = contenidos[nombre]
        expandido = len(datos)
        if formato == "zip":
            with zipfile.ZipFile(io.BytesIO(datos)) as z:
                expandido = max(len(datos), sum(e.file_size for e in z.infolist()))
        assets.append({"os": os_, "arch": arch, "formato": formato, "nombre": nombre,
                       "sha256": hashlib.sha256(datos).hexdigest(), "tamano": len(datos),
                       "tamano_expandido_max": expandido})
    m = manifiesto_valido(VERSION, assets=assets, commit=COMMIT, notas="- cambios")
    m.update(cambios)
    return m


def release_publicada(monkeypatch, contenidos, **cambios):
    """GhFalso con los paquetes y el manifest.json (sin firma) como los deja Actions."""
    datos = serializar(manifiesto_de(contenidos, **cambios))
    return instalar(monkeypatch, GhFalso({**contenidos, "manifest.json": datos})), datos


def escribir_firma(datos, minisig, manifiesto_local=None):
    os.makedirs(CARPETA, exist_ok=True)
    with open(os.path.join(CARPETA, "manifest.json"), "wb") as f:
        f.write(datos if manifiesto_local is None else manifiesto_local)
    with open(os.path.join(CARPETA, "manifest.json.minisig"), "w") as f:
        f.write(minisig)


def firmar_solo(monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["publicar_release.py", "--solo-firma", f"v{VERSION}", *extra])
    publicar_release.main()


def preparar(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["preparar_release.py", f"v{VERSION}"])
    preparar_release.main()


# ------------------------------------------------------------------ preparar_release

def test_preparar_descarga_comprueba_y_muestra_el_comando(entorno, monkeypatch, capsys):
    falso, datos = release_publicada(monkeypatch, paquetes())
    preparar(monkeypatch)
    salida = capsys.readouterr().out
    assert set(os.listdir(CARPETA)) == set(NOMBRES) | {"manifest.json"}
    assert "minisign -S" in salida and "--solo-firma" in salida
    assert f"version={VERSION}" in salida
    assert not falso.hizo("release", "upload")


def test_preparar_con_paquete_alterado_falla(entorno, monkeypatch):
    contenidos = paquetes()
    falso, _ = release_publicada(monkeypatch, contenidos)
    falso.assets[NOMBRES[0]] = contenidos[NOMBRES[0]][:-1] + b"X"
    with pytest.raises(SystemExit):
        preparar(monkeypatch)


def test_preparar_con_archivo_inesperado_falla(entorno, monkeypatch):
    falso, _ = release_publicada(monkeypatch, paquetes())
    falso.assets["Compresorfree-Windows.zip"] = b"viejo"
    with pytest.raises(SystemExit):
        preparar(monkeypatch)


def test_preparar_si_falta_el_manifiesto_falla(entorno, monkeypatch):
    falso, _ = release_publicada(monkeypatch, paquetes())
    del falso.assets["manifest.json"]
    with pytest.raises(SystemExit):
        preparar(monkeypatch)


def test_preparar_con_borrador_falla(entorno, monkeypatch):
    falso, _ = release_publicada(monkeypatch, paquetes())
    falso.draft = True
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not falso.hizo("release", "download")


def test_preparar_con_carpeta_existente_falla(entorno, monkeypatch):
    release_publicada(monkeypatch, paquetes())
    os.makedirs(CARPETA)
    open(os.path.join(CARPETA, "x"), "w").close()
    with pytest.raises(SystemExit):
        preparar(monkeypatch)


# ------------------------------------------------------------------ publicar_release --solo-firma

def test_solo_firma_sube_unicamente_la_firma(entorno, monkeypatch, capsys):
    falso, datos = release_publicada(monkeypatch, paquetes())
    _, minisig = firmar_manifiesto(entorno, manifiesto_de(paquetes()))
    escribir_firma(datos, minisig)
    firmar_solo(monkeypatch)
    assert f"Firma de v{VERSION} subida." in capsys.readouterr().out
    subir = next(a for a in falso.llamadas if a[:2] == ("release", "upload"))
    assert [os.path.basename(r) for r in subir[subir.index("--clobber") + 1:]] == \
        ["manifest.json.minisig"]
    assert "manifest.json.minisig" in falso.assets


def test_solo_firma_con_firma_invalida_no_sube(entorno, monkeypatch):
    falso, datos = release_publicada(monkeypatch, paquetes())
    _, minisig = firmar_manifiesto(Par(), manifiesto_de(paquetes()))  # firma ajena
    escribir_firma(datos, minisig)
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert falso.llamadas == []


def test_solo_firma_sin_claves_de_confianza_falla(entorno, monkeypatch):
    falso, datos = release_publicada(monkeypatch, paquetes())
    _, minisig = firmar_manifiesto(entorno, manifiesto_de(paquetes()))
    escribir_firma(datos, minisig)
    monkeypatch.setattr(claves_confianza, "CLAVES", [])
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert falso.llamadas == []


def test_solo_firma_con_manifiesto_distinto_del_publicado_no_sube(entorno, monkeypatch, capsys):
    contenidos = paquetes()
    falso, _ = release_publicada(monkeypatch, contenidos)
    local, minisig = firmar_manifiesto(entorno, manifiesto_de(contenidos, notas="- otras"))
    escribir_firma(local, minisig)
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert "identico" in capsys.readouterr().err
    assert not falso.hizo("release", "upload")


def test_solo_firma_con_manifiesto_manipulado_tras_firmar(entorno, monkeypatch):
    falso, datos = release_publicada(monkeypatch, paquetes())
    _, minisig = firmar_manifiesto(entorno, manifiesto_de(paquetes()))
    escribir_firma(datos, minisig, manifiesto_local=datos.replace(b'"tamano"', b'"tamano" '))
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert falso.llamadas == []


def test_solo_firma_con_rotacion_o_version_ajena_falla(entorno, monkeypatch, capsys):
    falso, datos = release_publicada(monkeypatch, paquetes())
    rot, minisig = firmar_manifiesto(entorno, manifiesto_rotacion(Par(), VERSION))
    escribir_firma(rot, minisig)
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    otro, minisig = firmar_manifiesto(entorno, manifiesto_valido("1.3.0"))
    escribir_firma(otro, minisig)
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert not falso.hizo("release", "upload")


def test_solo_firma_si_falta_un_archivo_local_falla(entorno, monkeypatch):
    falso, _ = release_publicada(monkeypatch, paquetes())
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert falso.llamadas == []


def test_solo_firma_con_borrador_falla(entorno, monkeypatch):
    falso, datos = release_publicada(monkeypatch, paquetes())
    falso.draft = True
    _, minisig = firmar_manifiesto(entorno, manifiesto_de(paquetes()))
    escribir_firma(datos, minisig)
    with pytest.raises(SystemExit):
        firmar_solo(monkeypatch)
    assert not falso.hizo("release", "upload")
