# SPIKE PR3-B: instalador seguro de actualizaciones (prototipo, NO integrable)

Codigo: `spike/instalador/instalador.py`; pruebas: `spike/instalador/test_instalador.py`.
No toca `actualizador.py`, `app.py` ni nada de la app. Nota: `docs/CLAUDE_RESPUESTA_2.md` y
`docs/CLAUDE_RESPUESTA_3.md` no existen en la rama w-spike (2400d93); el diseno sigue el
encargo recibido.

## Diseno

1. El paquete ya verificado (`verificacion`) se extrae a una carpeta temporal A.
2. Se lanza el binario de A: `--instalar-sobre <ruta> --pid <n> --nonce <hex>`.
3. A espera la muerte del PID comparando tambien la hora de inicio (PID reutilizado = original muerto).
4. A COPIA (nunca mueve) su arbol a `<ruta>.nueva` (mismo volumen, `symlinks=True`), fsync de ficheros y escribe
   dentro la marca `.cf_instalacion` con el nonce. Antes comprueba espacio libre (1,1x) y permisos del padre.
5. Journal en un directorio de estado fuera de la app: tmp + fsync + `os.replace` + fsync del directorio.
   Pasos: iniciado, copiando, copiado, intercambiando, anterior_movida, intercambiado, lanzada,
   confirmada | revirtiendo, terminado.
6. Intercambio: macOS `renamex_np(RENAME_SWAP)` (atomico; el viejo queda en `.nueva`); Windows/Linux
   `rename(ruta, .anterior)` + `rename(.nueva, ruta)` (hay un hueco de milisegundos, cubierto por la recuperacion).
7. Se lanza la nueva con `CF_NONCE` y `CF_SALUD_DIR`; se espera (timeout configurable) un JSON
   `{nonce, version, ruta_exe, pid}` en el directorio creado por A. Se valida nonce, version, `realpath(ruta_exe)`
   igual al exe esperado y pid del proceso lanzado.
8. Sin salud, proceso muerto o no arranca: rollback (`ruta -> .fallida`, viejo -> `ruta`) y se relanza la anterior.
9. `--recuperar` lee el journal: si la nueva esta activa y hay salud valida confirma; si no, revierte. Es
   idempotente y garantiza que `<ruta>` exista (ultimo recurso: `.anterior`/`.fallida`). Decide quien es quien
   con la marca del nonce, asi que no depende de en que paso exacto se corto.
10. Windows: `registrar_runonce()` escribe `HKCU\...\RunOnce` apuntando a la copia de A con `--recuperar`
    (solo se ejecuta en win32; probada con un `winreg` falso). La copia de A debe persistir hasta `terminado`.

Todo lo no portable se inyecta: `lanzar`, `esperar`, `ahora`, `dormir`, `swap`, `rename`, `copiar`, `libre`,
`escribible` y `hook(paso)` (los tests lanzan `Corte(BaseException)` para simular kill/corte de energia).

## Resultados en Linux

`python3 -m pytest -q spike/instalador`: 47 passed, codigo 0. `ruff check --select F,E9 spike`: limpio.
Cubierto: camino feliz (dos renames y swap simulado); corte tras CADA paso (10 pasos x salud ok/nada, con
`--recuperar` doble); cortes con swap; hueco entre renames (la ruta realmente no existe y la recuperacion la
restaura); corte tras lanzar con salud valida (confirma); sin espacio y ENOSPC a mitad de copia; sin permisos
en el padre y PermissionError en rename 1 y 2; nueva sin salud / muerta / nonce incorrecto / version incorrecta /
exe ajeno / no arranca; PID reutilizado y PID vivo con timeout; PID real muerto; journal atomico.
Invariante verificada en todos: tras la operacion o `--recuperar`, `<ruta>` es una version completa (1.0 o 2.0),
sin restos `.nueva/.anterior/.fallida`.

## NO se pudo probar (honestamente)

- `renamex_np` real (solo se simulo el swap con 3 renames), `winreg`/RunOnce real, rutas Windows, antivirus,
  OneDrive, UAC. Ningun test se ejecuto en Windows ni macOS.
- Corte de energia real: se simula con excepcion tras el journal, no se prueba la durabilidad real de fsync
  (cache de disco, SSD) ni el orden de escritura del sistema de ficheros.
- Permisos reales (los tests corren como root, por eso se inyecta `escribible`). Hora de inicio de PID en
  Windows/macOS requiere `psutil` (no verificado). Firma/notarizacion de la copia en `.nueva`.
- Bloqueo de ficheros en Windows: `rename` de una carpeta con exe/DLL abiertos falla; sin probar.

## Matriz de pruebas manuales pendientes

Procedimiento comun: instalar 1.0, publicar 2.0 en un servidor local, actualizar. Escenarios por celda:
(a) feliz, (b) matar el instalador entre renames (kill -9 / apagado duro) y reiniciar, (c) nueva version que
no escribe salud, (d) disco casi lleno.

| Plataforma / condicion | Prueba | Criterio de aceptacion |
|---|---|---|
| Win11, usuario con nombre no ASCII (p. ej. `C:\Users\Ñandú`) | a, b, c; RunOnce con ruta no ASCII | Queda 2.0 (a) o 1.0 (b, c) completa; RunOnce ejecuta `--recuperar` al siguiente inicio de sesion y se auto-borra; sin errores de codificacion en journal ni argumentos |
| Win11 + Defender activo | a con analisis en tiempo real | Los dos renames se completan sin `PermissionError` persistente (hay que anadir reintentos, ver abajo); sin deteccion falsa del instalador; tiempo de copia aceptable |
| Win11, instalacion dentro de OneDrive | a, b | Sin bloqueos de sincronizacion que rompan el rename; ninguna carpeta `.nueva/.anterior` subida/duplicada como conflicto; si falla, rollback limpio. Si no cumple: modo manual |
| Win11, `Program Files` sin permisos (usuario estandar) | a | Detecta falta de permisos ANTES de tocar nada y deriva a descarga manual/elevacion; la instalacion 1.0 queda intacta |
| macOS arm64 y Intel, `/Applications` (usuario admin y estandar) | a, b, c | Swap atomico: nunca falta la ruta; la nueva abre sin dialogo de Gatekeeper; `codesign --verify --deep --strict` pasa sobre la copia; estandar sin permisos -> modo manual |
| macOS, app en `~/Downloads` con App Translocation | a | Detecta ruta translocada (`/private/var/folders/.../AppTranslocation/`), no intenta intercambiar sobre ella y pide mover la app a /Applications |
| macOS, cuarentena (`com.apple.quarantine`) | a con paquete descargado | La copia no hereda cuarentena ni la anade; `spctl --assess` acepta la nueva; si Gatekeeper bloquea el lanzamiento, no hay salud y se hace rollback correcto |
| macOS, apagado duro entre pasos | b | `--recuperar` (lanzado al abrir la app o por LaunchAgent) deja 1.0 o 2.0 completa |

## Recomendacion

- Podrian pasar a PR3-C tras la matriz: macOS en `/Applications` (swap atomico, mejor garantia) y Windows
  con instalacion por usuario fuera de OneDrive y con ruta no ASCII validada. En Windows anadir reintentos con
  backoff en los renames (Defender/indexador).
- Quedarian en modo manual (descarga + aviso): Windows en `Program Files` sin permisos, instalaciones en
  OneDrive hasta validarlas, macOS con App Translocation o sin permiso de escritura en `/Applications`,
  y Linux (no es plataforma objetivo del instalador).
- Pendiente de decidir antes de integrar: donde vive A durante la recuperacion en Windows y quien lanza
  `--recuperar` en macOS (al abrir la app o LaunchAgent).
