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
- **Antes de comprimir se comprueba el espacio libre** del destino (el archivo mas un margen
  de 50 MB). Si falta, aparece "No hay espacio suficiente en ..." y no se crea nada; si el
  disco se llena durante la compresion, tampoco queda un archivo a medias.
- **Cancelar detiene FFmpeg y Ghostscript en el acto.** Si cierras la ventana con una
  compresion en curso, la app pregunta; al aceptar, cancela, espera a que se limpien los
  temporales y se cierra sin dejar procesos ni archivos a medias. En Windows, aunque la app
  se cierre a la fuerza (Administrador de tareas), el sistema termina tambien FFmpeg y
  Ghostscript. En Linux/macOS eso no esta garantizado si la app muere con `kill -9`.
- **PDF firmados digitalmente o con contrasena de apertura se omiten** (estado *Omitido*);
  los cifrados solo con contrasena de propietario se comprimen conservando cifrado y permisos.
  Si el resultado altera la estructura (paginas, enlaces, formularios, adjuntos, marcadores...)
  no se guarda. El original queda intacto.

## Descargar la app
Ve a la pestana **Releases** del repositorio y descarga (X.Y.Z es la version):
- **Windows**: `Compresorfree-X.Y.Z-windows-x64.zip` -> descomprimir y abrir `Compresorfree.exe`.
- **Mac (M1/M2/M3...)**: `Compresorfree-X.Y.Z-macos-arm64.dmg`
- **Mac (Intel)**: `Compresorfree-X.Y.Z-macos-x64.dmg`

Cada release incluye `manifest.json` (SHA-256 de cada paquete) y su firma
`manifest.json.minisig`, hecha por el propietario con una clave que nunca esta en GitHub.

No hace falta instalar Python ni FFmpeg: todo va incluido.

> La app no esta firmada digitalmente, asi que la primera vez:
> - **Windows**: si aparece "Windows protegio su PC", pulsa *Mas informacion* -> *Ejecutar de todas formas*.
> - **Mac**: arrastra la app a *Aplicaciones*, luego clic derecho -> *Abrir* -> *Abrir*.
>   Si dice que "esta danada": `xattr -cr /Applications/Compresorfree.app` en la Terminal.

## Actualizaciones
La app busca actualizaciones sola al abrirse (y con el boton **Buscar actualizaciones**).
Si hay una version nueva, avisa y ofrece **abrir la pagina de descarga**: no descarga ni
instala nada por su cuenta. Solo anuncia releases que traen un manifiesto firmado y
comprueba la firma con las claves publicas de `claves_confianza.py`; si la firma no es
valida, avisa de que no se pudo verificar y recomienda descargar solo desde la pagina
oficial. Mientras hay una compresion en curso no se ofrece nada.

### Publicar una version (solo el propietario)
Ninguna clave privada ni secreto de firma se sube nunca a GitHub. GitHub Actions solo
compila y deja la release en **borrador**; el propietario la firma sin red y la publica.
Todo el proceso (crear las claves, guardarlas y firmar) esta en
[docs/GUIA_FIRMA.md](docs/GUIA_FIRMA.md).

1. **Borrador**: sube tus cambios a `main` y lanza la version (siempre mayor que la anterior):
   - **Desde la web**: pestana *Actions* -> *Compilar apps (Windows y macOS)* -> *Run workflow*,
     escribe la version (ej. `1.1.0`) y pulsa *Run workflow*.
   - **Con git**: `git tag v1.1.0` y `git push origin v1.1.0`.

   Actions pasa las pruebas, compila Windows y Mac y crea la release `v1.1.0` en borrador
   con los tres paquetes. La version que muestra la app sale de ese numero (no hace falta
   editar `version.py`).
2. **Preparar** (con [GitHub CLI](https://cli.github.com/) y `gh auth login`):
   ```bash
   python herramientas/preparar_release.py v1.1.0
   ```
   Descarga los paquetes a `release-v1.1.0/`, calcula sus SHA-256, escribe
   `release-v1.1.0/manifest.json`, lista los cambios en `.github/workflows/` desde la
   ultima release (revisalos) e imprime el comando de firma.
3. **Firmar sin red**: en el equipo de firma, desconectado, con la clave en el USB:
   ```bash
   minisign -S -s <ruta_usb>/principal.key -m release-v1.1.0/manifest.json \
     -t "compresorfree tipo=release version=1.1.0"
   ```
   Esto crea `release-v1.1.0/manifest.json.minisig`.
4. **Publicar**:
   ```bash
   python herramientas/publicar_release.py v1.1.0
   ```
   Verifica la firma con `claves_confianza.py`, comprueba que el manifiesto coincida con los
   paquetes (los locales y los del borrador en GitHub), sube el manifiesto y su firma y
   publica la release. Si algo no cuadra, no sube nada.

Una release publicada sin manifiesto firmado no se anuncia en la app.
En cada push a `main` tambien se compilan las apps (pestana *Actions*, como artefactos
`Compresorfree-0.0.0-dev-...`) para probarlas antes de publicar.

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
- **PDF**: recomprime las imagenes y optimiza la estructura del archivo. El motor por defecto es pikepdf (conservador); la casilla "Compresion agresiva (Ghostscript)" o `--motor ghostscript` usa Ghostscript si esta instalado (el resultado se descarta si altera enlaces, formularios, adjuntos, etc.).

### Requisitos
- Python 3.10+ con tkinter (viene incluido en Python para Windows/macOS)
- `pip install -r requirements.txt`
- Opcional: FFmpeg y/o Ghostscript instalados en el sistema. Ghostscript solo se usa para PDF si lo pides (compresion agresiva);
  por defecto se usa pikepdf + Pillow. Si no hay FFmpeg en el sistema se usa el de `imageio-ffmpeg`.

### Uso
- Interfaz grafica: `python app.py` -> elige "Video" o "PDF", agrega uno o varios archivos y el nivel.
- Linea de comandos (el tipo se detecta por la extension):
  - `python app.py video.mkv -n alta -o salida.mp4`
  - `python app.py documento.pdf -n media`
  - Varios a la vez: `python app.py video1.avi video2.mov video3.mkv -n media -d carpeta_salida`
  - Video a un tamano maximo (dos pasadas, p. ej. WhatsApp 16 MB): `python app.py video.mkv --max-mb 16`
    (en la interfaz: campo "Tamano maximo (MB)" y botones rapidos; si el video es demasiado largo da un error claro).
  - Solo ver el peso estimado: `python app.py video1.avi documento.pdf -n alta --estimar`
  - Solo se aceptan videos (avi, mkv, mov, mp4...) y PDF: un archivo de otro formato
    (por ejemplo `.jpg`) da el aviso "formato no soportado", cuenta como error y el resto sigue.
  - Codigo de salida: `0` si todo se comprimio; `1` si algun archivo dio error, se omitio
    o no es un formato soportado.

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
