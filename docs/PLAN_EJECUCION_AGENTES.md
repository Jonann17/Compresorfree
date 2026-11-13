# Plan de ejecución con subagentes — Compresorfree

**Fecha:** 2026-11-13 · **Autor:** Claude (orquestador) · **Base:** plan definitivo consensuado (`docs/CLAUDE_RESPUESTA_3.md` + `docs/CHATGPT_RESPUESTA_4.md`)
**Estado de partida:** PR1-A terminado → [PR #2](https://github.com/Jonann17/Compresorfree/pull/2) (draft, CI verde en Ubuntu/Windows/macOS, **pendiente de auditoría de Codex**).
**Este documento propone *cómo* ejecutar el resto del plan con subagentes y qué modelo usa cada uno. No cambia el orden ni el alcance de los PR ya aprobados.**

Las casillas `[ ]` de las secciones 5 y 7 son para que el propietario marque su elección.

---

## 1. Quién es quién

| Rol | Quién | Qué hace | Qué **no** hace |
|---|---|---|---|
| **Propietario** | tú | Aprueba el plan, cada merge y cada release; configura GitHub (Fase 0) | — |
| **Arquitecto** | ChatGPT | Revisa propuestas y debate decisiones de diseño | Programar en el repo |
| **Orquestador** | Claude, sesión principal | Reparte el trabajo, integra, ejecuta pruebas, abre los draft PR y responde a Codex | Hacer merge o publicar sin autorización |
| **Subagentes** | Claude, lanzados por el orquestador | Tareas acotadas (sección 3); cada uno devuelve un resultado que el orquestador **verifica** antes de usarlo | Hacer push, merge, abrir PR o tocar `main` |
| **Auditor** | Codex | Auditoría independiente del diff real de cada PR | Modificar el código del PR |

Regla clave: **los subagentes no confían entre sí ni el orquestador confía en ellos sin verificar.** Todo pasa por pruebas y por la revisión del orquestador, y después por Codex.

---

## 2. Modelos disponibles y su costo relativo

Precios por millón de tokens según la API de Anthropic. En Claude Code no pagas por token: el consumo sale de los límites de uso de tu plan, pero **la proporción es la misma**.

| Modelo | Entrada | Salida | Salida relativa a Haiku | Para qué sirve mejor |
|---|---|---|---|---|
| **Claude Haiku 5.5** | $0.10 | $0.50 | **1×** | Leer y resumir, buscar en el código, revisar logs de CI, tareas mecánicas |
| **Claude Sonnet 5.5** | $2 | $10 | **20×** | Programación del día a día, pruebas, documentación, investigación técnica |
| **Claude Opus 5.5** | $4 | $20 | **40×** | Código delicado (archivos, procesos, concurrencia), revisión crítica. Es el modelo de la sesión actual |
| **Claude Fable 5.2** | $8 | $40 | **80×** | El más capaz: seguridad criptográfica, diseño del instalador, razonamiento largo |

Notas:
- Pediste **Fable 5.1**. Existe, pero **Fable 5.2 es más nuevo, más capaz y más barato** ($8/$40 contra $10/$50). Recomiendo 5.2. En Claude Code el subagente se elige con el alias `fable`, que usa la versión de Fable que tenga habilitada tu cuenta.
- Todos tienen un contexto de 1M tokens: el tamaño del proyecto no limita a ninguno.
- Además del modelo se puede ajustar el **esfuerzo** (bajo, medio o alto). Un modelo grande con esfuerzo bajo a veces rinde igual que uno menor con esfuerzo alto. Lo indico donde importa.

---

## 3. Catálogo de subagentes

| ID | Subagente | Tipo en Claude Code | Modelo recomendado | Alternativa barata | Alternativa máxima | Herramientas | Aislamiento |
|---|---|---|---|---|---|---|---|
| **S1** | **Explorador**: localiza código afectado y mapea el impacto de un cambio | `Explore` (solo lectura) | Haiku 5.5 | — | Sonnet 5.5 | lectura y búsqueda | no necesita |
| **S2** | **Investigador**: documentación externa (minisign, `renamex_np`, Job Objects, pikepdf) | `general-purpose` | Sonnet 5.5 | Haiku 5.5 | Opus 5.5 | web y lectura | no necesita |
| **S3** | **Implementador**: escribe el código de un PR | `general-purpose` | **según el PR** (sección 4) | Sonnet 5.5 | Fable 5.2 | todas | **worktree propio** |
| **S4** | **Autor de pruebas independiente**: escribe las pruebas **solo a partir de la especificación**, sin ver la implementación, para que no la "copien" | `general-purpose` | Sonnet 5.5 | Haiku 5.5 | Opus 5.5 | todas | worktree propio |
| **S5** | **Revisor adversarial**: busca formas de romper el PR antes de Codex | `general-purpose` o `/code-review` | Opus 5.5 | Sonnet 5.5 | Fable 5.2 | lectura y ejecución de pruebas | no necesita |
| **S6** | **Triaje de CI**: lee los logs de GitHub Actions y resume la causa de un fallo | `general-purpose` | Haiku 5.5 | — | Sonnet 5.5 | lectura y GitHub | no necesita |
| **S7** | **Documentador**: README, notas de PR, guía de instalación manual | `general-purpose` | Sonnet 5.5 | Haiku 5.5 | Opus 5.5 | lectura y escritura | worktree del PR |
| **S8** | **Prototipador**: el spike no integrable del instalador (PR3-B) | `general-purpose` | Fable 5.2 | Opus 5.5 | Fable 5.2 con esfuerzo alto | todas | worktree propio, **nunca se integra** |

**Por qué S4 va separado de S3:** si quien implementa también escribe las pruebas, tiende a probar lo que hizo y no lo que se pidió. Un autor de pruebas que solo lee la especificación encuentra más errores reales. Es el patrón que mejor funcionó en el PR1-A, donde las pruebas de regresión se escribieron contra la API pública y se comprobaron en rojo sobre `main`.

---

## 4. Asignación por PR

Para cada PR, el equipo y el modelo del **implementador (S3)**, que es la decisión que más pesa en calidad y costo. Los demás roles usan su modelo recomendado salvo que se elija otro perfil (sección 5).

| PR | Riesgo | Equipo | Implementador recomendado | Por qué |
|---|---|---|---|---|
| **PR1-A** (hecho) | Alto | — | Opus 5.5 (sesión principal) | Ya en revisión de Codex. Solo falta responder a sus hallazgos. |
| **PR1-B** cancelación, cierre seguro y Job Objects | **Alto**: procesos, hilos, Windows | S1 → S2 (Job Objects) → S3 + S4 en paralelo → S5 → S6 si el CI falla | **Opus 5.5, esfuerzo alto** | Concurrencia y procesos en 3 sistemas operativos: los errores son sutiles. |
| **PR1-C** `%` en Ghostscript, C9, C10, Unicode, README | Bajo-medio | S1 → S3 + S4 → S7 → S6 | **Sonnet 5.5** | Cambios acotados y bien especificados. |
| **PR3-A** firma minisign L3, workflow, verificación en el cliente | **Muy alto**: seguridad | S2 (formato minisign) → S3 + S4 → S5 con Fable → S7 (guía de firma) | **Fable 5.2** (o Opus 5.5 con esfuerzo alto) | Un error criptográfico es invisible en las pruebas normales; es donde más rinde el mejor modelo. |
| **PR2-A** fidelidad PDF, huella, matriz de cifrado | Alto | S2 (pikepdf, pyHanko, veraPDF) → S3 + S4 (fixtures adversariales) → S5 | **Opus 5.5** | Muchos casos borde de formato PDF. |
| **PR2-B** política "sin mejora", lock de dependencias | Medio | S1 → S3 + S4 → S6 | **Sonnet 5.5** | Lógica simple; el lock requiere probar en 3 plataformas, lo que hace el CI. |
| **PR3-B** spike del instalador (no integrable) | Exploratorio | S2 → S8 → informe | **Fable 5.2** | Diseño con muchas incógnitas: cortes de energía, rollback, Gatekeeper. |
| **PR3-C** instalador definitivo | **Muy alto** | S3 + S4 → S5 con Fable → pruebas manuales tuyas | **Fable 5.2** | Si falla, la app queda rota en la máquina del usuario. |

---

## 5. Perfiles: elige uno

| Perfil | Implementadores | Revisor S5 | Resto | Consumo estimado* | Cuándo elegirlo |
|---|---|---|---|---|---|
| `[ ]` **A. Económico** | Sonnet 5.5 en todo | Sonnet 5.5 | Haiku 5.5 | 1× | Límites de uso ajustados; se compensa con más rondas de Codex |
| `[ ]` **B. Equilibrado** *(recomendado)* | Lo de la sección 4: Sonnet en lo simple, Opus en lo delicado, Fable en seguridad e instalador | Opus 5.5 (Fable en PR3) | Haiku/Sonnet según la tabla 3 | ≈ 2–3× | Calidad alta donde importa, sin gastar de más en lo mecánico |
| `[ ]` **C. Máxima calidad** | Fable 5.2 en todo | Fable 5.2 | Opus 5.5 | ≈ 6–8× | Cuando el presupuesto no es problema y prima la seguridad |

\*Estimación relativa al perfil A, a partir de la tabla de precios y del número de tokens de un PR típico. No es una medición; se puede medir después del primer PR.

---

## 6. Flujo de cada PR con subagentes

```
            ┌──────────────── Orquestador (Opus 5.5) ─────────────────┐
            │                                                           │
  S1 Explorar ─► S2 Investigar ─► ┌─ S3 Implementar (worktree A) ─┐     │
  (Haiku)        (Sonnet)         │                               ├─► Integra y ejecuta las pruebas
                                  └─ S4 Pruebas desde la spec ────┘     │   (tests de S4 contra el código de S3)
                                     (worktree B, en paralelo)          │
                                                                        ▼
                         S5 Revisión adversarial ─► correcciones ─► draft PR ─► CI 3 SO
                                                                        │   (S6 lee los logs si falla)
                                                                        ▼
                                                   Codex audita ─► el orquestador corrige ─► tú decides el merge
```

**Puertas obligatorias** (iguales en todos los perfiles):
1. Las pruebas de S4 se ejecutan **contra `main`** y deben fallar en los casos de regresión, y contra el PR, donde deben pasar.
2. El orquestador lee el diff completo de S3 antes de integrarlo; nada se acepta "porque el subagente dijo que funciona".
3. CI en verde en Ubuntu, Windows y macOS.
4. S5 sin hallazgos P0 o P1 abiertos.
5. Auditoría de Codex sobre el SHA final.
6. Merge y release solo con tu autorización.

---

## 7. Paralelismo y ramas: decisión del propietario

PR1-B y PR1-C modifican archivos que también cambió PR1-A (`compresor_video.py`, `compresor_pdf.py`, `app.py`). Hay tres formas de avanzar:

| Opción | Cómo | Ventaja | Riesgo |
|---|---|---|---|
| `[ ]` **1. Secuencial** | Esperar a que PR1-A se integre en `main` y empezar entonces PR1-B | Lo más simple de auditar; respeta "desde `main` actualizado" | Más lento: depende del ritmo de Codex y de tus merges |
| `[ ]` **2. Apilado** *(recomendado)* | PR1-B sale de la rama de PR1-A; su PR muestra solo su propio diff. Al integrarse PR1-A, se actualiza la base | Avanza ya sin conflictos y Codex sigue viendo diffs pequeños | Si Codex pide cambios en PR1-A, hay que llevarlos también a PR1-B |
| `[ ]` **3. Paralelo** | PR1-B (apilado) y **PR3-A** (desde `main`, casi sin archivos en común) al mismo tiempo, en worktrees separados | Lo más rápido | Dos PR abiertos a la vez que auditar; más consumo simultáneo |

PR1-C, PR2 y PR3-B/C quedan en orden secuencial en cualquier opción.

---

## 8. Límites y salvaguardas

- **Máximo 4 subagentes simultáneos** por PR, para controlar el consumo y la carga de revisión.
- Los subagentes **no** hacen push, merge, releases, cambios en `main` ni en la configuración de GitHub. Solo el orquestador hace push a ramas `feature/*` y abre draft PR.
- Ningún subagente maneja **claves de firma**. En el PR3-A, la firma la haces tú con minisign, sin red (plan consensuado).
- Muestras de prueba siempre **sintéticas**, nunca archivos personales.
- Si un subagente vuelve con algo dudoso, el orquestador lo descarta o lo repite; no se "arregla a mano" sin entender la causa.
- **Workflows** (orquestación automática de muchos agentes): no se usan salvo que lo pidas explícitamente ("usa un workflow"). Con este plan bastan subagentes individuales.

---

## 9. Decisiones que necesito del propietario

1. **Perfil:** A, **B (recomendado)** o C.
2. **Ramas:** 1, **2 (recomendado)** o 3.
3. **Fable:** ¿5.2 (recomendado, más nuevo y más barato) o mantienes 5.1?
4. **Arranque:** ¿empiezo el PR1-B con el perfil y la opción de ramas elegidos?
5. Recordatorio pendiente: la **Fase 0** (2FA, proteger `main`, releases inmutables) sigue siendo necesaria antes de la v1.2.0.

ESTADO: PROPUESTA DE EJECUCIÓN — ESPERANDO ELECCIÓN DEL PROPIETARIO
