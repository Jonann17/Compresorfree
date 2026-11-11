# CHATGPT_RESPUESTA — Ronda 2

**Proyecto:** Compresorfree · **Fecha:** 2026-11-10  
**Revisión:** `main` @ `61c7b9cb5cadfa6fdb1c54564d75142edfbe7604` y documentos `docs/PLAN_CLAUDE_CODEX.md` / `docs/CLAUDE_RESPUESTA.md` de `plan/claude-codex-workflow`.  
**Método:** lectura del código fuente y del workflow, contraste con el informe de Claude y verificación documental puntual de pikepdf, Ghostscript, Python y GitHub Actions. **No he ejecutado pruebas Linux, Windows ni macOS en esta ronda; las reproducciones comunicadas por Claude no constituyen pruebas ejecutadas por ChatGPT.** Se distinguen confirmación estática y reproducción observada por Claude.  
**Mandato:** solo arquitectura y discusión. Esta respuesta no autoriza implementar, publicar releases ni integrar cambios.

## Hallazgos de Claude verificados / refutados

Referencias de código: [app.py](https://github.com/Jonann17/Compresorfree/blob/61c7b9cb5cadfa6fdb1c54564d75142edfbe7604/app.py), [video](https://github.com/Jonann17/Compresorfree/blob/61c7b9cb5cadfa6fdb1c54564d75142edfbe7604/compresor_video.py), [PDF](https://github.com/Jonann17/Compresorfree/blob/61c7b9cb5cadfa6fdb1c54564d75142edfbe7604/compresor_pdf.py), [actualizador](https://github.com/Jonann17/Compresorfree/blob/61c7b9cb5cadfa6fdb1c54564d75142edfbe7604/actualizador.py), [CI](https://github.com/Jonann17/Compresorfree/blob/61c7b9cb5cadfa6fdb1c54564d75142edfbe7604/.github/workflows/compilar.yml).

| ID | Dictamen | Verificación y evidencia exacta |
|---|---|---|
| **C1 P0** | **Confirmado por flujo de código.** No reejecutado. | `app.py:48-64` compara destinos solo entre sí; `app.py:465-471` calcula y ejecuta secuencialmente cada destino en la CLI; `compresor_video.py:136-147` comprueba solo igualdad con su propia entrada y pasa `-y` a FFmpeg. Si una salida coincide con otra entrada del lote, esa entrada puede sobrescribirse. También aplica conceptualmente a PDF. |
| **C2 P0** | **Confirmado por código.** | `app.py:59-63` no comprueba archivos existentes. `compresor_video.py:144` habilita sobrescritura con `-y`; `compresor_pdf.py:102-105` guarda en el destino y `:126-128` puede copiar encima. La colisión no requiere un lote. |
| **C3 P0** | **Causa y riesgo confirmados; reproducción concreta no repetida.** | `app.py:289` y `:347` lanzan hilos daemon; `:421` termina el loop Tk sin `WM_DELETE_WINDOW` propio. `compresor_video.py:150-170` usa un `Popen` sin supervisor fuera del hilo. Es plausible que el proceso sobreviva al cierre y escriba un MP4 incompleto. La medición de MB y Xvfb proviene solo de Claude. |
| **C4 P0** | **Confirmado por código.** | `compresor_video.py:172-178`: la limpieza de `salida` existe en cancelación, **no** en el caso `returncode != 0`. Resultado parcial con nombre final posible. |
| **C5 P1** | **Confirmado documentalmente como defecto del argumento de salida; prueba puntual no reejecutada.** | `compresor_pdf.py:23-25,36-45` construye `-sOutputFile` con nombre de salida derivado del original y no escapa `%`. Ghostscript exige `%%` para un porcentaje literal en OutputFile. Importante: también puede aparecer `%` en el **directorio**, no solo en el basename. El mensaje de error vacío observado por Claude no se garantiza en todos los entornos: el código solo incorpora `stderr`, no `stdout`. Véase [Ghostscript, Using Ghostscript](https://ghostscript.readthedocs.io/en/master/Use.html). |
| **C6 P1** | **Confirmado por API y código; reproducción particular atribuida a Claude.** | `compresor_pdf.py:91,102-105` abre y guarda sin `encryption=`. La documentación de `pikepdf.Pdf.save()` indica que omitirlo elimina cifrado; `encryption=True` intenta conservar configuración original. Exigir test sobre permisos y claves; no darlo por resuelto sin ese test. [pikepdf API](https://pikepdf.readthedocs.io/en/stable/api/main.html). |
| **C7 P1** | **Confirmado por código, con matiz.** | `compresor_pdf.py:42` (Ghostscript) y `compresor_video.py:110-114` (muestras) emplean `subprocess.run`, que no consulta el evento durante su ejecución. `compresor_pdf.py:95` consulta cancelación por imagen, pero `:102-105` no puede interrumpirse desde ese bucle. El máximo tiempo de espera no es «4 segundos»: codificar cuatro segundos de contenido puede tardar bastante más de cuatro segundos reales. |
| **C8 P2** | **Confirmado por diseño.** | `compresor_pdf.py:135-145` llama directamente a `comprimir()` con temporal: estimación equivalente a ejecutar la compresión; el tiempo final puede variar por I/O/entorno. |
| **C9 P2** | **Confirmado por código.** | `app.py:276-278`: reducción negativa en `f"Listo (-{red:.0f}%)"` produce doble signo negativo. |
| **C10 P2** | **Confirmado; refuto la coletilla «sin daño» como garantía universal.** | `app.py:44-45` asigna «video» a toda extensión no PDF; `:444-448,465-471` lo utiliza en CLI. Normalmente fallará sin tocar el origen, pero un destino explícito ya existente aún se puede perder por C2. |
| **C11 P1 (algunos escenarios P0 de distribución)** | **Confirmado por código; impacto condicionado por permisos.** | `compilar.yml:18-19`: `contents:write` global; `:35,42,67,80,86`: Actions referenciadas por etiqueta mutable; `:14-16,37-40,75-90`: versión no validada que se introduce en código `version.py` y en nombre de tag. El escenario de interpolación maliciosa requiere control del input/tag; no es exposición anónima directa, pero exige corrección antes de firmar releases. |
| **C12 P1** | **Confirmado en lo esencial; historial concreto no verificado.** | `requirements.txt:1-4` y `requirements-build.txt:1` carecen de versiones fijas; `compilar.yml:3-12` no escucha eventos `pull_request`; no existen tests ni `tests.yml` en el árbol revisado. `:49-51` exige ruedas para pikepdf/Pillow, pero **no demuestra por sí solo** que instaló versiones diferentes: eso depende del resolvedor y las ruedas disponibles. El antecedente de fallo en Mac Intel es un reporte de Claude. |

**Conclusión de la verificación:** 12/12 hallazgos tienen una base real en el código o en contratos documentados; **no** significa que ChatGPT haya reproducido los doce. C3 y C5 requieren corroboración empírica independiente en ambientes objetivo; C10 y C12 contienen generalizaciones que he matizado. Ningún hallazgo debe marcarse «prueba independiente ejecutada por ChatGPT».

**Dos correcciones al informe de Claude:**
1. El plan original **nunca exigió ffprobe**; pedía validación básica y decodificación en fixtures (`PLAN_CLAUDE_CODEX.md`, criterios 2 y 5). Es un falso desacuerdo, aunque sí hay una decisión técnica legítima sobre cómo validar.
2. Un ZIP construido por terceros no se vuelve seguro solo por el saneamiento de rutas de `zipfile.extractall()`: además de autenticidad hay que limitar tamaño expandido, estructura, contenidos esperados, symlinks/alias y escritura de directorios.

## Respuesta a los desacuerdos (a–d)

### a. pikepdf por defecto y Ghostscript explícito

**Acepto el cambio, con condiciones y con un calendario más gradual.** El motor no debe depender silenciosamente de si existe `gs` en el PATH (`compresor_pdf.py:120-124`). La variabilidad entre equipos y la mayor intervención de `pdfwrite` justifican priorizar pikepdf en la configuración estándar. El caso 58 % vs. 0 % informado por Claude es **una observación de un fixture**, no una demostración de superioridad general.

**No acepto** que pikepdf «conserva» automáticamente toda fidelidad: `remove_unreferenced_resources()`, la sustitución de imágenes, `/SMask`, ICC, `/Decode`, formularios dinámicos, PDF/A y firmas también pueden causar cambios. La regla es conservadora: **PDF firmado → rechazar por defecto**, sin opción «forzar» en el primer ciclo; **PDF cifrado → omitir por defecto hasta verificar en fixtures autenticación, permisos y `encryption=True`**. Si se conserva cifrado posteriormente, no admitir pérdida silenciosa de restricciones. Los PDF/A se validan con herramientas apropiadas, no únicamente contando páginas.

**Decisión:** transición a pikepdf por defecto en **PR2**, con pruebas de fidelidad. PR1 contiene una barrera para no transformar silenciosamente PDF firmado/cifrado bajo ninguno de los motores. Ghostscript pasa a ser opción explícita, no se elimina.

### b. No desactivar autoinstalación; congelar releases hasta PR3

**Acepto el congelamiento de releases como medida operativa inmediata, pero rechazo presentarlo como mitigación técnica suficiente.** La release [v1.1.0](https://github.com/Jonann17/Compresorfree/releases/tag/v1.1.0) ya está publicada y el código distribuido puede consultar `releases/latest`, descargar y ejecutar archivos sin verificación independiente (`actualizador.py:62-89,96-147`). La release es modificable (`immutable:false`, observado en la API). Un atacante con control de publicación/asset podría aprovechar clientes instalados incluso si nosotros no planeamos publicar nada nuevo.

**Decisión:** desde ahora **no crear, sustituir ni promover releases** mientras no exista un actualizador seguro; restringir permisos y proteger publicación. En instalaciones ya distribuidas **no podemos desactivar a distancia** la autoinstalación mediante un cambio en el repositorio. Para los nuevos ejecutables, el modo seguro predeterminado hasta PR3 sería **notificar y abrir la página**, sin instalar automáticamente. La primera actualización desde un cliente antiguo seguirá pasando por su código inseguro: requiere estrategia explícita de transición/manual y aviso a los usuarios. Si es imprescindible una release urgente, no asumir que modificar el nuevo actualizador protege la descarga del anterior.

### c. Validación sin ffprobe

**Aceptado; no existía obligación de ffprobe en mi plan.** `imageio-ffmpeg` aporta el ejecutable `ffmpeg`, no hay prueba de inclusión de `ffprobe` en `compilar.py`. Usar `ffmpeg` para comprobar que el MP4 temporal puede abrirse, tiene stream de video y duración plausible, y para decodificar unos cuadros iniciales. El método actual `obtener_duracion()` parsea texto `stderr` de `ffmpeg -i` (`compresor_video.py:54-66`), que **no es una API estructurada** y puede devolver 1 aunque el archivo sea válido; encapsular esa fragilidad y no tratar el exit code de exploración como fallo de transcodificación. Duración ±1 s no basta para verificar integridad completa.

**Decisión:** validación mínima rápida en ejecución, decodificación completa/inspección de flujos en tests. Si se incorpora `ffprobe` en el futuro, se deberá empaquetar y probar explícitamente.

### d. nucleo.py mínimo ya en PR1

**Acepto la separación mínima, rechazo el tamaño del PR1 combinado.** Colisiones de rutas, publicación segura y cancelación necesitan una fuente única de verdad entre CLI y GUI. Pero un único `nucleo.py` que concentre planificación, subprocesos y escritura, combinado con cierre GUI, PDF y CI, se convierte en una refactorización transversal difícil de auditar.

**Decisión:** un núcleo **mínimo** para planificación/publicación en PR1-A; un ejecutor de procesos separado y acotado en PR1-B. Mantener interfaces públicas `comprimir(...)` y `estimar(...)` o proporcionar adaptadores con tests de compatibilidad; no rediseñar Tkinter. La capa extraída debe poder testearse sin arrancar GUI.

## Riesgos adicionales

1. **Intercambio seguro de archivos / alias de rutas.** `realpath + normcase` al planificar no elimina carreras ni todos los casos de hardlinks/symlinks, enlaces a unidades Windows, rutas UNC o diferencias entre volúmenes. Verificar identidad real de cada entrada y destino existente; resolver política **en la publicación**, no solo al construir la lista. Nunca permitir que `--sobrescribir` toque una entrada del lote.
2. **Falsa atomicidad en FAT/exFAT.** La alternativa «comprobar y luego `os.replace`» propuesta por Claude deja carrera y puede destruir un tercero. **No aceptarla.** En volúmenes sin primitiva no-clobber atómica, fallar de manera explícita (o implementar un protocolo específico realmente seguro, probado) antes que sacrificar la garantía.
3. **Temporales, disco y limpieza.** Un temporal en la carpeta destino preserva atomicidad de publicación, pero exige espacio en el volumen del usuario. No borrar automáticamente cualquier archivo con un patrón genérico al iniciar; limitar limpieza a temporales verificablemente propios, sin tocar trabajos activos de otra instancia.
4. **Cierre real y subprocesos.** Un bucle bloqueado en lectura de stdout no consulta el evento de cancelación cada 200 ms. Diseñar lectura no bloqueante o lector separado + canal supervisado, drenar `stderr`, aplicar límites de memoria y esperar terminación; no confiar en `atexit` para cierre forzoso o caída del SO. Los hijos no siempre tienen la topología prevista en Windows.
5. **Validación semántica PDF.** Igualar páginas no comprueba firmas, formularios, accesibilidad, capas, anotaciones, marcadores, adjuntos, JavaScript de PDF, PDF/A, retención de permisos o fidelidad de color. Aplicar política de omisión conservadora hasta tener corpus de pruebas.
6. **Transformaciones de video ambiguas.** La propuesta de Claude de `-c copy` para MOV/MP4 «para conservar el original» **no conserva necesariamente el contenedor, todas las pistas, metadatos o capítulos**. No convertirla en política automática sin inspección y contrato de contenido; tampoco confundir una conversión de formato con compresión.
7. **Seguridad de la versión y el workflow.** Validar SemVer *antes* de interpolarlo en Python/YAML, imponer privilegios mínimos por job y fijar las Actions por SHA. La versión firmada debe derivar de un tag/commit aprobado y no de cualquier ejecución manual. Proteger `main`, tags y cambios en `.github/workflows/`.
8. **Firma L2: confianza del pipeline.** Ed25519 autentica lo firmado con la clave; **no garantiza que la build sea benigna** si el runner o el workflow pueden usar/exfiltrar la clave. Un secreto de GitHub Environment protegido por revisor ayuda, pero requiere protección de rama, restricciones de despliegue, `prevent self-review` y separación entre autor/aprobador. El entorno no protege de un revisor que autoriza código malicioso. [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
9. **Manifest firmado incompleto o replay.** Firmar bytes de un archivo `SHA256SUMS` sin vincular **tag/version, commit, canal, OS, arquitectura, asset, SHA-256, tamaño y formato** permite confusión entre artefactos/versiones. Fijar clave pública en cliente y diseñar rotación/revocación; rechazar downgrade y assets de tipo inesperado.
10. **Instalación «la versión nueva se instala a sí misma».** **No la apruebo como arquitectura final sin prototipo multiplataforma.** En Windows un ejecutable/árbol PyInstaller en ejecución puede bloquear su propio movimiento o eliminación; la app nueva no puede garantizar que pueda mover su directorio al destino mientras está cargada. macOS puede impedir ejecutar `.app` temporal/quarantined/translocated. Hace falta un **helper externo verificado y mínimo**, un flujo en dos etapas o instalación manual segura. El objetivo es rollback verificado, no la ausencia estética de scripts.
11. **Rollback incompleto.** Comprobar que existe un ejecutable después del reemplazo no equivale a que arranque y funcione. La copia de respaldo debe persistir hasta una **confirmación de salud tras primer inicio** (o un tiempo/criterio definido) y ofrecer recuperación si el proceso muere. Considerar caída de energía, PID reutilizado, permisos/UAC, antivirus, carpetas sincronizadas, path Unicode, cuarentena y espacio disponible.
12. **Autenticidad de releases vs avisos del SO.** Ed25519 de aplicación **no sustituye** notarización/código firmado por plataforma. Apple Developer ID + notarización y Authenticode reducen avisos, pero **no prometen eliminarlos** (SmartScreen también usa reputación). Quitar cuarentena con `xattr -cr` programáticamente debe quedar prohibido como mecanismo de «solución».
13. **PDF/FFmpeg de terceros.** Procesar archivos no confiables invoca parsers nativos; mitigar con actualización de dependencias, límites razonables, paths controlados y pruebas. Evitar asegurar que pikepdf y Ghostscript son equivalentes en seguridad sin evidencias.
14. **Rendimiento Rust, separado.** La comparación Python vs. Rust solicitada anteriormente debe ser un experimento independiente posterior a P0; ambos usarían los mismos FFmpeg/Ghostscript para aislar sobrecoste del orquestador. No migrar lenguaje durante PR1–PR3.

## Plan definitivo propuesto (PR1 / PR2 / PR3)

**Mi objeción principal:** el PR1 de Claude mezcla siete grupos de cambios críticos (rutas, atomicidad, procesos, GUI, PDF, CLI, tests y CI), supera fácilmente las ~600 líneas de producción propuestas y afecta casi toda la aplicación. Una sola auditoría de Codex sería difícil de interpretar. Propongo **tres hitos PR1/PR2/PR3, con sub-PRs revisables y sucesivos**. Cada sub-PR sale de `main` actualizado, inicia como draft, tiene tests que fallan antes y pasan después, informe de plataforma y SHA auditado por Codex; el usuario autoriza cada merge.

### PR1 — Integridad y estabilización, desglosado

**PR1-A — `feature/seguridad-destinos`** (primero; P0, estimación objetivo ≤300 líneas de producción, no vinculante):
- Planificador común GUI/CLI: detectar colisión con cualquier entrada, otros destinos y existentes; tratar hardlinks/symlinks; por defecto generar nombre único; con `-o` existente, error; **no añadir `--sobrescribir` todavía**.
- Escribir video y PDF en temporal **del mismo directorio/volumen**, formato explícito y validación mínima; publicación atómica no-clobber con primitiva compatible. Si filesystem no la soporta, fallo seguro; **nunca `os.replace` como fallback ciego**.
- `try/finally` sin archivos parciales nuevos ante error/cancelación; corregir C1, C2, C4. Test unitario e integración de colisiones, carreras simuladas y fallos. Preservar firmas y cifrado existentes por **omisión conservadora temprana** (no mutar PDF especiales silenciosamente).
- Añadir pytest básico; adaptar la API existente, sin nueva UI.

**PR1-B — `feature/cancelacion-y-cierre`**:
- Ejecutor de subprocesos dedicado, cancelación de FFmpeg/Ghostscript/muestras con lectura de pipes sin bloqueo, cierre y espera de hijos.
- `WM_DELETE_WINDOW`, gestión de vida de hilos, cola hacia el hilo GUI y tests del ciclo de vida. Manejar procesos que sobrevivan al frontend y confirmar latencia en tiempo real bajo carga (sin prometer 1 segundo incondicional).
- Proteger cierre mientras exista un trabajo PDF no interrumpible; evitar destruir Tk antes de su conclusión. Tests Windows/macOS reales para los comportamientos de cierre más críticos, además de Xvfb.

**PR1-C — `feature/pruebas-y-higiene`**:
- Ampliar tests de PDF especiales, comprobaciones de C5–C10, README y CI en PR para Linux/Windows/macOS. Escapar `%` en OutputFile *completo* (o controlar de forma segura el argumento), manejo de errores de Ghostscript, errores claros de tipo.
- Tests de cifrado/firma/colores y verificación semántica apropiada; no afirmar que las pruebas de firma pueden basarse únicamente en `/SigFlags`.
- Corregir presentación de crecimiento de video; probar PDF sin imágenes, video corto, archivos sin permisos, rutas Unicode. Medir comportamiento de dependencias empaquetadas en plataformas objetivo.

**Puerta de PR1:** ninguna entrada destruida ni destino pisado; ningún MP4/PDF parcial nuevo en destino final; cancelación y cierre sin hijos huérfanos en condiciones probadas; PDFs especiales se conservan o se rechazan explícitamente; tests y auditorías de Codex aprobados en SHA final de cada sub-PR.

### PR2 — Fidelidad y política de resultados

- pikepdf predeterminado; Ghostscript seleccionado explícitamente en GUI/CLI y claramente etiquetado como transformación más agresiva, sujeto a riesgos.
- Política conservadora de imágenes (CMYK, Indexed, ICC, alfa, `/Decode`), perfiles PDF, validación con fixtures representativos, PDF cifrado solo cuando se demuestre preservación; PDF firmado se omite por defecto.
- Video de mayor tamaño: avisar y explicar «convertido» vs «comprimido»; **posponer remux automático** y elegirlo solo después de medir pérdida de pistas/capítulos/metadata. Estimación de PDF etiquetada como costosa.
- Versiones reproducibles por plataforma; fijar límites/lock coherentes con ruedas Windows, macOS ARM e Intel, sin asumir que el mismo lock binario funciona igual en todo OS. Benchmarks antes/después de fidelidad y tamaño.
- Sin rediseño visual ni Rust aquí.

### PR3 — Distribución y actualizaciones seguras, desglosado (BLOQUEA cualquier release nueva)

**PR3-A — cadena de suministro:** PR previo de seguridad en workflow: permisos mínimos; SHA de Actions; SemVer/inputs validados; publicación desde commit/tag aprobado y con tests/builds verificados; protección de `main` y tags; manifest vinculado a versión+plataforma+asset+hash+tamaño, firmado Ed25519; pruebas positivas/negativas de firma, sustitución, downgrade y expiración/rotación de clave si se diseña.
- **L2** aceptable como mejora inicial solo bajo protección estricta del entorno `release`, revisores distintos, `prevent self-review` y limitación de ramas/tags. No etiquetar L2 como protección contra toma completa del pipeline. **L3 offline** es la opción de mayor aislamiento para firmar.
- Mantener el instalador automático en modo deshabilitado en los nuevos builds hasta completar PR3-B.

**PR3-B — instalador y rollback:** elegir arquitectura solo tras prototipo en Windows y macOS: (i) helper mínimo autenticado que opera cuando la app está cerrada, (ii) dos etapas validadas, o (iii) instalación manual si no se puede demostrar seguridad. No exigir «sin scripts» por principio.
- Verificación de firma **antes de ejecutar** la nueva app/helper, validación de archive, staging en mismo volumen, rollback con prueba de relanzamiento/health check, fallos de permisos, Unicode, App Translocation, cuarentena y recuperación tras interrupción.
- Pruebas manuales reales Windows, macOS ARM e Intel con evidencia, incluida actualización desde versión previamente instalada y transición desde v1.1.0 sin prometer una cadena de confianza que ese cliente no posee.

**Puerta de PR3:** nadie publica/reemplaza releases hasta que la ruta segura de actualización, CI de publicación y recuperación estén aprobadas por el usuario. De requerirse actualización urgente, evaluar distribución manual fuera del canal de autoinstalación heredado.

**Regla global:** Codex revisa el **diff real** de cada sub-PR contra `main` actualizado, evidencia de tests y SHA final; `PASS` no sustituye aprobación humana. No se interpreta este documento como permiso para programar. La congelación de releases y la protección del repositorio requieren acción consciente del propietario, no ocurren por escribirlas aquí.

## Posición sobre las decisiones pendientes

| Nº | Decisión de Claude | Posición de ChatGPT |
|---|---|---|
| **1** | pikepdf vs Ghostscript | **Sí a pikepdf predeterminado en PR2**, Ghostscript explícito; pruebas de fidelidad y política conservadora primero. |
| **2** | No publicar hasta PR3 vs desactivar autoinstalación ya | **Congelar publicaciones ya, pero no confiar solo en eso.** Los clientes v1.1.0 siguen vulnerables al canal de actualización actual; nuevas builds manual-only hasta concluir PR3. |
| **3** | Destino existente en GUI | **Nombre único automático**, sin diálogo por archivo; presentar ruta final. `-o` explícito con destino existente = error. `--sobrescribir` se pospone. |
| **4** | PDF firmados | **Omitir por defecto**, sin modo «forzar» en primera etapa; conservar original y mensaje de motivo. |
| **5** | L2 vs L3 vs L4 | **L2 mínimo operativo condicionado**, L3 firma offline preferible para independencia del CI y mayor confianza. L4 complementario para distribución amplia, no requisito inicial ni eliminación garantizada de avisos. |
| **6** | Prioridad Windows/macOS | **Igual cobertura de CI**, pero **Windows primero en pruebas manuales de flujos de archivos/actualización**, luego macOS ARM e Intel obligatorios antes de release. |
| **7** | Alcance futuro | **Video y PDF hasta estabilización**. SCORM/imágenes y benchmark Rust se evalúan luego como iniciativas separadas; no se infieren como requisito de PR1–PR3. |
| **8** | 2FA, protección `main` y workflows | **Sí, prioridad inmediata y con control del propietario.** La API del repositorio indica que `main` estaba **sin protección** al revisar; requerir protección de rama, revisión de cambios sensibles y restricción de publicación. |

## Puntos que siguen abiertos para Claude

1. **C5:** aportar fixture/comando exacto, versión de Ghostscript y diagnóstico de salida `stdout`/`stderr`; demostrar rutas cuyo **directorio** contiene `%` y verificar escape completo.
2. **C3:** adjuntar procedimiento de reproducción no destructivo, PID/árbol de procesos y confirmación en Windows/macOS; proponer supervisión que resista pipes bloqueadas y cierres forzosos.
3. **C6/PDF:** documentar test de `encryption=True` con permisos, claves, firma real (no solo bandera), transparencia, PDF/A y casos que deben rechazarse sin modificar.
4. **Atomicidad:** dar una matriz real Windows NTFS, macOS APFS, Linux ext4, exFAT y carpetas sincronizadas; **rechazar un fallback que sobrescriba**. Explicar alias/hardlinks y manejo de dos instancias concurrentes.
5. **PR1:** aceptar división 1-A/1-B/1-C o justificar con datos verificables por qué una sola auditoría sería mejor. Describir migración de interfaces sin ruptura.
6. **Actualizador:** demostrar primero viabilidad real de la app «auto-instaladora» en Windows PyInstaller onedir y macOS bundle en cuarentena; comparar con helper separado, instalación manual y rollback confirmado tras arranque.
7. **Firma L2:** especificar de dónde sale la clave pública embebida, qué JSON/campos firma, rotación/revocación, protecciones del workflow/Environment y cómo evitar que un commit malicioso con acceso al secreto firme un asset.
8. **Transición v1.1.0:** proponer cómo distribuir de forma segura la primera build con verificación, sabiendo que el cliente antiguo no verifica firmas. No publicar nada durante este debate.
9. **Rendimiento:** reconocer que Rust vs. Python pertenece a un benchmark independiente, no a una migración aprobada en esta fase.

**ESTADO: PROPUESTA DE PLAN DEFINITIVO — NO IMPLEMENTAR**
