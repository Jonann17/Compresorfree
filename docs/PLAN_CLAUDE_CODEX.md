# Compresorfree — Plan de ingeniería y protocolo ChatGPT → Claude → Codex

**Estado:** PROPUESTA PARA DISCUSIÓN (NO autoriza implementación).  
**Repositorio:** https://github.com/Jonann17/Compresorfree  
**Rama base:** `main`  
**Idioma de coordinación:** español.

## 0. Reglas de colaboración

1. **ChatGPT** actúa como arquitecto/revisor de propuestas; **Claude** como interlocutor técnico e implementador; **Codex** como auditor independiente de los PR terminados. El dueño del repositorio aprueba las decisiones y el merge.
2. **Claude NO debe empezar a modificar código hasta completar una ronda de debate**. Debe entregar `docs/CLAUDE_RESPUESTA.md` (o texto equivalente para transmitir a ChatGPT) con objeciones, alternativas y decisiones pendientes.
3. No simules una conversación directa entre agentes: si no existe un canal real entre sesiones, el usuario transmite el plan y la respuesta entre ChatGPT y Claude mediante documentos/PR.
4. Cambios en una rama `feature/<tema>`; nunca escribir en `main`, crear un release, autoactualizar la app instalada ni hacer merge sin autorización explícita del propietario.
5. Cada implementación debe terminar en **draft PR**, pruebas, notas de riesgo y pasos de verificación. Codex revisará el diff del PR y puede solicitar cambios; Claude responde y corrige. Ni Claude ni Codex aprueban por sí solos el merge.
6. Evitar secretos, muestras personales y documentos privados en commits, logs y fixtures. No descargar ni ejecutar artefactos de terceros sin comprobar procedencia.

## 1. Estado actual constatado (revisión estática)

- `app.py`: GUI Tkinter, ejecución por lotes, estimaciones, progreso, cancelación y CLI.
- `compresor_video.py`: FFmpeg H.264/AAC, tres niveles CRF 23/28/32 y estimación mediante muestras.
- `compresor_pdf.py`: Ghostscript opcional; fallback pikepdf/Pillow; evita entregar un PDF mayor que el original copiándolo.
- `actualizador.py`: consulta GitHub Releases, descarga e instala paquetes Windows/macOS.
- `compilar.py`: PyInstaller.
- `.github/workflows/compilar.yml`: matriz Windows, macOS ARM e Intel; construye al hacer push a `main` y publica releases por tag o input manual.
- `requirements.txt` sin versiones fijadas; no se observan tests ni workflow de validación en la raíz. No se han ejecutado pruebas de funcionamiento en sistemas reales.

### Riesgos/hipótesis a verificar

- `rutas_salida()` deduplica dentro del lote pero no protege todos los destinos preexistentes; FFmpeg incluye `-y`.
- El proceso de video escribe al destino definitivo antes de asegurar éxito; una falla puede dejar un MP4 parcial.
- Ghostscript usa `subprocess.run` sin manejo de interrupción por `cancelar`; el muestreo de video también.
- La estimación de PDF puede consumir tiempo comparable a la compresión completa.
- Las actualizaciones no verifican explícitamente hash/firma del paquete ni origen final antes de reemplazar ejecutables.
- La instalación usa extracción ZIP y scripts de reemplazo: revisar protección frente a rutas maliciosas, archivos incompletos, rollback y permisos.
- El comando de compilación mezcla interfaces de varios OS; probar cada destino, no asumir compatibilidad.
- PDF con transparencias, máscaras, anotaciones, formularios, firmas o documentos cifrados requiere tratamiento conservador.
- `tipo_por_extension()` clasifica como video todo lo que no termina en `.pdf`; validar tipos y errores.
- La GUI actualiza widgets desde callbacks programados con `after`, pero hay que auditar cierre de ventana y operaciones en segundo plano.
- Resultados de compresión podrían crecer; definir política explícita para video y PDF.

No asumir que todas las hipótesis son bugs. Reproducirlas con pruebas pequeñas y documentar evidencia.

## 2. Objetivo de la primera iteración (MVP de estabilización)

**Mantener** compresión de videos a MP4, compresión PDF, GUI Tkinter, CLI, estimación, progreso, cancelación y builds Windows/macOS. **No** hacer rediseño visual integral ni agregar múltiples formatos nuevos en esta iteración.

Prioridades:
- P0 — integridad de archivos, no sobrescritura inadvertida, validación de inputs/outputs y cancelación/limpieza de temporales.
- P0 — seguridad del actualizador: verificar procedencia e integridad antes de instalar; instalación recuperable o, si no es posible garantizarla, ofrecer descarga manual segura.
- P1 — pruebas automatizadas rápidas y reproducibles (sin depender de videos de usuario).
- P1 — controles CI en pull requests (lint, pruebas unitarias, smoke tests con FFmpeg/Ghostscript disponibles, aislados por plataforma).
- P2 — modularización progresiva del procesamiento y la UI, solo si simplifica pruebas y no rompe compatibilidad.
- P2 — mejoras de estimación, experiencia y rendimiento, tras asegurar lo anterior.

### Criterios de aceptación

1. Ningún input original se altera. Si un destino existe, no se pisa silenciosamente: se rechaza o se crea un nombre único; la política debe quedar documentada y testeada.
2. Salidas se producen en temporales del mismo filesystem y se finalizan solo tras exit code 0 y validación básica; ante error/cancelación no quedan salidas nuevas corruptas.
3. Cancelación deja de procesar el lote y finaliza subprocesos hijos razonablemente; no bloquea la GUI.
4. Los resultados PDF abren y conservan cantidad de páginas; probar casos con gráficos, transparencias, anotaciones y metadatos. No alterar PDFs firmados sin aviso/decisión explícita.
5. Video mantiene compatibilidad H.264/AAC/MP4, relación de aspecto y dimensiones pares; FFmpeg verifica decodificación básica del output en fixtures.
6. Pruebas para selección de formatos, destinos duplicados, errores de dependencias, cancelación y fallos de subproceso; usar mocks donde convenga.
7. CI corre tests en PR. Windows/macOS producen artefactos verificables; releases siguen siendo acción deliberada.
8. Actualizaciones no ejecutan artefactos sin comprobar integridad contra referencia confiable; diseñar correctamente el modelo de confianza: un checksum alojado junto al ZIP no demuestra autenticidad por sí solo.
9. README explica instalación, restricciones de codecs/Ghostscript, políticas de sobrescritura, riesgos/limitaciones de PDFs y comandos de prueba.
10. Informe de tests con comandos, OS, versiones, evidencias y limitaciones. No afirmar pruebas que no se corrieron.

## 3. Plan por etapas

**Etapa A — diagnóstico y conversación (SIN PROGRAMAR)**  
Claude relee fuentes y CI, elabora inventario de riesgos reproducibles y responde a las 8 preguntas del apartado 4. ChatGPT y el usuario acuerdan decisiones. Entregable: `docs/CLAUDE_RESPUESTA.md` propuesto, sin código implementado.

**Etapa B — tests y seguridad P0**  
PR pequeño con test harness, sanitización/validación de destinos, escritura atómica, cleanup y control de procesos. Incluir pruebas de cancelación y archivo ya existente.

**Etapa C — actualizador**  
Separar búsqueda/descarga/instalación, implementar controles de confianza y rollback o cambiar a actualización manual por defecto. Revisión más estricta y matriz Windows/macOS.

**Etapa D — CI y documentación**  
Tests en PR, builds opcionales de validación, dependencia reproducible, mejora de README y trazabilidad de releases.

**Etapa E — mejoras futuras (no en primer PR)**  
Interfaz más moderna, perfiles CRF ajustables, objetivos de tamaño aproximados, métricas de calidad, procesado paralelo configurable, soporte de imágenes; evaluar tras benchmarks y validación.

## 4. Preguntas técnicas para debate con ChatGPT (OBLIGATORIAS)

Claude, **responde antes de implementar**, usando para cada pregunta: `opción propuesta / alternativas / riesgos / evidencia en código / decisión recomendada`.

1. ¿Es preferible conservar Tkinter o separar un backend sin UI antes de considerar otra tecnología gráfica?
2. ¿Cómo diseñar escritura atómica, manejo de nombres y comportamiento ante destino existente para GUI y CLI?
3. ¿Cómo cancelar FFmpeg, Ghostscript y estimaciones sin bloquear procesos ni dejar archivos parciales?
4. ¿Se mantiene Ghostscript como opción prioritaria? ¿Cómo manejar firmas, formularios, transparencias y archivos PDF cifrados?
5. ¿Conviene preservar video si el resultado crece, y cómo comunicar calidad/tamaño sin confundir al usuario?
6. ¿Qué modelo de integridad/autenticidad y rollback es alcanzable para las actualizaciones automáticas Windows/macOS con los recursos actuales? ¿Conviene deshabilitar auto-instalación hasta tenerlo?
7. ¿Cómo estructurar tests, fixtures y CI sin convertir cada PR en una compilación costosa? ¿Qué versiones de Python y plataformas probar?
8. ¿Qué cambios del plan aceptarías, rechazarías o pospondrías? Define PRs de tamaño acotado y criterios medibles.

Formato de respuesta exigido:
```md
# CLAUDE_RESPUESTA — Compresorfree
## Diagnóstico confirmado
## Riesgos no confirmados
## Debate: respuestas a las 8 preguntas
## Plan revisado (PR1 / PR2 / PR3)
## Decisiones pendientes para ChatGPT y usuario
## Pruebas previstas y definición de terminado
ESTADO: ESPERANDO REVISIÓN — NO IMPLEMENTAR
```

## 5. Orden de trabajo después de aprobar el debate

- Crear rama `feature/compresorfree-stabilization` desde `main` actualizado.
- Implementar **solo PR1** aprobado, tests y docs; no reescribir todo el proyecto.
- Ejecutar pruebas, describir salidas y adjuntar comandos usados.
- Abrir draft PR apuntando a `main`, con checklist de aceptación y riesgos.
- Solicitar revisión independiente de Codex sobre el PR. Codex debe consultar el diff **real**, no solo el resumen de Claude.
- Claude corrige hallazgos, añade regression tests y responde a cada comentario.
- Codex reaudita el último commit, señala `PASS`, `CHANGES_REQUESTED` o `BLOCKED` con justificación. Usuario decide merge.

## 6. Prompt para Codex (usar únicamente tras concluir un PR de Claude)

> Audita de forma independiente el PR de Compresorfree comparándolo contra `main`. No confíes en el informe de Claude sin corroborarlo. Revisa integridad de archivos, posibles sobrescrituras, comandos/subprocesos, cancelación, PDF, formatos, seguridad de actualizaciones, supply chain, regresiones GUI/CLI, tests y workflows. Ejecuta pruebas disponibles e informa cuáles no pudiste ejecutar. Para cada hallazgo indica severidad (P0/P1/P2), ruta, línea, escenario reproducible, impacto y corrección mínima sugerida. No modifiques ni mezcles el código durante esta auditoría. Reporta al final PASS / CHANGES_REQUESTED / BLOCKED. Revisa el SHA final del PR, no una versión antigua.

## 7. Límites y comunicación

- No hacer force push a `main` ni publicar releases en etapa de debate.
- Las sugerencias de Claude solo cambian el plan si ChatGPT/usuario las aceptan.
- Codex no es una garantía formal de seguridad: la aprobación requiere CI y, cuando corresponda, pruebas manuales reales.
- El usuario decide si se prioriza Windows frente a macOS, y si el objetivo siguiente es reducir archivos SCORM/otros formatos o mantener solo video/PDF.
