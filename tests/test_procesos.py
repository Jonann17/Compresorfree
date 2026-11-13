"""procesos.ejecutar: lectura sin deadlock, cancelacion real y limpieza de hijos.

Los hijos son `sys.executable -c ...` para que las pruebas sean portables.
Escritas desde la especificacion (PR1-B), no desde la implementacion.
"""
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from conftest import RAIZ

import procesos

PY = [sys.executable, "-u", "-c"]


def hijo(codigo):
    return PY + [textwrap.dedent(codigo)]


DORMIR = hijo("import time; print('listo'); time.sleep(60)")


@pytest.fixture(autouse=True)
def sin_procesos_vivos():
    yield
    vivos = procesos.procesos_vivos()
    for p in vivos:  # que un fallo no deje hijos de 60 s colgados
        p.kill()
    assert vivos == []


def en_hilo(funcion, limite=60):
    """Ejecuta funcion en un hilo y falla si no termina (deteccion de deadlock)."""
    caja = {}

    def correr():
        try:
            caja["ok"] = funcion()
        except BaseException as e:  # noqa: BLE001
            caja["error"] = e

    t = threading.Thread(target=correr, daemon=True)
    t.start()
    t.join(limite)
    assert not t.is_alive(), "ejecutar no termino: posible deadlock"
    if "error" in caja:
        raise caja["error"]
    return caja["ok"]


def test_cancelado_es_runtimeerror_con_mensaje_por_defecto():
    assert issubclass(procesos.Cancelado, RuntimeError)
    assert str(procesos.Cancelado()) == "Compresion cancelada."


def test_sin_consola_existe():
    assert procesos.SIN_CONSOLA == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def test_callbacks_en_orden_y_en_el_hilo_llamador():
    lineas, hilos = [], set()

    def cb(linea):
        lineas.append(linea)
        hilos.add(threading.get_ident())

    r = procesos.ejecutar(hijo("for i in range(300): print(i)"), on_stdout_linea=cb)
    assert lineas == [str(i) for i in range(300)]
    assert hilos == {threading.get_ident()}
    assert r.returncode == 0
    assert r.stdout == ""


def test_stdout_sin_callback_se_acota_a_las_ultimas_lineas():
    r = procesos.ejecutar(hijo("for i in range(1000): print('o%d' % i)"))
    assert r.stdout.split("\n") == [f"o{i}" for i in range(800, 1000)]


def test_stderr_acotado_a_max_lineas():
    codigo = "import sys\nfor i in range(1000): print('e%d' % i, file=sys.stderr)"
    r = procesos.ejecutar(hijo(codigo))
    assert r.stderr.split("\n") == [f"e{i}" for i in range(800, 1000)]
    r = procesos.ejecutar(hijo(codigo), max_lineas=5)
    assert r.stderr.split("\n") == [f"e{i}" for i in range(995, 1000)]


def test_returncode_distinto_de_cero_no_lanza():
    r = procesos.ejecutar(hijo("import sys; sys.exit(3)"))
    assert r.returncode == 3


def test_salida_grande_por_ambos_pipes_no_bloquea():
    codigo = """
        import sys
        linea = 'x' * 1023
        for i in range(8000):
            print(linea)
            print(linea, file=sys.stderr)
    """
    cuenta = []
    r = en_hilo(lambda: procesos.ejecutar(hijo(codigo), on_stdout_linea=cuenta.append))
    assert len(cuenta) == 8000
    assert r.returncode == 0
    assert len(r.stderr.split("\n")) == 200
    # y sin callback (stdout tambien en el deque)
    r = en_hilo(lambda: procesos.ejecutar(hijo(codigo)))
    assert len(r.stdout.split("\n")) == 200 and len(r.stderr.split("\n")) == 200


def test_procesos_vivos_durante_y_despues():
    visto = []

    def cb(linea):
        visto.extend(procesos.procesos_vivos())

    procesos.ejecutar(hijo("print('hola')"), on_stdout_linea=cb)
    assert len(visto) == 1 and isinstance(visto[0], subprocess.Popen)
    assert procesos.procesos_vivos() == []


def test_cancelacion_desde_otro_hilo_es_rapida_y_mata_al_hijo():
    cancelar = threading.Event()
    vivos, marca = [], []

    def disparar():
        vivos.extend(procesos.procesos_vivos())
        marca.append(time.monotonic())
        cancelar.set()

    timer = threading.Timer(0.5, disparar)
    timer.start()
    with pytest.raises(procesos.Cancelado):
        procesos.ejecutar(DORMIR, cancelar)
    latencia = time.monotonic() - marca[0]
    timer.join()
    assert latencia < 1.0
    assert len(vivos) == 1 and vivos[0].poll() is not None
    assert procesos.procesos_vivos() == []


@pytest.mark.skipif(os.name == "nt", reason="SIGTERM ignorable solo en POSIX")
def test_escala_a_kill_si_el_hijo_ignora_sigterm():
    codigo = """
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        print('listo', flush=True)
        time.sleep(60)
    """
    cancelar = threading.Event()
    vivos, marca = [], []

    def cb(linea):  # el hijo ya instalo el manejador: cancelar de forma determinista
        vivos.extend(procesos.procesos_vivos())
        marca.append(time.monotonic())
        cancelar.set()

    with pytest.raises(procesos.Cancelado):
        procesos.ejecutar(hijo(codigo), cancelar, on_stdout_linea=cb, timeout_terminar=1.0)
    assert time.monotonic() - marca[0] < 1.0 + 2
    assert vivos[0].poll() == -signal.SIGKILL


@pytest.mark.parametrize("excepcion", [ValueError, KeyboardInterrupt])
def test_excepcion_en_callback_termina_el_hijo_y_se_propaga(excepcion):
    vivos = []

    def cb(linea):
        vivos.extend(procesos.procesos_vivos())
        raise excepcion("fallo del callback")

    t0 = time.monotonic()
    with pytest.raises(excepcion):
        procesos.ejecutar(DORMIR, on_stdout_linea=cb)
    assert time.monotonic() - t0 < 10
    assert len(vivos) == 1 and vivos[0].poll() is not None


def test_ya_cancelado_no_crea_el_proceso(monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debia crearse ningun proceso")

    monkeypatch.setattr(subprocess, "Popen", prohibido)
    cancelar = threading.Event()
    cancelar.set()
    with pytest.raises(procesos.Cancelado):
        procesos.ejecutar(DORMIR, cancelar)


def test_terminar_es_idempotente_y_tolera_procesos_terminados():
    p = subprocess.Popen(PY + ["import time; time.sleep(60)"])
    procesos.terminar(p, timeout=3.0)
    assert p.poll() is not None
    procesos.terminar(p)  # ya terminado: no debe fallar
    procesos.terminar_todos()  # registro vacio: no debe fallar


@pytest.mark.skipif(sys.platform != "win32",
                    reason="Job Objects: la garantia de matar al hijo si el padre muere "
                           "a la fuerza solo existe en Windows")
def test_windows_matar_al_padre_a_la_fuerza_mata_al_hijo(tmp_path):
    """Garantia 2: el proceso que llamo a ejecutar muere con kill() y el nieto tambien."""
    import ctypes

    pid_archivo = tmp_path / "pid.txt"
    aux = tmp_path / "padre.py"
    aux.write_text(textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {RAIZ!r})
        import procesos
        destino = {str(pid_archivo)!r}
        codigo = ("import os, time\\n"
                  "open(%r + '.tmp', 'w').write(str(os.getpid()))\\n"
                  "os.replace(%r + '.tmp', %r)\\n"
                  "time.sleep(60)" % (destino, destino, destino))
        procesos.ejecutar([sys.executable, "-c", codigo])
    """), encoding="utf-8")

    padre = subprocess.Popen([sys.executable, str(aux)])
    pid = None
    try:
        limite = time.monotonic() + 20
        while time.monotonic() < limite and pid is None:
            if pid_archivo.exists():
                texto = pid_archivo.read_text().strip()
                pid = int(texto) if texto else None
            time.sleep(0.1)
        assert pid, "el hijo no escribio su PID"
        padre.kill()
        padre.wait(10)

        SYNCHRONIZE = 0x00100000
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.WaitForSingleObject.restype = ctypes.c_uint32
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        h = k32.OpenProcess(SYNCHRONIZE, False, pid)
        if h:  # si no se puede abrir, el proceso ya no existe
            try:
                assert k32.WaitForSingleObject(h, 5000) == 0, "el nieto sigue vivo"
            finally:
                k32.CloseHandle(h)
    finally:
        if padre.poll() is None:
            padre.kill()
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def test_env_se_pasa_al_hijo():
    env = dict(os.environ, COMPRESORFREE_PRUEBA="hola")
    r = procesos.ejecutar([sys.executable, "-c",
                           "import os; print(os.environ.get('COMPRESORFREE_PRUEBA'))"], env=env)
    assert r.stdout.strip() == "hola"
