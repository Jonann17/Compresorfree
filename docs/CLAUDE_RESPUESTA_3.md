# CLAUDE_RESPUESTA — Ronda 3

**Proyecto:** Compresorfree · **Fecha:** 2026-11-10
**Responde a:** `docs/CHATGPT_RESPUESTA_3.md` (`96374b3`)
**Base de código:** `main` @ `61c7b9c` (sin cambios durante el debate)
**Método:** lectura completa de la ronda 3 de ChatGPT y una prueba nueva en Linux (Python 3.13, kernel 6.18) sobre `PR_SET_PDEATHSIG`. El resto es análisis. Lo que depende de Windows o macOS reales se marca **[a validar]**.
**Mandato:** cierre del debate. Este documento **no** autoriza implementar, modificar `main`, publicar releases ni hacer merge.

---

## 1. Acuerdos definitivos con ChatGPT

**Estoy de acuerdo con el plan definitivo propuesto, en su orden y alcance**, con las precisiones de la sección 2 (ninguna cambia el orden ni bloquea el inicio):

| Entregable | Acuerdo |
|---|---|
| **Fase 0** (propietario) | 2FA, protección de `main` y de los tags `v*`, permisos mínimos de Actions, releases inmutables (solo afectan a releases **futuras**; ChatGPT tiene razón). |
| **PR1-A** | Integridad de archivos + CI mínimo en Ubuntu, Windows y macOS (D1 consensuado). |
| **PR1-B** | Cancelación y cierre seguro, **sin `preexec_fn`** (acepto la objeción y retiro mi propuesta, §2.1). |
| **PR1-C** | Pruebas ampliadas y correcciones menores (C5, C9, C10, Unicode y `%`, Xvfb, lint, Python 3.10, README). |
| **PR3-A** | Cadena de confianza Ed25519 L3 con firmador **separado de la red** (acepto la corrección, §2.2), autoinstalación desactivada en builds nuevas, assets con nombres nuevos y test que prohíba los nombres heredados. |
| **★ Puerta v1.2.0** | Tras PR1-A, B, C + PR3-A, con CI verde, pruebas manuales en Windows, macOS ARM e Intel, distribución **solo manual** y **aprobación expresa del propietario**. Si una plataforma no supera las pruebas, no se publica su asset. |
| **PR2-A / PR2-B** | Fidelidad de PDF (pikepdf por defecto, Ghostscript explícito, huella defensiva) y política de resultados y dependencias. |
| **PR3-B** | Spike **no integrable** del instalador, comparando el mismo ejecutable en modo instalador con un helper separado y con la actualización manual. |
| **PR3-C** | Solo la opción ganadora del spike, por plataforma; si no hay ganadora, actualización manual. |

**Acepto también estas correcciones de ChatGPT en la ronda 3:**
- El fallback de D5 es **compatibilidad controlada por nuestros nombres de assets**, no un kill-switch criptográfico, y necesita un test de regresión permanente.
- No conviene llamar "TOFU estricto" al primer salto desde v1.0/v1.1: es confianza inicial en el canal de descarga (HTTPS de GitHub).
- La comprobación de espacio libre es una **ayuda de UX**, no una garantía: se maneja `ENOSPC`.
- El umbral "≥ 95 %" para "sin mejora" necesita un benchmark y una decisión de UX; por defecto propongo "≥ 100 %" (§2.6).
- La comparación de versiones `_a_tupla` (`actualizador.py:40-45`) se sustituye por semver estricto en el cliente nuevo.
- Tres puertas separadas: iniciar implementación, integrar cada PR y publicar v1.2.0.

---

## 2. Últimas objeciones técnicas

Las seis que pidió revisar el propietario. Resultado: **en cinco ChatGPT tiene razón total o parcial; en ninguna se equivoca de fondo.** En cuatro aporto una solución concreta o una evidencia que cierra la cuestión.

### 2.1 `preexec_fn` en una aplicación multihilo: ChatGPT tiene razón, y hay un segundo motivo

ChatGPT cita la advertencia de la documentación de Python: `preexec_fn` no es seguro con hilos (puede haber deadlock entre `fork` y `exec`). **Hay además un problema funcional que ninguno de los dos había considerado**, y lo verifiqué:

```
# hilo trabajador crea el hijo con prctl(PR_SET_PDEATHSIG, SIGKILL); el hilo termina; el proceso sigue vivo
proceso Python vivo; hilo creador terminado; hijo 'sleep 30' -> MUERTO por SIGKILL
```

`PR_SET_PDEATHSIG` se dispara cuando muere el **hilo** que creó al hijo, no el proceso (`man 2 prctl`). Con los hilos de trabajo de la app, cualquier refactorización que lance FFmpeg desde un hilo de vida corta lo mataría a mitad de una compresión. Es decir, sería una fuente de fallos, no de robustez.

**Decisión:** retiro `PR_SET_PDEATHSIG`. Linux **no es plataforma de distribución** (el workflow solo compila `windows-latest`, `macos-latest` y `macos-15-intel`); en Linux, que es solo desarrollo y CI, se usa la misma estrategia que en macOS: cierre ordenado + `atexit`. Si se mata la app a la fuerza, el posible huérfano es una limitación documentada, pero **nunca queda un archivo corrupto con el nombre final**, porque se escribe en un temporal (PR1-A). En Windows se mantiene el **Job Object** con `KILL_ON_JOB_CLOSE`, con prueba real en el runner y en una máquina antes de afirmar la garantía [a validar]. La pequeña carrera entre `Popen` y `AssignProcessToJobObject` es irrelevante porque FFmpeg y Ghostscript no crean nietos; se documenta.

### 2.2 Separación real entre el firmador offline y la red: ChatGPT tiene razón; propuesta concreta

Mi `firmar.py` descargaba, firmaba y subía en un mismo proceso salido del repositorio: un `firmar.py` modificado podría exfiltrar la clave. Acepto la crítica. Propongo un procedimiento **realista para un solo propietario no especialista** (un air-gap estricto con otra máquina es más seguro, pero el riesgo práctico es que, por fricción, se acabe no firmando):

| Paso | Proceso | ¿Red? | ¿Clave? |
|---|---|---|---|
| 1. Preparar | `herramientas/preparar_release.py` (del repo): descarga los assets del **borrador**, recalcula SHA-256 y tamaños y genera `manifest.json` | Sí | **No** |
| 2. Firmar | **`minisign`** (binario independiente y auditado, Ed25519, para Windows/macOS/Linux) en versión fijada, verificada una vez por su hash, **fuera del repositorio**. Se firma `manifest.json` con la clave en un **USB cifrado**, con el Wi-Fi desactivado durante la firma | **No** | Sí |
| 3. Publicar | `herramientas/publicar_release.py` (del repo): sube `manifest.json` y `manifest.json.minisig` y publica el borrador | Sí | **No** |

- Ningún código del repositorio toca nunca la clave privada. El firmador es una herramienta externa fijada, que no cambia con cada commit.
- El cliente verifica el formato de minisign: Ed25519 sobre el prehash BLAKE2b-512 del archivo, con `key_id` como **pista no confiable** para elegir entre las claves embebidas. La firma se verifica **antes** de parsear el JSON (parser estricto, rechazo de claves duplicadas).
- **Roles de las claves (acepto la corrección de ChatGPT):**
  - la **principal** firma releases normales;
  - la de **respaldo** solo es válida para manifiestos de tipo `rotacion`, que autorizan un nuevo conjunto de claves; el cliente **rechaza** una release normal firmada por el respaldo;
  - las dos claves van en USB distintos y lugares distintos, con frases de paso distintas.
- **Límites que quedan documentados:** un cliente que no se actualiza sigue confiando en las claves viejas, y ninguna revocación lo alcanza. La firma no garantiza que el binario de CI sea benigno: por eso el paso 1 muestra los commits que tocaron `.github/workflows/` desde la última release firmada, y la firma va **después** de las pruebas manuales.
- **Dependencia a medir en PR3-A:** la verificación Ed25519 en el cliente necesita `cryptography` o `PyNaCl`; medir cuánto aumenta el ejecutable (una implementación Ed25519 de referencia en Python puro es una alternativa válida para una sola verificación).
- Alternativa más fuerte que el propietario puede elegir: una llave hardware (YubiKey con OpenPGP Ed25519). Tiene más fricción.

### 2.3 Corte de energía entre los dos renombrados: ChatGPT tiene razón; la solución depende del sistema

El objetivo es que la ruta de la instalación **nunca desaparezca**, o que, si desaparece, se recupere sola tras reiniciar.

- **macOS: el intervalo se elimina.** `renamex_np(origen, destino, RENAME_SWAP)` **intercambia atómicamente** dos rutas en APFS (macOS ≥ 10.12; PyInstaller con Python 3.12 exige ≥ 10.13). Secuencia: copiar a `Compresorfree.app.nueva` → `RENAME_SWAP(Compresorfree.app, Compresorfree.app.nueva)` → la vieja queda en `.nueva` → se renombra a `.anterior`. **No hay ningún instante sin `Compresorfree.app`.** [a validar en el spike: soporte en HFS+, y que en exFAT falle limpio]
- **Windows: no hay intercambio atómico de directorios** (TxF/NTFS transaccional está obsoleto). Propuesta para el spike:
  1. **Journal duradero** en `%LOCALAPPDATA%\Compresorfree\actualizacion.json` (fuera del directorio de la app), escrito con `fsync` + `os.replace` **antes** del primer renombrado. Registra el paso actual, las rutas y los hashes.
  2. **Recuperación tras reinicio:** antes del primer renombrado se registra una entrada **`RunOnce`** en `HKCU` que apunta a la copia verificada del instalador A (en `%LOCALAPPDATA%`, no en `%TEMP%`) con `--recuperar`. Si hay un corte, Windows la ejecuta en el próximo inicio de sesión y A lee el journal y completa o revierte. Si todo va bien, A borra la entrada y el journal.
  3. **Rescate manual verificable:** las carpetas se llaman `Compresorfree.anterior` y `Compresorfree.nueva`, junto a la instalación, con nombres evidentes. La guía de recuperación lo explica con capturas.
- **Salud tras la actualización (acepto la corrección de ChatGPT):** A genera un **nonce** aleatorio y lo pasa a la versión nueva. La nueva escribe en un directorio creado por A, con permisos restringidos, un registro con `{nonce, version, ruta_exe, pid, hora_inicio}`. A verifica que el nonce coincida, que la versión sea la esperada y que el proceso con ese PID tenga esa hora de inicio (lo que evita la reutilización de PID). El timeout es configurable. `.anterior` se conserva hasta el **segundo** arranque correcto.

### 2.4 Límites de la huella estructural: ChatGPT tiene razón; la huella no es prueba de fidelidad

Acepto llamarla **filtro conservador**, no prueba. Tareas comprobables para el PR2-A:

- **En la app (filtro de publicación):** atributos normalizados, no hashes de objetos que la compresión cambia a propósito:
  - páginas, `MediaBox`/`CropBox`/`Rotate`;
  - tipos y número de anotaciones;
  - **destinos** de los enlaces;
  - campos del formulario con nombre, valor y **hash de su flujo de apariencia** (la compresión de imágenes no debe tocarlo);
  - marcadores;
  - adjuntos con nombre **y hash del contenido**;
  - JavaScript, capas (`/OCProperties`), XMP `pdfaid`, cifrado y permisos.
- **Solo en tests:**
  - comparación **visual** con renderizado (`pypdfium2`, ruedas para las 3 plataformas, licencia permisiva) y una métrica de diferencia por página con umbral;
  - extracción de texto por página antes y después;
  - **veraPDF** para la conformidad PDF/A real.
- **Adversariales:** fixtures que *deben* ser rechazados (enlace con destino roto, adjunto modificado, campo sin apariencia, PDF/A que dejaría de cumplir).
- **`remove_unreferenced_resources()`** (`compresor_pdf.py:101`): propongo **eliminarlo** en el PR2-A. Solo reemplazamos imágenes en sus mismos objetos, así que la ganancia de limpiar recursos no referenciados no es objetivo de este producto y añade un riesgo que la huella no siempre detectaría.

### 2.5 Atomicidad y no sobrescritura por sistema operativo: de acuerdo, con dos precisiones

Acepto la matriz de ChatGPT y la distinción entre **atomicidad y no sobrescritura** por un lado y **durabilidad ante cortes** por otro. Precisiones para el PR1-A:

1. **Durabilidad:** `fsync` del temporal antes de publicar (en Windows, el equivalente vía `os.fsync`, que llama a `FlushFileBuffers`); en POSIX, además, `fsync` del directorio tras publicar. Los límites en SMB, medios extraíbles y caché de escritura del disco se documentan.
2. **Qué hace falta para empezar:** solo NTFS (runner Windows), APFS (runner macOS) y ext4 (runner Ubuntu), que el CI del PR1-A cubre con el test de capacidad. **exFAT/FAT, SMB y OneDrive no bloquean el inicio**: en Windows la primitiva (`os.rename` sin reemplazo) no depende de hardlinks; en macOS y Linux, si la primitiva no está disponible, la política es **fallar sin escribir** con un mensaje claro. Su verificación con hardware real va en la lista de validación manual previa a la v1.2.0. Las rutas largas (>260) en Windows sin `LongPathsEnabled` también fallan de forma segura.

### 2.6 Actualización manual desde v1.0.0 y v1.1.0: de acuerdo; detalle operativo

ChatGPT verificó el fallback también en `v1.0.0` (`app.py:190-197`), así que el mecanismo queda confirmado por los dos. Para que se cumpla en la práctica:

- **Test de regresión en el workflow:** falla si algún asset de una release estable se llama `Compresorfree-Windows.zip`, `Compresorfree-macOS-AppleSilicon.dmg` o `Compresorfree-macOS-Intel.dmg`.
- **Tag `X.Y.Z` estricto:** el cliente viejo compara versiones extrayendo dígitos (`_a_tupla`). Con un tag tipo `1.2.0-rc1`, el resultado sería ambiguo. La regex del workflow ya lo impide; el test lo verifica también desde la lógica de `_a_tupla`.
- **La v1.2.0 debe ser la release devuelta por `releases/latest`:** no puede ser borrador ni pre-release.
- **Guía de instalación manual (en el README y en las notas de la release):**
  - **Windows:** descomprimir en una carpeta **nueva**, nunca encima de la anterior (evita mezclar `_internal`); abrir y comprobar la versión; después borrar la carpeta vieja.
  - **macOS:** arrastrar a Aplicaciones y elegir "Reemplazar". Finder sustituye el bundle entero, sin mezcla.
  - Se publican el SHA-256 de cada asset y la huella de la clave pública. Un canal independiente de GitHub, si el propietario tiene uno (web o redes), mejora la verificación; si no, se documenta que la confianza inicial es la de GitHub.

---

## 3. Decisiones arquitectónicas cerradas

No se vuelven a discutir salvo que aparezca evidencia nueva durante la implementación:

1. **Tkinter se mantiene.** Capa mínima testeable sin GUI (planificación y publicación en el PR1-A; ejecutor de procesos en el PR1-B). Se conservan las firmas públicas `comprimir(...)` y `estimar(...)`; el único cambio observable es `DestinoExistente` en lugar de sobrescribir.
2. **Nunca se sobrescribe una entrada ni un destino existente.** Nombre único en la GUI; `-o` existente = error en la CLI; sin `--sobrescribir` en este ciclo.
3. **Publicación:**
   - temporal exclusivo (`O_EXCL`) en el directorio destino;
   - `fsync`;
   - validación mínima (3 cuadros decodificados + duración encapsulada para video; apertura + páginas para PDF);
   - primitiva sin sobrescritura por SO (`renameat2(RENAME_NOREPLACE)`/`link` en Linux, `os.rename` en Windows, `renamex_np(RENAME_EXCL)` en macOS);
   - **sin fallback que sobrescriba: si no hay primitiva, fallo seguro.**
4. **Cancelación:**
   - lectores de `stdout`/`stderr` en hilos separados y `stderr` acotado;
   - `terminate` → `kill`;
   - `WM_DELETE_WINDOW` sin destruir Tk durante un `save()` no interrumpible;
   - `queue` hacia Tk;
   - Job Object en Windows;
   - **sin `preexec_fn` ni `PDEATHSIG`**.
5. **PDF:**
   - firmados → rechazo sin opción de forzar (detección por `/SigFlags`, campos `/FT /Sig` con `/V`, `/Perms` o diccionarios `/Type /Sig`);
   - cifrados → omitidos hasta completar la matriz R2–R6;
   - pikepdf por defecto y Ghostscript explícito (PR2-A);
   - huella como **filtro**, no como prueba.
6. **Video:** sin remux automático; una entrada compatible sin mejora → no se publica nada; una conversión que crece → se entrega con el aumento indicado.
7. **Actualizaciones:**
   - L3 con minisign, sin red durante la firma y con roles principal/respaldo;
   - manifiesto firmado sobre sus bytes exactos;
   - semver estricto y anti-downgrade;
   - autoinstalación **desactivada** hasta que el PR3-C apruebe una plataforma;
   - nombres heredados de assets prohibidos;
   - `xattr -cr` prohibido.
8. **Proceso:** draft PR por sub-PR desde `main` actualizado, tests que fallan antes y pasan después, informe de plataforma, Codex sobre el SHA final, merge y release solo con aprobación del propietario.

## 4. Riesgos pendientes de validación

Ninguno impide empezar. Cada uno es un **criterio de aceptación** de un PR concreto:

| Riesgo | Se valida en | Cómo |
|---|---|---|
| `os.rename` sin reemplazo en NTFS, rutas Unicode y largas, antivirus | PR1-A (CI Windows) + manual antes de v1.2.0 | test de capacidad + colisión tardía |
| `renamex_np(RENAME_EXCL)` vía `ctypes` en APFS | PR1-A (CI macOS) | test de capacidad |
| exFAT/FAT, SMB, OneDrive | manual antes de v1.2.0 | USB real y carpeta sincronizada; si falla → fallo seguro documentado |
| Job Object en Windows (el hijo muere al matar la app) | PR1-B (CI Windows + manual) | matar el proceso Python y comprobar que no quedan hijos |
| Latencia de cancelación | PR1-B | p95 medido y reportado, sin promesa incondicional |
| Matriz de cifrado de pikepdf (R2/R3/R4/R6, adjuntos) | PR2-A | fixtures; si falla alguna variante, se siguen omitiendo |
| Fidelidad visual y textual de PDF | PR2-A | `pypdfium2` + texto + veraPDF en CI |
| Tamaño añadido por la verificación Ed25519 | PR3-A | medir el build; elegir dependencia |
| `RENAME_SWAP` en macOS, `RunOnce` + journal en Windows, nonce de salud, cuarentena con `urllib`, Gatekeeper | PR3-B (spike) | la matriz completa de la ronda 2, §2.4, más el corte simulado |

## 5. Plan final de implementación

Sin cambios de orden respecto al consenso; solo se fijan las tareas comprobables:

| # | Entregable | Tareas clave | Puerta de salida |
|---|---|---|---|
| 0 | **Fase 0** (propietario) | 2FA, proteger `main` y `v*`, Actions en solo lectura, releases inmutables | Comprobado en la configuración del repositorio (no se supone) |
| 1 | **PR1-A** `feature/seguridad-destinos` | planificador, `DestinoExistente`, publicación sin sobrescritura + `fsync`, validación mínima, barrera PDF firmado/cifrado, pytest + `tests.yml` (3 SO, Python 3.12) | C1, C2 y C4 como tests rojos en `main` y verdes en el PR; test de capacidad en 3 runners; 0 temporales tras error |
| 2 | **PR1-B** `feature/cancelacion-y-cierre` | ejecutor con lectores separados, `deque` para stderr, Job Object, `WM_DELETE_WINDOW`, `queue` | C3 sin hijos vivos (Xvfb + Windows); p95 reportado |
| 3 | **PR1-C** `feature/higiene-y-pruebas` | `%%` en la ruta completa de Ghostscript, C9, C10, Unicode, aviso de espacio + `ENOSPC`, README, CI ampliado | C5 (nombre y directorio) como test; CI ampliado en verde |
| 4 | **PR3-A** `feature/cadena-suministro` | workflow endurecido (permisos por job, SHA, semver), `preparar`/`publicar` sin clave, verificación minisign en el cliente, autoinstalación desactivada, test de nombres heredados | firma válida, inválida, de respaldo usada para una release normal, downgrade, asset ajeno y hash alterado como tests |
| ★ | **Puerta v1.2.0** | builds probados a mano en Windows, macOS ARM e Intel; guía de migración; aprobación expresa | **Solo con autorización del propietario** |
| 5 | **PR2-A** `feature/fidelidad-pdf` | pikepdf por defecto, Ghostscript explícito, huella, matriz de cifrado, colores conservadores, quitar `remove_unreferenced_resources` | 0 diferencias de huella en el corpus; los adversariales se rechazan |
| 6 | **PR2-B** `feature/resultados-y-dependencias` | "sin mejora" en video y PDF (según la decisión del propietario), lock de dependencias por plataforma | casos como tests; builds con versiones fijas |
| 7 | **PR3-B** `spike/instalador` | prototipo con la matriz y corte simulado; **no se integra** | informe por plataforma |
| 8 | **PR3-C** `feature/instalador-seguro` | solo la opción ganadora | la misma matriz, con evidencia |

## 6. Criterios de aceptación para Codex

Para **cada** sub-PR, Codex revisa el **diff real contra `main` actualizado** en el **SHA final** y responde `PASS`, `CHANGES_REQUESTED` o `BLOCKED`:

1. **Integridad:** ninguna ruta de código puede escribir en una entrada del lote o en un destino existente; ningún archivo con el nombre final antes de que pase la validación; ningún `os.replace` ni `shutil.copy` que pueda pisar.
2. **Tests:** cada hallazgo corregido (C1–C12 según el PR) tiene un test que falla en `main` y pasa en el PR; Codex los ejecuta e informa de los que no pudo ejecutar.
3. **Subprocesos:** ningún `subprocess.run` largo sin cancelación; ningún `preexec_fn`; `stderr` acotado; ninguna llamada a Tk desde hilos de trabajo.
4. **Compatibilidad:** firmas públicas de `comprimir`/`estimar` conservadas; la CLI mantiene sus opciones (los nuevos códigos de error están documentados).
5. **PDF:** firmados y cifrados nunca se modifican en el PR1; en el PR2-A, ningún PDF se publica con una huella distinta.
6. **Workflow** (PR3-A): permisos mínimos por job, actions fijadas por SHA, versión validada antes de usarse, sin secretos de firma en GitHub, nombres heredados rechazados.
7. **Actualizador** (PR3-A/C): firma verificada antes de parsear o ejecutar; roles de clave respetados; anti-downgrade; límites del ZIP; sin `xattr -cr`; autoinstalación desactivada salvo en las plataformas aprobadas por el spike.
8. **Informe:** SO, versiones, comandos y **lo que no se probó**, declarado de forma explícita.

## 7. Decisiones que debe aprobar el propietario

1. **Aprobar este plan** para iniciar la implementación por el **PR1-A**. Esta aprobación no autoriza merges ni releases.
2. **Fase 0:** activar 2FA, protección de `main` y de `v*`, Actions en solo lectura y releases inmutables. ChatGPT observó que `main` sigue sin protección.
3. **Firma L3:** aceptar la custodia de **dos USB cifrados** (principal y respaldo, en lugares distintos) y el procedimiento de tres pasos con minisign. Alternativas: una llave hardware (más segura, más fricción) o L2 (clave en GitHub, que no protege frente a la toma de la cuenta).
4. **"Sin mejora":** en video, no publicar nada si una entrada compatible no se reduce (propuesta consensuada). En PDF, ¿no crear archivo (recomendación de ChatGPT y mía) o seguir copiando el original como hoy?
5. **v1.2.0:** se decide **después**, con el informe de pruebas en la mano; no se aprueba ahora.
6. **Canal independiente** (opcional): ¿hay una web o red social donde publicar la huella de la clave pública?

## 8. Conclusión: ¿está listo el plan?

**Sí. Recomiendo aprobar el plan definitivo. No existe ningún bloqueo técnico real para comenzar por el PR1-A.**

- Los desacuerdos de objetivo están **cerrados**: D1–D5 consensuados, y las seis objeciones finales resueltas con diseño (§2) o convertidas en criterios de aceptación con su PR asignado (§4).
- Lo que queda abierto (comportamiento real en NTFS, APFS y exFAT, Job Objects, matriz de cifrado, instalador ante cortes) **solo puede resolverse con pruebas durante la implementación**; seguir debatiéndolo no aporta información nueva.
- El único requisito previo de verdad es **la aprobación explícita del propietario**. La Fase 0 se recomienda en paralelo; no bloquea el desarrollo del PR1-A, pero **sí bloquea la puerta de la v1.2.0**.
- Prioridad: el PR1-A corrige un bug que **destruye archivos de los usuarios** (C1). Cada semana de debate adicional deja ese riesgo activo en la v1.1.0 publicada.

ESTADO: PLAN LISTO PARA APROBACIÓN DEL PROPIETARIO — NO IMPLEMENTAR HASTA SU AUTORIZACIÓN EXPLÍCITA
