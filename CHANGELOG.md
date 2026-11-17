# Cambios de Compresorfree

Cada bloque `## X.Y.Z - AAAA-MM-DD` se usa como notas de la release y se muestra en el
aviso de actualizacion de la app. No cambies el formato del encabezado.

## 1.2.0 - 2026-11-17
- Seguridad de archivos: la salida nunca sobrescribe el original, se escribe en un archivo temporal y solo se renombra si la compresion termina bien; no se siguen enlaces simbolicos ni se aceptan rutas peligrosas.
- Cancelacion: se puede cancelar una compresion en curso (video y PDF) y no queda ningun archivo parcial.
- PDF: motor conservador por defecto (pikepdf) y compresion agresiva opcional con Ghostscript; si el resultado altera enlaces, formularios o adjuntos, se descarta.
- Firma de versiones: cada release lleva `manifest.json` con los SHA-256 de los paquetes; la firma con minisign es opcional y posterior.
- Experiencia: resultados claros por archivo, boton para abrir la carpeta de salida, preferencias recordadas, arrastrar y soltar y avisos cuando falta una dependencia.
- Tamano objetivo: se puede pedir un tamano maximo de salida y la app ajusta la compresion para acercarse.
- Actualizaciones: nuevo instalador de Windows (`Compresorfree-Setup-X.Y.Z.exe`), notas de cada version y publicacion automatica de la release desde GitHub Actions.

## 1.1.0 - 2026-11-09
- Compresion de PDF con pikepdf y Pillow.
- Aviso de nueva version al abrir la app y con el boton Buscar actualizaciones.

## 1.0.0 - 2026-10-26
- Primera version: compresion de video a MP4 (H.264 + AAC) con FFmpeg incluido, para Windows y macOS.
