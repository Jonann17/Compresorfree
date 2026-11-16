"""Claves PUBLICAS minisign en las que confia la app para verificar releases.

Aqui solo van claves publicas (la segunda linea del archivo .pub de minisign).
Las claves privadas nunca se suben al repositorio ni a GitHub: se guardan sin
conexion, como explica docs/GUIA_FIRMA.md.

Cada entrada: {"id": "<id en hex mayusculas, como lo muestra minisign>",
               "rol": "principal" | "respaldo",
               "publica": "<linea base64 de la clave publica>"}
- principal: firma releases (tipo=release) y rotaciones de claves.
- respaldo: solo puede firmar rotaciones (tipo=rotacion).

Esta vacia hasta que el propietario genere sus claves y las anada en un PR.
Mientras este vacia, ninguna release se da por verificada.
"""

CLAVES = []
