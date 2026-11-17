import json
import os

import app
import preferencias


def test_ida_y_vuelta(tmp_path):
    ruta = str(tmp_path / "sub" / "p.json")
    carpeta = str(tmp_path)
    assert preferencias.guardar({"tipo": "pdf", "nivel": "alta", "carpeta": carpeta}, ruta)
    assert preferencias.cargar(ruta) == {"tipo": "pdf", "nivel": "alta", "carpeta": carpeta}
    assert os.listdir(tmp_path / "sub") == ["p.json"]  # sin temporales


def test_ausente_corrupto_o_invalido(tmp_path):
    assert preferencias.cargar(str(tmp_path / "no.json")) == preferencias.DEFECTO
    mal = tmp_path / "mal.json"
    mal.write_text("{no es json", encoding="utf-8")
    assert preferencias.cargar(str(mal)) == preferencias.DEFECTO
    mal.write_text("[1]", encoding="utf-8")
    assert preferencias.cargar(str(mal)) == preferencias.DEFECTO
    mal.write_text(json.dumps({"tipo": "x", "nivel": 3, "carpeta": 5}), encoding="utf-8")
    assert preferencias.cargar(str(mal)) == preferencias.DEFECTO


def test_carpeta_inexistente_se_ignora(tmp_path):
    ruta = str(tmp_path / "p.json")
    preferencias.guardar({"tipo": "pdf", "nivel": "baja", "carpeta": str(tmp_path / "ya_no")}, ruta)
    assert preferencias.cargar(ruta) == {"tipo": "pdf", "nivel": "baja", "carpeta": ""}


def test_ruta_por_plataforma(monkeypatch):
    monkeypatch.delenv("COMPRESORFREE_CONFIG", raising=False)
    monkeypatch.setattr(preferencias.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/x/AppData/Roaming")
    assert preferencias.directorio_config() == os.path.join("C:/Users/x/AppData/Roaming", "Compresorfree")
    monkeypatch.setattr(preferencias.sys, "platform", "darwin")
    assert preferencias.directorio_config().endswith(
        os.path.join("Library", "Application Support", "Compresorfree"))
    monkeypatch.setattr(preferencias.sys, "platform", "linux")
    assert preferencias.directorio_config().endswith(os.path.join(".config", "compresorfree"))
    assert preferencias.ruta_config().endswith("preferencias.json")


def test_filtrar_soltados(tmp_path):
    v1, v2, p = (tmp_path / n for n in ("a.MP4", "b.mkv", "c.pdf"))
    for f in (v1, v2, p):
        f.write_bytes(b"x")
    carpeta = tmp_path / "d.mp4"
    carpeta.mkdir()
    rutas = [str(v1), str(v1), str(v2), str(p), str(carpeta), str(tmp_path / "no.mp4"),
             str(tmp_path / "t.txt")]
    assert app.filtrar_soltados(rutas, "video") == [str(v1), str(v2)]
    assert app.filtrar_soltados(rutas, "video", existentes=[str(v1)]) == [str(v2)]
    assert app.filtrar_soltados(rutas, "pdf") == [str(p)]
