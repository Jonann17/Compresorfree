"""Escritura segura de archivos, comun a video, PDF, interfaz grafica y CLI.

Garantias:
- Nunca se sobrescribe un archivo existente (ni una entrada del lote ni un
  archivo de terceros): la publicacion usa primitivas del sistema operativo que
  fallan si el destino ya existe.
- El archivo final solo aparece cuando el resultado esta completo y validado:
  se escribe primero en un temporal oculto del mismo directorio y se publica
  con un renombrado atomico.
- Si el sistema de archivos no ofrece una primitiva sin sobrescritura, se falla
  sin escribir el destino en lugar de arriesgarse a pisar algo.
"""

import contextlib
import ctypes
import ctypes.util
import errno
import os
import sys
import uuid


class DestinoExistente(FileExistsError):
    """El destino ya existe; no se sobrescribe."""


class PublicacionNoSegura(OSError):
    """El sistema de archivos no permite publicar sin riesgo de sobrescribir."""


class ArchivoOmitido(Exception):
    """El archivo no se procesa a proposito (por ejemplo, un PDF firmado)."""


# ---------------------------------------------------------------- Rutas

def nombre_alternativo(destino, n):
    """'video_comprimido.mp4', 2 -> 'video_comprimido (2).mp4'."""
    base, ext = os.path.splitext(destino)
    return f"{base} ({n}){ext}"


def clave_ruta(ruta):
    """Clave para comparar rutas que quiza aun no existen.

    Es conservadora: ignora mayusculas aunque el disco las distinga, lo que
    en el peor caso cuesta un "(2)" de mas, nunca una sobrescritura."""
    carpeta, nombre = os.path.split(os.path.abspath(ruta))
    return os.path.normcase(os.path.realpath(carpeta)), nombre.casefold()


def es_misma_ruta(a, b):
    """True si `a` y `b` son el mismo archivo (symlinks, hardlinks, mayusculas)."""
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return clave_ruta(a) == clave_ruta(b)


def planificar_lote(entradas, ruta_por_defecto, carpeta=None):
    """Elige un destino para cada entrada sin chocar con nada.

    ruta_por_defecto: funcion entrada -> ruta de salida sugerida.
    Un destino nunca coincide con una entrada del lote, con otro destino del
    lote ni con un archivo que ya exista. Ante conflicto se agrega (2), (3)...
    """
    ocupadas = {clave_ruta(e) for e in entradas}
    destinos = []
    for entrada in entradas:
        sugerido = ruta_por_defecto(entrada)
        if carpeta:
            sugerido = os.path.join(carpeta, os.path.basename(sugerido))
        destino, n = sugerido, 2
        while clave_ruta(destino) in ocupadas or os.path.lexists(destino):
            destino = nombre_alternativo(sugerido, n)
            n += 1
        ocupadas.add(clave_ruta(destino))
        destinos.append(destino)
    return destinos


# ---------------------------------------------------------------- Temporales

def crear_temporal(destino):
    """Crea (en exclusiva) un temporal oculto junto a `destino`.

    Conserva la extension para que FFmpeg sepa el formato. Dos instancias
    nunca comparten temporal (uuid + O_EXCL)."""
    carpeta, nombre = os.path.split(os.path.abspath(destino))
    base, ext = os.path.splitext(nombre)
    while True:
        tmp = os.path.join(carpeta, f".{base}.parcial-{uuid.uuid4().hex[:12]}{ext}")
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        except FileExistsError:
            continue
        os.close(fd)
        return tmp


@contextlib.contextmanager
def salida_temporal(destino):
    """Entrega una ruta temporal y la borra al salir si no se publico."""
    tmp = crear_temporal(destino)
    try:
        yield tmp
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(tmp)


def _fsync_archivo(ruta):
    with open(ruta, "rb+") as f:
        os.fsync(f.fileno())


def _fsync_carpeta(carpeta):
    if os.name == "nt":
        return  # en Windows no se puede abrir un directorio para fsync
    with contextlib.suppress(OSError):
        fd = os.open(carpeta, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


# ---------------------------------------------------------------- Publicacion

_NO_SOPORTADO = {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}


def _libc():
    if sys.platform == "darwin":
        return ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    return ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)


def _renombrar_exclusivo(origen, destino):
    """Renombrado atomico que falla si `destino` existe.

    Devuelve True si se hizo, False si el sistema no ofrece la primitiva.
    Lanza DestinoExistente si el destino ya existe."""
    if os.name == "nt":
        # MoveFileExW sin MOVEFILE_REPLACE_EXISTING: falla si existe.
        try:
            os.rename(origen, destino)
        except FileExistsError as e:
            raise DestinoExistente(errno.EEXIST, "El destino ya existe", destino) from e
        return True

    try:
        libc = _libc()
        if sys.platform == "darwin":
            funcion = libc.renamex_np
            funcion.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            llamada = lambda: funcion(os.fsencode(origen), os.fsencode(destino), 0x4)  # RENAME_EXCL
        else:
            funcion = libc.renameat2
            funcion.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                ctypes.c_char_p, ctypes.c_uint]
            llamada = lambda: funcion(-100, os.fsencode(origen), -100,  # AT_FDCWD
                                      os.fsencode(destino), 1)          # RENAME_NOREPLACE
    except (OSError, AttributeError):
        return False  # libc sin la funcion: se prueba con hardlink

    if llamada() == 0:
        return True
    codigo = ctypes.get_errno()
    if codigo == errno.EEXIST:
        raise DestinoExistente(errno.EEXIST, "El destino ya existe", destino)
    if codigo in _NO_SOPORTADO:
        return False
    raise OSError(codigo, os.strerror(codigo), destino)


def _enlazar_exclusivo(origen, destino):
    """Alternativa POSIX: hardlink (falla si existe) y borrar el temporal."""
    try:
        os.link(origen, destino)
    except FileExistsError as e:
        raise DestinoExistente(errno.EEXIST, "El destino ya existe", destino) from e
    except OSError as e:
        if e.errno in _NO_SOPORTADO | {errno.EPERM, errno.EMLINK, errno.EXDEV}:
            return False
        raise
    os.remove(origen)
    return True


def publicar(tmp, destino):
    """Mueve `tmp` a `destino` sin sobrescribir nunca.

    Lanza DestinoExistente si el destino aparecio, o PublicacionNoSegura si
    el disco no permite hacerlo sin riesgo (en ese caso `tmp` queda intacto)."""
    _fsync_archivo(tmp)
    if not (_renombrar_exclusivo(tmp, destino) or _enlazar_exclusivo(tmp, destino)):
        raise PublicacionNoSegura(
            errno.ENOTSUP,
            "Este disco no permite guardar sin riesgo de sobrescribir archivos. "
            "Elige otra carpeta de destino.", destino)
    _fsync_carpeta(os.path.dirname(os.path.abspath(destino)))
    return destino


def publicar_con_nombre_libre(tmp, destino, max_intentos=1000):
    """Como publicar(), pero si el destino existe prueba con (2), (3)..."""
    candidato = destino
    for n in range(2, max_intentos + 2):
        try:
            return publicar(tmp, candidato)
        except DestinoExistente:
            candidato = nombre_alternativo(destino, n)
    raise DestinoExistente(errno.EEXIST, "No se encontro un nombre libre", destino)


def finalizar(tmp, destino, si_existe):
    """Publica segun la politica: 'error' (CLI -o) o 'renombrar' (lotes)."""
    if si_existe == "renombrar":
        return publicar_con_nombre_libre(tmp, destino)
    if si_existe == "error":
        return publicar(tmp, destino)
    raise ValueError(f"si_existe invalido: {si_existe}")


def comprobar_destino(entrada, salida, si_existe):
    """Validaciones previas, antes de gastar tiempo comprimiendo."""
    if si_existe not in ("error", "renombrar"):
        raise ValueError(f"si_existe invalido: {si_existe}")
    if es_misma_ruta(salida, entrada):
        raise ValueError("El archivo de salida no puede ser el mismo que el de entrada.")
    if si_existe == "error" and os.path.lexists(salida):
        raise DestinoExistente(errno.EEXIST, "El destino ya existe", salida)
    carpeta = os.path.dirname(os.path.abspath(salida))
    if not os.path.isdir(carpeta):
        raise FileNotFoundError(f"No existe la carpeta de destino: {carpeta}")
