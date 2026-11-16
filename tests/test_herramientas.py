"""PR3-A: herramientas de release (preparar_release / publicar_release) con un `gh` FALSO.

El falso simula un borrador de GitHub y registra cada llamada, para comprobar que no se
sube ni se publica nada cuando alguna comprobacion falla."""
import hashlib
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
OTRO_COMMIT = "b" * 40
CARPETA = f"release-v{VERSION}"
NOMBRES = sorted(_comun.nombres_esperados(VERSION))


def zip_valido(extra=b""):
    import io
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Compresorfree/Compresorfree.exe", b"exe" + extra)
    return b.getvalue()


def paquetes(extra=b""):
    """Contenido de los tres paquetes esperados (el zip es valido)."""
    return {n: (zip_valido(extra) if n.endswith(".zip") else b"dmg " + n.encode() + extra)
            for n in NOMBRES}


class GhFalso:
    """Simula `gh`. `cambios` = {n: dict}: sobrescribe campos de la n-esima llamada a
    `release view` (1-based) para simular un borrador que cambia durante la publicacion."""

    def __init__(self, assets, *, draft=True, commit=COMMIT, estado_compare="identical",
                 cambios=None, descarga=None):
        self.assets = dict(assets)          # lo que hay en el borrador de GitHub
        self.draft, self.commit = draft, commit
        self.estado_compare = estado_compare
        self.cambios = cambios or {}
        self.descarga = descarga or {}      # contenido distinto al descargar (nombre -> bytes)
        self.llamadas = []
        self.vistas = 0

    def __call__(self, *args, opcional=False):
        self.llamadas.append(args)
        if args[:2] == ("release", "view") and args[2].startswith("v"):
            self.vistas += 1
            datos = {"isDraft": self.draft, "tagName": args[2], "targetCommitish": self.commit,
                     "assets": [{"name": n} for n in self.assets]}
            datos.update(self.cambios.get(self.vistas, {}))
            return json.dumps(datos)
        if args[:2] == ("release", "view"):   # release publicada anterior
            return None
        if args[0] == "api" and "/git/ref/tags/" in args[1]:
            return None                        # el tag aun no existe
        if args[0] == "api" and "/compare/" in args[1]:
            return json.dumps({"status": self.estado_compare})
        if args[:2] == ("release", "download"):
            destino = args[args.index("--dir") + 1]
            os.makedirs(destino, exist_ok=True)
            if "--pattern" in args:
                nombres = [args[args.index("--pattern") + 1]]
            else:
                nombres = [n for n in self.assets if n not in ("manifest.json",
                                                                "manifest.json.minisig")]
            for n in nombres:
                with open(os.path.join(destino, n), "wb") as f:
                    f.write(self.descarga.get(n, self.assets[n]))
            return ""
        if args[:2] == ("release", "upload"):
            for ruta in args[args.index("--clobber") + 1:]:
                self.assets[os.path.basename(ruta)] = b"subido"
            return ""
        if args[:2] == ("release", "edit"):
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
        assets.append({"os": os_, "arch": arch, "formato": formato, "nombre": nombre,
                       "sha256": hashlib.sha256(datos).hexdigest(), "tamano": len(datos),
                       "tamano_expandido_max": len(datos)})
    m = manifiesto_valido(VERSION, assets=assets, commit=COMMIT)
    m.update(cambios)
    return m


def escribir_local(contenidos, datos, minisig, extra_local=None):
    os.makedirs(CARPETA, exist_ok=True)
    for n, c in {**contenidos, **(extra_local or {})}.items():
        with open(os.path.join(CARPETA, n), "wb") as f:
            f.write(c)
    with open(os.path.join(CARPETA, "manifest.json"), "wb") as f:
        f.write(datos)
    with open(os.path.join(CARPETA, "manifest.json.minisig"), "w") as f:
        f.write(minisig)


def publicar(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["publicar_release.py", f"v{VERSION}"])
    publicar_release.main()


def nada_subido_ni_publicado(falso):
    assert not falso.hizo("release", "upload"), falso.llamadas
    assert not falso.hizo("release", "edit"), falso.llamadas


@pytest.fixture
def escenario(entorno, monkeypatch):
    """Borrador correcto, firmado y listo: devuelve (gh_falso, contenidos, par)."""
    contenidos = paquetes()
    datos, minisig = firmar_manifiesto(entorno, manifiesto_de(contenidos))
    escribir_local(contenidos, datos, minisig)
    return instalar(monkeypatch, GhFalso(contenidos)), contenidos, entorno


# ------------------------------------------------------------------ publicar_release

def test_publicar_caso_feliz_sube_y_despues_publica(escenario, monkeypatch, capsys):
    falso, _, _ = escenario
    publicar(monkeypatch)
    assert f"Release v{VERSION} publicada." in capsys.readouterr().out
    posicion = {a[:2]: i for i, a in reversed(list(enumerate(falso.llamadas)))}
    assert ("release", "upload") in posicion and ("release", "edit") in posicion
    assert posicion[("release", "upload")] < posicion[("release", "edit")]
    editar = next(a for a in falso.llamadas if a[:2] == ("release", "edit"))
    assert editar[2] == f"v{VERSION}" and "--draft=false" in editar
    subir = next(a for a in falso.llamadas if a[:2] == ("release", "upload"))
    assert [os.path.basename(r) for r in subir[-2:]] == ["manifest.json", "manifest.json.minisig"]


def test_publicar_con_firma_invalida_no_toca_github(escenario, monkeypatch):
    falso, contenidos, _ = escenario
    datos, minisig = firmar_manifiesto(Par(), manifiesto_de(contenidos))  # firma ajena
    escribir_local(contenidos, datos, minisig)
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)
    assert falso.llamadas == []


def test_publicar_con_manifiesto_manipulado_despues_de_firmar(escenario, monkeypatch):
    falso, contenidos, par = escenario
    datos, minisig = firmar_manifiesto(par, manifiesto_de(contenidos))
    escribir_local(contenidos, datos.replace(b'"tamano"', b'"tamano" '), minisig)
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert falso.llamadas == []


def test_publicar_sin_claves_de_confianza_falla(escenario, monkeypatch):
    falso, _, _ = escenario
    monkeypatch.setattr(claves_confianza, "CLAVES", [])
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert falso.llamadas == []


def test_publicar_con_rotacion_firmada_falla(escenario, monkeypatch, capsys):
    falso, contenidos, par = escenario
    datos, minisig = firmar_manifiesto(par, manifiesto_rotacion(Par(), VERSION))
    escribir_local(contenidos, datos, minisig)
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert "no es de la release" in capsys.readouterr().err  # lo para la comprobacion de tipo
    assert falso.llamadas == []


def test_publicar_con_manifiesto_de_otra_version_falla(escenario, monkeypatch, capsys):
    falso, contenidos, par = escenario
    m = manifiesto_valido("1.3.0")
    datos, minisig = firmar_manifiesto(par, m)
    escribir_local(contenidos, datos, minisig)
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert "no es de la release" in capsys.readouterr().err
    assert falso.llamadas == []


def test_publicar_con_manifiesto_que_no_lista_todos_los_paquetes_falla(escenario, monkeypatch):
    falso, contenidos, par = escenario
    m = manifiesto_de(contenidos)
    m["assets"] = m["assets"][:1]
    datos, minisig = firmar_manifiesto(par, m)
    escribir_local(contenidos, datos, minisig)
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)
    assert falso.llamadas == []


def test_publicar_si_ya_esta_publicada_falla(escenario, monkeypatch):
    falso, _, _ = escenario
    falso.draft = False
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)
    assert falso.vistas == 1  # para en la primera comprobacion, no en una posterior


def test_publicar_con_commit_del_borrador_distinto_falla(escenario, monkeypatch):
    falso, _, _ = escenario
    falso.commit = OTRO_COMMIT
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)
    assert falso.vistas == 1  # para en la primera comprobacion, no en una posterior
    assert not falso.hizo("release", "download")


def test_publicar_con_borrador_con_archivo_inesperado_falla_sin_subir(escenario, monkeypatch):
    falso, _, _ = escenario
    falso.assets["instalador-extra.exe"] = b"malware"
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)
    assert not falso.hizo("release", "download")  # ni siquiera llega a descargar


def test_publicar_con_paquete_local_alterado_falla(escenario, monkeypatch):
    falso, contenidos, _ = escenario
    nombre = NOMBRES[0]
    with open(os.path.join(CARPETA, nombre), "wb") as f:
        f.write(contenidos[nombre][:-1] + b"X")
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)


def test_publicar_con_paquete_local_que_falta_falla(escenario, monkeypatch):
    falso, _, _ = escenario
    os.remove(os.path.join(CARPETA, NOMBRES[1]))
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)


def test_publicar_con_paquete_del_borrador_distinto_del_local_falla(escenario, monkeypatch):
    falso, contenidos, _ = escenario
    nombre = NOMBRES[2]
    falso.descarga[nombre] = contenidos[nombre][:-1] + b"X"  # lo que baja de GitHub
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    nada_subido_ni_publicado(falso)


def test_publicar_si_el_borrador_cambia_antes_de_subir_no_sube(escenario, monkeypatch):
    """La 2.a consulta del borrador (justo antes de subir) ve algo distinto."""
    falso, _, _ = escenario
    for n, cambio in {
        "assets": {"assets": [{"name": n} for n in NOMBRES] + [{"name": "nuevo.exe"}]},
        "commit": {"targetCommitish": OTRO_COMMIT},
        "ya_publicado": {"isDraft": False},
    }.items():
        falso.cambios, falso.vistas, falso.llamadas = {2: cambio}, 0, []
        with pytest.raises(SystemExit):
            publicar(monkeypatch)
        nada_subido_ni_publicado(falso)


@pytest.mark.parametrize("cambio", [
    {"assets": [{"name": "otro.exe"}]},
    {"targetCommitish": OTRO_COMMIT},
], ids=["assets", "commit"])
def test_publicar_si_el_borrador_cambia_tras_subir_no_publica(escenario, monkeypatch, cambio):
    """La 3.a consulta (tras subir manifiesto y firma) ve algo distinto: no se publica."""
    falso, _, _ = escenario
    falso.cambios = {3: cambio}
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert falso.hizo("release", "upload")   # ya se subio, pero...
    assert not falso.hizo("release", "edit")  # ...nunca se publica


def test_publicar_si_aparece_un_archivo_extra_tras_subir_no_publica(escenario, monkeypatch):
    falso, _, _ = escenario
    extra = [{"name": n} for n in NOMBRES + ["manifest.json", "manifest.json.minisig", "x.exe"]]
    falso.cambios = {3: {"assets": extra}}
    with pytest.raises(SystemExit):
        publicar(monkeypatch)
    assert not falso.hizo("release", "edit")


# ------------------------------------------------------------------ preparar_release

def preparar(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["preparar_release.py", f"v{VERSION}"])
    preparar_release.main()


def manifiesto_escrito():
    return os.path.join(CARPETA, "manifest.json")


def test_preparar_caso_feliz_escribe_un_manifiesto_valido(entorno, monkeypatch):
    falso = instalar(monkeypatch, GhFalso(paquetes()))
    preparar(monkeypatch)
    with open(manifiesto_escrito(), "rb") as f:
        m = verificacion.cargar_manifiesto(f.read())
    assert m["commit"] == COMMIT and m["version"] == VERSION and m["tipo"] == "release"
    assert {a["nombre"] for a in m["assets"]} == set(NOMBRES)
    assert falso.hizo("release", "download")


@pytest.mark.parametrize("estado", ["ahead", "diverged"])
def test_preparar_con_commit_fuera_de_main_falla_sin_escribir_manifiesto(entorno, monkeypatch,
                                                                        estado):
    instalar(monkeypatch, GhFalso(paquetes(), estado_compare=estado))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not os.path.exists(manifiesto_escrito())


@pytest.mark.parametrize("estado", ["identical", "behind"])
def test_preparar_acepta_commit_en_main(entorno, monkeypatch, estado):
    instalar(monkeypatch, GhFalso(paquetes(), estado_compare=estado))
    preparar(monkeypatch)
    assert os.path.exists(manifiesto_escrito())


def test_preparar_si_la_release_ya_esta_publicada_falla(entorno, monkeypatch):
    falso = instalar(monkeypatch, GhFalso(paquetes(), draft=False))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not falso.hizo("release", "download")
    assert not os.path.exists(manifiesto_escrito())


def test_preparar_con_paquetes_inesperados_falla(entorno, monkeypatch):
    contenidos = paquetes()
    contenidos["extra.exe"] = b"x"
    instalar(monkeypatch, GhFalso(contenidos))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not os.path.exists(manifiesto_escrito())


def test_preparar_con_paquete_que_falta_falla(entorno, monkeypatch):
    contenidos = paquetes()
    contenidos.pop(NOMBRES[0])
    instalar(monkeypatch, GhFalso(contenidos))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not os.path.exists(manifiesto_escrito())


def test_preparar_con_zip_peligroso_falla(entorno, monkeypatch):
    import io
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Compresorfree/ok.txt", b"x")
        z.writestr("Compresorfree/../../evil.txt", b"x")
    contenidos = paquetes()
    zip_nombre = next(n for n in NOMBRES if n.endswith(".zip"))
    contenidos[zip_nombre] = b.getvalue()
    instalar(monkeypatch, GhFalso(contenidos))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not os.path.exists(manifiesto_escrito())


def test_preparar_si_la_carpeta_ya_existe_no_la_pisa(entorno, monkeypatch):
    os.makedirs(CARPETA)
    with open(os.path.join(CARPETA, "viejo.txt"), "w") as f:
        f.write("x")
    falso = instalar(monkeypatch, GhFalso(paquetes()))
    with pytest.raises(SystemExit):
        preparar(monkeypatch)
    assert not falso.hizo("release", "download")


def test_preparar_con_version_invalida_falla(entorno, monkeypatch):
    instalar(monkeypatch, GhFalso(paquetes()))
    monkeypatch.setattr(sys, "argv", ["preparar_release.py", "v1.2"])
    with pytest.raises(SystemExit):
        preparar_release.main()


def test_serializacion_de_preparar_coincide_con_la_de_las_pruebas(entorno, monkeypatch):
    """El manifiesto que escribe preparar_release es el mismo formato que firma firma_util."""
    instalar(monkeypatch, GhFalso(paquetes()))
    preparar(monkeypatch)
    with open(manifiesto_escrito(), "rb") as f:
        escrito = f.read()
    assert serializar(json.loads(escrito)) == escrito
