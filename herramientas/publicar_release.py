"""Verifica la firma del manifiesto y publica la release en borrador.

    python herramientas/publicar_release.py vX.Y.Z [--repo Jonann17/Compresorfree]

Necesita release-vX.Y.Z/manifest.json y release-vX.Y.Z/manifest.json.minisig
(creados con preparar_release.py y firmados sin red). Antes de subir nada:
verifica la firma con las claves de claves_confianza.py, compara el manifiesto con
los paquetes locales y con los del borrador en GitHub (descargados de nuevo).
Requiere el CLI de GitHub (gh) con la sesion iniciada.
"""

import argparse
import os
import tempfile

from _comun import (REPO, carpeta_release, commit_de_release, fallar, gh, leer_version,
                    nombres_esperados, ver_release, verificacion)

import claves_confianza  # noqa: E402  (la raiz del repo la anade _comun a sys.path)

MANIFIESTO = "manifest.json"
FIRMA = "manifest.json.minisig"


def comprobar_paquetes(carpeta, manifiesto, que):
    for asset in manifiesto["assets"]:
        ruta = os.path.join(carpeta, asset["nombre"])
        if not os.path.isfile(ruta):
            fallar(f"falta {asset['nombre']} ({que})")
        try:
            verificacion.verificar_archivo(ruta, asset)
        except verificacion.VerificacionFallida as e:
            fallar(f"{asset['nombre']} ({que}): {e}")
        print(f"  OK {asset['nombre']} ({que})")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="version de la release, ej. v1.2.0")
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()
    version = leer_version(args.version)
    carpeta = carpeta_release(version)
    ruta_manifiesto = os.path.join(carpeta, MANIFIESTO)
    ruta_firma = os.path.join(carpeta, FIRMA)
    for ruta in (ruta_manifiesto, ruta_firma):
        if not os.path.isfile(ruta):
            fallar(f"falta {ruta}")

    with open(ruta_manifiesto, "rb") as f:
        datos = f.read()
    with open(ruta_firma, "rb") as f:
        firma = f.read()
    try:
        manifiesto = verificacion.verificar_manifiesto(datos, firma, claves_confianza.CLAVES)
    except verificacion.VerificacionFallida as e:
        motivo = str(e)
        if not claves_confianza.CLAVES:
            motivo += ". Anade antes tu clave publica a claves_confianza.py (docs/GUIA_FIRMA.md)"
        fallar(f"la firma del manifiesto no es valida: {motivo}. No se ha subido nada.")
    print("Firma del manifiesto valida.")
    if manifiesto["tipo"] != "release" or manifiesto["version"] != version:
        fallar(f"el manifiesto no es de la release v{version}")
    if {a["nombre"] for a in manifiesto["assets"]} != nombres_esperados(version):
        fallar("el manifiesto no lista exactamente los paquetes esperados")

    release = ver_release(version, args.repo)
    if not release.get("isDraft"):
        fallar(f"v{version} no es un borrador: ya esta publicada.")
    if commit_de_release(version, args.repo, release) != manifiesto["commit"]:
        fallar("el commit del borrador no coincide con el del manifiesto")
    en_github = {a["name"] for a in release.get("assets", [])}
    if not en_github <= nombres_esperados(version) | {MANIFIESTO, FIRMA}:
        fallar(f"el borrador tiene archivos inesperados: {sorted(en_github)}")

    comprobar_paquetes(carpeta, manifiesto, "local")
    with tempfile.TemporaryDirectory(prefix="compresorfree_publicar_") as tmp:
        for nombre in sorted(nombres_esperados(version)):
            gh("release", "download", f"v{version}", "--repo", args.repo, "--dir", tmp,
               "--pattern", nombre)
        comprobar_paquetes(tmp, manifiesto, "borrador en GitHub")

    print("Subiendo el manifiesto y su firma...")
    gh("release", "upload", f"v{version}", "--repo", args.repo, "--clobber",
       ruta_manifiesto, ruta_firma)
    print("Publicando la release...")
    gh("release", "edit", f"v{version}", "--repo", args.repo, "--draft=false")
    print(f"Release v{version} publicada.")


if __name__ == "__main__":
    main()
