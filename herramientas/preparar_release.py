"""Descarga una release publicada y comprueba su manifiesto, para firmarlo (opcional).

    python herramientas/preparar_release.py vX.Y.Z [--repo Jonann17/Compresorfree]

GitHub Actions ya publica la release con su manifest.json. Esta herramienta descarga
los archivos a release-vX.Y.Z/, comprueba que son exactamente los esperados y que cada
paquete coincide con el manifiesto (tamano y SHA-256), y muestra el comando de minisign
para firmarlo sin red. No firma nada ni toca claves privadas.
Requiere el CLI de GitHub (gh) con la sesion iniciada.
"""

import argparse
import os

from _comun import (REPO, carpeta_release, fallar, gh, leer_version, nombres_esperados,
                    ver_release, verificacion)

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

    release = ver_release(version, args.repo)
    if release.get("isDraft"):
        fallar(f"v{version} es un borrador: publicala primero (Actions la publica sola).")
    if os.path.exists(carpeta) and os.listdir(carpeta):
        fallar(f"{carpeta}/ ya existe y no esta vacia. Borrala para empezar de cero.")

    print(f"Descargando v{version} a {carpeta}/ ...")
    gh("release", "download", f"v{version}", "--repo", args.repo, "--dir", carpeta)

    esperados = nombres_esperados(version) | {MANIFIESTO}
    encontrados = set(os.listdir(carpeta)) - {FIRMA}
    if encontrados != esperados:
        fallar("la release no tiene exactamente los archivos esperados.\n"
               f"  Esperados: {sorted(esperados)}\n  Encontrados: {sorted(encontrados)}")

    with open(os.path.join(carpeta, MANIFIESTO), "rb") as f:
        datos = f.read()
    try:
        manifiesto = verificacion.cargar_manifiesto(datos)
    except verificacion.VerificacionFallida as e:
        fallar(f"el manifiesto no es valido: {e}")
    if manifiesto["tipo"] != "release" or manifiesto["version"] != version:
        fallar(f"el manifiesto no es de la release v{version}")
    if {a["nombre"] for a in manifiesto["assets"]} != nombres_esperados(version):
        fallar("el manifiesto no lista exactamente los paquetes esperados")
    comprobar_paquetes(carpeta, manifiesto, "descargado")

    print(f"\nManifiesto de v{version} (commit {manifiesto['commit']}) correcto.")
    if os.path.exists(os.path.join(carpeta, FIRMA)):
        print("La release ya tiene firma (manifest.json.minisig).")
        return
    print("Para firmarlo (opcional), prueba antes los ejecutables y, SIN RED, ejecuta:\n")
    print(f'  minisign -S -s <ruta_usb>/principal.key -m {carpeta}/{MANIFIESTO} '
          f'-t "compresorfree tipo=release version={version}"')
    print(f"\nDespues sube la firma con:\n"
          f"  python herramientas/publicar_release.py --solo-firma v{version}")


if __name__ == "__main__":
    main()
