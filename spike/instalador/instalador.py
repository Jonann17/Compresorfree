"""SPIKE PR3-B: instalador seguro de actualizaciones (prototipo, no integrable).

Protocolo (A = paquete ya verificado y extraido a una carpeta temporal):
  1. A espera a que muera el PID de la app (comprobando hora de inicio).
  2. A COPIA su arbol a <ruta>.nueva (mismo volumen), con marca del nonce.
  3. Journal duradero (fsync + os.replace) con el paso actual, fuera de la app.
  4. Intercambio: renamex_np(RENAME_SWAP) en macOS; dos renames en Windows/Linux.
  5. Lanza la nueva con CF_NONCE/CF_SALUD_DIR y espera un registro de salud.
  6. Sin salud o proceso muerto: rollback y relanza la anterior.
  --recuperar: lee el journal y completa o revierte (tras corte de energia).
Todo lo no portable se inyecta (lanzar_proceso, esperar_pid, ahora, intercambio...).
"""
import argparse
import ctypes
import errno
import json
import os
import shutil
import subprocess
import sys
import time

MARCA = ".cf_instalacion"
JOURNAL = "journal.json"
INTERCAMBIAR = "intercambiar"


class ErrorInstalacion(Exception):
    pass


# ---------------------------------------------------------------- utilidades
def _fsync_dir(ruta):
    if os.name == "nt":
        return
    fd = os.open(ruta, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def escribir_journal(estado_dir, datos):
    """Escritura atomica y duradera: tmp + fsync + os.replace + fsync(dir)."""
    os.makedirs(estado_dir, exist_ok=True)
    destino = os.path.join(estado_dir, JOURNAL)
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, destino)
    _fsync_dir(estado_dir)


def leer_journal(estado_dir):
    try:
        with open(os.path.join(estado_dir, JOURNAL), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hora_inicio_pid(pid):
    """Hora de inicio del proceso (None si no existe o no se puede saber)."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            datos = f.read().decode("utf-8", "replace")
        return int(datos.rsplit(")", 1)[1].split()[19])  # starttime (ticks)
    except (OSError, ValueError, IndexError):
        pass
    try:
        import psutil  # opcional en Windows/macOS
        return psutil.Process(pid).create_time()
    except Exception:
        return None


def pid_vivo(pid):
    if os.name == "nt":
        return hora_inicio_pid(pid) is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # un zombi cuenta como muerto
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            return f.read().decode("utf-8", "replace").rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def esperar_pid(pid, inicio, timeout=60.0, vivo=pid_vivo, hora_inicio=hora_inicio_pid,
                ahora=time.monotonic, dormir=time.sleep):
    """True si el proceso original murio (o su PID fue reutilizado por otro)."""
    limite = ahora() + timeout
    while ahora() < limite:
        if not vivo(pid):
            return True
        actual = hora_inicio(pid)
        if inicio is not None and actual is not None and actual != inicio:
            return True  # PID reutilizado: el original ya no existe
        dormir(0.1)
    return False


def lanzar_proceso(args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.Popen(args, env=e, close_fds=True)


def _tamano(ruta):
    total = 0
    for base, _, ficheros in os.walk(ruta):
        for n in ficheros:
            try:
                total += os.lstat(os.path.join(base, n)).st_size
            except OSError:
                pass
    return total


def espacio_libre(ruta):
    return shutil.disk_usage(ruta).free


def puede_escribir(directorio):
    return os.access(directorio, os.W_OK | os.X_OK)


def _borrar(ruta):
    if os.path.islink(ruta) or os.path.isfile(ruta):
        os.remove(ruta)
    elif os.path.isdir(ruta):
        shutil.rmtree(ruta, ignore_errors=True)


def _fsync_arbol(raiz):
    if os.name == "nt":
        return
    for base, dirs, ficheros in os.walk(raiz):
        for n in ficheros:
            p = os.path.join(base, n)
            if os.path.islink(p):
                continue
            fd = os.open(p, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def _leer_marca(arbol):
    try:
        with open(os.path.join(arbol, MARCA), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


# ------------------------------------------------------------- intercambio
def swap_macos(a, b):
    """renamex_np(a, b, RENAME_SWAP): intercambio atomico (solo macOS)."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renamex_np(os.fsencode(a), os.fsencode(b), 0x2) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e), a)


def _rutas(ruta):
    return ruta + ".nueva", ruta + ".anterior", ruta + ".fallida"


def intercambio_dos_renames(ruta, nueva, anterior, rename=os.rename, hook=lambda p: None):
    rename(ruta, anterior)
    hook("tras_rename1")
    rename(nueva, ruta)


# ------------------------------------------------------------------ rollback
def _localizar_viejo(ruta):
    nueva, anterior, _ = _rutas(ruta)
    for c in (anterior, nueva):  # tras swap atomico el viejo queda en .nueva
        if os.path.isdir(c) and _leer_marca(c) is None:
            return c
    return None


def rollback(ruta, rename=os.rename):
    """ruta -> .fallida, viejo -> ruta. Idempotente; nunca deja la ruta vacia
    si existe una version completa."""
    _, _, fallida = _rutas(ruta)
    viejo = _localizar_viejo(ruta)
    if viejo is None:
        return False
    if os.path.lexists(ruta):
        if _leer_marca(ruta) is None:
            return True  # ya esta la anterior
        _borrar(fallida)
        rename(ruta, fallida)
    rename(viejo, ruta)
    return True


# --------------------------------------------------------------------- salud
def _salud_valida(salud_dir, nonce, version, exe_esperado, pid=None):
    try:
        nombres = os.listdir(salud_dir)
    except OSError:
        return False
    for n in nombres:
        try:
            with open(os.path.join(salud_dir, n), encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or r.get("nonce") != nonce or r.get("version") != version:
            continue
        if os.path.realpath(str(r.get("ruta_exe", ""))) != os.path.realpath(exe_esperado):
            continue
        if pid is not None and r.get("pid") != pid:
            continue
        return True
    return False


def esperar_salud(salud_dir, nonce, version, exe, proc, timeout, ahora=time.monotonic,
                  dormir=time.sleep):
    limite = ahora() + timeout
    while True:
        if _salud_valida(salud_dir, nonce, version, exe, getattr(proc, "pid", None)):
            return True
        if proc.poll() is not None and not _salud_valida(salud_dir, nonce, version, exe):
            return False
        if ahora() >= limite:
            return False
        dormir(0.1)


# ------------------------------------------------------------------ instalar
def instalar(origen, ruta, pid, nonce, version, exe_rel, estado_dir, *, timeout_salud=30.0,
             inicio_pid=None, lanzar=lanzar_proceso, esperar=esperar_pid, ahora=time.monotonic,
             dormir=time.sleep, swap=None, rename=os.rename, copiar=shutil.copytree,
             libre=espacio_libre, escribible=puede_escribir, hook=lambda p: None):
    """Devuelve 'instalada' | 'revertida' | 'sin_cambios'. hook(paso) permite
    inyectar cortes (excepcion BaseException) tras cada paso del protocolo."""
    ruta = os.path.abspath(ruta)
    padre = os.path.dirname(ruta)
    nueva, anterior, fallida = _rutas(ruta)
    salud_dir = os.path.join(estado_dir, "salud")
    estado = {"paso": "iniciado", "ruta": ruta, "nonce": nonce, "version": version,
              "exe_rel": exe_rel, "origen": origen, "salud_dir": salud_dir,
              "swap": swap is not None}

    def paso(nombre):
        estado["paso"] = nombre
        escribir_journal(estado_dir, estado)
        hook(nombre)

    def relanzar_anterior():
        lanzar([os.path.join(ruta, exe_rel)])

    # 0. precondiciones (no tocan nada)
    if not escribible_ok(escribible, padre):
        paso("terminado")
        raise ErrorInstalacion("sin permisos de escritura en " + padre)
    paso("iniciado")
    if inicio_pid is None:
        inicio_pid = hora_inicio_pid(pid)
    if not esperar(pid, inicio_pid):
        paso("terminado")
        raise ErrorInstalacion("la app original no termino")

    # 1. copiar (nunca mover) a <ruta>.nueva
    for r in (nueva, anterior, fallida):
        _borrar(r)
    paso("copiando")
    try:
        if libre(padre) < int(_tamano(origen) * 1.1) + 1:
            raise OSError(errno.ENOSPC, "sin espacio")
        copiar(origen, nueva, symlinks=True)
        with open(os.path.join(nueva, MARCA), "w", encoding="utf-8") as f:
            f.write(nonce)
            f.flush()
            os.fsync(f.fileno())
        _fsync_arbol(nueva)
    except OSError:
        _borrar(nueva)
        paso("terminado")
        relanzar_anterior()
        return "revertida"
    paso("copiado")

    # 2. intercambio
    paso("intercambiando")
    try:
        if swap is not None:
            swap(ruta, nueva)
            hook("tras_swap")
        else:
            intercambio_dos_renames(ruta, nueva, anterior, rename, hook)
            paso("anterior_movida")
    except OSError:
        # fallo limpio (p.ej. permisos): dejar la ruta como estaba
        rollback(ruta)
        _borrar(nueva)
        paso("terminado")
        relanzar_anterior()
        return "revertida"
    paso("intercambiado")

    # 3. lanzar la nueva y esperar salud
    os.makedirs(salud_dir, exist_ok=True)
    exe = os.path.join(ruta, exe_rel)
    try:
        proc = lanzar([exe], {"CF_NONCE": nonce, "CF_SALUD_DIR": salud_dir})
        paso("lanzada")
        sano = esperar_salud(salud_dir, nonce, version, exe, proc, timeout_salud, ahora, dormir)
    except OSError:
        sano = False
    if sano:
        paso("confirmada")
        _limpiar(ruta)
        paso("terminado")
        return "instalada"
    paso("revirtiendo")
    rollback(ruta, rename)
    _borrar(fallida)
    _borrar(nueva)
    paso("terminado")
    relanzar_anterior()
    return "revertida"


def escribible_ok(escribible, padre):
    return bool(escribible(padre))


def _limpiar(ruta):
    for r in _rutas(ruta):
        _borrar(r)


# ----------------------------------------------------------------- recuperar
def recuperar(estado_dir, *, lanzar=lanzar_proceso, rename=os.rename):
    """Tras un corte: completa o revierte. Garantiza que <ruta> exista y sea
    una version completa. Devuelve 'nada' | 'confirmada' | 'revertida'."""
    j = leer_journal(estado_dir)
    if not j:
        return "nada"
    ruta = j["ruta"]
    nueva, anterior, fallida = _rutas(ruta)
    paso = j["paso"]
    exe = os.path.join(ruta, j["exe_rel"])
    resultado = "revertida"
    if paso == "terminado":
        resultado = "nada"
    elif paso == "confirmada":
        resultado = "confirmada"
    else:
        nueva_activa = os.path.isdir(ruta) and _leer_marca(ruta) == j["nonce"]
        if nueva_activa and _salud_valida(j["salud_dir"], j["nonce"], j["version"], exe):
            resultado = "confirmada"
        else:
            if nueva_activa or not os.path.lexists(ruta):
                rollback(ruta, rename)
    if resultado == "confirmada":
        _limpiar(ruta)
    elif resultado == "revertida":
        if os.path.isdir(ruta):
            _borrar(fallida)
            _borrar(nueva)
    # invariante: la ruta nunca falta
    if not os.path.lexists(ruta):
        for c in (anterior, fallida):
            if os.path.isdir(c):
                rename(c, ruta)
                break
    j["paso"] = "terminado"
    escribir_journal(estado_dir, j)
    if resultado == "revertida":
        lanzar([os.path.join(ruta, j["exe_rel"])])
    return resultado


# -------------------------------------------------------------------- RunOnce
def registrar_runonce(exe_copia, estado_dir, winreg=None, nombre="CompresorFreeRecuperar"):
    """Entrada HKCU RunOnce que ejecuta la copia de A con --recuperar.
    Solo se ejecuta en win32 (winreg inyectable para pruebas)."""
    if winreg is None:
        if sys.platform != "win32":
            return False
        import winreg
    cmd = f'"{exe_copia}" --recuperar --estado-dir "{estado_dir}"'
    clave = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\RunOnce")
    try:
        winreg.SetValueEx(clave, nombre, 0, winreg.REG_SZ, cmd)
    finally:
        winreg.CloseKey(clave)
    return True


# ------------------------------------------------------------------------ CLI
def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--instalar-sobre")
    p.add_argument("--pid", type=int)
    p.add_argument("--nonce")
    p.add_argument("--recuperar", action="store_true")
    p.add_argument("--estado-dir", required=True)
    p.add_argument("--origen", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--version", default="")
    p.add_argument("--exe-rel", default="app")
    p.add_argument("--timeout-salud", type=float, default=30.0)
    a = p.parse_args(argv)
    if a.recuperar:
        print(recuperar(a.estado_dir))
        return 0
    if not (a.instalar_sobre and a.pid and a.nonce):
        p.error("faltan --instalar-sobre/--pid/--nonce")
    if sys.platform == "win32":
        registrar_runonce(sys.executable, a.estado_dir)
    swap = swap_macos if sys.platform == "darwin" else None
    print(instalar(a.origen, a.instalar_sobre, a.pid, a.nonce, a.version, a.exe_rel,
                   a.estado_dir, timeout_salud=a.timeout_salud, swap=swap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
