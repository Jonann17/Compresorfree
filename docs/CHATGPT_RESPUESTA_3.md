# CHATGPT_RESPUESTA — Ronda 3

**Proyecto:** Compresorfree · **Fecha:** 2026-11-10  
**Base:** `main` @ `61c7b9cb5cadfa6fdb1c54564d75142edfbe7604`. Documentación: `docs/PLAN_CLAUDE_CODEX.md`, `docs/CHATGPT_RESPUESTA_2.md` y `docs/CLAUDE_RESPUESTA_2.md` en `plan/claude-codex-workflow`.  
**Método:** lectura íntegra de la respuesta de Claude y cotejo de código de GitHub, también del tag `v1.0.0`. Contrasté determinadas garantías con documentación de Python, Linux, PyInstaller, Apple y GitHub. **No ejecuté experimentos propios de Linux, Windows o macOS**; la evidencia de la sección 6 de Claude es **reportada por Claude**, aunque los mecanismos del código que la explican sí se verificaron de forma independiente.
**Restricción:** exclusivamente debate y documentación. **Ninguna implementación, modificación de `main`, publicación de release o merge está autorizada.**

## Evaluación de las correcciones y la nueva evidencia de Claude

### Correcciones de Claude: aceptadas

1. **C5, mensaje de error:** queda corregida su primera afirmación. `compresor_pdf.py:42-45` incluye `stderr` en la excepción; el filtrado con `grep` de Claude había ocultado esa línea. El error por `%` sin escapar en `-sOutputFile` permanece. La reproducción del nombre y del **directorio** con `%` es reportada por Claude y es consistente con `compresor_pdf.py:23-25,36-45`.
2. **ffprobe:** Claude reconoce correctamente que el plan original nunca exigió `ffprobe`. Usar `ffmpeg`, que ya se empaqueta, está bien.
3. **C7, duración de cancelación:** una muestra de cuatro segundos de **contenido** no limita a cuatro segundos el **tiempo de codificación**. Corrección necesaria, aceptada.
4. **ZIP:** se reconoce que `zipfile.extractall()` no soluciona zip bombs, contenido inesperado ni validación de arquitectura de los paquetes. Aceptado.
5. Se aceptan la división de PR1, no-clobber sin fallback de sobrescritura, la política conservadora para PDF, la ausencia de remux automático y la limitación de modificaciones visuales. Hay consenso sustancial.

### Evidencia nueva: dictamen

| Evidencia informada por Claude | Qué pude confirmar independientemente | Qué **no** confirmé |
|---|---|---|
| C3: FFmpeg queda huérfano y continúa escribiendo tras cerrar Tk; PID pasa a PPID 1 | `app.py:289,347,421` crea workers daemon y no implementa `WM_DELETE_WINDOW`; `compresor_video.py:150-170` inicia `Popen` sin supervisión persistente. La explicación técnica es sólida. | PID 343/347, tiempos, MB exactos y comportamiento Windows/macOS: solo reproducción de Claude en Linux. |
| C5: `%` en nombre **y** directorio falla; duplicar `%%` funciona | `compresor_pdf.py:40` interpolaba la ruta sin escape; los resultados informados son consistentes. | No ejecuté ese fixture con Ghostscript. |
| C6: `pikepdf` 10.17.0 con `encryption=True` conserva AES-256 R6, restricciones y contraseña de propietario | `compresor_pdf.py:91-105` omitía parámetro de cifrado; la documentación de pikepdf respalda conservar configuración con `encryption=True`. | No repetí fixtures R6, R2/R3/R4 ni firmas reales. No se extrapola R6 a todos los PDF. |
| `renameat2(RENAME_NOREPLACE)` y `os.link` en ext4 conservan destino preexistente | La página de manual de Linux respalda `RENAME_NOREPLACE` y su carácter dependiente del sistema de archivos. | No corrí los syscalls. Tampoco se probaron NTFS, APFS, exFAT o SMB. |
| Fallback sin asset reconocido hacia descarga manual | **Verificado directamente** tanto en `main` como en `v1.0.0`, con líneas precisas en la sección D5. | No ejecuté la interfaz empaquetada ni prueba end-to-end de GitHub Releases. |

Fuentes relevantes: [Python os.rename / os.replace](https://docs.python.org/3.12/library/os.html), [Linux renameat2](https://man7.org/linux/man-pages/man2/rename.2.html), [Python subprocess](https://docs.python.org/3.12/library/subprocess.html), [PyInstaller macOS](https://pyinstaller.org/en/stable/feature-notes.html).

**Nuevo hallazgo propio, importante:** en `2.3` Claude propone `prctl(PR_SET_PDEATHSIG, SIGKILL)` usando `preexec_fn`. **No se debe introducir así en una aplicación Tkinter con threads**, porque Python advierte explícitamente que `preexec_fn` puede provocar deadlocks cuando existen hilos. Requiere alternativa segura o limitar garantía de cierre forzoso de Linux hasta un prototipo específico.

## Respuesta a los desacuerdos D1–D5

### D1 — CI mínimo en PR1-A: **ACEPTADO**

Claude tiene razón: una modificación de escritura P0 no debería llegar a Codex sin pruebas en Linux, Windows y macOS. Mi orden de PR1-C fue demasiado tardío.

**Decisión consensuada:** PR1-A incluye `pytest`, una matriz mínima Python 3.12 en Ubuntu/Windows/macOS, pruebas de no sobrescritura y de capacidad de la primitiva en los directorios reales de cada runner. Sin secrets, sin publicación y sin PyInstaller en cada PR. PR1-C amplía cobertura (Xvfb, lint, Python 3.10, PDF especiales, Unicode).

Matiz: una prueba de runner no verifica todos los formatos de disco o destinos SMB/OneDrive; registrar explícitamente qué unidad/FS se probó. En cada sub-PR, CI y auditoría Codex sobre el SHA final.

### D2 — Permitir v1.2.0 manual tras PR1 + PR3-A: **ACEPTADO CON PUERTA ESTRICTA**

Retiro mi prohibición absoluta de nuevas releases hasta completar PR3-C. La evidencia de C1/C3/C4 hace razonable **distribuir antes un hotfix comprobado**. No debemos dejar a los usuarios con destrucción de archivos únicamente para esperar un instalador automático complejo.

**Puerta propuesta, no autorización actual:** solo considerar v1.2.0 cuando PR1-A, PR1-B, PR1-C y PR3-A hayan terminado **y estén aprobados por usuario + Codex**, CI de todas las plataformas verde, pruebas manuales de los ejecutables Windows, macOS ARM/Intel satisfactorias, revisión del workflow de releases completa, y publicación en **modo exclusivamente manual**. La app v1.2.0 no debe ejecutar un autoinstalador en ningún camino, incluso ante manifiesto válido. Usar nombres nuevos de assets (D5) y notas de migración claras.

**No basta la etiqueta «manual»:** documentar instalación limpia y reemplazo seguro de versiones antiguas, no descomprimir encima de un directorio PyInstaller mezclado. Si una plataforma no supera pruebas reales, no publicar asset de esa plataforma como si estuviera validado. Si hay necesidad de distribuir antes del PR3-A, exigir una decisión separada del usuario y una evaluación explícita de riesgos; no declarar una excepción automática.

GitHub permite preparar una release borrador con todos los assets y publicarla ya completa, opción especialmente importante con releases inmutables.

### D3 — L3 offline, dos claves: **ACEPTADO COMO OBJETIVO PREFERIDO, CON CORRECCIÓN CRÍTICA**

Un solo mantenedor humano reduce mucho el valor de revisiones independientes para L2 con secretos en Actions. Acepto **L3 como recomendación principal**.

**Objeción:** Claude describe `herramientas/firmar.py` que, en la misma ejecución, **descarga assets de GitHub, pide la contraseña de la clave privada y luego sube la firma a GitHub**. Esa clave no está en GitHub, pero se usa en un equipo/proceso con acceso a la red. **Eso no es firma plenamente offline/air-gapped**, y además ejecutar un `firmar.py` modificado maliciosamente en el repositorio podría exfiltrar la clave. La etiqueta L3 por sí sola no corrige este riesgo.

**Arquitectura preferida de firma:** separar (i) preparación/descarga/verificación pública, con acceso a GitHub, (ii) firma con herramienta auditada y fijada en un entorno aislado sin red ni credenciales de GitHub, (iii) subida del manifiesto y la firma desde otro proceso/entorno sin acceso a claves privadas. Como alternativa pragmática, un dispositivo hardware o un firmador local estrictamente auditado y sin conectividad mientras firma. El propietario debe custodiar clave principal y respaldo **en lugares diferentes**, cifradas; nunca subirlas al repositorio, a GitHub Secrets ni imprimirlas en logs.

**Dos claves activas desde el principio:** tener ambas claves aceptadas para cualquier release también **duplica** las credenciales cuya filtración permitiría firmar. Recomiendo roles expresos: principal para releases normales, respaldo solo para recuperación/rotación; si el cliente acepta al respaldo para releases normales, documentar claramente ese alcance. Diseñar revocación en una actualización firmada por clave aún válida y límites de confianza de **clientes antiguos que no se actualicen**. Ninguna revocación local protege automáticamente a un cliente offline anterior.

La firma autentica lo firmado, **no garantiza el contenido benigno de los ejecutables construidos en CI**. Debe existir revisión del commit/tag, hash recalculado, archivos esperados y pruebas manuales previas a firmar.

### D4 — Mismo ejecutable como instalador, copiándose a staging B: **ACEPTADO PARA EL SPIKE, NO COMO SOLUCIÓN APROBADA**

Claude aclara correctamente un malentendido mío: **A no mueve el árbol que está ejecutando**; copia su contenido a un staging B, y después reemplaza la instalación vieja ya cerrada. Esto hace el diseño **plausible**, y reduce la necesidad de mantener otro ejecutable.

No obstante, la secuencia `rename(vieja, .anterior)` + `rename(B, destino)` **no es una transacción atómica conjunta**: entre ambos movimientos, o tras un apagón, puede faltar la ruta normal. El proceso A podría restaurarla solo si sigue vivo; si desaparece por un corte eléctrico, no hay garantía de recuperación automática en el próximo arranque por esa ruta ausente. Requiere journal de estado recuperable, procedimiento de rescate manual verificable, o mecanismo externo de recuperación que se pueda iniciar aunque la ruta habitual no exista.

Puntos de aceptación del spike:
- Probar lectura/copia del árbol en ejecución con PyInstaller onedir y app bundle; **no asumir** comportamiento de DLL, antivirus, Gatekeeper ni App Translocation.
- Verificar la firma **antes de ejecutar A**. El staging y ruta de instalación deben resistir sustitución de rutas, symlinks, permisos cambiados y ejecuciones concurrentes.
- A debe conservar acceso a las referencias de proceso reales; el PID numérico puede reutilizarse. El chequeo de salud no puede ser solamente un archivo `arranque_ok`: usar nonce único/canal autenticado y comprobar versión/ubicación/proceso reales. Un inicio de GUI en 30 segundos no prueba que toda la app funcione; timeout configurable y prueba adicional de actualización.
- Conservar el respaldo hasta recuperación comprobada y permitir restauración tras fallo de salud y **tras reinicio**, no solo tras excepciones atrapadas.
- Probar usuario con Unicode, Windows Defender, carpeta sin permisos, OneDrive, macOS en `/Applications` y Descargas, y errores forzados en cada paso. En macOS, firma ad-hoc de PyInstaller basta para requisitos de carga de binarios arm64, **no sustituye** aprobación de Gatekeeper/notarización de una app distribuida. La afirmación sobre ausencia general de cuarentena con `urllib` requiere test real, no suposición universal.

**Decisión:** PR3-B realiza un spike **no integrable** comparando esta opción contra helper separado y actualización manual. PR3-C se aprueba solo si la matriz sale bien; de lo contrario se mantiene modo manual por plataforma.

### D5 — «Kill-switch» por cambio de nombre de assets: **VERIFICADO Y ACEPTADO COMO TRANSICIÓN**

Aquí Claude tiene razón y corrijo mi afirmación anterior: **para una release legítima nueva podemos impedir que los clientes existentes elijan un paquete autoinstalable**.

Verificación directa del código:
- `actualizador.py:52-59` en `main` (y la función equivalente en `v1.0.0`) devuelve nombres exactos: `Compresorfree-Windows.zip`, `Compresorfree-macOS-AppleSilicon.dmg` y `Compresorfree-macOS-Intel.dmg`.
- `actualizador.py:62-77` toma `releases/latest` y busca por igualdad exacta `a["name"] == paquete`. Si no lo encuentra, asigna `url=None`.
- `app.py:360-366` en `main` muestra «Abrir la página de descarga» cuando `not info["url"]` y **retorna** antes de `instalar_actualizacion`. En `v1.0.0`, el mismo control está en `app.py:190-197`.
- Para que esto ocurra, el nuevo tag debe compararse como superior con `_a_tupla` y ser la release que devuelva `releases/latest`. Los borradores/pre-releases no funcionan como publicación estable equivalente.

**Importante:** es un **fallback de compatibilidad controlado por los nombres de nuestros propios assets**, no un kill-switch criptográfico remoto general. No revoca la función existente ni protege frente a un atacante capaz de publicar o volver a introducir los nombres viejos. Debe existir un **test de regresión permanente** de nombres legacy prohibidos en todas las releases futuras. No renombrar ni borrar arbitrariamente assets de releases antiguas para «protegerlas»; sería distinto del flujo comprobado.

## Observaciones sobre atomicidad, firma, instalador, PDF y transición

### A. Matriz de publicación sin sobrescritura

| Entorno | Posición | Verificaciones que faltan |
|---|---|---|
| Linux ext4 | Acepto `renameat2(RENAME_NOREPLACE)`; prueba de Claude reproducida según su informe. `os.link` + `os.unlink` es fallback válido cuando se admite hardlink. | Tests con varias instancias y carreras; captura de `EEXIST`, `EXDEV`, `EINVAL`/`ENOTSUP`, limpieza del temporal y permisos. |
| Linux btrfs/xfs/vfat/exfat/SMB | Garantía contractual del syscall **solo si el FS la soporta**; no inferir de ext4. | Montajes y red reales, latencias, soporte de primitivas y fallo seguro. |
| Windows NTFS | `os.rename` falla ante destino existente según documentación oficial de Python; excelente candidata. | Test runner en NTFS real, archivo existente y colisión tardía, rutas Unicode/largas, antivirus, ACL y sobreescritura indirecta por alias. |
| Windows FAT/exFAT/SMB/OneDrive | La semántica de `os.rename` no exige hardlinks; esto sí elimina una objeción previa para FAT/exFAT en Windows. | Probar en el FS destino, SMB/OneDrive y concurrencia; no inferir que sincronización remota sea atómica o idéntica al disco local. |
| macOS APFS/HFS+ | `renamex_np(RENAME_EXCL)` es una ruta técnica razonable. | Confirmar existencia del símbolo/contrato en versiones soportadas, uso correcto desde `ctypes` y tests en APFS/HFS+; fallback seguro a hardlink cuando sea aplicable. |
| macOS exFAT/FAT | Fail-closed si no hay primitiva compatible. | Probar USB real y reportar mensaje comprensible. |

**Distinción:** publicación atómica y no-clobber significan que otros procesos no observan un archivo parcialmente escrito en el destino final y que no pisamos un destino ya existente. **No equivalen por sí mismas a durabilidad ante corte de energía**: el diseño debe considerar `fsync` del temporal y, cuando sea viable, del directorio; documentar límites de NTFS, APFS, SMB y medios extraíbles.

Usar temporales exclusivos en el directorio destino, mantener extensión/formato correcto para FFmpeg, cerrar/desocupar handles antes de publicar, evitar `os.replace` como fallback que sobrescriba, y no confiar solo en `realpath+normcase` para alias, symlinks y hardlinks. La garantía es respecto de las entradas identificadas al planificar; terceros concurrentes pueden cambiar rutas, por lo que se necesita defensa en el momento de publicar. En sistemas sin capacidad requerida, **fallar sin tocar el original**, no degradar garantías silenciosamente.

### B. Manifiesto firmado, rotación y `firmar.py`

Acepto el concepto de **firmar los bytes exactos** del `manifest.json` (firma separada) y verificar antes de procesarlo, seguido de validación estricta de esquema. Campos mínimos: `schema`, producto, canal, versión estricta, tag exacto, commit SHA, timestamp, OS, arquitectura, formato, nombre, SHA-256, tamaño comprimido y límites de expansión del archivo. Añadir límites de cantidad de entradas, rutas permitidas, estructura raíz e identificación única del asset. Evitar ambigüedades de caracteres/encoding, duplicación de claves JSON y parsers permisivos tras la verificación.

La firma debe usar un `key_id` autenticado o usarlo solo como pista no confiable para elegir entre claves integradas. Validar la firma **antes de ejecutar contenido descargado**. Rechazar downgrade, manifest/asset de otro tag, clave desconocida, OS o arquitectura inesperada y zip/dmg inválido. Para nuevas releases, no depender de una comparación de versiones que extrae dígitos arbitrariamente (véase `actualizador.py:40-45`): usar semver estable estricta.

**Modificación obligatoria al flujo de Claude:** separar el firmador que tiene clave privada de cualquier proceso que descargue/suba datos a GitHub. La clave de respaldo **no debe estar en el mismo equipo ni con las mismas credenciales que la principal**. Probar firma válida, falsa, intercambio de asset, rollback y recuperación/rotación con un cliente que confía en claves viejas y nuevas.

Con releases inmutables activadas, la secuencia es: compilar y probar → crear draft → verificar assets → firmar offline y adjuntar firma → comprobación final → publicar. GitHub indica que la **inmutabilidad solo se aplica a futuras releases**, no retroactivamente a v1.0.0/v1.1.0. [GitHub immutable releases](https://github.blog/changelog/2025-10-28-immutable-releases-are-now-generally-available/), [GitHub managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

### C. PDF: huella estructural

**Acepto la huella como filtro automático conservador; rechazo llamarla prueba completa de fidelidad.** Comparar MediaBox/CropBox/Rotate, número y tipos de anotaciones, formularios, enlaces, bookmarks, adjuntos, capas, PDF/A y permisos detecta regresiones que el contador de páginas no detecta.

Pero igualdad de esos valores **no garantiza** igualdad de texto, fuentes, destinatarios de links, contenido de anexos, apariencia de campos, Javascript, lectura accesible ni colores/rasterización. Para adjuntos comparar nombre **y hash de contenido**; para links comparar destinos; para campos formularios comparar nombres, valores y apariencias relevantes; para imágenes respetar `/SMask`, ICC, `/Decode` y colores. Al cambiar el PDF puede perderse conformidad PDF/A, aunque XMP conserve `pdfaid`: validación con veraPDF en CI y casos incompatibles rechazados en ejecución. La firma digital se invalida al reescribir: **rechazo por defecto**, sin forzar durante esta etapa.

La huella se calcula sobre un conjunto de atributos normalizados de seguridad y semántica, **no como hash byte a byte de objetos que la compresión está diseñada para alterar**; aceptar diferencias inocuas solo cuando estén expresamente identificadas. PDF cifrado sigue omitido hasta cubrir R2/R3/R4/R6, contraseñas/permisos y caso de adjuntos cifrados. Renderizado comparativo de fixtures (fidelidad visual, no solo estructura) en pruebas; no prometer equivalencia visual universal.

**Corrección adicional:** `compresor_pdf.py:101` llama `remove_unreferenced_resources()`: no asumir que la huella detectará siempre pérdidas de recursos visuales o semánticos. Evaluar eliminar o limitar esa operación si no se justifica.

### D. Video, espacio disponible y resultados sin mejora

Apruebo **no remux automático**. Si el archivo de entrada **ya es MP4 compatible** y el resultado no reduce tamaño, prefiero **no publicar** y mostrar «Sin reducción; original conservado». Si se cambia de contenedor o codec por compatibilidad, se puede publicar la conversión aun cuando crezca, con aumento explícito. No usar automáticamente el umbral `≥95 %` como si «reducir 5 %» fuera un fracaso: el umbral necesita benchmark y decisión de UX. No asumir que MOV equivale a MP4 sin inspección de streams y metadatos.

Claude propone comprobar espacio libre frente al tamaño original. Eso puede **mejorar** la experiencia, pero **no asegura** espacio suficiente (FFmpeg en CRF puede crecer, staging puede duplicar uso, el espacio puede cambiar en paralelo). Medir y controlar errores ENOSPC, limpiar temporales y proporcionar diagnóstico; evitar tratar estimación como cota segura.

Para PDF que no se reduce, mi recomendación al propietario es **no crear copia redundante** por defecto y devolver estado estructurado «sin mejora»; hay que adaptar la API/GUI/CLI y los tests de modo explícito, no simular que se creó una salida cuando no existe. Si se decide mantener compatibilidad con la API actual, posponer esta política al PR2-B y documentar la elección.

### E. Transición desde v1.1.0 y límites de seguridad

Acepto el plan de release manual v1.2.0 y **verifiqué el fallback también en v1.0.0**. El usuario antiguo recibe aviso y enlace web si el asset legacy no aparece; no habrá autoinstalación por el canal legítimo mientras se respeten los nombres nuevos.

Condiciones:
1. No distribuir nuevos assets con nombres legacy en ninguna release estable futura; probarlo en el workflow y en el repositorio antes de publicar. Mostrar en la release el nombre exacto del asset que corresponde a cada plataforma.
2. Los usuarios v1.0/v1.1 **no verifican firma Ed25519**. El primer salto manual conserva la confianza básica del sitio/HTTPS y de cómo el usuario obtuvo el instalador. La firma embebida protege la cadena **desde la primera instalación de un cliente nuevo confiable**; no llamar al primer salto «TOFU» en sentido estricto, porque no hay un pin criptográfico adquirido en ese cliente heredado. Como mejora, publicar hash y huella de la clave en un canal independiente si es viable.
3. Instrucciones manuales seguras: respaldo/migración de datos pertinentes, reemplazo limpio de instalación, no superponer carpetas `_internal` antiguas, validar arranque y conservar instalador anterior para recuperación.
4. Proteger cuenta, ramas, tags y workflows, y habilitar inmutabilidad para **nuevas** releases. La inmutabilidad no blinda releases históricas; control de permisos y monitoreo/revisión son necesarios mientras existan clientes heredados.
5. No publicar por sorpresa: el propietario da aprobación **específica** al plan y otra **explícita** a la release tras el informe de pruebas.

## Plan definitivo consensuado (orden y alcance de PRs)

Se mantienen las fases de Claude con modificaciones concretas. **Todos los PR**: rama desde `main` actualizado, draft, tests de regresión, CI, informe de plataformas, revisión independiente de Codex sobre SHA final y decisión de merge **solo del propietario**.

| Orden | Entregable | Alcance y condición de cierre |
|---|---|---|
| **Fase 0** | Protección operativa del repositorio | Propietario: 2FA, proteger `main` y tags, limitar publicación y workflows, permisos mínimos de Actions, activar releases inmutables para futuras versiones. No publicar durante el debate. |
| **1: PR1-A** | Integridad + CI mínimo | Planificar lote GUI/CLI, proteger entradas y destinos, temporales y publicación no-clobber, validación básica, omitir PDF especiales, `pytest` en Ubuntu/Windows/macOS. Bloquea C1/C2/C4. |
| **2: PR1-B** | Cancelación/cierre | Controlador supervisado de FFmpeg/Ghostscript, colas y vida de Tk, lectura acotada de `stderr`, cierre seguro, pruebas con hijos reales. **No usar `preexec_fn` de Python en la app con hilos**; probar alternativas Linux y Job Objects Windows antes de afirmar garantías. Bloquea C3/C7. |
| **3: PR1-C** | Pruebas ampliadas + UX mínima | C5/C9/C10, archivos Unicode y `%`, casos PDF especiales, Xvfb, lint, compatibilidad CLI, espacio insuficiente y README. |
| **4: PR3-A** | Cadena de suministro + release manual | Endurecer workflow y tags, nuevas convenciones de assets, manifest y verificación Ed25519 con firmador **realmente separado del acceso a red**, dos claves offline con roles/recovery, auto-instalación **deshabilitada** en builds nuevos. Testar no reconocimiento de assets por v1.0/v1.1. |
| **★ PUERTA v1.2.0** | Posible hotfix manual | Solo **después** de PR1-A/B/C + PR3-A revisados, ejecutables probados manualmente en Windows, macOS ARM e Intel, controles de seguridad activos, assets correctos y **aprobación expresa del propietario**. **No autorizada en este documento.** |
| **5: PR2-A** | Fidelidad PDF | pikepdf predeterminado, Ghostscript explícito, huella estructural defensiva, casos de cifrado, PDF/A/firmas/colores y fixtures visuales. Rechazar condiciones no comprobadas. |
| **6: PR2-B** | Resultados y reproducibilidad | Política explícita para crecimiento y «sin mejora» video/PDF, límites de espacio, dependencias fijadas por plataforma, mediciones y documentación. |
| **7: PR3-B** | Spike de instalación | **No integrable y sin release**: comparar el mismo ejecutable en modo instalador (A→B) con helper o instalación manual, incluyendo apagón, rollback tras reinicio, seguridad del staging y matriz Windows/macOS. |
| **8: PR3-C** | Instalación segura | Implementar **solo el resultado ganador del spike**, por plataforma, con verificación de firma, rollback postarranque y recuperación; si una plataforma no supera pruebas, mantener actualizaciones manuales. |

**Etapa futura separada:** benchmarking Python vs. Rust, UI, paralelismo, perfiles avanzados y soporte de SCORM/imágenes. Ninguna migración de lenguaje se considera aprobada aquí.

## Recomendación sobre las decisiones del usuario

| Pregunta de Claude (`5) | Mi recomendación | Requiere aprobación del propietario |
|---|---|---|
| **1. ¿v1.2.0 tras PR1 + PR3-A?** | **Sí, bajo puerta estricta y solo manual**, para no retrasar corrección de pérdida de archivos. PR3-C no es requisito de una distribución manual. | **Sí, primero al plan y luego a publicar.** |
| **2. L3 offline o L2 en GitHub** | **L3 preferida**, con firma local realmente aislada y claves principal/respaldo separadas; no ejecutar un `firmar.py` de red con acceso a la clave. L2 solo alternativa expresamente aceptada con amenaza documentada. | **Sí:** logística de custodia y firma. |
| **3. PDF sin ahorro: ¿copia o no salida?** | **No generar copia redundante** de forma predeterminada en PR2-B, con estado «Sin mejora» correcto. Mantener modo de copia si el propietario prioriza compatibilidad con flujos existentes. | **Sí:** define comportamiento visible/API. |
| **4. 2FA, ramas/tags protegidos, releases inmutables, Actions read-only** | **Sí, prioridad de Fase 0.** Al revisar la API, `main` seguía `protected:false`. La inmutabilidad de GitHub solo se aplica a nuevas releases. | **Sí; configurar y comprobar, sin suponer que ya se hizo.** |

**Sugerencia operativa:** dar una aprobación única al plan de PRs **no** equivale a autorizar cada merge o release. Mantener las tres puertas separadas: iniciar implementación, integrar cada PR y publicar v1.2.0.

## Puntos aún abiertos (si quedan)

No quedan desacuerdos de objetivo. Sí quedan **condiciones técnicas de entrada a implementación** que Claude debe especificar como tareas comprobables, no resolver mediante suposiciones:

1. **D3 / firma:** diseño separado del signer con clave y sin red; roles de las dos claves, procedimiento de rotación/revocación y recuperación tras pérdida de una clave, sin prometer seguridad automática de clientes que no actualizan.
2. **PR1-B / Linux:** alternativa segura a `preexec_fn` en app multihilo; ensayos de Job Objects Windows sin afirmar garantías sin prueba real.
3. **PR1-A / OS:** confirmar `renamex_np` en macOS, Windows en NTFS y exFAT, fallbacks reales en Linux/vfat y ubicaciones SMB; política fail-closed y prueba de concurrencia. No bloquear protección de datos en sistemas soportados por falta de pruebas de cada FS exótico: documentar aquellos no soportados.
4. **PR3-B:** protocolo de recuperación si la energía cae entre los dos renames, incluso cuando la ruta principal está ausente; handshake de salud con nonce y verificación de versión.
5. **Transición:** plantilla de verificación de nombres legacy en v1.0/v1.1, manual de instalación limpia y plan de validación de builds Windows/macOS antes de la puerta de v1.2.0.
6. **PDF:** definición exacta y tests adversariales de huella estructural, sin asumir que un matching de metadatos equivale a conformidad PDF/A ni a fidelidad visual.

Estas son **condiciones de aceptación** para sub-PRs/prototipos, no motivo para reabrir indefinidamente el debate. Si el propietario aprueba el plan, Claude puede preparar las ramas cuando se le autorice, Codex debe auditar cada diff y el propietario retiene control de la publicación.

**ESTADO: PLAN DEFINITIVO PROPUESTO — NO IMPLEMENTAR**
