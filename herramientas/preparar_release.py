"""Prepara el manifiesto de una release en borrador para firmarlo sin red.

    python herramientas/preparar_release.py vX.Y.Z [--repo Jonann17/Compresorfree]

Descarga los paquetes del borrador a release-vX.Y.Z/, calcula sus hashes y escribe
release-vX.Y.Z/manifest.json. No firma nada ni toca claves privadas: al final
muestra el comando de minisign que hay que ejecutar en el equipo de firma.
Requiere el CLI de GitHub (gh) con la sesion iniciada.
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import zipfile

from _comun import (REPO, carpeta_release, commit_de_release, fallar, gh, leer_version,
                    nombres_esperados, ver_release, verificacion)


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
            fallar(f"{os.path.basename(ruta)}: zip invalido ({e})")
    asset = {"os": os_, "arch": arch, "formato": formato,
             "nombre": verificacion.nombre_asset(version, os_, arch, formato),
             "sha256": h.hexdigest(), "tamano": tamano, "tamano_expandido_max": expandido}
    if formato == "zip":
        try:
            verificacion.validar_zip(ruta, asset)
        except verificacion.VerificacionFallida as e:
            fallar(f"{asset['nombre']}: {e}")
    return asset


def commits_de_workflows(version, repo, commit):
    """Commits que tocaron .github/workflows/ desde la ultima release publicada."""
    salida = gh("release", "view", "--repo", repo, "--json", "tagName", opcional=True)
    if not salida:
        print("  (no hay una release publicada anterior)")
        return
    anterior = json.loads(salida)["tagName"]
    try:
        r = subprocess.run(["git", "log", "--oneline", f"{anterior}..{commit}", "--",
                            ".github/workflows/"], capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        r = None
    if r is None or r.returncode != 0:
        print(f"  No se pudo ejecutar git log {anterior}..{commit[:12]}. Ejecuta 'git fetch --tags' "
              "en tu copia del repositorio y revisalo a mano.")
        return
    print(f"Commits que cambiaron .github/workflows/ desde {anterior} (revisalos):")
    print("\n".join("  " + linea for linea in r.stdout.splitlines()) or "  (ninguno)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="version de la release, ej. v1.2.0")
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()
    version = leer_version(args.version)
    carpeta = carpeta_release(version)

    release = ver_release(version, args.repo)
    if not release.get("isDraft"):
        fallar(f"v{version} no es un borrador: ya esta publicada.")
    if os.path.exists(carpeta) and os.listdir(carpeta):
        fallar(f"{carpeta}/ ya existe y no esta vacia. Borrala para empezar de cero.")

    print(f"Descargando los paquetes del borrador v{version} a {carpeta}/ ...")
    gh("release", "download", f"v{version}", "--repo", args.repo, "--dir", carpeta)

    esperados = nombres_esperados(version)
    encontrados = set(os.listdir(carpeta))
    if encontrados != esperados:
        fallar("el borrador no tiene exactamente los paquetes esperados.\n"
               f"  Esperados: {sorted(esperados)}\n  Encontrados: {sorted(encontrados)}")

    assets = [describir_asset(os.path.join(carpeta, verificacion.nombre_asset(version, *a)),
                              version, *a) for a in verificacion.ASSETS_ESPERADOS]
    commit = commit_de_release(version, args.repo, release)
    manifiesto = {
        "schema": 1, "app": "Compresorfree", "canal": "estable", "tipo": "release",
        "version": version, "tag": f"v{version}", "commit": commit,
        "creado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assets": assets,
    }
    datos = (json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    verificacion.cargar_manifiesto(datos)  # el cliente debe poder leerlo
    ruta = os.path.join(carpeta, "manifest.json")
    with open(ruta, "wb") as f:
        f.write(datos)

    print(f"\nManifiesto escrito en {ruta}")
    print(f"  version {version}, commit {commit}")
    for a in assets:
        print(f"  {a['nombre']}\n    sha256 {a['sha256']}\n    {a['tamano']} bytes "
              f"(expandido max. {a['tamano_expandido_max']})")
    print()
    commits_de_workflows(version, args.repo, commit)
    print("\nCopia la carpeta al equipo de firma y, SIN CONEXION A LA RED, ejecuta:\n")
    print(f'  minisign -S -s <ruta_usb>/principal.key -m {carpeta}/manifest.json '
          f'-t "compresorfree tipo=release version={version}"')
    print(f"\nDespues trae {carpeta}/manifest.json.minisig y ejecuta:\n"
          f"  python herramientas/publicar_release.py v{version}")


if __name__ == "__main__":
    main()
