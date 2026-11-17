"""tools/version_release.py: version, pre-release y salidas del workflow."""
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import version_release as vr  # noqa: E402


def test_tag_final_no_es_prerelease():
    d = vr.decidir("push", ref="v1.2.0")
    assert d == {"version": "1.2.0", "numerica": "1.2.0", "tag": "v1.2.0",
                 "prerelease": False, "publicar": True}


def test_tag_con_sufijo_es_prerelease_y_la_numerica_no_lo_lleva():
    d = vr.decidir("push", ref="v1.3.0-rc.1")
    assert d["version"] == "1.3.0-rc.1" and d["numerica"] == "1.3.0"
    assert d["tag"] == "v1.3.0-rc.1" and d["prerelease"] is True


@pytest.mark.parametrize("valor,esperado", [("true", True), ("false", False), ("", False),
                                            ("TRUE", True), (True, True), (False, False),
                                            (None, False)])
def test_la_casilla_del_dispatch_llega_como_texto(valor, esperado):
    # bool("false") seria True: la pre-release saldria siempre marcada.
    d = vr.decidir("workflow_dispatch", entrada_version="1.2.0", entrada_prerelease=valor)
    assert d["prerelease"] is esperado


def test_en_dispatch_la_casilla_gana_al_sufijo():
    d = vr.decidir("workflow_dispatch", entrada_version="1.3.0-rc.1", entrada_prerelease="false")
    assert d["prerelease"] is False and d["version"] == "1.3.0-rc.1"
    d = vr.decidir("workflow_dispatch", entrada_version="v1.3.0", entrada_prerelease="true")
    assert d["prerelease"] is True and d["version"] == "1.3.0"


def test_sin_version_solo_compila():
    for evento, kw in [("push", {"ref": ""}), ("push", {"ref": "main"}),
                       ("workflow_dispatch", {"entrada_version": ""})]:
        d = vr.decidir(evento, **kw)
        assert d["publicar"] is False and d["version"] == "0.0.0-dev" and not d["prerelease"]


@pytest.mark.parametrize("mala", ["1.2", "v1.2.3.4", "01.2.3", "1.2.3\nx=1", "1.2.3;rm -rf /",
                                  "$(id)", "1.2.3-", "1.2.3-rc..1", "\u0661.2.3", " 1.2.3",
                                  "1.2.3-rc_1", "vv1.2.3"])
def test_versiones_no_validas_fallan(mala):
    with pytest.raises(SystemExit):
        vr.decidir("workflow_dispatch", entrada_version=mala)


def test_script_escribe_las_salidas_en_github_output(tmp_path):
    salida = tmp_path / "salida"
    salida.write_text("")
    r = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "tools", "version_release.py"), "--evento",
         "workflow_dispatch", "--entrada-version", "1.3.0-rc.1", "--entrada-prerelease", "false"],
        env=dict(os.environ, GITHUB_OUTPUT=str(salida)), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    valores = dict(l.split("=", 1) for l in salida.read_text().splitlines())
    assert valores == {"version": "1.3.0-rc.1", "numerica": "1.3.0", "tag": "v1.3.0-rc.1",
                       "prerelease": "false", "publicar": "true"}
