"""tools/generar_manifiesto.py: manifiesto valido para la app y notas del CHANGELOG."""
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import generar_manifiesto as gm  # noqa: E402
import verificacion  # noqa: E402

COMMIT = "c" * 40
CHANGELOG = """# Cambios

## 1.3.0 - 2026-12-01
- Algo nuevo
- Otra cosa

## 1.2.0 - 2026-11-17
- Antiguo
"""


def zip_bytes():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Compresorfree/Compresorfree.exe", b"exe" * 100)
    return b.getvalue()


@pytest.fixture
def carpeta(tmp_path):
    def crear(version, omitir=None):
        d = tmp_path / "descargas"
        d.mkdir(exist_ok=True)
        for a in verificacion.ASSETS_ESPERADOS:
            nombre = verificacion.nombre_asset(version, *a)
            if nombre != omitir:
                (d / nombre).write_bytes(zip_bytes() if a[2] == "zip" else b"bin " + nombre.encode())
        return str(d)
    return crear


def test_manifiesto_valido_para_la_app_con_notas_y_exe(carpeta):
    datos, notas = gm.generar("1.3.0", carpeta("1.3.0"), COMMIT, CHANGELOG,
                              creado="2026-12-01T10:00:00Z")
    m = verificacion.cargar_manifiesto(datos)
    assert m["notas"] == notas == "- Algo nuevo\n- Otra cosa"
    assert m["commit"] == COMMIT and m["tag"] == "v1.3.0"
    formatos = {(a["os"], a["arch"], a["formato"]) for a in m["assets"]}
    assert formatos == set(verificacion.ASSETS_ESPERADOS)
    exe = verificacion.asset_para_sistema(m, "windows", "x64")
    assert exe["formato"] == "exe" and exe["nombre"] == "Compresorfree-Setup-1.3.0.exe"
    assert exe["tamano_expandido_max"] == exe["tamano"]
    zip_ = verificacion.asset_para_sistema(m, "windows", "x64", "zip")
    assert zip_["tamano_expandido_max"] >= zip_["tamano"]


def test_falla_sin_bloque_en_el_changelog(carpeta):
    with pytest.raises(gm.ErrorManifiesto, match="2.0.0"):
        gm.generar("2.0.0", carpeta("2.0.0"), COMMIT, CHANGELOG)


def test_falla_con_bloque_vacio():
    with pytest.raises(gm.ErrorManifiesto, match="vacio"):
        gm.extraer_notas("## 1.0.0 - 2026-01-01\n\n## 0.9.0\n- x\n", "1.0.0")


def test_prerelease_usa_las_notas_de_la_final(carpeta):
    assert gm.extraer_notas(CHANGELOG, "1.3.0-rc.1") == "- Algo nuevo\n- Otra cosa"
    datos, _ = gm.generar("1.3.0-rc.1", carpeta("1.3.0-rc.1"), COMMIT, CHANGELOG)
    assert verificacion.cargar_manifiesto(datos)["version"] == "1.3.0-rc.1"


def test_falla_si_falta_un_paquete_o_sobra_uno(carpeta):
    d = carpeta("1.3.0", omitir="Compresorfree-Setup-1.3.0.exe")
    with pytest.raises(gm.ErrorManifiesto, match="inesperados"):
        gm.generar("1.3.0", d, COMMIT, CHANGELOG)
    d = carpeta("1.3.0")
    open(os.path.join(d, "Compresorfree-Windows.zip"), "wb").close()
    with pytest.raises(gm.ErrorManifiesto):
        gm.generar("1.3.0", d, COMMIT, CHANGELOG)


def test_falla_con_commit_invalido(carpeta):
    with pytest.raises(gm.ErrorManifiesto, match="commit"):
        gm.generar("1.3.0", carpeta("1.3.0"), "abc", CHANGELOG)


def test_cli_escribe_manifiesto_y_notas(carpeta, tmp_path):
    d = carpeta("1.2.0")
    notas = tmp_path / "notas_release.md"
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "generar_manifiesto.py"),
                        "--version", "1.2.0", "--assets", d, "--commit", COMMIT,
                        "--notas", str(notas)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = verificacion.cargar_manifiesto(open(os.path.join(d, "manifest.json"), "rb").read())
    assert m["notas"] in notas.read_text(encoding="utf-8")
    assert json.loads(open(os.path.join(d, "manifest.json"), encoding="utf-8").read())["version"] == "1.2.0"


def test_cli_falla_sin_bloque(carpeta, tmp_path):
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "generar_manifiesto.py"),
                        "--version", "9.9.9", "--assets", carpeta("9.9.9"), "--commit", COMMIT,
                        "--notas", str(tmp_path / "n.md")], capture_output=True, text=True)
    assert r.returncode != 0 and "CHANGELOG" in r.stderr
