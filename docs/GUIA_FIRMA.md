# Guía de firma de versiones (minisign, nivel L3)

Guía para el propietario de Compresorfree. No hace falta ser especialista: basta seguir los pasos en orden.

## 1. Qué es y por qué

Cada versión de Compresorfree lleva un archivo `manifest.json` (con los nombres, tamaños y huellas SHA-256 de los instaladores y las notas de la versión), que genera GitHub Actions al publicar. **La firma es opcional y posterior**: puedes firmar ese `manifest.json` con minisign y subir `manifest.json.minisig`. La app comprueba esa firma con tu **clave pública**, que va incluida en el código (`claves_confianza.py`). Sin firma (o sin claves en el código) la app sigue funcionando confiando en el SHA-256 publicado en el canal oficial de GitHub, pero no marca la versión como verificada; con claves configuradas, exige una firma válida para la autoinstalación.

Lo importante es dónde vive la clave **privada**: en un USB, nunca en GitHub ni en tu ordenador de forma permanente. Así, aunque alguien robe tu cuenta de GitHub, puede subir archivos pero **no puede firmarlos**, y la app lo detecta.

La firma protege frente a una cuenta de GitHub comprometida: quien la robe puede subir archivos, pero no firmarlos.

Qué es público y qué es secreto:

| Archivo | Naturaleza | Dónde va |
|---|---|---|
| `principal.pub`, `respaldo.pub` | Público | Se añade al repositorio por PR |
| `principal.key`, `respaldo.key` | **SECRETO** | Solo en su USB; jamás en GitHub, correo ni nube |
| Frase de paso | **SECRETA** | Tu memoria o un gestor de contraseñas (una distinta por clave) |

## 2. Instalar minisign

**Windows** (cualquiera de las dos):
- `scoop install minisign` o `winget install minisign`.
- Descarga oficial: <https://github.com/jedisct1/minisign/releases>. Baja el ZIP de Windows y comprueba su hash con `Get-FileHash minisign-*.zip -Algorithm SHA256`; debe coincidir con el publicado por el proyecto.

**macOS**: `brew install minisign`.

Comprueba con `minisign -v`.

## 3. Crear las claves (una sola vez)

Necesitas **dos USB distintos** y **dos frases de paso distintas**. Hazlo con el ordenador sin conexión si puedes.

```
minisign -G -p principal.pub -s principal.key   # USB 1
minisign -G -p respaldo.pub  -s respaldo.key    # USB 2
```

- **Principal**: firma las versiones (`tipo=release`) y también puede firmar cambios de claves.
- **Respaldo**: NO firma versiones. Solo sirve para cambiar de claves (manifiesto `tipo=rotacion`) si pierdes o te roban la principal.
- Guarda el USB de respaldo en un lugar físico distinto y seguro (cajón con llave, caja fuerte). Haz una copia de cada `.key` en un segundo USB si quieres.
- **Si pierdes una clave**: si es la principal, usa la de respaldo para emitir una rotación. Si se pierde la de respaldo, genera otra pareja y sustitúyela mediante una rotación firmada con la principal. Si pierdes ambas, hay que publicar una nueva versión de la app con claves nuevas y avisar a los usuarios por otro canal.

**Pasar las claves públicas al código.** Abre cada `.pub`: la 1.ª línea es un comentario (`untrusted comment: minisign public key <ID>`) y la 2.ª es la clave en base64. Con `minisign -G` el ID (hasta 16 caracteres hexadecimales en mayúsculas) también aparece en pantalla. minisign omite los ceros iniciales, así que a veces verás 15 o menos: cópialo tal cual, la app lo completa. Abre un PR que añada a `claves_confianza.py`:

```python
CLAVES = [
    {"id": "XXXXXXXXXXXXXXXX", "rol": "principal", "publica": "RWQ..."},
    {"id": "YYYYYYYYYYYYYYYY", "rol": "respaldo",  "publica": "RWQ..."},
]
```

**Nunca** añadas ni envíes archivos `.key`: solo las claves públicas.

## 4. Publicar y firmar una versión

**(a) Publicar.** Añade el bloque `## X.Y.Z - AAAA-MM-DD` a `CHANGELOG.md`. En GitHub: Actions, "Run workflow" (compilar), escribe la versión (por ejemplo `1.2.0`; con sufijo `-rc.1` y/o la casilla *prerelease* se marca como pre-release), o sube un tag `vX.Y.Z`. Se pasan las pruebas, se compila, se genera `manifest.json` y la release queda **publicada** con las notas del CHANGELOG. Ya es utilizable sin firma.

**(b) Preparar** (opcional, con internet; requiere `gh` con sesión iniciada: `gh auth status`):

```
python herramientas/preparar_release.py vX.Y.Z
```

Descarga la release a `release-vX.Y.Z/`, comprueba que contiene exactamente los archivos esperados y que cada paquete coincide con el manifiesto, e imprime el comando de firma.

**(c) Firmar sin red.** Prueba antes los ejecutables descargados. Luego:
1. Desconecta el Wi-Fi y el cable de red.
2. Inserta el USB de la clave principal.
3. Ejecuta (el comando exacto lo imprime el paso b):
   ```
   minisign -S -s <usb>/principal.key -m release-vX.Y.Z/manifest.json -t "compresorfree tipo=release version=X.Y.Z"
   ```
4. Introduce la frase de paso. Se crea `release-vX.Y.Z/manifest.json.minisig`.
5. Retira el USB.

**(d) Subir la firma.** Reconecta la red y ejecuta:

```
python herramientas/publicar_release.py --solo-firma vX.Y.Z
```

Verifica la firma con las claves de `claves_confianza.py`, comprueba que el `manifest.json` firmado es idéntico al publicado y solo entonces sube `manifest.json.minisig`. No modifica nada más de la release.

## 5. Lista de comprobación de seguridad

- Activa la verificación en dos pasos (2FA) en tu cuenta de GitHub, preferiblemente con llave de seguridad o app, no SMS.
- No ejecutes scripts del repositorio ni del `release-vX.Y.Z/` con el USB conectado; el USB solo se conecta para el comando `minisign -S`.
- Firma únicamente después de probar los ejecutables descargados y revisar los cambios en workflows.
- Firma siempre sin red y retira el USB al terminar.
- Nunca subas un `.key` a GitHub, correo, nube o chat; revisa `git status` antes de cada commit.
- Usa frases de paso largas y distintas para cada clave.
- Guarda el USB de respaldo separado del principal y no lo uses para firmar versiones.
- Comprueba que el comentario de firma (`-t`) coincide exactamente con tipo y versión; si no, la app lo rechaza.

## 6. Problemas frecuentes

- **`gh: command not found` o "not logged in"**: instala GitHub CLI y ejecuta `gh auth login`.
- **`preparar_release.py` dice que faltan o sobran assets**: la release debe tener exactamente los 4 paquetes (`Setup-X.Y.Z.exe`, `windows-x64.zip`, `macos-arm64.dmg`, `macos-x64.dmg`) y `manifest.json`. Vuelve a lanzar el workflow.
- **`publicar_release.py --solo-firma` rechaza la firma**: casi siempre es una versión o `-t` mal escritos, firmar con la clave de respaldo, o que `claves_confianza.py` no tenga aún tu clave pública. Rehaz el paso (c) y no modifiques `manifest.json` tras firmar. Si dice que no es idéntico al publicado, vuelve a ejecutar `preparar_release.py` con la carpeta vacía y firma ese archivo.
- **Olvidé la frase de paso**: no hay recuperación. Usa la clave de respaldo para rotar (ver sección 3).
- **La app muestra "no se pudo verificar su firma"**: la release se publicó sin firma (es opcional) o con una firma no válida o las claves de la app no coinciden. Comprueba que `manifest.json.minisig` está en la release y que el PR de claves está en la versión instalada.
