"""Descarga verificada, busqueda con/sin claves, instalacion simulada y puede_autoinstalar."""
import hashlib
import os
import subprocess
import sys
import threading

import pytest

import actualizador
import claves_confianza
import verificacion
from firma_util import Par, firmar_manifiesto, manifiesto_valido
from test_actualizador import API, BASE, Resp, publicar, release_json  # noqa: F401
import test_actualizador as _ta

red = _ta.red  # reutiliza el fixture de HTTP simulado

DATOS = os.urandom(1024 * 1024 + 123)
NOMBRE = "Compresorfree-Setup-1.2.0.exe"
URL = f"{BASE}/v1.2.0/{NOMBRE}"


def asset(datos=DATOS, **cambios):
    a = {"os": "windows", "arch": "x64", "formato": "exe", "nombre": NOMBRE, "url": URL,
         "sha256": hashlib.sha256(datos).hexdigest(), "tamano": len(datos),
         "tamano_expandido_max": len(datos)}
    a.update(cambios)
    return a


class Flujo:
    """Respuesta por bloques que puede disparar un callback a mitad de lectura."""

    def __init__(self, datos, tras_bloque=None):
        self.datos, self.pos, self.tras = datos, 0, tras_bloque

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self, n=-1):
        bloque = self.datos[self.pos:self.pos + n]
        self.pos += len(bloque)
        if self.tras and bloque:
            self.tras()
        return bloque


@pytest.fixture
def servidor(monkeypatch):
    estado = {"datos": DATOS, "tras": None, "pedidas": []}

    def falso(url, *a, **kw):
        estado["pedidas"].append(url)
        return Flujo(estado["datos"], estado["tras"])

    monkeypatch.setattr(actualizador, "_abrir", falso)
    return estado


# ------------------------------------------------------------------ descargar

def test_descarga_correcta(tmp_path, servidor):
    avances = []
    ruta = actualizador.descargar(asset(), str(tmp_path), lambda a, b: avances.append((a, b)))
    assert open(ruta, "rb").read() == DATOS
    assert os.path.basename(ruta) == NOMBRE
    assert avances[-1] == (len(DATOS), len(DATOS))
    assert os.listdir(tmp_path) == [NOMBRE]


def test_hash_incorrecto_no_deja_archivo(tmp_path, servidor):
    with pytest.raises(verificacion.VerificacionFallida, match="SHA-256"):
        actualizador.descargar(asset(sha256="0" * 64), str(tmp_path))
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("delta", [-1, 1])
def test_tamano_incorrecto_no_deja_archivo(tmp_path, servidor, delta):
    with pytest.raises(verificacion.VerificacionFallida):
        actualizador.descargar(asset(tamano=len(DATOS) + delta), str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_menos_de_1mb_se_rechaza_sin_descargar(tmp_path, servidor):
    pequeno = b"<html>404</html>"
    servidor["datos"] = pequeno
    with pytest.raises(verificacion.VerificacionFallida, match="plausible"):
        actualizador.descargar(asset(pequeno), str(tmp_path))
    assert servidor["pedidas"] == [] and os.listdir(tmp_path) == []


def test_cancelacion_borra_el_parcial(tmp_path, servidor):
    ev = threading.Event()
    servidor["tras"] = ev.set
    with pytest.raises(actualizador.Cancelado):
        actualizador.descargar(asset(), str(tmp_path), cancelar=ev)
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("url", ["http://github.com/x/" + NOMBRE, "file:///tmp/" + NOMBRE,
                                 "", None, "HTTPS://github.com/x/" + NOMBRE])
def test_url_sin_https_se_rechaza(tmp_path, servidor, url):
    with pytest.raises(verificacion.VerificacionFallida):
        actualizador.descargar(asset(url=url), str(tmp_path))
    assert servidor["pedidas"] == []


@pytest.mark.parametrize("nombre", ["../x.exe", "a/b.exe", "..", "", "a\\b.exe"])
def test_nombre_de_asset_peligroso_se_rechaza(tmp_path, servidor, nombre):
    with pytest.raises(verificacion.VerificacionFallida):
        actualizador.descargar(asset(nombre=nombre, url=f"{BASE}/v1.2.0/{nombre}"),
                               str(tmp_path))
    assert servidor["pedidas"] == []


def test_url_con_otro_nombre_que_el_asset_se_rechaza(tmp_path, servidor):
    with pytest.raises(verificacion.VerificacionFallida):
        actualizador.descargar(asset(url=f"{BASE}/v1.2.0/otro.exe"), str(tmp_path))


# ------------------------------------------------------------------ buscar_actualizacion

def _release_con_exe(version="1.2.0"):
    r = release_json(version)
    nombre = f"Compresorfree-Setup-{version}.exe"
    r["assets"].append({"name": nombre, "browser_download_url": f"{BASE}/v{version}/{nombre}"})
    r["published_at"] = "2026-11-20T10:00:00Z"
    return r


def _manifiesto_con_exe(version="1.2.0", **cambios):
    m = manifiesto_valido(version, **cambios)
    m["assets"].append({"os": "windows", "arch": "x64", "formato": "exe",
                        "nombre": f"Compresorfree-Setup-{version}.exe", "sha256": "e" * 64,
                        "tamano": 2000000, "tamano_expandido_max": 2000000})
    return m


@pytest.fixture
def en_windows(monkeypatch):
    original = verificacion.asset_para_sistema
    monkeypatch.setattr(verificacion, "asset_para_sistema",
                        lambda m, *a, **k: original(m, "windows", "x64"))
    monkeypatch.setattr(actualizador, "VERSION", "1.1.0")


def test_sin_claves_auto_true_y_asset_exe(red, en_windows, monkeypatch):
    monkeypatch.setattr(claves_confianza, "CLAVES", [])
    par = Par()
    datos, minisig = firmar_manifiesto(par, _manifiesto_con_exe(notas="- novedad"))
    publicar(red, _release_con_exe(), datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["verificada"] is False and r["auto"] is True
    assert r["asset"]["formato"] == "exe" and r["asset"]["url"] == URL
    assert r["notas"] == "- novedad" and r["fecha"] == "2026-11-16"
    assert r["version"] == "1.2.0"


def test_con_claves_y_firma_valida_es_verificada_y_auto(red, en_windows, monkeypatch):
    par = Par()
    monkeypatch.setattr(claves_confianza, "CLAVES", [par.entrada("principal")])
    datos, minisig = firmar_manifiesto(par, _manifiesto_con_exe())
    publicar(red, _release_con_exe(), datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["verificada"] is True and r["auto"] is True
    assert r["asset"]["nombre"] == NOMBRE


def test_con_claves_y_sin_firma_no_hay_autoinstalacion(red, en_windows, monkeypatch):
    par = Par()
    monkeypatch.setattr(claves_confianza, "CLAVES", [par.entrada("principal")])
    datos, _ = firmar_manifiesto(par, _manifiesto_con_exe())
    rel = _release_con_exe()
    rel["assets"] = [a for a in rel["assets"] if a["name"] != "manifest.json.minisig"]
    publicar(red, rel)
    red[f"{BASE}/v1.2.0/manifest.json"] = datos
    r = actualizador.buscar_actualizacion()
    assert r["verificada"] is False and r["auto"] is False and r["asset"] is None


def test_con_claves_y_firma_ajena_no_hay_autoinstalacion(red, en_windows, monkeypatch):
    monkeypatch.setattr(claves_confianza, "CLAVES", [Par().entrada("principal")])
    datos, minisig = firmar_manifiesto(Par(), _manifiesto_con_exe())
    publicar(red, _release_con_exe(), datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["auto"] is False and r["asset"] is None


def test_url_del_asset_que_no_es_la_oficial_no_se_ofrece(red, en_windows, monkeypatch):
    monkeypatch.setattr(claves_confianza, "CLAVES", [])
    datos, minisig = firmar_manifiesto(Par(), _manifiesto_con_exe())
    rel = _release_con_exe()
    for a in rel["assets"]:
        if a["name"] == NOMBRE:
            a["browser_download_url"] = "https://evil.example/" + NOMBRE
    publicar(red, rel, datos, minisig)
    r = actualizador.buscar_actualizacion()
    assert r["asset"] is None and r["auto"] is False


# ------------------------------------------------------------------ instalar_windows

class ProcesoFalso:
    def __init__(self, sinal=None, muere=None):
        self.sinal, self.muere, self.llamadas = sinal, muere, 0

    def poll(self):
        self.llamadas += 1
        if self.muere is not None:
            return self.muere
        if self.sinal and self.llamadas >= 2:
            open(self.sinal, "w").close()
        return None


def _sinal_de(args):
    return next(a.split("=", 1)[1] for a in args if a.startswith("/SINAL="))


def test_instalar_windows_espera_el_sinal(tmp_path, monkeypatch):
    lanzados = []

    def popen(cmd, **kw):
        lanzados.append((cmd, kw))
        return ProcesoFalso(_sinal_de(cmd))

    monkeypatch.setattr(subprocess, "Popen", popen)
    exe = tmp_path / NOMBRE
    exe.write_bytes(b"x")
    actualizador.instalar_windows(str(exe), dormir=lambda s: None)
    cmd, kw = lanzados[0]
    assert cmd[0] == str(exe)
    for flag in ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                 "/CURRENTUSER", "/REABRIR=1"):
        assert flag in cmd
    assert kw["close_fds"] is True
    assert kw["creationflags"] == 0x8 | 0x200


def test_instalar_windows_si_el_proceso_muere(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: ProcesoFalso(muere=3))
    with pytest.raises(actualizador.InstaladorNoArranco, match="3"):
        actualizador.instalar_windows(str(tmp_path / NOMBRE), dormir=lambda s: None)


def test_instalar_windows_tiempo_agotado(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: ProcesoFalso())
    t = iter(range(0, 10000, 100))
    with pytest.raises(actualizador.InstaladorNoArranco, match="a tiempo"):
        actualizador.instalar_windows(str(tmp_path / NOMBRE), espera=250,
                                      dormir=lambda s: None, relogio=lambda: next(t))


def test_instalar_windows_error_740_reintenta_con_runas(tmp_path, monkeypatch):
    def popen(cmd, **kw):
        e = OSError("requiere elevacion")
        e.winerror = 740
        raise e

    elevados = []

    def shell(ruta, params):
        elevados.append((ruta, params))
        open(params.split("/SINAL=")[1].split(" ")[0].strip('"'), "w").close()
        return 42

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(actualizador, "_shell_execute_runas", shell)
    actualizador.instalar_windows(str(tmp_path / NOMBRE), dormir=lambda s: None)
    assert len(elevados) == 1 and "/REABRIR=1" in elevados[0][1]


def test_instalar_windows_otro_error_de_os_se_propaga(tmp_path, monkeypatch):
    def popen(cmd, **kw):
        raise OSError("no existe")

    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(OSError):
        actualizador.instalar_windows(str(tmp_path / NOMBRE))


def test_instalar_windows_uac_rechazado(tmp_path, monkeypatch):
    def popen(cmd, **kw):
        e = OSError()
        e.winerror = 740
        raise e

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(actualizador, "_shell_execute_runas", lambda r, p: 5)
    with pytest.raises(actualizador.InstaladorNoArranco):
        actualizador.instalar_windows(str(tmp_path / NOMBRE))


def test_instalar_macos_abre_el_dmg(monkeypatch):
    llamadas = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: llamadas.append(cmd))
    actualizador.instalar_macos("/tmp/x.dmg")
    assert llamadas == [["open", "/tmp/x.dmg"]]


def test_instalar_segun_plataforma(monkeypatch):
    llamadas = []
    monkeypatch.setattr(actualizador, "instalar_windows", lambda r: llamadas.append("w"))
    monkeypatch.setattr(actualizador, "instalar_macos", lambda r: llamadas.append("m"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert actualizador.instalar("x") == "cerrar"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert actualizador.instalar("x") == "manual"
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(actualizador.InstaladorNoArranco):
        actualizador.instalar("x")
    assert llamadas == ["w", "m"]


# ------------------------------------------------------------------ puede_autoinstalar

def test_puede_autoinstalar_windows_con_registro(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(actualizador, "_clave_registro_existe", lambda: True)
    assert actualizador.puede_autoinstalar() is True
    monkeypatch.setattr(actualizador, "_clave_registro_existe", lambda: False)
    assert actualizador.puede_autoinstalar() is False  # portable: solo la pagina


def test_puede_autoinstalar_sin_compilar_es_falso(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(actualizador, "_clave_registro_existe", lambda: True)
    assert actualizador.puede_autoinstalar() is False


def test_puede_autoinstalar_macos_compilado(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert actualizador.puede_autoinstalar() is True
    monkeypatch.setattr(sys, "platform", "linux")
    assert actualizador.puede_autoinstalar() is False


# ------------------------------------------------------------------ limpieza y log

def test_limpiar_descargas_borra_instaladores_viejos(tmp_path, monkeypatch):
    monkeypatch.setattr(actualizador, "dir_descargas", lambda: str(tmp_path))
    (tmp_path / NOMBRE).write_bytes(b"x")
    (tmp_path / (NOMBRE + ".part")).write_bytes(b"x")
    actualizador.limpiar_descargas()
    assert os.listdir(tmp_path) == []
    monkeypatch.setattr(actualizador, "dir_descargas", lambda: str(tmp_path / "no_existe"))
    actualizador.limpiar_descargas()  # sin carpeta: no falla


def test_log_se_escribe_y_rota(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPRESORFREE_CONFIG", str(tmp_path))
    actualizador._log("hola")
    assert "hola" in open(actualizador.ruta_log(), encoding="utf-8").read()
    with open(actualizador.ruta_log(), "w") as f:
        f.write("x" * (actualizador.MAX_LOG + 1))
    actualizador._log("nuevo")
    assert os.path.exists(actualizador.ruta_log() + ".1")
    assert open(actualizador.ruta_log(), encoding="utf-8").read().count("nuevo") == 1


