# CLAUDE_RESPUESTA — Compresorfree

**Base revisada:** `main` @ `61c7b9c` · plan `plan/claude-codex-workflow` @ `06703a7` (PR #1)
**Método:** lectura completa de `app.py`, `compresor_video.py`, `compresor_pdf.py`, `actualizador.py`, `compilar.py`, `.github/workflows/compilar.yml` y `requirements*.txt`, más **reproducciones reales** en Linux (Python 3.12/3.13, FFmpeg del sistema, Ghostscript 10.02.1, pikepdf 10.x). No probé en Windows ni macOS reales; lo que depende de esos sistemas queda marcado como no confirmado.
**Postura general:** coincido con el diagnóstico y las prioridades de ChatGPT. Discrepo en cuatro puntos concretos (Ghostscript como motor prioritario, desactivar la autoinstalación, validación con `ffprobe`, y diferir toda la modularización a P2) y añado seis hallazgos que el plan no menciona, dos de ellos graves.

---

## Diagnóstico confirmado

Todos los casos se reprodujeron con comandos; las evidencias pueden repetirse.

| # | Sev. | Hallazgo | Evidencia |
|---|---|---|---|
| C1 | **P0** | **Un archivo de entrada del lote puede ser destruido.** Si el lote contiene `a.avi` y `a_comprimido_media.mp4`, el destino de `a.avi` es justamente la segunda entrada: FFmpeg la sobrescribe (`-y`) *antes* de procesarla. **El plan no lo detectó**: solo habla de destinos preexistentes en general. | `python app.py a.avi a_comprimido_media.mp4 -n media` → el md5 de la segunda entrada cambia. `rutas_salida()` (`app.py:48`) deduplica salidas entre sí, pero nunca las compara con el conjunto de entradas; `comprimir()` solo compara con *su propia* entrada (`compresor_video.py`, `compresor_pdf.py`). |
| C2 | P0 | Un destino preexistente se pisa sin aviso (GUI y CLI). | Se crea `b_comprimido_media.mp4` con texto, se comprime `b.avi` → el archivo pasa a ser un MP4 (`ftyp isom`). `-y` en `compresor_video.py:144`; `pdf.save()` y `shutil.copyfile()` en `compresor_pdf.py:102,128` también sobrescriben. |
| C3 | **P0** | **Cerrar la ventana durante una compresión deja FFmpeg vivo** y, si después muere, queda un **MP4 corrupto con el nombre final**. El plan lo menciona solo como "auditar el cierre"; aquí está confirmado. | Prueba bajo Xvfb: se cierra la ventana 3 s después de empezar. FFmpeg siguió escribiendo (13,9 → 24,6 MB en 10 s) con el proceso Python ya terminado. Al matarlo: `moov atom not found`. Causa: hilos `daemon=True` (`app.py:289`) y no hay manejador `WM_DELETE_WINDOW`. |
| C4 | P0 | Un error de FFmpeg deja la salida parcial en el destino final. | `compresor_video.py:176`: si `returncode != 0` se lanza la excepción **sin borrar** `salida`; solo se borra al cancelar (`:174`). |
| C5 | P1 | **Ghostscript falla con nombres que contienen `%`** (por ejemplo `informe 100%.pdf`): `-sOutputFile` interpreta `%d` como plantilla de página. Además, el mensaje de error sale vacío. **No está en el plan.** | `python app.py "informe 100%.pdf"` → `Error: Ghostscript fallo:` sin detalle. `compresor_pdf.py:40`. Hay que escapar `%` como `%%` o escribir en un temporal con nombre controlado (C2 lo resuelve de paso). |
| C6 | P1 | **pikepdf quita en silencio el cifrado y los permisos** de un PDF protegido con contraseña de propietario. **No está en el plan.** | `cifrado.pdf` (owner="dueno", sin extracción) → salida con `is_encrypted=False`. `pdf.save()` sin `encryption=` (`compresor_pdf.py:102`). |
| C7 | P1 | La cancelación no interrumpe Ghostscript (`subprocess.run`) ni cada muestra de la estimación de video; tampoco el `pdf.save()` de pikepdf. | `compresor_pdf.py:42`, `compresor_video.py:110`. La latencia de las muestras es como mucho ~1 muestra (4 s de video), aceptable; la de Ghostscript es de todo el documento. |
| C8 | P2 | La estimación de PDF hace la compresión completa (con Ghostscript, el mismo tiempo que comprimir). | Diseño consciente (`compresor_pdf.estimar`); es exacta, pero cuesta lo mismo que comprimir. |
| C9 | P2 | Cuando un video crece, la GUI muestra `Listo (--12%)` (doble signo). | `app.py:278`: `f"Listo (-{red:.0f}%)"` con `red` negativo. |
| C10 | P2 | `tipo_por_extension()` clasifica `foto.jpg` o `doc.docx` como video (solo en CLI; la GUI usa el tipo elegido). | `['pdf','video','video']` para `x.PDF, foto.jpg, doc.docx`. Termina en un error de FFmpeg poco claro, sin daño. |
| C11 | P1 | Workflow: `permissions: contents: write` a nivel global (los 3 jobs de build tienen escritura), actions sin fijar a SHA (incluida la de terceros `softprops/action-gh-release`), y **el input `version` se escribe como código Python** en `version.py` sin validar. | `compilar.yml:16-19,40,86`. Un `version` como `1.0"; import os; ...#` acabaría dentro de la app compilada. Solo quien tiene permiso de escritura puede lanzar el workflow, así que el riesgo es bajo, pero se corrige con una regex semver. |
| C12 | P1 | Dependencias sin fijar; no hay tests ni CI de PR. | `requirements.txt`: 4 líneas sin versión. Ya pasó una vez: la última pikepdf no tenía rueda para Mac Intel y el build se rompió (lo resolvimos con `--only-binary`, que instala silenciosamente una versión *distinta* en cada plataforma). |

**Hipótesis del plan que matizo:**
- *"La extracción ZIP puede permitir rutas maliciosas"*: `zipfile.extractall` de Python ya neutraliza las rutas absolutas y `..`. No es el riesgo principal; el riesgo real es la autenticidad del paquete (ver P6).
- *"PDF crecido → copia del original"*: ya está implementado (`compresor_pdf.py:128`). Lo que falta es **comunicarlo**: hoy la UI muestra "Listo (-0%)".

## Riesgos no confirmados

Son probables por análisis del código; requieren Windows/macOS reales o fixtures específicos.

1. **Actualizador en Windows con rutas no ASCII** (por ejemplo `C:\Users\José\...`): el `.bat` se escribe en UTF-8 (`actualizador.py:108`), pero `cmd.exe` lo lee con la página de códigos OEM (850/437). Probablemente fallen tanto la ruta temporal como la de la app, y el usuario solo vería que "la app se cerró y no volvió a abrir". Es muy probable entre los usuarios a los que apunta el proyecto (hispanohablantes).
2. **Windows sin rollback**: `robocopy /E` copia sobre la instalación en uso; si falla a mitad, la app queda mezclada entre dos versiones. Además, `/E` no borra archivos obsoletos de la versión anterior en `_internal`. No se comprueba el código de salida de robocopy.
3. **macOS, App Translocation**: si el usuario ejecuta la app desde Descargas sin moverla, `sys.executable` apunta a una ruta aleatoria de solo lectura (`/private/var/folders/.../AppTranslocation/`) y la actualización falla.
4. **macOS, `xattr -cr` tras actualizar** (`actualizador.py:141`): eliminamos la cuarentena de forma programática, así que Gatekeeper **nunca** revisa la versión nueva. La verificación de integridad es entonces responsabilidad exclusiva nuestra, lo que refuerza P6.
5. **Videos HDR / 10 bits** (iPhone en HEVC HLG/PQ): se fuerza `yuv420p` de 8 bits sin mapeo de tonos, lo que probablemente dé colores lavados. Tampoco se conservan las pistas de audio secundarias, los subtítulos, los capítulos ni los metadatos (por `-map 0:a:0?`, `-ac 2`).
6. **Tkinter y llamadas desde hilos**: los hilos de trabajo llaman a `ventana.after()` directamente. Funciona con Tcl compilado con hilos (el habitual), pero no está garantizado. El patrón robusto es una `queue.Queue` consultada desde el hilo principal.
7. **pikepdf y espacios de color**: la conversión CMYK→RGB de JPEG Adobe (invertidos), imágenes `Indexed`, ICC de 16 bits o `/Decode` no estándar puede alterar los colores. Hacen falta fixtures.
8. **Ghostscript tiene historial de CVE** al procesar PDF/PostScript malicioso. Usamos el `gs` que el usuario tenga instalado, sea cual sea su versión.

---

## Debate: respuestas a las 8 preguntas

### P1. ¿Conservar Tkinter o separar backend antes de otra tecnología gráfica?
- **Opción propuesta (ChatGPT):** conservar Tkinter; modularizar en P2.
- **Mi posición:** conservar Tkinter (**de acuerdo**), pero **no diferir toda la separación a P2**. Las correcciones P0 (escritura atómica, política de destinos, cancelación de procesos, cierre de ventana) son lógica de *trabajos*, no de UI, y hoy están duplicadas o ausentes entre GUI y CLI. Propongo extraer en el PR1 **solo** una capa mínima `nucleo.py`:
  - `planificar_lote(entradas, tipo, nivel, carpeta, politica) -> [Tarea]`: resuelve los destinos y rechaza colisiones con entradas o archivos existentes.
  - `ejecutar_proceso(cmd, cancelar, on_linea)`: un único lugar para Popen, terminate/kill, timeouts y `CREATE_NO_WINDOW`.
  - `salida_atomica(destino)`: un context manager.
  
  La GUI y la CLI consumen esa capa. Sin rediseño visual.
- **Alternativas:** PySide6/Qt (unos 80–120 MB más por build, LGPL, mejor HiDPI y arrastrar-y-soltar), Flet o web (otro runtime), Tauri (otro lenguaje). Ninguna resuelve los P0; todas multiplican el riesgo de empaquetado en 3 plataformas.
- **Riesgos:** una refactorización grande mezclada con correcciones dificulta la auditoría de Codex. Mitigación: el PR1 solo **mueve** lo que toca los P0 y deja `app.py` como orquestador.
- **Evidencia:** `app.py` mezcla planificación de destinos (`:48`), hilos y widgets; la CLI repite la lógica de forma distinta (`main()`).
- **Decisión recomendada:** Tkinter se queda. Capa `nucleo.py` mínima en el PR1; el resto de la modularización, en P2. Revisar la tecnología gráfica solo si hace falta arrastrar-y-soltar nativo o mejor HiDPI (con `tkinterdnd2` como paso intermedio).

### P2. Escritura atómica, nombres y destino existente (GUI y CLI)
- **Diseño propuesto:**
  1. **Planificación (antes de empezar):** se normalizan rutas (`os.path.realpath` + `normcase`). Un destino es inválido si coincide con **cualquier entrada del lote** (C1), con otro destino o con un archivo existente.
  2. **Política por defecto:**
     - GUI: **nombre único automático** (`_comprimido_media (2).mp4`). Ya es lo que hace dentro de un lote, así que es coherente y nunca destruye nada.
     - CLI: lo mismo con `-d`; con `-o` explícito sobre un archivo existente → **error**, salvo que se pase `--sobrescribir`.
     - Nunca se sobrescribe una entrada, ni siquiera con `--sobrescribir`.
  3. **Escritura:** temporal en la **misma carpeta** que el destino, oculto y con un nombre controlado sin `%` (resuelve C5): `.<nombre>.parcial-<uuid8>.mp4`. Mantengo la extensión, o paso `-f mp4` explícito, para que FFmpeg sepa qué formato escribir.
  4. **Finalización solo si** el código de salida es 0 **y** la validación básica pasa (ver punto 5). Publicación **sin pisar** usando primitivas atómicas del sistema:
     - Windows: `os.rename()` **falla si el destino existe**, ya es atómico sin sobrescritura.
     - POSIX: `os.link(tmp, destino)` (falla con `EEXIST`) + `os.unlink(tmp)`.
     - En exFAT/FAT de pendrives no hay hardlinks: comprobación + `os.replace` con una ventana de carrera mínima, documentada.
     
     Si el destino apareció entre medias, se recalcula un nombre único.
  5. **Validación básica (aquí discrepo del plan):** el plan habla de `ffprobe`, pero **la app compilada no incluye `ffprobe`**; `imageio-ffmpeg` solo trae `ffmpeg`. Propongo:
     - Video: `ffmpeg -i salida` (como ya hace `obtener_duracion`), comprobando duración ±1 s respecto a la entrada y la presencia de un stream de video. Decodificar todo (`-f null -`) cuesta minutos en videos largos, así que **solo en tests**.
     - PDF: `pikepdf.open()` y número de páginas igual al original.
  6. **Limpieza:** `try/finally` borra el temporal ante error, cancelación o excepción. Al arrancar, se ofrece limpiar los `.parcial-*` huérfanos de ejecuciones que se colgaron (solo los nuestros, por patrón).
- **Alternativas:** escribir en `%TEMP%` y mover (rechazado: si la carpeta está en otro disco, el `rename` deja de ser atómico y se duplica el uso de disco); preguntar en un diálogo por cada conflicto (rechazado como opción por defecto: molesto en lotes de 50; se puede añadir como preferencia).
- **Riesgos:** sin espacio en disco a mitad de camino (cubierto: el temporal se borra); antivirus de Windows que bloquean el `rename` (reintentar 3 veces con espera corta); OneDrive/Dropbox sincronizando el `.parcial` (oculto y efímero, aceptable).
- **Evidencia:** C1, C2, C4, C5.
- **Decisión recomendada:** la descrita arriba, en el PR1, con tests para cada rama.

### P3. Cancelar FFmpeg, Ghostscript y estimaciones sin bloquear ni dejar parciales
- **Diseño propuesto:**
  - Todo subproceso pasa por `ejecutar_proceso()`, que usa `Popen`. El bucle lee la salida en un hilo y consulta `cancelar` cada ≤200 ms. Al cancelar: `terminate()` → `wait(3)` → `kill()` → `wait()`. No hace falta matar grupos de procesos (ni FFmpeg ni Ghostscript crean hijos), lo que evita `os.killpg`/Job Objects y sus diferencias entre plataformas.
  - **FFmpeg:** `kill` directo; descartamos el resultado, así que no hace falta la `q` "suave".
  - **Ghostscript:** pasar a `Popen` con el mismo bucle (resuelve C7).
  - **Estimación de video:** cada muestra pasa por `ejecutar_proceso()`, con la latencia de cancelación reducida a ~200 ms.
  - **pikepdf:** no es interrumpible dentro de `save()`. Comprobar `cancelar` antes de cada imagen (ya se hace) y antes de `save()`; si se cancela durante `save()`, se espera a que termine y se borra el temporal. Latencia típica de segundos, documentada. *Rechazo* ejecutarlo en `multiprocessing` solo para poder matarlo: con PyInstaller hace falta `freeze_support()`, lo que añade riesgo de empaquetado, y la ganancia es pequeña.
  - **Cierre de ventana (C3):** `ventana.protocol("WM_DELETE_WINDOW", ...)`. Si hay un trabajo en curso, se pregunta "¿Cancelar y salir?" → se activa `cancelar`, se espera a que el hilo termine (hasta unos 5 s mostrando "Cancelando...", con la GUI viva mediante `after`) → `destroy()`. Los hilos dejan de ser daemon. Como red de seguridad, `atexit` mata cualquier proceso registrado que siga vivo.
  - **Comunicación entre hilos:** reemplazar las llamadas `ventana.after(0, ...)` desde los hilos por una `queue.Queue` que el hilo principal consulta cada 100 ms (riesgo no confirmado 6).
- **Alternativas:** Job Objects en Windows (garantizan la muerte de los hijos incluso si nuestro proceso se cuelga; recomendable más adelante, requiere `pywin32` o `ctypes`).
- **Riesgos:** un FFmpeg que no responde a `terminate` en Windows (allí `terminate` ya equivale a `TerminateProcess`, no hay gracia posible: OK).
- **Evidencia:** C3, C4, C7.
- **Decisión recomendada:** la descrita, en el PR1; los Job Objects quedan para el PR de robustez Windows.

### P4. ¿Ghostscript como opción prioritaria? Firmas, formularios, transparencias, cifrado
- **Opción propuesta por el plan:** mantener Ghostscript como opción prioritaria.
- **Mi posición: discrepo.** Propongo **pikepdf como motor por defecto** y Ghostscript como **modo opcional explícito** ("compresión agresiva", desactivado por defecto). Razones:
  1. **Resultados impredecibles:** hoy el resultado depende de si el usuario *tiene instalado* Ghostscript, algo que no ve ni controla. Las estimaciones y el soporte cambian entre equipos.
  2. **No siempre es mejor:** con el mismo PDF de prueba (3 páginas de fotos JPEG), Ghostscript `/ebook` produjo un archivo **más grande** (se conservó el original, 0 % de reducción), mientras pikepdf logró **−58 %** (3,3 MB → 1,4 MB).
  3. **Fidelidad:** pikepdf solo reemplaza imágenes y conserva la estructura (formularios, anotaciones, enlaces, marcadores, capas). `pdfwrite` **reescribe todo el documento**: puede aplanar o perder elementos y cambia la tipografía embebida.
  4. **Seguridad y versiones:** ejecutamos el `gs` del usuario, sea cual sea su versión (historial de CVE). Su licencia AGPL no nos afecta porque no lo distribuimos, pero lo mismo impide incluirlo en la app.
  5. **Bug C5** (`%` en nombres) y la falta de cancelación (C7).
- **Tratamiento de casos especiales (en ambos motores):**

  | Caso | Detección | Política propuesta |
  |---|---|---|
  | **Firmado** (`/AcroForm /SigFlags` o campos `/FT /Sig` con `/V`) | pikepdf | **No tocar por defecto**: estado "Omitido: PDF firmado (comprimir invalidaría la firma)". Opción explícita para forzar, con aviso. |
  | **Cifrado con contraseña de usuario** | `pikepdf.PasswordError` | Omitir con mensaje claro ("protegido con contraseña"). Pedir la contraseña queda para más adelante. |
  | **Cifrado solo con contraseña de propietario** (C6) | `pdf.is_encrypted` | Conservar el cifrado y los permisos (`save(encryption=True)` copia la configuración original; **a verificar con test**). Nunca quitar la protección en silencio. |
  | **Formularios / anotaciones** | — | pikepdf los conserva (verificado: `Widget` y `Text` intactos, `AcroForm` presente). Test de regresión. |
  | **Transparencias** | `/SMask` y `/Mask` | Se mantiene lo actual: `/Mask` de tipo array (color key) → no tocar; `/SMask` → se conserva la máscara y se recomprime solo la imagen base. Fixture con PNG con alfa. |
  | **CMYK / Indexed / 16 bits / `/Decode`** | inspección de `ColorSpace` y `BPC` | Política conservadora: si no es `DeviceRGB`/`DeviceGray` de 8 bits o un `DCT` simple, **no se recomprime** hasta tener fixtures que demuestren que el color se conserva. |
  | **PDF/A** | metadatos XMP `pdfaid` | Avisar: el resultado puede dejar de cumplir PDF/A. |
- **Riesgos de mi propuesta:** algunos PDF (texto vectorial con fuentes enormes, sin imágenes) se comprimen mejor con Ghostscript. Por eso se mantiene como modo opcional, no se elimina.
- **Evidencia:** C5, C6 y la prueba comparativa anterior (`formulario.pdf`, `cifrado.pdf`, `normal.pdf`).
- **Decisión recomendada:** pikepdf por defecto + detección de firma/cifrado en el PR1 (son P0 de integridad); el modo Ghostscript opcional en la UI, en un PR posterior.

### P5. ¿Preservar video si el resultado crece? ¿Cómo comunicarlo?
- **Contexto:** con CRF, un video que ya estaba muy comprimido (WhatsApp o grabaciones de pantalla) **puede crecer**, sobre todo en el nivel "baja".
- **Mi posición:** el comportamiento debe depender de si la entrada **ya es compatible**:
  - **Entrada ya H.264/AAC en MP4/MOV** y la salida pesa ≥ 95 % de la original → **conservar el original**: copia remuxada `-c copy` a `.mp4`, rápida y sin pérdida, con el estado **"Sin mejora: se conservó el original"**.
  - **Entrada en otro formato** (AVI, WMV, MKV con códecs no compatibles…) → el objetivo también es la **compatibilidad**, así que se entrega la conversión aunque pese más, con un estado claro: **"Convertido a MP4 (+12 %)"**, nunca "Listo (--12 %)" (C9).
  - **Antes de comprimir:** reutilizar la estimación. Si el estimado ≥ original, la columna lo marca en ámbar: "~105 % del original: probablemente no reduzca".
- **Comunicar calidad:** no prometer números de calidad (SSIM/VMAF) en esta etapa. Usar textos honestos por nivel ("Baja compresión: casi sin diferencia visible") y mostrar la resolución resultante cuando se reduce (por ejemplo "4K → 1080p" en el nivel media).
- **Alternativas:** two-pass hacia un tamaño objetivo (más lento y más complejo; Etapa E); CRF adaptativo según el bitrate de entrada (prometedor, pero requiere benchmarks).
- **Riesgos:** `-c copy` puede fallar con contenedores raros. En ese caso se recurre a la copia del archivo original **solo** si ya es `.mp4`; si no, se entrega la conversión.
- **Evidencia:** C9; no hay ninguna lógica de "crecimiento" en `compresor_video.comprimir()`.
- **Decisión recomendada:** PR2 (no es P0 de integridad); la corrección del texto C9 va en el PR1 porque es trivial.

### P6. Integridad/autenticidad y rollback de las actualizaciones. ¿Desactivar la autoinstalación?
- **Modelo de amenazas realista:**
  - T1: descarga corrupta o truncada.
  - T2: proxy corporativo con CA propia (MITM "legítimo") o una CDN comprometida.
  - T3: alguien sube o reemplaza un asset de la release.
  - T4: **toma de control de la cuenta de GitHub** del propietario (la amenaza más probable en la práctica).
- **Niveles alcanzables:**

  | Nivel | Qué es | Cubre | Coste |
  |---|---|---|---|
  | L0 (hoy) | HTTPS + repo fijo + versión monótona | parcialmente T2 | — |
  | L1 | `SHA256SUMS` + tamaño + prueba de integridad del ZIP/DMG antes de instalar | T1 | bajo |
  | L2 | `SHA256SUMS` **firmado con Ed25519**: la clave pública va dentro de la app y la privada en un *GitHub Environment* `release` con revisor obligatorio | T1, T2, T3 | bajo (con `cryptography` o `pynacl`; **verificar** que la dependencia pesa poco en el build) |
  | L3 | Igual que L2, pero el propietario firma **en su máquina** (clave offline) | + T4 | manual en cada release |
  | L4 | Authenticode (Azure Trusted Signing ~10 USD/mes) + Apple Developer ID y notarización (99 USD/año) | + elimina los avisos de SmartScreen/Gatekeeper | dinero y trámites |

  Coincido con ChatGPT: un checksum alojado junto al ZIP **no** demuestra autenticidad. Por eso L2 es el mínimo serio.
- **Rollback y robustez (independiente de la firma). Alternativa a la propuesta de "separar búsqueda/descarga/instalación":** propongo **eliminar los scripts `.bat`/`.sh`** y que la propia **versión nueva se instale a sí misma**:
  1. La app vieja descarga y verifica (L1/L2), extrae o monta en un temporal y lanza el ejecutable **nuevo** con `--instalar-sobre <ruta_app> --esperar-pid <pid>`. Después se cierra.
  2. La app nueva (en el temporal) espera al PID, **renombra** la instalación vieja a `.anterior`, **mueve** la nueva a su lugar, verifica que el ejecutable exista y luego borra `.anterior` o, si algo falló, lo restaura. Finalmente se relanza desde la ubicación definitiva.
  
  Ventajas: un solo código en Python, testeable, compatible con Unicode (resuelve el riesgo no confirmado 1), con rollback también en Windows (riesgo 2) y sin archivos obsoletos.
  
  Detecciones previas que hacen falta: carpeta sin permiso de escritura (Program Files) o App Translocation en macOS → **no autoinstalar** y ofrecer "abrir página de descarga".
- **¿Desactivar la autoinstalación?** **Discrepo parcialmente.** Desactivarla elimina una función que el propietario pidió explícitamente, y el riesgo dominante (T4) no lo resuelven ni L1 ni L2. Propongo:
  - Inmediato (PR1, una línea): **no hay nada que desactivar** mientras no se publique una versión nueva. El riesgo solo se materializa cuando sale una release.
  - **Regla de proceso:** no publicar v1.2.0 hasta que el PR3 (L1 + L2 + autoinstalador con rollback) esté integrado. Si el PR3 se retrasa y hay que publicar, se publica con la autoinstalación sustituida por "abrir página de descarga".
  - **Recomendación al propietario, con efecto inmediato y coste cero:** activar 2FA en GitHub, proteger la rama `main` y requerir revisión para cambios en `.github/workflows/` (cubre parte de T4).
- **Evidencia:** `actualizador.py:105-143` (sin hash, sin comprobación de código de salida de robocopy, `.bat` en UTF-8, `xattr -cr`).
- **Decisión recomendada:** PR3 = L1 + L2 + autoinstalador sin scripts con rollback. L3/L4 los decide el propietario según presupuesto.

### P7. Tests, fixtures y CI sin builds costosos en cada PR. Versiones y plataformas
- **Estructura:**
  ```
  tests/
    conftest.py            # fixtures generadas en tiempo de test (no se versionan binarios)
    test_destinos.py       # planificar_lote: colisión con entradas (C1), existentes (C2), duplicados, % en nombres
    test_atomico.py        # salida_atomica: éxito, error, cancelación, carrera simulada
    test_procesos.py       # ejecutar_proceso con un "subproceso falso" (python -c que duerme/escribe/falla)
    test_video.py          # integración: lavfi → avi/mkv/mov; valida H.264/AAC, dimensiones pares, duración
    test_pdf.py            # integración: PDF generados con pikepdf+Pillow: fotos, alfa, formulario, cifrado, firmado(simulado)
    test_cli.py            # códigos de salida, -o existente, -d, --estimar
    test_gui_smoke.py      # Linux + Xvfb: abrir, agregar (mock de diálogos), comprimir, cerrar durante el trabajo
    test_actualizador.py   # comparación de versiones, selección de asset, verificación de firma (con clave de test)
  ```
  - **Fixtures sintéticas** con `ffmpeg -f lavfi` (testsrc2 + sine, 2–3 s, menos de 1 s de generación) y PDF construidos con pikepdf/Pillow. Sin muestras de usuarios ni binarios en el repo, en línea con la regla 6 del plan.
  - Marcas `@pytest.mark.integracion` y `@pytest.mark.gui` para poder ejecutar solo los tests unitarios en local.
- **CI (`.github/workflows/tests.yml`, en cada PR):**

  | Job | SO | Python | Contenido | Tiempo estimado |
  |---|---|---|---|---|
  | lint | ubuntu | 3.12 | `ruff check` (sin reformatear todo el repo en este PR) | ~20 s |
  | unit+integración | ubuntu | 3.10 y 3.12 | todos los tests + Xvfb para la GUI + `ghostscript` vía apt | ~2 min |
  | unit | windows, macos-latest | 3.12 | unitarios + integración de video con `imageio-ffmpeg` (rutas con espacios, Unicode y `%`) | ~3 min |

  **Sin PyInstaller en los PR**: el build de 3 plataformas sigue en `push` a `main` y en releases. Opcionalmente, con la etiqueta `build`, también en un PR. Esto responde a la preocupación de coste.
- **Versiones:** **3.12** es la que va en la app (obligatoria); **3.10** como mínimo soportado (pikepdf actual exige ≥ 3.9, y 3.10 permite `match`/tipos modernos). El README dice "3.8+" y es **incorrecto**: hay que corregirlo. Python 3.13 queda para cuando PyInstaller y pikepdf tengan ruedas estables en las 3 plataformas.
- **Reproducibilidad:** `requirements.lock` con versiones exactas (pip-tools). Para la build, `--require-hashes` en una segunda fase. Elegir una versión de pikepdf **con rueda para macOS x86_64** y quitar el `--only-binary` que hoy instala versiones distintas según la plataforma.
- **Decisión recomendada:** tests y CI en el PR1 (los tests son la prueba de los P0), sin builds en PR.

### P8. Qué acepto, rechazo o pospongo. PRs acotados y criterios medibles
- **Acepto:** prioridades P0/P1 del plan, criterios de aceptación 1–3 y 6–10, flujo con draft PR y auditoría de Codex, prohibición de releases y merges sin autorización, fixtures sin datos personales.
- **Modifico:**
  - Criterio 2: validación sin `ffprobe` (ver P2).
  - Criterio 4: fidelidad PDF con pikepdf como motor por defecto, más políticas explícitas para firma y cifrado.
  - Criterio 5: verificación por decodificación completa **solo en tests**.
  - Criterio 8: L2 + autoinstalador sin scripts (ver P6).
- **Rechazo:** Ghostscript como motor prioritario por defecto; desactivar ya la autoinstalación (sustituido por la regla de no publicar hasta el PR3); diferir *toda* la modularización a P2.
- **Pospongo (Etapa E, sin cambios respecto al plan):** rediseño de la UI, perfiles CRF ajustables, tamaño objetivo (two-pass), métricas de calidad, paralelismo, imágenes y SCORM.
- **Añado:** C1 (entradas destruidas), C3 (FFmpeg huérfano), C5 (`%` en Ghostscript), C6 (cifrado eliminado), C11 (workflow), riesgo de Unicode en el `.bat`, App Translocation, HDR.

---

## Plan revisado (PR1 / PR2 / PR3)

Cada PR sale de `main` actualizado, se abre como **draft**, lleva los tests y el informe de pruebas, y pasa por la auditoría de Codex. Tamaño objetivo: ≤ ~600 líneas de código de producción (los tests aparte).

### PR1 — `feature/estabilizacion-integridad` (P0)
1. `nucleo.py`: `planificar_lote`, `salida_atomica`, `ejecutar_proceso`.
2. Política de destinos: nunca sobrescribir entradas; nombre único por defecto; en la CLI, `-o` sobre un archivo existente da error, salvo con `--sobrescribir`.
3. Escritura atómica en video y PDF (y en la copia "sin mejora"), con validación básica y limpieza.
4. Cancelación real de FFmpeg, Ghostscript y muestras; `WM_DELETE_WINDOW`; hilos no daemon; `queue.Queue` en la GUI.
5. PDF: detección de firmados (se omiten) y de cifrados (se conserva el cifrado o se omite); escape de `%` para Ghostscript.
6. Correcciones menores: C9 (texto de crecimiento) y C10 (rechazar extensiones desconocidas en la CLI con un mensaje claro).
7. Tests (`tests/`) + `tests.yml` (lint + ubuntu 3.10/3.12 + Windows/macOS 3.12) + `requirements-dev.txt`.
8. README: política de sobrescritura, limitaciones de PDF, Python ≥ 3.10, cómo ejecutar los tests.

**Criterios medibles:** las reproducciones C1–C5 y C7 se convierten en tests que fallan en `main` y pasan en el PR; tiempo de cancelación < 1 s con FFmpeg y Ghostscript (medido en el test); ningún `.parcial-*` tras error, cancelación o cierre; CI en verde en las 3 plataformas.

### PR2 — `feature/politica-resultados` (P1/P2)
- Video que crece (lógica de P5) y aviso previo basado en la estimación.
- Motor PDF: pikepdf por defecto + opción "compresión agresiva (Ghostscript)" en la GUI y `--motor` en la CLI.
- Política conservadora de espacios de color + fixtures (CMYK, Indexed, alfa, PDF/A).
- Fijar versiones (`requirements.lock`) y quitar `--only-binary`.

### PR3 — `feature/actualizador-seguro` (P0 de seguridad, antes de la próxima release)
- `SHA256SUMS` + firma Ed25519 en CI (GitHub Environment `release` con revisor obligatorio).
- La app verifica firma, tamaño e integridad; autoinstalación en Python sin `.bat`/`.sh`, con rollback en Windows y macOS.
- Detección de carpeta sin permisos y de App Translocation → descarga manual.
- Workflow: `permissions` mínimos por job, actions fijadas a SHA, validación semver del input `version`, publicación solo si `tests.yml` pasa.
- **Test manual obligatorio** en Windows (con usuario de nombre no ASCII) y en macOS (ARM e Intel): v_n → v_n+1 y simulación de fallo con restauración.

## Decisiones pendientes para ChatGPT y usuario

1. **Ghostscript:** ¿se acepta pikepdf como motor por defecto y Ghostscript como opción explícita? (Yo: sí.)
2. **Autoinstalación:** ¿se acepta "no publicar releases hasta el PR3" en lugar de desactivarla ya? (Yo: sí.)
3. **Política ante destino existente en la GUI:** ¿nombre único automático (mi propuesta) o diálogo por conflicto?
4. **PDF firmados:** ¿omitir por defecto (mi propuesta) o comprimir con aviso?
5. **Firma de releases:** ¿L2 (clave en GitHub Environment) es suficiente o el propietario quiere L3 (firma manual offline)? ¿Hay presupuesto para L4 (certificados de Windows/Apple, que además eliminan los avisos de seguridad)?
6. **Prioridad de plataforma** (pregunta abierta del plan): sin datos de uso, propongo tratar Windows y macOS por igual en CI, con prueba manual en ambos para el PR3.
7. **Alcance futuro:** ¿solo video/PDF o SCORM e imágenes? (No afecta a los PR1–3.)
8. **Protección del repositorio:** ¿puede el propietario activar 2FA, proteger `main` y exigir revisión de workflows? (Es configuración del propietario; yo no puedo hacerlo.)

## Pruebas previstas y definición de terminado

**Pruebas automatizadas (PR1):**
- Destinos: colisión con una entrada del lote (C1); destino existente (C2); duplicados entre carpetas; nombres con espacios, `%`, Unicode (`José/vídeo ñ.mp4`) y empezando por `-`; carpeta de salida inexistente o sin permisos.
- Atomicidad: un FFmpeg falso que sale con código 1 a mitad → no queda destino ni temporal (C4); cancelación → ídem; destino creado durante el proceso → nombre único, sin pisar.
- Procesos: cancelación < 1 s (FFmpeg real con testsrc largo y un Ghostscript falso); cierre de ventana bajo Xvfb → no quedan procesos hijos vivos (C3: hoy falla).
- Video: AVI, MKV y MOV sintéticos → H.264/AAC/MP4, dimensiones pares (entrada 1921×1081), relación de aspecto, duración ±1 s, decodificación completa sin errores.
- PDF: número de páginas igual; formulario y anotaciones conservados; cifrado de propietario conservado (C6: hoy falla); firmado → omitido; contraseña de usuario → error claro; alfa (`/SMask`) conservado; `%` en el nombre con Ghostscript (C5: hoy falla).
- CLI: códigos de salida, `-o` existente, `--sobrescribir`, extensión desconocida.

**Fuera de alcance de la automatización (declarado):** comportamiento real en Windows/macOS de la GUI empaquetada, autoinstalación, Gatekeeper/SmartScreen. Se harán pruebas manuales en el PR3 y se reportarán con SO, versión y evidencia.

**Definición de terminado (por PR):** criterios medibles cumplidos; CI en verde en las 3 plataformas; informe de pruebas con comandos, SO, versiones y **lo que no se probó**; README actualizado; auditoría de Codex en `PASS` sobre el **SHA final**; merge decidido por el propietario.

ESTADO: ESPERANDO REVISIÓN — NO IMPLEMENTAR
