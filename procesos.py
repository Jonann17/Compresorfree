"""Procesos externos (FFmpeg, Ghostscript) cancelables y sin huerfanos.

- ejecutar() lanza el comando, lee stdout y stderr en hilos aparte (nunca se
  bloquea aunque el hijo escriba mucho), guarda solo las ultimas lineas y
  comprueba `cancelar` cada `intervalo` segundos.
- Todo proceso vivo queda en un registro: terminar_todos() los cierra (se usa
  al cerrar la ventana, con Ctrl+C y al salir del interprete).
- En Windows los hijos van a un Job Object con KILL_ON_JOB_CLOSE: si la app
  muere de golpe, Windows los mata. En Linux/macOS no hay garantia equivalente
  si el proceso de la app recibe SIGKILL (limitacion conocida).
"""

import atexit
import collections
import logging
import queue
import subprocess
import sys
import threading
import time
import typing

log = logging.getLogger(__name__)

# En Windows evita que se abra una ventana de consola por cada proceso.
SIN_CONSOLA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_FIN = object()  # marca de fin de stdout en la cola
_lock = threading.Lock()
_registro = set()


class Cancelado(RuntimeError):
    """El usuario cancelo la tarea."""

    def __init__(self, mensaje="Compresion cancelada."):
        super().__init__(mensaje)


class Resultado(typing.NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _comprobar(cancelar):
    if cancelar is not None and cancelar.is_set():
        raise Cancelado()


def ejecutar(cmd, cancelar=None, on_stdout_linea=None, max_lineas=200,
             timeout_terminar=3.0, intervalo=0.2):
    """Ejecuta `cmd` y devuelve un Resultado (no lanza por returncode != 0).

    on_stdout_linea: se llama en este mismo hilo con cada linea de stdout
    (sin el salto final); entonces Resultado.stdout queda vacio.
    Lanza Cancelado si `cancelar` se activa; el proceso se termina antes."""
    _comprobar(cancelar)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", creationflags=SIN_CONSOLA,
    )
    with _lock:
        _registro.add(proc)
    lectores = []
    try:
        _asignar_job(proc)
        return _vigilar(proc, lectores, cancelar, on_stdout_linea, max_lineas, intervalo)
    except BaseException:
        terminar(proc, timeout_terminar)
        raise
    finally:
        with _lock:
            _registro.discard(proc)
        _cerrar_flujos(proc, lectores)


def _vigilar(proc, lectores, cancelar, on_stdout_linea, max_lineas, intervalo):
    salida = collections.deque(maxlen=max_lineas)
    errores = collections.deque(maxlen=max_lineas)
    cola = queue.Queue()
    lectores.append(_lector(proc.stdout, cola.put if on_stdout_linea else salida.append,
                            lambda: cola.put(_FIN)))
    lectores.append(_lector(proc.stderr, errores.append))

    while True:
        _comprobar(cancelar)
        try:
            linea = cola.get(timeout=intervalo)
        except queue.Empty:
            continue
        if linea is _FIN:
            break
        on_stdout_linea(linea)

    while True:
        _comprobar(cancelar)
        try:
            proc.wait(timeout=intervalo)
            break
        except subprocess.TimeoutExpired:
            pass

    for hilo in lectores:
        hilo.join(timeout=2.0)
    return Resultado(proc.returncode, "\n".join(salida), "\n".join(errores))


def _lector(flujo, destino, al_terminar=None):
    def leer():
        try:
            for linea in flujo:
                destino(linea[:-1] if linea.endswith("\n") else linea)
        except (OSError, ValueError):
            pass  # flujo cerrado
        finally:
            if al_terminar:
                al_terminar()

    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    return hilo


def _cerrar_flujos(proc, lectores):
    for hilo in lectores:
        hilo.join(timeout=1.0)
    if any(hilo.is_alive() for hilo in lectores):
        return  # un nieto conserva el pipe: se deja al recolector
    for flujo in (proc.stdout, proc.stderr):
        try:
            flujo.close()
        except (OSError, ValueError, AttributeError):
            pass


def terminar(proc, timeout=3.0):
    """terminate(); si no termina en `timeout` s, kill(). Idempotente."""
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except OSError:  # incluye ProcessLookupError: ya habia terminado
        pass


def terminar_todos(timeout=3.0):
    """Termina todos los procesos lanzados por ejecutar() que sigan vivos."""
    vivos = procesos_vivos()
    for proc in vivos:
        try:
            proc.terminate()  # primero a todos, para que cierren en paralelo
        except OSError:
            pass
    limite = time.monotonic() + timeout
    for proc in vivos:
        terminar(proc, max(0.0, limite - time.monotonic()))


def procesos_vivos():
    with _lock:
        procs = list(_registro)
    return [p for p in procs if p.poll() is None]


atexit.register(terminar_todos)


# ---------------------------------------------------------------- Windows: Job Object

_job = None          # handle del job (vive mientras viva la app); False si no se pudo crear
_job_asignado = False


def job_windows_activo():
    """True si el ultimo proceso quedo dentro del Job Object (solo Windows)."""
    return sys.platform == "win32" and bool(_job) and _job_asignado


def _asignar_job(proc):
    global _job, _job_asignado
    if sys.platform != "win32":
        return
    try:
        with _lock:
            if _job is None:
                _job = False
                _job = _crear_job()
        if not _job:
            raise OSError("no hay Job Object")
        if not _kernel32.AssignProcessToJobObject(_job, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        _job_asignado = True
    except Exception as e:
        _job_asignado = False
        log.warning("No se pudo asignar el proceso al Job Object: %s", e)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _crear_job():
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
                job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return job
