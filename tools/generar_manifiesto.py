"""Genera manifest.json y las notas de la release a partir de los paquetes compilados.

    python tools/generar_manifiesto.py --version 1.2.0 --assets descargas --commit <sha>

Calcula SHA-256 y tamanos (y el tamano expandido del zip), toma las notas del bloque
`## X.Y.Z` de CHANGELOG.md (falla si no existe) y escribe `<assets>/manifest.json`
(validado con verificacion.cargar_manifiesto, igual que lo hace la app) y
`notas_release.md`. No firma nada: la firma con minisign es opcional y posterior
(docs/GUIA_FIRMA.md).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import verificacion  # noqa: E402


class ErrorManifiesto(Exception):
    pass


def extraer_notas(changelog, version):
    """Texto del bloque `## version[ - fecha]` hasta el siguiente `## `.

    Una pre-release sin bloque propio (1.3.0-rc.1) usa el de su version final."""
    candidatas = [version]
    if "-" in version:
        candidatas.append(version.split("-")[0])
    lineas = changelog.splitlines()
    for candidata in candidatas:
        patron = re.compile(r"##\s+" + re.escape(candidata) + r"(\s+-\s+.*)?\s*")
        for i, linea in enumerate(lineas):
            if patron.fullmatch(linea):
                cuerpo = []
                for sig in lineas[i + 1:]:
                    if sig.startswith("## "):
                        break
                    cuerpo.append(sig)
                texto = "\n".join(cuerpo).strip()
                if texto:
                    return texto
                raise ErrorManifiesto(f"el bloque de {candidata} en CHANGELOG.md esta vacio")
    raise ErrorManifiesto(f"CHANGELOG.md no tiene un bloque '## {version}'")


def describir_asset(ruta, version, os_, arch, formato):
    h = hashlib.sha256()
    tamano = 0
    with open(ruta, "rb") as f:
        while bloque := f.read(1024 * 1024):
            h.update(bloque)
            tamano += len(bloque)
    expandido = tamano
    if formato == "zip":
        try:
            with zipfile.ZipFile(ruta) as z:
                expandido = max(tamano, sum(e.file_size for e in z.infolist()))
        except zipfile.BadZipFile as e:
            raise ErrorManifiesto(f"{os.path.basename(ruta)}: zip invalido ({e})") from None
    asset = {"os": os_, "arch": arch, "formato": formato,
             "nombre": verificacion.nombre_asset(version, os_, arch, formato),
             "sha256": h.hexdigest(), "tamano": tamano, "tamano_expandido_max": expandido}
    if formato == "zip":
        try:
            verificacion.validar_zip(ruta, asset)
        except verificacion.VerificacionFallida as e:
            raise ErrorManifiesto(f"{asset['nombre']}: {e}") from None
    return asset


def generar(version, carpeta_assets, commit, changelog, creado=None):
    """Devuelve (bytes del manifiesto, notas). Lanza ErrorManifiesto si algo no cuadra."""
    if not verificacion.es_semver(version):
        raise ErrorManifiesto(f"version no valida: {version!r}")
    notas = extraer_notas(changelog, version)
    esperados = {verificacion.nombre_asset(version, *a) for a in verificacion.ASSETS_ESPERADOS}
    presentes = set(os.listdir(carpeta_assets)) - {"manifest.json", "manifest.json.minisig"}
    if presentes != esperados:
        raise ErrorManifiesto("paquetes inesperados: "
                              f"{sorted(presentes ^ esperados)} (esperados {sorted(esperados)})")
    assets = [describir_asset(os.path.join(carpeta_assets, verificacion.nombre_asset(version, *a)),
                              version, *a) for a in verificacion.ASSETS_ESPERADOS]
    creado = creado or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifiesto = {"schema": 1, "app": "Compresorfree", "canal": "estable", "tipo": "release",
                  "version": version, "tag": f"v{version}", "commit": commit, "creado": creado,
                  "assets": assets, "notas": notas}
    datos = (json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False)
             + "\n").encode("utf-8")
    try:
        verificacion.cargar_manifiesto(datos)  # la app debe poder leerlo
    except verificacion.VerificacionFallida as e:
        raise ErrorManifiesto(f"el manifiesto generado no es valido: {e}") from None
    return datos, notas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", required=True, help="ej. 1.2.0 (sin v; admite -rc.1)")
    ap.add_argument("--assets", required=True, help="carpeta con los paquetes")
    ap.add_argument("--commit", required=True, help="SHA completo del commit compilado")
    ap.add_argument("--changelog", default=os.path.join(RAIZ, "CHANGELOG.md"))
    ap.add_argument("--notas", default="notas_release.md", help="donde escribir las notas")
    args = ap.parse_args()
    try:
        with open(args.changelog, encoding="utf-8") as f:
            changelog = f.read()
        datos, notas = generar(args.version.removeprefix("v"), args.assets, args.commit, changelog)
    except (ErrorManifiesto, OSError) as e:
        sys.exit(f"ERROR: {e}")
    with open(os.path.join(args.assets, "manifest.json"), "wb") as f:
        f.write(datos)
    with open(args.notas, "w", encoding="utf-8", newline="\n") as f:
        f.write(notas + "\n")
    print(f"manifest.json y {args.notas} escritos para v{args.version.removeprefix('v')}")


if __name__ == "__main__":
    main()
