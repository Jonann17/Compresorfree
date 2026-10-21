# Compresorfree

App de escritorio para **Windows** y **macOS** que comprime videos (a MP4) y PDF.

## Descargar la app
Ve a la pestana **Releases** del repositorio y descarga:
- **Windows**: `Compresorfree-Windows.zip` -> descomprimir y abrir `Compresorfree.exe`.
- **Mac (M1/M2/M3...)**: `Compresorfree-macOS-AppleSilicon.dmg`
- **Mac (Intel)**: `Compresorfree-macOS-Intel.dmg`

No hace falta instalar Python ni FFmpeg: todo va incluido.

> La app no esta firmada digitalmente, asi que la primera vez:
> - **Windows**: si aparece "Windows protegio su PC", pulsa *Mas informacion* -> *Ejecutar de todas formas*.
> - **Mac**: arrastra la app a *Aplicaciones*, luego clic derecho -> *Abrir* -> *Abrir*.
>   Si dice que "esta danada": `xattr -cr /Applications/Compresorfree.app` en la Terminal.

## Actualizaciones
La app busca actualizaciones sola al abrirse (y con el boton **Buscar actualizaciones**).
Si hay una version nueva en *Releases*, la descarga, reemplaza la app y la vuelve a abrir.

### Publicar una actualizacion
1. Sube tus cambios a `main`.
2. Crea un tag con el numero de version nuevo (siempre mayor que el anterior):
   ```bash
   git tag v1.1.0
   git push origin v1.1.0
   ```
3. GitHub Actions compila Windows y Mac, crea la release `v1.1.0` y todas las apps
   instaladas la detectan la proxima vez que se abran.

La version que muestra la app sale del tag (no hace falta editar `version.py`).
En cada push a `main` tambien se compilan las apps (pestana *Actions*, como artefactos)
para probarlas antes de publicar.

## Compilar en tu computadora
```bash
pip install -r requirements.txt -r requirements-build.txt
python compilar.py
```
Resultado en `dist/` (`Compresorfree.exe` en Windows, `Compresorfree.app` en Mac).
Hay que compilar en cada sistema: el .exe en Windows y la .app en Mac.

## Usar desde el codigo fuente


Interfaz grafica para comprimir:
- **Video**: cualquier formato (avi, mkv, mov, wmv, flv, webm, mpeg, 3gp, ts, ...) se convierte a MP4 (H.264 + AAC).
- **PDF**: recomprime las imagenes y optimiza la estructura del archivo.

### Requisitos
- Python 3.8+ con tkinter (viene incluido en Python para Windows/macOS)
- `pip install -r requirements.txt`
- Opcional: FFmpeg y/o Ghostscript instalados en el sistema. Si existe Ghostscript se usa para PDF;
  si no, se usa pikepdf + Pillow. Si no hay FFmpeg en el sistema se usa el de `imageio-ffmpeg`.

### Uso
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
