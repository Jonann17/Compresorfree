"""PR3-A: buscar_actualizacion con HTTP simulado (garantia 6)."""
import io
import json
import urllib.error

import pytest

import actualizador
import claves_confianza
from firma_util import (Par, firmar_manifiesto, manifiesto_valido, serializar)

API = actualizador.URL_API
BASE = "https://github.com/Jonann17/Compresorfree/releases/download"


class Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def release_json(version="1.2.0", con_manifiesto=True, tag=None):
    tag = tag or f"v{version}"
    assets = [{"name": f"Compresorfree-{version}-windows-x64.zip",
               "browser_download_url": f"{BASE}/{tag}/Compresorfree-{version}-windows-x64.zip"}]
    if con_manifiesto:
        assets += [{"name": "manifest.json",
                    "browser_download_url": f"{BASE}/{tag}/manifest.json"},
                   {"name": "manifest.json.minisig",
                    "browser_download_url": f"{BASE}/{tag}/manifest.json.minisig"}]
    return {"tag_name": tag, "body": "Notas de prueba",
            "html_url": f"https://github.com/Jonann17/Compresorfree/releases/tag/{tag}",
            "assets": assets}


@pytest.fixture
def red(monkeypatch):
    """Registra respuestas por URL; cualquier URL no registrada falla el test."""
    respuestas = {}
    pedidas = []

    def falso_abrir(url, *a, **kw):
        pedidas.append(url)
        if url not in respuestas:
            raise AssertionError(f"URL inesperada: {url}")
        r = respuestas[url]
        if isinstance(r, Exception):
            raise r
        return Resp(r)

    monkeypatch.setattr(actualizador, "_abrir", falso_abrir)
    respuestas["pedidas"] = pedidas
    return respuestas


@pytest.fixture
def principal(monkeypatch):
    par = Par()
    monkeypatch.setattr(claves_confianza, "CLAVES", [par.entrada("principal")])
    monkeypatch.setattr(actualizador, "VERSION", "1.1.0")
    return par


def publicar(red, release, datos=None, minisig=None):
    red[API] = json.dumps(release).encode()
    tag = release["tag_name"]
    if datos is not None:
        red[f"{BASE}/{tag}/manifest.json"] = datos
        red[f"{BASE}/{tag}/manifest.json.minisig"] = minisig.encode()


def test_release_firmada_valida_es_verificada(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.2.0"))
    publicar(red, release_json("1.2.0"), datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["verificada"] is True
    assert r["version"] == "1.2.0"
    assert r["notas"] == "Notas de prueba"
    assert r["url_pagina"].startswith("https://github.com/")


def test_manifiesto_manipulado_no_es_verificado(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.2.0"))
    manipulado = datos.replace(b"61234567", b"61234568")
    assert manipulado != datos
    publicar(red, release_json("1.2.0"), manipulado, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["verificada"] is False
    assert r["version"] == "1.2.0"


def test_firma_de_clave_ajena_no_es_verificada(red, principal):
    datos, minisig = firmar_manifiesto(Par(), manifiesto_valido("1.2.0"))
    publicar(red, release_json("1.2.0"), datos, minisig)
    assert actualizador.buscar_actualizacion()["verificada"] is False


def test_sin_claves_de_confianza_no_es_verificada(red, principal, monkeypatch):
    monkeypatch.setattr(claves_confianza, "CLAVES", [])
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.2.0"))
    publicar(red, release_json("1.2.0"), datos, minisig)
    assert actualizador.buscar_actualizacion()["verificada"] is False


def test_manipulado_con_tag_no_semver_devuelve_none(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.2.0"))
    publicar(red, release_json("1.2.0", tag="nightly"), b"{}", "x")
    red[f"{BASE}/nightly/manifest.json"] = datos.replace(b"61234567", b"1")
    assert actualizador.buscar_actualizacion() is None


def test_manipulado_y_version_no_mas_nueva_devuelve_none(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.0.0"))
    publicar(red, release_json("1.0.0"), datos + b" ", minisig)
    assert actualizador.buscar_actualizacion() is None


def test_version_igual_devuelve_none(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.1.0"))
    publicar(red, release_json("1.1.0"), datos, minisig)
    assert actualizador.buscar_actualizacion() is None


def test_version_anterior_firmada_devuelve_none(red, principal):
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.0.0"))
    publicar(red, release_json("1.0.0"), datos, minisig)
    assert actualizador.buscar_actualizacion() is None


def test_sin_manifiesto_devuelve_none(red, principal):
    publicar(red, release_json("1.2.0", con_manifiesto=False))
    assert actualizador.buscar_actualizacion() is None
    assert red["pedidas"] == [API]  # no intenta descargar nada mas


def test_solo_manifiesto_sin_firma_devuelve_none(red, principal):
    r = release_json("1.2.0")
    r["assets"] = [a for a in r["assets"] if a["name"] != "manifest.json.minisig"]
    publicar(red, r)
    assert actualizador.buscar_actualizacion() is None


def test_tag_de_la_release_distinto_del_manifiesto_no_es_verificado(red, principal):
    """Manifiesto firmado de 1.2.0 reutilizado en la release v1.3.0."""
    datos, minisig = firmar_manifiesto(principal, manifiesto_valido("1.2.0"))
    publicar(red, release_json("1.3.0"), datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r is None or r["verificada"] is False


def test_release_404_devuelve_none(red, principal):
    red[API] = urllib.error.HTTPError(API, 404, "Not Found", {}, None)
    assert actualizador.buscar_actualizacion() is None


def test_ya_no_existe_la_autoinstalacion():
    for nombre in ("descargar", "instalar", "nombre_paquete"):
        assert not hasattr(actualizador, nombre)
    assert actualizador.URL_RELEASES
