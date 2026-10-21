# Compresorfree


Interfaz grafica para comprimir:
- **Video**: cualquier formato (avi, mkv, mov, wmv, flv, webm, mpeg, 3gp, ts, ...) se convierte a MP4 (H.264 + AAC).
- **PDF**: recomprime las imagenes y optimiza la estructura del archivo.

## Requisitos
- Python 3.8+ con tkinter (viene incluido en Python para Windows/macOS)
- `pip install -r requirements.txt`
- Opcional: FFmpeg y/o Ghostscript instalados en el sistema. Si existe Ghostscript se usa para PDF;
  si no, se usa pikepdf + Pillow. Si no hay FFmpeg en el sistema se usa el de `imageio-ffmpeg`.

## Uso
- Interfaz grafica: `python app.py` -> elige "Video" o "PDF", el archivo y el nivel.
- Linea de comandos (el tipo se detecta por la extension):
  - `python app.py video.mkv -n alta -o salida.mp4`
  - `python app.py documento.pdf -n media`

## Niveles
| Nivel | Video                          | PDF (imagenes)                   |
|-------|--------------------------------|----------------------------------|
| baja  | CRF 23, resolucion original, audio 160k | JPEG calidad 85, lado max. 2500 px |
| media | CRF 28, max. 1080p, audio 128k | JPEG calidad 70, lado max. 1600 px |
| alta  | CRF 32, max. 720p, audio 96k   | JPEG calidad 50, lado max. 1000 px |

Si un PDF ya esta optimizado y el resultado pesaria mas, se guarda una copia del original.
