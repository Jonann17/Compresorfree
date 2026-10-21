"""Compresor de video a MP4 (H.264 + AAC) usando FFmpeg.

Acepta cualquier formato de video que FFmpeg pueda leer (avi, mkv, mov, wmv,
flv, webm, mpeg, 3gp, ts, m4v, ...) y lo convierte a MP4 con tres niveles de
compresion: baja, media o alta.

La interfaz grafica y la linea de comandos estan en app.py.
"""

import os
import re
import shutil
import subprocess
import threading

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


def obtener_duracion(ffmpeg, entrada):
    """Duracion del video en segundos (None si no se puede determinar)."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", entrada],
        capture_output=True, text=True, errors="replace",
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        if "Invalid data" in proc.stderr or "No such file" in proc.stderr:
            raise RuntimeError(f"No se puede leer el archivo de video:\n{entrada}")
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def ruta_salida_por_defecto(entrada, nivel):
    base, _ = os.path.splitext(entrada)
    return f"{base}_comprimido_{nivel}.mp4"


def comprimir(entrada, salida=None, nivel="media", progreso=None, cancelar=None):
    """Comprime `entrada` a MP4. Devuelve la ruta del archivo generado.

    progreso: funcion opcional que recibe un porcentaje (0-100).
    cancelar: threading.Event opcional; si se activa se detiene FFmpeg.
    """
    if nivel not in NIVELES:
        raise ValueError(f"Nivel invalido: {nivel}. Usa: {', '.join(NIVELES)}")
    if not os.path.isfile(entrada):
        raise FileNotFoundError(f"No existe el archivo: {entrada}")

    cfg = NIVELES[nivel]
    salida = salida or ruta_salida_por_defecto(entrada, nivel)
    if os.path.abspath(salida) == os.path.abspath(entrada):
        raise ValueError("El archivo de salida no puede ser el mismo que el de entrada.")

    ffmpeg = buscar_ffmpeg()
    duracion = obtener_duracion(ffmpeg, entrada)

    # Dimensiones pares (requisito de H.264/yuv420p) y limite de altura opcional.
    if cfg["altura_max"]:
        escala = f"scale=-2:'min({cfg['altura_max']},trunc(ih/2)*2)'"
    else:
        escala = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

    cmd = [
        ffmpeg, "-hide_banner", "-y", "-i", entrada,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", escala,
        "-c:v", "libx264", "-crf", str(cfg["crf"]), "-preset", cfg["preset"],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", cfg["audio"], "-ac", "2",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        salida,
    ]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )
    errores = []
    hilo_err = threading.Thread(
        target=lambda: errores.extend(proc.stderr.readlines()), daemon=True
    )
    hilo_err.start()

    for linea in proc.stdout:
        if cancelar is not None and cancelar.is_set():
            proc.kill()
            break
        if progreso and duracion and linea.startswith("out_time_us="):
            valor = linea.split("=", 1)[1].strip()
            if valor.isdigit():
                progreso(min(100.0, int(valor) / 1e6 / duracion * 100))

    proc.wait()
    hilo_err.join(timeout=2)

    if cancelar is not None and cancelar.is_set():
        if os.path.exists(salida):
            os.remove(salida)
        raise RuntimeError("Compresion cancelada.")
    if proc.returncode != 0:
        detalle = "".join(errores[-15:])
        raise RuntimeError(f"FFmpeg fallo (codigo {proc.returncode}):\n{detalle}")

    if progreso:
        progreso(100.0)
    return salida


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
