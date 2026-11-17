"""CHANGELOG.md: formato y que cada version tenga su bloque."""
import os
import re
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import generar_manifiesto  # noqa: E402
import verificacion  # noqa: E402
import version  # noqa: E402

with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as _f:
    TEXTO = _f.read()
ENCABEZADOS = re.findall(r"^## (\S+) - (\d{4}-\d{2}-\d{2})$", TEXTO, re.M)


def test_todos_los_bloques_tienen_formato_y_notas():
    todos = re.findall(r"^## .*$", TEXTO, re.M)
    assert len(todos) == len(ENCABEZADOS) >= 3
    for v, _ in ENCABEZADOS:
        assert verificacion.es_semver(v), v
        assert generar_manifiesto.extraer_notas(TEXTO, v).startswith("- ")


def test_versiones_en_orden_descendente():
    versiones = [v for v, _ in ENCABEZADOS]
    for nueva, vieja in zip(versiones, versiones[1:]):
        assert verificacion.es_mas_nueva(nueva, vieja), (nueva, vieja)


def test_hay_bloque_para_la_version_actual():
    if version.VERSION == "1.0.0":
        pytest.skip("version.py no esta estampado (1.0.0 es el valor por defecto del repo): "
                    "se exige la version mas alta del CHANGELOG en su lugar")
    assert generar_manifiesto.extraer_notas(TEXTO, version.VERSION)


def test_la_version_mas_alta_tiene_bloque_y_es_1_2_0_o_superior():
    mas_alta = ENCABEZADOS[0][0]
    assert not verificacion.es_mas_nueva("1.2.0", mas_alta)
    assert generar_manifiesto.extraer_notas(TEXTO, mas_alta)
