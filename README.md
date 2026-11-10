# Compresorfree

App de escritorio para **Windows** y **macOS** que comprime videos (a MP4) y PDF.

## Que hace
- Comprime **varios archivos a la vez**: agregalos a la lista y se procesan uno tras otro,
  con el estado de cada uno y una barra de progreso general.
- **Peso estimado** antes de comprimir (boton *Estimar peso*): en videos comprime unos
  segundos de muestra y extrapola; en PDF hace la compresion en un archivo temporal.
- Guarda los resultados junto a cada original o en la carpeta que elijas.

## Tus archivos estan protegidos
- **Nunca se modifica ni se borra un archivo original.**
- **Nunca se sobrescribe un archivo que ya existe.** Si el nombre de salida esta ocupado
  (o coincide con otro archivo de la lista), se guarda como `nombre (2).mp4`, `(3)`...
  En la linea de comandos, `-o` con un archivo que ya existe da error y no toca nada.
- **Nunca queda un archivo a medias con el nombre final.** Se escribe en un temporal oculto
  (`.nombre.parcial-xxxx.mp4`) en la misma carpeta, se comprueba que el resultado sea valido
  (el video se decodifica al principio y al final y dura lo mismo; el PDF tiene las mismas
  paginas) y solo entonces aparece con su nombre. Ante un error o una cancelacion, el temporal
  se borra.
- Si el disco no permite guardar sin riesgo de pisar archivos, la app avisa y no guarda.
- **PDF firmados digitalmente o cifrados se omiten** (estado *Omitido*): comprimirlos
  invalidaria la firma o quitaria su proteccion. El original queda intacto.

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
2. Publica la version nueva (siempre un numero mayor que el anterior), de cualquiera de estas formas:
   - **Desde la web**: pestana *Actions* -> *Compilar apps (Windows y macOS)* -> *Run workflow*,
     escribe la version (ej. `1.1.0`) y pulsa *Run workflow*.
   - **Con git**:
     ```bash
     git tag v1.1.0
     git push origin v1.1.0
     ```
3. GitHub Actions compila Windows y Mac, crea la release `v1.1.0` y todas las apps
   instaladas la detectan la proxima vez que se abran.

La version que muestra la app sale de ese numero (no hace falta editar `version.py`).
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
- Python 3.10+ con tkinter (viene incluido en Python para Windows/macOS)
- `pip install -r requirements.txt`
- Opcional: FFmpeg y/o Ghostscript instalados en el sistema. Si existe Ghostscript se usa para PDF;
  si no, se usa pikepdf + Pillow. Si no hay FFmpeg en el sistema se usa el de `imageio-ffmpeg`.

### Uso
- Interfaz grafica: `python app.py` -> elige "Video" o "PDF", agrega uno o varios archivos y el nivel.
- Linea de comandos (el tipo se detecta por la extension):
  - `python app.py video.mkv -n alta -o salida.mp4`
  - `python app.py documento.pdf -n media`
  - Varios a la vez: `python app.py video1.avi video2.mov video3.mkv -n media -d carpeta_salida`
  - Solo ver el peso estimado: `python app.py video1.avi documento.pdf -n alta --estimar`
  - Codigo de salida: `0` si todo se comprimio; `1` si algun archivo dio error o se omitio.

### Pruebas
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -v
```
Las pruebas generan sus propios videos y PDF sinteticos (no usan archivos personales).
Si Ghostscript esta instalado, tambien se prueba ese motor. Se ejecutan en GitHub Actions
(Ubuntu, Windows y macOS) en cada pull request.

## Niveles
| Nivel | Video                          | PDF (imagenes)                   |
|-------|--------------------------------|----------------------------------|
| baja  | CRF 23, resolucion original, audio 160k | JPEG calidad 85, lado max. 2500 px |
| media | CRF 28, max. 1080p, audio 128k | JPEG calidad 70, lado max. 1600 px |
| alta  | CRF 32, max. 720p, audio 96k   | JPEG calidad 50, lado max. 1000 px |

Si un PDF ya esta optimizado y el resultado pesaria mas, se guarda una copia del original.
