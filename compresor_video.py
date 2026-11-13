"""Compresor de video a MP4 (H.264 + AAC) usando FFmpeg.

Acepta cualquier formato de video que FFmpeg pueda leer (avi, mkv, mov, wmv,
flv, webm, mpeg, 3gp, ts, m4v, ...) y lo convierte a MP4 con tres niveles de
compresion: baja, media o alta.

La interfaz grafica y la linea de comandos estan en app.py.
"""

import os
import re
import shutil
import tempfile

import nucleo
import procesos

# Niveles de compresion. Un CRF mas alto = archivo mas pequeno y menor calidad.
NIVELES = {
    "baja": {
        "crf": 23, "preset": "medium", "audio": "160k", "altura_max": None,
    },
    "media": {
        "crf": 28, "preset": "medium", "audio": "128k", "altura_max": 1080,
    },
    "alta": {
        "crf": 32, "preset": "slow", "audio": "96k", "altura_max": 720,
    },
}

SIN_CONSOLA = procesos.SIN_CONSOLA  # alias por compatibilidad

EXTENSIONES_VIDEO = (
    "*.mp4 *.m4v *.avi *.mkv *.mov *.wmv *.flv *.webm *.mpeg *.mpg *.3gp "
    "*.3g2 *.ts *.mts *.m2ts *.vob *.ogv *.asf *.rm *.rmvb *.divx *.f4v"
)


def buscar_ffmpeg():
    """Devuelve la ruta a ffmpeg (sistema o paquete imageio-ffmpeg)."""
    ruta = shutil.which("ffmpeg")
    if ruta:
        return ruta
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError(
            "No se encontro FFmpeg. Instalalo (https://ffmpeg.org) o ejecuta:\n"
            "    pip install imageio-ffmpeg"
        )


def obtener_duracion(ffmpeg, entrada, cancelar=None):
    """Duracion del video en segundos (None si no se puede determinar)."""
    # Margen amplio de lineas: con muchos capitulos o metadatos el stderr es largo.
    stderr = procesos.ejecutar([ffmpeg, "-hide_banner", "-i", entrada], cancelar,
                               max_lineas=5000).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not m:
        if "Invalid data" in stderr or "No such file" in stderr:
            raise RuntimeError(f"No se puede leer el archivo de video:\n{entrada}")
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def ruta_salida_por_defecto(entrada, nivel):
    base, _ = os.path.splitext(entrada)
    return f"{base}_comprimido_{nivel}.mp4"


def _opciones_codificacion(cfg):
    # Dimensiones pares (requisito de H.264/yuv420p) y limite de altura opcional.
    if cfg["altura_max"]:
        escala = f"scale=-2:'min({cfg['altura_max']},trunc(ih/2)*2)'"
    else:
        escala = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    return [
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", escala,
        "-c:v", "libx264", "-crf", str(cfg["crf"]), "-preset", cfg["preset"],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", cfg["audio"], "-ac", "2",
    ]


def estimar(entrada, nivel="media", cancelar=None):
    """Estima el tamano final en bytes comprimiendo algunos segundos de muestra
    (al 20%, 50% y 80% del video) y extrapolando a la duracion total.
    Devuelve None si no se puede estimar o si se cancela."""
    try:
        return _estimar(entrada, NIVELES[nivel], cancelar)
    except procesos.Cancelado:
        return None


def _estimar(entrada, cfg, cancelar):
    ffmpeg = buscar_ffmpeg()
    duracion = obtener_duracion(ffmpeg, entrada, cancelar)
    if not duracion:
        return None

    largo = 4.0
    if duracion <= 3 * largo * 1.5:
        tramos = [(0.0, duracion)]  # video corto: se comprime entero
    else:
        tramos = [(duracion * f - largo / 2, largo) for f in (0.2, 0.5, 0.8)]

    total_bytes = total_seg = 0.0
    with tempfile.TemporaryDirectory(prefix="compresorfree_") as tmp:
        for i, (inicio, seg) in enumerate(tramos):
            muestra = os.path.join(tmp, f"muestra{i}.mp4")
            r = procesos.ejecutar(
                [ffmpeg, "-hide_banner", "-y", "-ss", f"{inicio:.3f}", "-i", entrada,
                 "-t", f"{seg:.3f}", *_opciones_codificacion(cfg), muestra],
                cancelar,
            )
            if r.returncode != 0 or not os.path.exists(muestra):
                continue
            total_bytes += os.path.getsize(muestra)
            total_seg += seg
    if not total_seg:
        return None
    return int(total_bytes / total_seg * duracion)


def validar_salida(ffmpeg, ruta, duracion_esperada, cancelar=None):
    """Comprobacion rapida antes de publicar: el MP4 se abre, tiene video que
    se decodifica y una duracion coherente con la del original."""
    # Se decodifica el principio y el ultimo segundo: un archivo truncado o
    # corrupto falla o deja errores en stderr.
    for posicion in (["-frames:v", "3"], ["-sseof", "-1"]):
        entrada = ["-i", ruta, *posicion] if posicion[0] == "-frames:v" else [*posicion, "-i", ruta]
        r = procesos.ejecutar(
            [ffmpeg, "-v", "error", *entrada, "-map", "0:v:0", "-f", "null", "-"], cancelar)
        if r.returncode != 0 or r.stderr.strip():
            raise RuntimeError(f"El resultado no es un video valido:\n{r.stderr[-1000:]}")
    if duracion_esperada:
        try:
            duracion = obtener_duracion(ffmpeg, ruta, cancelar)
        except procesos.Cancelado:
            raise
        except RuntimeError:
            duracion = None
        # Holgura para contenedores cuya duracion incluye pistas que no se copian.
        tolerancia = max(2.0, duracion_esperada * 0.05)
        if duracion is None or abs(duracion - duracion_esperada) > tolerancia:
            raise RuntimeError(
                f"El resultado dura {duracion} s y el original {duracion_esperada:.1f} s; "
                "no se guardo para no entregar un video incompleto.")


def comprimir(entrada, salida=None, nivel="media", progreso=None, cancelar=None,
              si_existe="error"):
    """Comprime `entrada` a MP4. Devuelve la ruta del archivo generado.

    progreso: funcion opcional que recibe un porcentaje (0-100).
    cancelar: threading.Event opcional; si se activa se detiene FFmpeg.
    si_existe: 'error' (no toca un destino existente y lanza DestinoExistente)
               o 'renombrar' (guarda como "nombre (2).mp4", "(3)"...).
    Nunca sobrescribe nada: escribe en un temporal y lo publica al final.
    """
    if nivel not in NIVELES:
        raise ValueError(f"Nivel invalido: {nivel}. Usa: {', '.join(NIVELES)}")
    if not os.path.isfile(entrada):
        raise FileNotFoundError(f"No existe el archivo: {entrada}")

    cfg = NIVELES[nivel]
    salida = salida or ruta_salida_por_defecto(entrada, nivel)
    nucleo.comprobar_destino(entrada, salida, si_existe)

    ffmpeg = buscar_ffmpeg()
    duracion = obtener_duracion(ffmpeg, entrada, cancelar)

    with nucleo.salida_temporal(salida) as tmp:
        _codificar(ffmpeg, entrada, tmp, cfg, duracion, progreso, cancelar)
        validar_salida(ffmpeg, tmp, duracion, cancelar)
        # Nada se publica despues de cancelar; el temporal lo borra salida_temporal().
        if cancelar is not None and cancelar.is_set():
            raise procesos.Cancelado()
        final = nucleo.finalizar(tmp, salida, si_existe)

    if progreso:
        progreso(100.0)
    return final


def _codificar(ffmpeg, entrada, salida, cfg, duracion, progreso, cancelar):
    cmd = [
        ffmpeg, "-hide_banner", "-y", "-i", entrada, *_opciones_codificacion(cfg),
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        salida,
    ]

    def linea_progreso(linea):
        if progreso and duracion and linea.startswith("out_time_us="):
            valor = linea.split("=", 1)[1].strip()
            if valor.isdigit():
                progreso(min(100.0, int(valor) / 1e6 / duracion * 100))

    r = procesos.ejecutar(cmd, cancelar, on_stdout_linea=linea_progreso)
    if r.returncode != 0:
        detalle = "\n".join(r.stderr.splitlines()[-15:])
        raise RuntimeError(f"FFmpeg fallo (codigo {r.returncode}):\n{detalle}")


def tamano_legible(nbytes):
    for unidad in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unidad}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def resumen(entrada, salida):
    antes, despues = os.path.getsize(entrada), os.path.getsize(salida)
    reduccion = (1 - despues / antes) * 100 if antes else 0
    return (f"Original:   {tamano_legible(antes)}\n"
            f"Comprimido: {tamano_legible(despues)}\n"
            f"Reduccion:  {reduccion:.1f}%")
