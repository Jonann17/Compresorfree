"""Compresor de archivos: video (a MP4) y PDF, con niveles baja/media/alta.

Uso:
    python app.py                               -> abre la interfaz grafica
    python app.py archivo.mkv -n alta [-o salida.mp4]
    python app.py video1.avi video2.mov video3.mkv -n media [-d carpeta_salida]
    python app.py video1.avi documento.pdf -n alta --estimar   -> solo peso estimado
    python app.py documento.pdf -n media [-o salida.pdf]
"""

import argparse
import os
import sys
import threading

import actualizador
import compresor_pdf
import compresor_video
import nucleo
from compresor_video import resumen
from version import VERSION

TIPOS = {
    "video": {
        "nombre": "Video (a MP4)",
        "modulo": compresor_video,
        "filtro": [("Videos", compresor_video.EXTENSIONES_VIDEO)],
        "extension": ".mp4",
    },
    "pdf": {
        "nombre": "PDF",
        "modulo": compresor_pdf,
        "filtro": [("PDF", "*.pdf")],
        "extension": ".pdf",
    },
}

DESCRIPCION_NIVELES = {
    "baja": "Baja compresion (alta calidad, archivo mas grande)",
    "media": "Compresion media (equilibrio calidad/tamano)",
    "alta": "Alta compresion (archivo pequeno, menor calidad)",
}


def tipo_por_extension(ruta):
    return "pdf" if ruta.lower().endswith(".pdf") else "video"


def rutas_salida(entradas, tipo, nivel, carpeta=None):
    """Ruta de salida para cada archivo: junto al original o en `carpeta`.
    Nunca coincide con una entrada del lote, con otra salida ni con un archivo
    existente: ante conflicto agrega (2), (3)..."""
    modulo = TIPOS[tipo]["modulo"]
    return nucleo.planificar_lote(
        entradas, lambda e: modulo.ruta_salida_por_defecto(e, nivel), carpeta)


# ---------------------------------------------------------------- Interfaz grafica

def iniciar_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    ventana = tk.Tk()
    ventana.title(f"Compresorfree {VERSION}")
    ventana.resizable(False, False)

    var_tipo = tk.StringVar(value="video")
    var_carpeta = tk.StringVar()  # vacio = junto a cada original
    var_nivel = tk.StringVar(value="media")
    var_estado = tk.StringVar(value="Elige el tipo de archivo y agrega uno o varios.")
    cancelar = threading.Event()
    archivos = {}  # id de fila de la lista -> ruta completa

    marco = ttk.Frame(ventana, padding=12)
    marco.grid()

    def en_ui(funcion, *args):
        ventana.after(0, lambda: funcion(*args))

    def poner_estado_fila(fila, texto):
        lista.set(fila, "estado", texto)

    def cambiar_tipo():
        limpiar()
        var_estado.set(f"Agrega archivos: {TIPOS[var_tipo.get()]['nombre']}.")

    def agregar():
        tipo = TIPOS[var_tipo.get()]
        rutas = filedialog.askopenfilenames(
            title="Seleccionar archivos (puedes elegir varios)",
            filetypes=tipo["filtro"] + [("Todos los archivos", "*.*")],
        )
        existentes = set(archivos.values())
        for ruta in rutas:
            if ruta not in existentes:
                existentes.add(ruta)
                tamano = compresor_video.tamano_legible(os.path.getsize(ruta))
                fila = lista.insert("", "end",
                                    values=(os.path.basename(ruta), tamano, "", "Pendiente"))
                archivos[fila] = ruta
        actualizar_contador()

    def quitar():
        for fila in lista.selection():
            lista.delete(fila)
            archivos.pop(fila, None)
        actualizar_contador()

    def limpiar():
        for fila in list(archivos):
            lista.delete(fila)
        archivos.clear()
        barra["value"] = 0
        actualizar_contador()

    def actualizar_contador():
        n = len(archivos)
        var_estado.set(f"{n} archivo(s) en la lista." if n else
                       "Agrega uno o varios archivos.")

    def elegir_carpeta():
        ruta = filedialog.askdirectory(title="Carpeta donde guardar los archivos comprimidos")
        if ruta:
            var_carpeta.set(ruta)
            etiqueta_carpeta.config(text=ruta)

    def carpeta_original():
        var_carpeta.set("")
        etiqueta_carpeta.config(text="Junto a cada archivo original")

    grupo_tipo = ttk.LabelFrame(marco, text="Que quieres comprimir?", padding=8)
    grupo_tipo.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    radios_tipo = []
    for clave, tipo in TIPOS.items():
        r = ttk.Radiobutton(grupo_tipo, text=tipo["nombre"], value=clave,
                            variable=var_tipo, command=cambiar_tipo)
        r.pack(side="left", padx=(0, 20))
        radios_tipo.append(r)

    ttk.Label(marco, text="Archivos a comprimir:").grid(row=1, column=0, sticky="w")
    marco_lista = ttk.Frame(marco)
    marco_lista.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
    lista = ttk.Treeview(marco_lista, columns=("archivo", "tamano", "estimado", "estado"),
                         show="headings", height=7, selectmode="extended")
    for col, titulo, ancho, alin in (("archivo", "Archivo", 185, "w"),
                                     ("tamano", "Tamano", 75, "e"),
                                     ("estimado", "Estimado", 85, "e"),
                                     ("estado", "Estado", 135, "w")):
        lista.heading(col, text=titulo)
        lista.column(col, width=ancho, anchor=alin)
    desplazar = ttk.Scrollbar(marco_lista, orient="vertical", command=lista.yview)
    lista.configure(yscrollcommand=desplazar.set)
    lista.pack(side="left", fill="both", expand=True)
    desplazar.pack(side="left", fill="y")

    botones_lista = ttk.Frame(marco)
    botones_lista.grid(row=2, column=1, sticky="n")
    btn_agregar = ttk.Button(botones_lista, text="Agregar...", command=agregar)
    btn_quitar = ttk.Button(botones_lista, text="Quitar", command=quitar)
    btn_limpiar = ttk.Button(botones_lista, text="Vaciar lista", command=limpiar)
    btn_estimar = ttk.Button(botones_lista, text="Estimar peso")
    for b in (btn_agregar, btn_quitar, btn_limpiar, btn_estimar):
        b.pack(fill="x", pady=(0, 4))

    ttk.Label(marco, text="Guardar en:").grid(row=3, column=0, sticky="w", pady=(10, 0))
    etiqueta_carpeta = ttk.Label(marco, text="Junto a cada archivo original",
                                 relief="sunken", padding=3, width=55)
    etiqueta_carpeta.grid(row=4, column=0, sticky="ew", padx=(0, 6))
    botones_carpeta = ttk.Frame(marco)
    botones_carpeta.grid(row=4, column=1)
    btn_carpeta = ttk.Button(botones_carpeta, text="Elegir carpeta...", command=elegir_carpeta)
    btn_original = ttk.Button(botones_carpeta, text="Junto al original", command=carpeta_original)
    btn_carpeta.pack(fill="x")
    btn_original.pack(fill="x", pady=(4, 0))

    grupo = ttk.LabelFrame(marco, text="Nivel de compresion", padding=8)
    grupo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
    radios_nivel = []
    for nombre, texto in DESCRIPCION_NIVELES.items():
        r = ttk.Radiobutton(grupo, text=texto, value=nombre, variable=var_nivel,
                            command=lambda: borrar_estimados())
        r.pack(anchor="w")
        radios_nivel.append(r)

    barra = ttk.Progressbar(marco, length=420, maximum=100)
    barra.grid(row=6, column=0, columnspan=2, sticky="ew")
    ttk.Label(marco, textvariable=var_estado).grid(row=7, column=0, columnspan=2, sticky="w", pady=4)

    btn_actualizar = ttk.Button(marco, text="Buscar actualizaciones")
    btn_actualizar.grid(row=8, column=0, sticky="w")

    botones = ttk.Frame(marco)
    botones.grid(row=8, column=0, columnspan=2, sticky="e")
    btn_comprimir = ttk.Button(botones, text="Comprimir")
    btn_cancelar = ttk.Button(botones, text="Cancelar", state="disabled",
                              command=cancelar.set)
    btn_comprimir.pack(side="left", padx=4)
    btn_cancelar.pack(side="left")

    # Controles que no se pueden tocar mientras se comprime
    bloqueables = [btn_agregar, btn_quitar, btn_limpiar, btn_estimar, btn_carpeta, btn_original,
                   btn_comprimir, btn_actualizar] + radios_tipo + radios_nivel

    def bloquear(si):
        for w in bloqueables:
            w.config(state="disabled" if si else "normal")
        btn_cancelar.config(state="normal" if si else "disabled")

    def al_terminar(resultados, omitidos, cancelado):
        bloquear(False)
        ok = [(e, s) for e, s, err in resultados if not err]
        fallidos = [(e, err) for e, s, err in resultados if err]
        antes = sum(os.path.getsize(e) for e, _ in ok)
        despues = sum(os.path.getsize(s) for _, s in ok)
        texto = f"Comprimidos: {len(ok)} de {len(archivos)}"
        if ok:
            reduccion = (1 - despues / antes) * 100 if antes else 0
            texto += (f"\n\nTotal original:   {compresor_video.tamano_legible(antes)}"
                      f"\nTotal comprimido: {compresor_video.tamano_legible(despues)}"
                      f"\nReduccion:        {reduccion:.1f}%")
        if fallidos:
            texto += "\n\nCon error:\n" + "\n".join(
                f"- {os.path.basename(e)}: {err.splitlines()[0]}" for e, err in fallidos[:10])
        if omitidos:
            texto += "\n\nOmitidos (el original queda intacto):\n" + "\n".join(
                f"- {os.path.basename(e)}: {motivo}" for e, motivo in omitidos[:10])
        if cancelado:
            var_estado.set("Cancelado.")
            messagebox.showwarning("Compresion cancelada", texto)
        else:
            var_estado.set("Listo." if not fallidos else "Terminado con errores.")
            barra["value"] = 100
            (messagebox.showwarning if fallidos else messagebox.showinfo)(
                "Compresion terminada", texto)

    def iniciar():
        if not archivos:
            messagebox.showwarning("Faltan archivos", "Agrega al menos un archivo.")
            return
        filas = list(lista.get_children())
        entradas = [archivos[f] for f in filas]
        tipo, nivel = var_tipo.get(), var_nivel.get()
        salidas = rutas_salida(entradas, tipo, nivel, var_carpeta.get() or None)
        modulo = TIPOS[tipo]["modulo"]
        total = len(filas)

        cancelar.clear()
        bloquear(True)
        barra["value"] = 0
        for f in filas:
            poner_estado_fila(f, "Pendiente")

        def trabajo():
            resultados, omitidos = [], []
            for i, (fila, entrada, salida) in enumerate(zip(filas, entradas, salidas)):
                if cancelar.is_set():
                    break
                nombre = os.path.basename(entrada)

                def progreso(p, i=i, fila=fila, nombre=nombre):
                    general = (i + p / 100) / total * 100
                    en_ui(lambda: (barra.configure(value=general),
                                   poner_estado_fila(fila, f"Comprimiendo {p:.0f}%"),
                                   var_estado.set(f"Archivo {i + 1} de {total}: {nombre}")))

                progreso(0)
                try:
                    out = modulo.comprimir(entrada, salida, nivel, progreso, cancelar,
                                           si_existe="renombrar")
                    antes, despues = os.path.getsize(entrada), os.path.getsize(out)
                    red = (1 - despues / antes) * 100 if antes else 0
                    en_ui(poner_estado_fila, fila, f"Listo (-{red:.0f}%)")
                    resultados.append((entrada, out, None))
                except nucleo.ArchivoOmitido as e:
                    en_ui(poner_estado_fila, fila, "Omitido")
                    omitidos.append((entrada, str(e)))
                except Exception as e:
                    msg = str(e)
                    if cancelar.is_set():
                        en_ui(poner_estado_fila, fila, "Cancelado")
                        break
                    en_ui(poner_estado_fila, fila, "Error")
                    resultados.append((entrada, None, msg))
            en_ui(al_terminar, resultados, omitidos, cancelar.is_set())

        threading.Thread(target=trabajo, daemon=True).start()

    btn_comprimir.config(command=iniciar)

    # ------------------------------------------------------------ Estimar peso final

    def borrar_estimados():
        # Al cambiar el nivel los estimados anteriores ya no sirven
        for fila in archivos:
            lista.set(fila, "estimado", "")
        actualizar_contador()

    def estimar():
        if not archivos:
            messagebox.showwarning("Faltan archivos", "Agrega al menos un archivo.")
            return
        filas = list(lista.get_children())
        modulo = TIPOS[var_tipo.get()]["modulo"]
        nivel = var_nivel.get()
        cancelar.clear()
        bloquear(True)
        barra["value"] = 0

        def trabajo():
            antes = despues = 0
            for i, fila in enumerate(filas):
                if cancelar.is_set():
                    break
                ruta = archivos[fila]
                en_ui(lambda i=i, ruta=ruta, fila=fila: (
                    lista.set(fila, "estimado", "calculando..."),
                    var_estado.set(f"Estimando {i + 1} de {len(filas)}: {os.path.basename(ruta)}")))
                omitido = False
                try:
                    bytes_ = modulo.estimar(ruta, nivel, cancelar)
                except nucleo.ArchivoOmitido:
                    bytes_, omitido = None, True
                except Exception:
                    bytes_ = None
                if omitido:
                    texto = "omitido"
                elif bytes_ is None:
                    texto = "" if cancelar.is_set() else "?"
                else:
                    antes += os.path.getsize(ruta)
                    despues += bytes_
                    texto = "~" + compresor_video.tamano_legible(bytes_)
                en_ui(lista.set, fila, "estimado", texto)
                en_ui(lambda p=(i + 1) / len(filas) * 100: barra.configure(value=p))

            def fin():
                bloquear(False)
                if cancelar.is_set():
                    var_estado.set("Estimacion cancelada.")
                elif antes:
                    red = (1 - despues / antes) * 100
                    var_estado.set(
                        f"Total: {compresor_video.tamano_legible(antes)} -> "
                        f"~{compresor_video.tamano_legible(despues)} estimado (-{red:.0f}%)")
                else:
                    var_estado.set("No se pudo estimar el peso.")
            en_ui(fin)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_estimar.config(command=estimar)

    # ------------------------------------------------------------ Actualizaciones

    def ofrecer_actualizacion(info, manual):
        btn_actualizar.config(state="normal")
        if info is None:
            if manual:
                messagebox.showinfo("Actualizaciones", f"Ya tienes la ultima version ({VERSION}).")
            return
        notas = f"\n\nNovedades:\n{info['notas'][:600]}" if info["notas"].strip() else ""
        if not actualizador.es_app_compilada() or not info["url"]:
            if messagebox.askyesno(
                    "Nueva version disponible",
                    f"Hay una version nueva: {info['version']} (tienes {VERSION}).{notas}"
                    "\n\nAbrir la pagina de descarga?"):
                import webbrowser
                webbrowser.open(actualizador.URL_RELEASES)
            return
        if messagebox.askyesno(
                "Nueva version disponible",
                f"Hay una version nueva: {info['version']} (tienes {VERSION}).{notas}"
                "\n\nDescargar e instalar ahora? La app se reiniciara."):
            instalar_actualizacion(info)

    def instalar_actualizacion(info):
        bloquear(True)
        btn_cancelar.config(state="disabled")
        var_estado.set("Descargando actualizacion...")

        def progreso(p):
            en_ui(lambda: (barra.configure(value=p),
                           var_estado.set(f"Descargando actualizacion... {p:.0f}%")))

        def trabajo():
            try:
                paquete = actualizador.descargar(info["url"], progreso)
                en_ui(var_estado.set, "Instalando actualizacion...")
                actualizador.instalar(paquete)
                en_ui(ventana.destroy)  # al cerrarse, el script copia la version nueva y la abre
            except Exception as e:
                msg = str(e)
                def fallo():
                    bloquear(False)
                    barra["value"] = 0
                    var_estado.set("No se pudo actualizar.")
                    messagebox.showerror("Error al actualizar", msg)
                en_ui(fallo)

        threading.Thread(target=trabajo, daemon=True).start()

    def buscar_actualizacion(manual=False):
        btn_actualizar.config(state="disabled")

        def trabajo():
            try:
                info = actualizador.buscar_actualizacion()
            except Exception as e:
                msg = str(e)
                def fallo():
                    btn_actualizar.config(state="normal")
                    if manual:
                        messagebox.showerror("Actualizaciones",
                                             f"No se pudo buscar actualizaciones:\n{msg}")
                en_ui(fallo)
                return
            en_ui(ofrecer_actualizacion, info, manual)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_actualizar.config(command=lambda: buscar_actualizacion(manual=True))
    ventana.after(1500, buscar_actualizacion)  # busca en silencio al abrir la app
    ventana.mainloop()


# ---------------------------------------------------------------- Linea de comandos

def main():
    parser = argparse.ArgumentParser(
        description="Comprime videos (a MP4) y PDF. Sin argumentos abre la interfaz grafica."
    )
    parser.add_argument("entradas", nargs="*", help="Uno o varios videos (cualquier formato) o PDF")
    parser.add_argument("-o", "--salida", help="Archivo de salida (solo con un archivo)")
    parser.add_argument("-d", "--carpeta", help="Carpeta donde guardar los archivos comprimidos")
    parser.add_argument("-e", "--estimar", action="store_true",
                        help="Solo muestra el peso final estimado, sin comprimir")
    parser.add_argument("-n", "--nivel", choices=list(DESCRIPCION_NIVELES), default="media",
                        help="Nivel de compresion (por defecto: media)")
    args = parser.parse_args()

    if not args.entradas:
        iniciar_gui()
        return
    if args.salida and len(args.entradas) > 1:
        parser.error("-o/--salida solo se puede usar con un archivo; usa -d/--carpeta")
    if args.estimar:
        for entrada in args.entradas:
            modulo = TIPOS[tipo_por_extension(entrada)]["modulo"]
            try:
                bytes_ = modulo.estimar(entrada, args.nivel)
            except nucleo.ArchivoOmitido as e:
                print(f"{entrada}: {e}", file=sys.stderr)
                continue
            except Exception as e:
                print(f"{entrada}: error ({e})", file=sys.stderr)
                continue
            estimado = "?" if bytes_ is None else "~" + compresor_video.tamano_legible(bytes_)
            print(f"{entrada}: {compresor_video.tamano_legible(os.path.getsize(entrada))}"
                  f" -> {estimado} (nivel {args.nivel})")
        return
    if args.salida and os.path.lexists(args.salida):
        print(f"Error: {args.salida} ya existe; no se sobrescribe. Elige otro nombre.",
              file=sys.stderr)
        sys.exit(1)
    if args.carpeta:
        os.makedirs(args.carpeta, exist_ok=True)

    def barra(p):
        llenos = int(p / 2.5)
        print(f"\r[{'#' * llenos}{'.' * (40 - llenos)}] {p:5.1f}%", end="", flush=True)

    errores = omitidos = 0
    total = len(args.entradas)
    # Se planifica todo el lote junto: ninguna salida puede caer sobre otra entrada.
    if args.salida:
        planes = [(args.entradas[0], args.salida, "error")]
    else:
        salidas = nucleo.planificar_lote(
            args.entradas,
            lambda e: TIPOS[tipo_por_extension(e)]["modulo"].ruta_salida_por_defecto(e, args.nivel),
            args.carpeta)
        planes = [(e, s, "renombrar") for e, s in zip(args.entradas, salidas)]
    for i, (entrada, salida, si_existe) in enumerate(planes, 1):
        modulo = TIPOS[tipo_por_extension(entrada)]["modulo"]
        if total > 1:
            print(f"[{i}/{total}] {entrada}")
        try:
            salida = modulo.comprimir(entrada, salida, args.nivel, barra, si_existe=si_existe)
        except KeyboardInterrupt:
            print("\nCancelado.")
            sys.exit(1)
        except nucleo.ArchivoOmitido as e:
            print(f"\n{e} El original queda intacto.", file=sys.stderr)
            omitidos += 1
            continue
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)
            errores += 1
            continue
        print(f"\nListo: {salida}\n{resumen(entrada, salida)}\n")
    if errores or omitidos:
        print(f"{errores} con error y {omitidos} omitido(s) de {total} archivo(s).",
              file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
