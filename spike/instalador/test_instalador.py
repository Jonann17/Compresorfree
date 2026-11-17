"""Pruebas del spike con inyeccion de fallos (Linux)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import instalador as ins  # noqa: E402

NONCE = "ab" * 8


class Corte(BaseException):
    """Simula un corte de energia / kill -9: no lo atrapa ningun except."""


def hacer_app(base, version):
    os.makedirs(os.path.join(base, "data"))
    for n, c in (("app", "bin-" + version), ("VERSION", version), ("data/blob", version * 50)):
        with open(os.path.join(base, n), "w") as f:
            f.write(c)
    os.symlink("VERSION", os.path.join(base, "enlace"))
    return base


def version_completa(ruta):
    """La ruta contiene un arbol completo y coherente de UNA version."""
    v = open(os.path.join(ruta, "VERSION")).read()
    assert open(os.path.join(ruta, "app")).read() == "bin-" + v
    assert open(os.path.join(ruta, "data/blob")).read() == v * 50
    assert os.readlink(os.path.join(ruta, "enlace")) == "VERSION"
    return v


class Entorno:
    def __init__(self, tmp):
        self.tmp = str(tmp)
        self.ruta = hacer_app(os.path.join(self.tmp, "apps", "CF"), "1.0")
        self.origen = hacer_app(os.path.join(self.tmp, "A"), "2.0")
        self.estado = os.path.join(self.tmp, "estado")
        self.lanzadas = []
        self.salud = "ok"  # ok | nada | nonce_malo | muere | version_mala
        self.reloj = 0.0

    def ahora(self):
        return self.reloj

    def dormir(self, s):
        self.reloj += s

    def lanzar(self, args, env=None):
        self.lanzadas.append((args, env))
        proc = type("P", (), {"pid": 4242, "poll": lambda s: None})()
        if env and "CF_NONCE" in env:
            ver = open(os.path.join(os.path.dirname(args[0]), "VERSION")).read()
            reg = {"nonce": env["CF_NONCE"], "version": ver, "ruta_exe": args[0], "pid": 4242}
            if self.salud == "nonce_malo":
                reg["nonce"] = "00"
            elif self.salud == "version_mala":
                reg["version"] = "9.9"
            elif self.salud == "muere":
                proc.poll = lambda: 1
                return proc
            if self.salud != "nada":
                with open(os.path.join(env["CF_SALUD_DIR"], "s.json"), "w") as f:
                    json.dump(reg, f)
        return proc

    def instalar(self, **kw):
        base = dict(origen=self.origen, ruta=self.ruta, pid=1, nonce=NONCE, version="2.0",
                    exe_rel="app", estado_dir=self.estado, timeout_salud=5,
                    lanzar=self.lanzar, esperar=lambda *a, **k: True, ahora=self.ahora,
                    dormir=self.dormir)
        base.update(kw)
        return ins.instalar(**base)

    def recuperar(self):
        return ins.recuperar(self.estado, lanzar=self.lanzar)


@pytest.fixture
def env(tmp_path):
    return Entorno(tmp_path)


def sin_restos(env):
    assert not any(os.path.exists(env.ruta + s) for s in (".nueva", ".anterior", ".fallida"))


def test_camino_feliz(env):
    assert env.instalar() == "instalada"
    assert version_completa(env.ruta) == "2.0"
    assert os.path.isdir(env.origen)  # se copia, nunca se mueve
    sin_restos(env)


def test_camino_feliz_con_swap_atomico_simulado(env):
    def swap(a, b):  # emula RENAME_SWAP con tres renames
        os.rename(a, a + ".t")
        os.rename(b, a)
        os.rename(a + ".t", b)
    assert env.instalar(swap=swap) == "instalada"
    assert version_completa(env.ruta) == "2.0"
    sin_restos(env)


PASOS = ["iniciado", "copiando", "copiado", "intercambiando", "tras_rename1",
         "anterior_movida", "intercambiado", "lanzada", "confirmada", "revirtiendo"]


@pytest.mark.parametrize("corte", PASOS)
@pytest.mark.parametrize("salud", ["ok", "nada"])
def test_corte_en_cada_paso_y_recuperar(env, corte, salud):
    env.salud = salud

    def hook(p):
        if p == corte:
            raise Corte(p)
    try:
        env.instalar(hook=hook)
    except Corte:
        pass
    env.recuperar()
    assert os.path.isdir(env.ruta)
    assert version_completa(env.ruta) in ("1.0", "2.0")
    env.recuperar()  # idempotente
    assert version_completa(env.ruta) in ("1.0", "2.0")
    sin_restos(env)


@pytest.mark.parametrize("corte", ["tras_swap", "intercambiado", "lanzada"])
def test_corte_con_swap(env, corte):
    env.salud = "nada"

    def swap(a, b):
        os.rename(a, a + ".t")
        os.rename(b, a)
        os.rename(a + ".t", b)

    def hook(p):
        if p == corte:
            raise Corte(p)
    with pytest.raises(Corte):
        env.instalar(swap=swap, hook=hook)
    env.recuperar()
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)


def test_corte_entre_renames_sin_salud_vuelve_a_la_anterior(env):
    def hook(p):
        if p == "tras_rename1":
            raise Corte(p)
    with pytest.raises(Corte):
        env.instalar(hook=hook)
    assert not os.path.exists(env.ruta)  # el hueco existe realmente
    assert env.recuperar() == "revertida"
    assert version_completa(env.ruta) == "1.0"


def test_corte_tras_exito_con_salud_confirma(env):
    def hook(p):
        if p == "lanzada":
            raise Corte(p)
    with pytest.raises(Corte):
        env.instalar(hook=hook)
    assert env.recuperar() == "confirmada"
    assert version_completa(env.ruta) == "2.0"
    sin_restos(env)


def test_sin_espacio(env):
    assert env.instalar(libre=lambda p: 10) == "revertida"
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)


def test_enospc_a_mitad_de_copia(env):
    def copiar(src, dst, symlinks=True):
        os.makedirs(dst)
        open(os.path.join(dst, "app"), "w").write("parcial")
        raise OSError(28, "No space left on device")
    assert env.instalar(copiar=copiar) == "revertida"
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)


def test_sin_permisos_directorio_padre(env):
    with pytest.raises(ins.ErrorInstalacion):
        env.instalar(escribible=lambda d: False)
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)


@pytest.mark.parametrize("cual", [1, 2])
def test_permiso_denegado_en_rename(env, cual):
    n = {"c": 0}

    def rename(a, b):
        n["c"] += 1
        if n["c"] == cual:
            raise PermissionError(13, "denegado")
        os.rename(a, b)
    assert env.instalar(rename=rename) == "revertida"
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)


@pytest.mark.parametrize("salud", ["nada", "muere", "nonce_malo", "version_mala"])
def test_nueva_version_no_sana_hace_rollback(env, salud):
    env.salud = salud
    assert env.instalar() == "revertida"
    assert version_completa(env.ruta) == "1.0"
    sin_restos(env)
    assert env.lanzadas[-1][0] == [os.path.join(env.ruta, "app")]  # relanza la anterior
    assert env.lanzadas[-1][1] is None


def test_nueva_version_no_arranca(env):
    def lanzar(args, env_=None):
        if env_:
            raise OSError("no arranca")
        return None
    assert env.instalar(lanzar=lanzar) == "revertida"
    assert version_completa(env.ruta) == "1.0"


def test_salud_con_ruta_exe_ajena_rechazada(env, tmp_path):
    env.salud = "nada"
    otra = os.path.join(str(tmp_path), "otra", "app")
    orig = env.lanzar

    def lanzar(args, e=None):
        p = orig(args, e)
        if e:
            json.dump({"nonce": NONCE, "version": "2.0", "ruta_exe": otra, "pid": 4242},
                      open(os.path.join(e["CF_SALUD_DIR"], "x.json"), "w"))
        return p
    assert env.instalar(lanzar=lanzar) == "revertida"


def test_pid_reutilizado_no_bloquea():
    estado = {"t": 0.0}
    ok = ins.esperar_pid(77, 1000, timeout=5, vivo=lambda p: True, hora_inicio=lambda p: 2000,
                         ahora=lambda: estado["t"], dormir=lambda s: None)
    assert ok  # mismo PID, otra hora de inicio: el original murio


def test_pid_vivo_mismo_inicio_agota_timeout():
    t = {"t": 0.0}

    def dormir(s):
        t["t"] += s
    assert not ins.esperar_pid(77, 1000, timeout=1, vivo=lambda p: True,
                               hora_inicio=lambda p: 1000, ahora=lambda: t["t"], dormir=dormir)


def test_pid_muerto_real():
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    ini = ins.hora_inicio_pid(p.pid)
    p.wait()
    assert ins.esperar_pid(p.pid, ini, timeout=5)


def test_app_original_no_termina(env):
    with pytest.raises(ins.ErrorInstalacion):
        env.instalar(esperar=lambda *a, **k: False)
    assert version_completa(env.ruta) == "1.0"


def test_recuperar_sin_journal_no_hace_nada(env):
    assert env.recuperar() == "nada"
    assert version_completa(env.ruta) == "1.0"


def test_journal_atomico_y_duradero(tmp_path):
    ins.escribir_journal(str(tmp_path), {"paso": "a"})
    ins.escribir_journal(str(tmp_path), {"paso": "b"})
    assert ins.leer_journal(str(tmp_path)) == {"paso": "b"}
    assert not os.path.exists(os.path.join(str(tmp_path), "journal.json.tmp"))


def test_runonce_con_winreg_falso():
    llamadas = []

    class W:
        HKEY_CURRENT_USER, REG_SZ = 1, 1
        CreateKey = staticmethod(lambda h, k: llamadas.append(("k", k)) or "c")
        SetValueEx = staticmethod(lambda c, n, r, t, v: llamadas.append(("v", v)))
        CloseKey = staticmethod(lambda c: None)
    assert ins.registrar_runonce(r"C:\Users\Ñandú\A\app.exe", r"C:\e", winreg=W)
    assert "--recuperar" in llamadas[-1][1]


def test_runonce_no_se_ejecuta_fuera_de_win32():
    if sys.platform != "win32":
        assert ins.registrar_runonce("x", "y") is False


def test_cli_recuperar(env):
    assert ins.main(["--recuperar", "--estado-dir", env.estado]) == 0
