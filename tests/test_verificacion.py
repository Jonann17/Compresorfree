"""PR3-A: verificacion de firmas minisign (Ed25519), manifiesto, archivos y zips.
Garantias 1 a 5 de la especificacion."""
import copy
import hashlib
import json
import shutil
import subprocess
import zipfile

import pytest

import verificacion
from verificacion import VerificacionFallida
from firma_util import (Par, b64, comentario_de, firmar, firmar_manifiesto,
                        manifiesto_rotacion, manifiesto_valido, nombre_asset, serializar)

DATOS = b"contenido de prueba\n"
COMENTARIO = "compresorfree tipo=release version=1.2.0"
requiere_minisign = pytest.mark.skipif(shutil.which("minisign") is None,
                                       reason="minisign no instalado")


@pytest.fixture
def principal():
    return Par()


@pytest.fixture
def respaldo():
    return Par()


@pytest.fixture
def claves(principal, respaldo):
    return [principal.entrada("principal"), respaldo.entrada("respaldo")]


# ---------- 1. Firmas validas ----------

def test_firma_creada_con_cryptography_se_verifica(principal, claves):
    r = verificacion.verificar_firma(DATOS, firmar(principal, DATOS, COMENTARIO), claves)
    assert r["clave"] == claves[0]
    assert r["comentario"] == COMENTARIO


def test_firma_acepta_trusted_comment_unicode(principal, claves):
    com = "compresorfree tipo=release version=1.2.0 \u00f1\u00e1"
    r = verificacion.verificar_firma(DATOS, firmar(principal, DATOS, com), claves)
    assert r["comentario"] == com


@requiere_minisign
def test_firma_de_minisign_real_se_verifica(tmp_path):
    pub, sec = tmp_path / "pub", tmp_path / "sec"
    subprocess.run(["minisign", "-G", "-W", "-p", str(pub), "-s", str(sec)],
                   check=True, capture_output=True)
    lineas = pub.read_text().splitlines()
    publica = lineas[1].strip()
    # id como lo muestra minisign: ultimos 8 bytes de la clave antes de la pk, invertidos
    import base64
    crudo = base64.b64decode(publica)
    clave = {"id": crudo[2:10][::-1].hex().upper(), "rol": "principal", "publica": publica}
    assert clave["id"] in lineas[0]

    manifiesto = manifiesto_valido()
    ruta = tmp_path / "manifest.json"
    ruta.write_bytes(serializar(manifiesto))
    subprocess.run(["minisign", "-S", "-s", str(sec), "-m", str(ruta), "-t",
                    "compresorfree tipo=release version=1.2.0"],
                   check=True, capture_output=True)
    minisig = (tmp_path / "manifest.json.minisig").read_text()

    r = verificacion.verificar_manifiesto(ruta.read_bytes(), minisig, [clave])
    assert r["version"] == "1.2.0"

    corrupto = bytearray(ruta.read_bytes())
    corrupto[10] ^= 1
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(bytes(corrupto), minisig, [clave])


# ---------- 2. Rechazos de firma ----------

def test_byte_alterado_en_el_manifiesto(principal, claves):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido())
    alterado = bytearray(datos)
    alterado[len(alterado) // 2] ^= 0x01
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_manifiesto(bytes(alterado), minisig, claves)


def test_trusted_comment_alterado(principal, claves):
    minisig = firmar(principal, DATOS, COMENTARIO)
    alterado = minisig.replace("version=1.2.0", "version=9.9.9")
    assert alterado != minisig
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, alterado, claves)


def test_firma_global_alterada(principal, claves):
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    otra = firmar(principal, DATOS, COMENTARIO + "x").splitlines()
    lineas[3] = otra[3]  # firma global de otro comentario
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


def test_firma_global_con_bit_alterado(principal, claves):
    import base64
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    g = bytearray(base64.b64decode(lineas[3]))
    g[0] ^= 1
    lineas[3] = b64(bytes(g))
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


def test_id_desconocido(claves):
    ajena = Par()
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, firmar(ajena, DATOS, COMENTARIO), claves)


def test_id_falsificado_con_otra_clave(principal, claves):
    """Firma hecha con otra clave pero declarando el id de la principal."""
    impostor = Par()
    minisig = firmar(impostor, DATOS, COMENTARIO, key_id=principal.key_id)
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, minisig, claves)


def test_algoritmo_legacy_Ed_rechazado(principal, claves):
    minisig = firmar(principal, DATOS, COMENTARIO, algoritmo=b"Ed", prehash=False)
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, minisig, claves)


def test_algoritmo_Ed_con_firma_prehash_rechazado(principal, claves):
    minisig = firmar(principal, DATOS, COMENTARIO, algoritmo=b"Ed")
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, minisig, claves)


@pytest.mark.parametrize("modo", ["extra", "falta_global", "falta_una", "vacio"])
def test_minisig_con_lineas_de_mas_o_de_menos(principal, claves, modo):
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    if modo == "extra":
        lineas.append("linea sobrante")
    elif modo == "falta_global":
        lineas = lineas[:3]
    elif modo == "falta_una":
        del lineas[0]
    else:
        lineas = []
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


@pytest.mark.parametrize("indice", [1, 3])
def test_base64_invalido(principal, claves, indice):
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    lineas[indice] = "!!!esto no es base64!!!"
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


def test_longitud_de_firma_incorrecta(principal, claves):
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    lineas[1] = b64(b"ED" + principal.key_id + b"\x00" * 63)
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


def test_prefijos_de_linea_incorrectos(principal, claves):
    lineas = firmar(principal, DATOS, COMENTARIO).splitlines()
    lineas[2] = lineas[2].replace("trusted comment:", "comentario:")
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, "\n".join(lineas) + "\n", claves)


def test_claves_vacias(principal):
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_firma(DATOS, firmar(principal, DATOS, COMENTARIO), [])


# ---------- 3. Roles y trusted comment ----------

def test_respaldo_firmando_release_se_rechaza(respaldo, claves):
    datos, minisig = firmar_manifiesto(respaldo, manifiesto_valido())
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_manifiesto(datos, minisig, claves)


def test_respaldo_firmando_rotacion_se_acepta(principal, respaldo, claves):
    m = manifiesto_rotacion(Par())
    datos, minisig = firmar_manifiesto(respaldo, m)
    r = verificacion.verificar_manifiesto(datos, minisig, claves)
    assert r["tipo"] == "rotacion"


def test_principal_puede_firmar_release_y_rotacion(principal, claves):
    for m in (manifiesto_valido(), manifiesto_rotacion(Par())):
        datos, minisig = firmar_manifiesto(principal, m)
        assert verificacion.verificar_manifiesto(datos, minisig, claves)["tipo"] == m["tipo"]


def test_release_firmada_valida_devuelve_manifiesto(principal, claves):
    m = manifiesto_valido()
    datos, minisig = firmar_manifiesto(principal, m)
    assert verificacion.verificar_manifiesto(datos, minisig, claves) == m


@pytest.mark.parametrize("comentario", [
    "compresorfree tipo=rotacion version=1.2.0",   # tipo distinto
    "compresorfree tipo=release version=1.2.1",    # version distinta
    "compresorfree tipo=release version=1.2.0 ",   # espacio extra
    "tipo=release version=1.2.0",
    "",
])
def test_trusted_comment_no_coincide_con_tipo_y_version(principal, claves, comentario):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido(), comentario=comentario)
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_manifiesto(datos, minisig, claves)


def test_la_firma_se_comprueba_antes_que_el_json(principal, claves):
    """Con firma invalida el error es de verificacion, aunque el JSON sea basura."""
    basura = b"{esto no es json"
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_manifiesto(basura, firmar(Par(), basura, COMENTARIO), claves)


# ---------- 4. Manifiesto ----------

def cargar(m):
    return verificacion.cargar_manifiesto(m if isinstance(m, bytes) else serializar(m))


def test_manifiesto_valido_se_carga():
    assert cargar(manifiesto_valido()) == manifiesto_valido()


def test_claves_json_duplicadas():
    texto = serializar(manifiesto_valido()).decode()
    duplicado = texto.replace('"app": "Compresorfree",',
                              '"app": "Compresorfree",\n  "app": "Otra",', 1)
    assert duplicado != texto
    with pytest.raises(VerificacionFallida):
        cargar(duplicado.encode())


def test_claves_duplicadas_anidadas():
    texto = serializar(manifiesto_valido()).decode()
    duplicado = texto.replace('"os": "windows",', '"os": "windows", "os": "macos",', 1)
    with pytest.raises(VerificacionFallida):
        cargar(duplicado.encode())


def test_campo_desconocido_en_raiz():
    with pytest.raises(VerificacionFallida):
        cargar(manifiesto_valido(extra="x"))


def test_campo_desconocido_en_asset():
    m = manifiesto_valido()
    m["assets"][0]["extra"] = 1
    with pytest.raises(VerificacionFallida):
        cargar(m)


@pytest.mark.parametrize("campo", ["schema", "app", "canal", "tipo", "version", "tag",
                                   "commit", "creado", "assets"])
def test_falta_campo_obligatorio(campo):
    m = manifiesto_valido()
    del m[campo]
    with pytest.raises(VerificacionFallida):
        cargar(m)


@pytest.mark.parametrize("version", ["1.2", "1.2.3.4", "v1.2.0", "1.2.0-beta", "a.b.c",
                                     "01.2.0x", "", "1.2.0\n"])
def test_version_no_semver(version):
    m = manifiesto_valido(version="1.2.0")
    m["version"] = version
    m["tag"] = f"v{version}"
    for a in m["assets"]:
        a["nombre"] = nombre_asset(version)
    with pytest.raises(VerificacionFallida):
        cargar(m)


def test_tag_distinto_de_la_version():
    with pytest.raises(VerificacionFallida):
        cargar(manifiesto_valido(tag="v1.2.1"))


@pytest.mark.parametrize("nombre", [
    "Compresorfree-Windows.zip",
    "Compresorfree-macOS-AppleSilicon.dmg",
    "Compresorfree-macOS-Intel.dmg",
    "Compresorfree-1.2.1-windows-x64.zip",        # version equivocada
    "Compresorfree-1.2.0-windows-x64.dmg",        # formato que no corresponde
    "compresorfree-1.2.0-windows-x64.zip",
    "../Compresorfree-1.2.0-windows-x64.zip",
    "",
])
def test_nombre_heredado_o_mal_formado(nombre):
    m = manifiesto_valido()
    m["assets"][0]["nombre"] = nombre
    with pytest.raises(VerificacionFallida):
        cargar(m)


@pytest.mark.parametrize("campo,valor", [
    ("os", "linux"), ("arch", "arm32"), ("formato", "exe"),
])
def test_enumeraciones_de_asset_invalidas(campo, valor):
    m = manifiesto_valido()
    m["assets"][0][campo] = valor
    with pytest.raises(VerificacionFallida):
        cargar(m)


@pytest.mark.parametrize("sha", ["", "b" * 63, "b" * 65, "B" * 64, "z" * 64, 123, None])
def test_sha256_invalido(sha):
    m = manifiesto_valido()
    m["assets"][0]["sha256"] = sha
    with pytest.raises(VerificacionFallida):
        cargar(m)


@pytest.mark.parametrize("campo,valor", [
    ("tamano", 0), ("tamano", -5), ("tamano", "10"), ("tamano", 1.5), ("tamano", True),
    ("tamano_expandido_max", 100),   # menor que tamano
])
def test_tamano_invalido(campo, valor):
    m = manifiesto_valido()
    m["assets"][0][campo] = valor
    with pytest.raises(VerificacionFallida):
        cargar(m)


def test_dmg_con_tamano_expandido_igual_a_tamano():
    m = manifiesto_valido()
    m["assets"][0].update(os="macos", arch="arm64", formato="dmg",
                          nombre=nombre_asset("1.2.0", "macos", "arm64", "dmg"),
                          tamano=1000, tamano_expandido_max=1000)
    assert cargar(m)["assets"][0]["formato"] == "dmg"


def test_commit_invalido():
    with pytest.raises(VerificacionFallida):
        cargar(manifiesto_valido(commit="abc123"))


def test_tipo_y_schema_invalidos():
    for cambio in ({"tipo": "otro"}, {"schema": 2}, {"app": "Otra"}):
        with pytest.raises(VerificacionFallida):
            cargar(manifiesto_valido(**cambio))


def test_rotacion_con_assets_vacios_y_claves():
    m = manifiesto_rotacion(Par())
    assert cargar(m)["claves"][0]["rol"] == "principal"


def test_rotacion_con_rol_invalido():
    m = manifiesto_rotacion(Par())
    m["claves"][0]["rol"] = "root"
    with pytest.raises(VerificacionFallida):
        cargar(m)


def test_no_utf8_y_no_objeto():
    for datos in (b"\xff\xfe{}", b"[]", b"", b"nulo"):
        with pytest.raises(VerificacionFallida):
            cargar(datos)


@pytest.mark.parametrize("version,actual,esperado", [
    ("1.2.0", "1.1.0", True),
    ("1.1.0", "1.1.0", False),       # igualdad
    ("1.0.9", "1.1.0", False),       # downgrade
    ("1.10.0", "1.9.0", True),       # comparacion numerica, no de texto
    ("0.0.1", "0.0.0-dev", True),
    ("0.0.0", "0.0.0-dev", False),
    ("1.0.0", "0.0.0-dev", True),
    ("2.0.0", "1.99.99", True),
    ("1.2.0", "raro", True),         # actual no estricta cuenta como 0.0.0
])
def test_es_mas_nueva(version, actual, esperado):
    assert verificacion.es_mas_nueva(version, actual) is esperado


def test_es_mas_nueva_rechaza_version_no_estricta():
    for v in ("1.2", "v1.2.0", "1.2.0-beta", ""):
        try:
            assert verificacion.es_mas_nueva(v, "0.0.0") is False
        except VerificacionFallida:
            pass


def test_asset_para_sistema_explicito():
    m = manifiesto_valido()
    m["assets"].append({"os": "macos", "arch": "arm64", "formato": "dmg",
                        "nombre": nombre_asset("1.2.0", "macos", "arm64", "dmg"),
                        "sha256": "c" * 64, "tamano": 10, "tamano_expandido_max": 10})
    assert verificacion.asset_para_sistema(m, "windows", "x64")["formato"] == "zip"
    assert verificacion.asset_para_sistema(m, "macos", "arm64")["formato"] == "dmg"
    assert verificacion.asset_para_sistema(m, "macos", "x64") is None
    assert verificacion.asset_para_sistema(m, "windows", "arm64") is None


@pytest.mark.parametrize("plataforma,maquina,os_,arch", [
    ("win32", "AMD64", "windows", "x64"),
    ("darwin", "arm64", "macos", "arm64"),
    ("darwin", "x86_64", "macos", "x64"),
])
def test_asset_para_sistema_detecta_el_actual(monkeypatch, plataforma, maquina, os_, arch):
    monkeypatch.setattr(verificacion.sys, "platform", plataforma)
    monkeypatch.setattr(verificacion.platform, "machine", lambda: maquina)
    m = manifiesto_valido()
    m["assets"] = [{"os": os_, "arch": arch,
                    "formato": "zip" if os_ == "windows" else "dmg",
                    "nombre": nombre_asset("1.2.0", os_, arch,
                                           "zip" if os_ == "windows" else "dmg"),
                    "sha256": "d" * 64, "tamano": 5, "tamano_expandido_max": 5}]
    assert verificacion.asset_para_sistema(m)["arch"] == arch


def test_asset_para_sistema_aarch64_es_arm64(monkeypatch):
    monkeypatch.setattr(verificacion.sys, "platform", "darwin")
    monkeypatch.setattr(verificacion.platform, "machine", lambda: "aarch64")
    m = manifiesto_valido()
    m["assets"] = [{"os": "macos", "arch": "arm64", "formato": "dmg",
                    "nombre": nombre_asset("1.2.0", "macos", "arm64", "dmg"),
                    "sha256": "d" * 64, "tamano": 5, "tamano_expandido_max": 5}]
    assert verificacion.asset_para_sistema(m) is not None


# ---------- 5. Archivos y zips ----------

def asset_de(ruta, **cambios):
    datos = open(ruta, "rb").read()
    a = {"os": "windows", "arch": "x64", "formato": "zip",
         "nombre": nombre_asset("1.2.0"), "sha256": hashlib.sha256(datos).hexdigest(),
         "tamano": len(datos), "tamano_expandido_max": 10_000_000}
    a.update(cambios)
    return a


def test_verificar_archivo_correcto_y_grande(tmp_path):
    ruta = tmp_path / "x.bin"
    ruta.write_bytes(b"0123456789" * 500_000)  # > un bloque de lectura
    verificacion.verificar_archivo(str(ruta), asset_de(ruta))


def test_verificar_archivo_hash_incorrecto(tmp_path):
    ruta = tmp_path / "x.bin"
    ruta.write_bytes(b"hola")
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_archivo(str(ruta), asset_de(ruta, sha256="0" * 64))


def test_verificar_archivo_tamano_incorrecto(tmp_path):
    ruta = tmp_path / "x.bin"
    ruta.write_bytes(b"hola")
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_archivo(str(ruta), asset_de(ruta, tamano=5))


def test_verificar_archivo_un_byte_cambiado(tmp_path):
    ruta = tmp_path / "x.bin"
    ruta.write_bytes(b"hola mundo")
    asset = asset_de(ruta)
    ruta.write_bytes(b"hola mundO")
    with pytest.raises(VerificacionFallida):
        verificacion.verificar_archivo(str(ruta), asset)


def hacer_zip(ruta, entradas, symlinks=()):
    """entradas: {nombre: bytes}; symlinks: nombres que se marcan como enlace."""
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in entradas.items():
            info = zipfile.ZipInfo(nombre)
            if nombre in symlinks:
                info.external_attr = 0o120777 << 16
            z.writestr(info, datos)
    return str(ruta)


def test_validar_zip_correcto(tmp_path):
    ruta = hacer_zip(tmp_path / "ok.zip", {
        "Compresorfree/Compresorfree.exe": b"x" * 100,
        "Compresorfree/_internal/datos.bin": b"y" * 100,
    })
    verificacion.validar_zip(ruta, asset_de(ruta))


@pytest.mark.parametrize("nombre", [
    "Compresorfree/../../evil.txt",
    "../evil.txt",
    "/etc/evil.txt",
    "C:/evil.txt",
    "C:\\evil.txt",
    "Compresorfree/..\\evil.txt",
])
def test_validar_zip_rechaza_rutas_peligrosas(tmp_path, nombre):
    ruta = hacer_zip(tmp_path / "mal.zip", {"Compresorfree/ok.txt": b"a", nombre: b"b"})
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta))


def test_validar_zip_rechaza_symlink(tmp_path):
    ruta = hacer_zip(tmp_path / "sym.zip",
                     {"Compresorfree/ok.txt": b"a", "Compresorfree/enlace": b"/etc/passwd"},
                     symlinks={"Compresorfree/enlace"})
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta))


@pytest.mark.parametrize("entradas", [
    {"Otra/app.exe": b"a"},                                   # raiz distinta
    {"app.exe": b"a"},                                        # sin carpeta raiz
    {"Compresorfree/a": b"a", "Otra/b": b"b"},                # dos raices
    {"compresorfree/a": b"a"},                                # mayusculas distintas
    {},                                                       # vacio
])
def test_validar_zip_rechaza_raiz_distinta(tmp_path, entradas):
    ruta = hacer_zip(tmp_path / "raiz.zip", entradas)
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta))


def test_validar_zip_rechaza_expansion_excesiva(tmp_path):
    ruta = hacer_zip(tmp_path / "bomba.zip", {"Compresorfree/a.bin": b"\0" * 2_000_000})
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta, tamano_expandido_max=1_000_000))


def test_validar_zip_suma_de_varias_entradas(tmp_path):
    ruta = hacer_zip(tmp_path / "suma.zip", {f"Compresorfree/{i}.bin": b"\0" * 400_000
                                              for i in range(5)})
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta, tamano_expandido_max=1_500_000))


def test_validar_zip_limite_de_entradas(tmp_path):
    ruta = hacer_zip(tmp_path / "muchos.zip",
                     {f"Compresorfree/{i}": b"" for i in range(20001)})
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(ruta, asset_de(ruta, tamano_expandido_max=10**9))


def test_validar_zip_no_es_zip(tmp_path):
    ruta = tmp_path / "falso.zip"
    ruta.write_bytes(b"esto no es un zip")
    with pytest.raises(VerificacionFallida):
        verificacion.validar_zip(str(ruta), asset_de(ruta))
