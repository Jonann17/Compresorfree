# Instrucciones para Claude — Compresorfree

Comunicarse siempre en español.

## Flujo ChatGPT → Claude → Codex
El protocolo completo está en `docs/PLAN_CLAUDE_CODEX.md`. Resumen de lo que el propietario pidió explícitamente:

1. **Cada respuesta de debate se sube a git automáticamente**, sin preguntar, para que quede registrada y ChatGPT pueda leerla:
   - Archivo `docs/CLAUDE_RESPUESTA.md` (si ya existe una ronda anterior, agregar la nueva como `docs/CLAUDE_RESPUESTA_<n>.md` o una sección nueva, sin borrar las anteriores).
   - Commit y push a la rama del PR de planificación en curso (no a `main`).
2. **Al terminar, entregar en el chat un mensaje listo para copiar y pegar a ChatGPT**, con el mismo estilo del mensaje que el propietario le da a Claude: contexto (repo, rama, PR, documento), qué hacer paso a paso, formato de respuesta esperado y la advertencia de no implementar hasta aprobar.
3. No implementar cambios de código hasta que el propietario apruebe el plan definitivo.
4. Las implementaciones van en ramas `feature/<tema>` y terminan en un **draft PR** independiente para que Codex lo audite antes de integrarlo en `main`. Nunca hacer merge, publicar releases ni escribir en `main` sin autorización explícita.
