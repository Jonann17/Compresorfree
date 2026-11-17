"""Compresor de archivos: video (a MP4) y PDF, con niveles baja/media/alta.

Uso:
    python app.py                               -> abre la interfaz grafica
    python app.py archivo.mkv -n alta [-o salida.mp4]
    python app.py video1.avi video2.mov video3.mkv -n media [-d carpeta_salida]
    python app.py video1.avi documento.pdf -n alta --estimar   -> solo peso estimado
    python app.py documento.pdf -n media [-o salida.pdf]
"""

import argparse
import contextlib
import gc
import os
import queue
import sys
import subprocess
import threading
import time

import actualizador
import compresor_pdf
import compresor_video
import nucleo
import preferencias
import procesos
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
    """'pdf', 'video' o None si la extension no es compatible."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {e.lstrip("*").lower() for e in compresor_video.EXTENSIONES_VIDEO.split()}:
        return "video"
    return None


def filtrar_soltados(rutas, tipo, existentes=()):
    """Archivos soltados que valen para `tipo` ('video'/'pdf'): existen, son
    archivos, tienen la extension del tipo y no estan repetidos ni en `existentes`."""
    vistos = set(existentes)
    out = []
    for ruta in rutas:
        if ruta in vistos or not os.path.isfile(ruta):
            continue
        if tipo_por_extension(ruta) == tipo:
            vistos.add(ruta)
            out.append(ruta)
    return out


def abrir_carpeta(carpeta):
    """Abre `carpeta` en el explorador del sistema."""
    if sys.platform == "win32":
        os.startfile(carpeta)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", carpeta])
    else:
        subprocess.Popen(["xdg-open", carpeta])


def texto_resultado(antes, despues):
    """Estado de la fila al terminar: 'Listo (-59%)', '(+12%)' o '(sin cambio)'."""
    if not antes:
        return "Listo"
    red = (1 - despues / antes) * 100
    if abs(red) < 0.5:
        return "Listo (sin cambio)"
    return f"Listo (-{red:.0f}%)" if red > 0 else f"Listo (+{-red:.0f}%)"


def rutas_salida(entradas, tipo, nivel, carpeta=None):
    """Ruta de salida para cada archivo: junto al original o en `carpeta`.
    Nunca coincide con una entrada del lote, con otra salida ni con un archivo
    existente: ante conflicto agrega (2), (3)..."""
    modulo = TIPOS[tipo]["modulo"]
    return nucleo.planificar_lote(
        entradas, lambda e: modulo.ruta_salida_por_defecto(e, nivel), carpeta)


# ---------------------------------------------------------------- Interfaz grafica

def iniciar_gui():
    _iniciar_gui()
    # Al volver, los widgets y variables de Tk quedan en ciclos de referencias (los
    # cierres de _iniciar_gui). Se recolectan aqui, en el hilo principal: si los
    # recolectara un hilo de trabajo, Tcl abortaria el proceso (Tcl_AsyncDelete).
    gc.collect()


def _iniciar_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:  # arrastrar y soltar es opcional
        from tkinterdnd2 import DND_FILES, TkinterDnD
        ventana = TkinterDnD.Tk()
    except Exception:  # noqa: BLE001  (no instalado o plataforma sin soporte)
        DND_FILES = None
        ventana = tk.Tk()
    ventana.title(f"Compresorfree {VERSION}")
    ventana.resizable(False, False)

    prefs = preferencias.cargar()
    var_tipo = tk.StringVar(value=prefs["tipo"])
    var_carpeta = tk.StringVar(value=prefs["carpeta"])  # vacio = junto a cada original
    var_nivel = tk.StringVar(value=prefs["nivel"])
    ultima_carpeta = [None]  # carpeta del ultimo resultado
    var_estado = tk.StringVar(value="Elige el tipo de archivo y agrega uno o varios.")
    cancelar = threading.Event()
    archivos = {}  # id de fila de la lista -> ruta completa
    cola_ui = queue.Queue()
    hilo_tarea = None  # hilo de compresion o estimacion en curso
    cerrando = False

    marco = ttk.Frame(ventana, padding=12)
    marco.grid()

    def en_ui(funcion, *args):
        # Los hilos de trabajo nunca tocan Tk: encolan y el hilo principal ejecuta.
        cola_ui.put((funcion, args))

    def vaciar_cola_ui():
        try:
            while True:
                try:
                    funcion, args = cola_ui.get_nowait()
                except queue.Empty:
                    break
                if not cerrando:
                    funcion(*args)
        finally:
            with contextlib.suppress(tk.TclError):  # la ventana ya se destruyo
                ventana.after(50, vaciar_cola_ui)

    def tarea_en_curso():
        return hilo_tarea is not None and hilo_tarea.is_alive()

    def lanzar_tarea(trabajo):
        nonlocal hilo_tarea
        # No es daemon: al salir se espera a que termine y limpie sus temporales.
        hilo_tarea = threading.Thread(target=trabajo, daemon=False)
        hilo_tarea.start()

    def cancelar_tarea():
        cancelar.set()
        threading.Thread(target=procesos.terminar_todos, daemon=True).start()

    def poner_estado_fila(fila, texto):
        lista.set(fila, "estado", texto)

    def guardar_prefs():
        preferencias.guardar({"tipo": var_tipo.get(), "nivel": var_nivel.get(),
                              "carpeta": var_carpeta.get()})

    def cambiar_tipo():
        guardar_prefs()
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
                anadir_fila(ruta)
        actualizar_contador()

    def anadir_fila(ruta):
        tamano = compresor_video.tamano_legible(os.path.getsize(ruta))
        fila = lista.insert("", "end", values=(os.path.basename(ruta), tamano, "", "Pendiente"))
        archivos[fila] = ruta

    def soltar(evento):
        if tarea_en_curso():
            return
        for ruta in filtrar_soltados(ventana.tk.splitlist(evento.data), var_tipo.get(),
                                     archivos.values()):
            anadir_fila(ruta)
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
            guardar_prefs()

    def carpeta_original():
        var_carpeta.set("")
        etiqueta_carpeta.config(text="Junto a cada archivo original")
        guardar_prefs()

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
    etiqueta_carpeta = ttk.Label(marco, text=prefs["carpeta"] or "Junto a cada archivo original",
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
                            command=lambda: (guardar_prefs(), borrar_estimados()))
        r.pack(anchor="w")
        radios_nivel.append(r)
    var_agresiva = tk.BooleanVar(value=False)
    chk_agresiva = ttk.Checkbutton(grupo, text="Compresion agresiva (Ghostscript)",
                                   variable=var_agresiva, command=lambda: borrar_estimados())
    chk_agresiva.pack(anchor="w", pady=(6, 0))
    if compresor_pdf.buscar_ghostscript() is None:
        chk_agresiva.state(["disabled"])

    var_max_mb = tk.StringVar(value="")
    fila_max = ttk.Frame(grupo)
    fila_max.pack(anchor="w", pady=(6, 0))
    ttk.Label(fila_max, text="Tamano maximo (MB), solo video:").pack(side="left")
    entrada_max = ttk.Entry(fila_max, textvariable=var_max_mb, width=7)
    entrada_max.pack(side="left", padx=4)
    botones_max = [ttk.Button(fila_max, text=t, command=lambda v=v: var_max_mb.set(v))
                   for t, v in (("WhatsApp 16 MB", "16"), ("Correo 25 MB", "25"))]
    for b in botones_max:
        b.pack(side="left", padx=2)
    var_max_mb.trace_add("write", lambda *_: borrar_estimados())

    def objetivo_mb():
        """MB indicados (float) o None; ValueError si el texto no es valido."""
        texto = var_max_mb.get().strip().replace(",", ".")
        if not texto:
            return None
        valor = float(texto)
        if not valor > 0:
            raise ValueError(texto)
        return valor

    def extra_video(tipo):
        if tipo != "video":
            return {}
        try:
            mb = objetivo_mb()
        except ValueError:
            messagebox.showwarning("Tamano maximo", "Indica un numero de MB mayor que 0.")
            raise
        return {"objetivo_mb": mb} if mb else {}

    def actualizar_max(*_):
        estado = ["!disabled"] if var_tipo.get() == "video" else ["disabled"]
        for w in (entrada_max, *botones_max):
            w.state(estado)

    var_tipo.trace_add("write", actualizar_max)
    actualizar_max()

    def opciones_motor(tipo):
        """PDF: motor; video: tamano maximo opcional."""
        if tipo != "pdf":
            return extra_video(tipo)
        return {"motor": "ghostscript" if var_agresiva.get() else "pikepdf"}

    barra = ttk.Progressbar(marco, length=420, maximum=100)
    barra.grid(row=6, column=0, columnspan=2, sticky="ew")
    ttk.Label(marco, textvariable=var_estado).grid(row=7, column=0, columnspan=2, sticky="w", pady=4)

    btn_actualizar = ttk.Button(marco, text="Buscar actualizaciones")
    btn_actualizar.grid(row=8, column=0, sticky="w")

    botones = ttk.Frame(marco)
    botones.grid(row=8, column=0, columnspan=2, sticky="e")
    btn_comprimir = ttk.Button(botones, text="Comprimir")
    btn_cancelar = ttk.Button(botones, text="Cancelar", state="disabled",
                              command=cancelar_tarea)
    btn_comprimir.pack(side="left", padx=4)
    btn_cancelar.pack(side="left")
    btn_abrir = ttk.Button(botones, text="Abrir carpeta", state="disabled",
                           command=lambda: ultima_carpeta[0] and abrir_carpeta(ultima_carpeta[0]))
    btn_abrir.pack(side="left", padx=(4, 0))
    if DND_FILES:
        try:
            lista.drop_target_register(DND_FILES)
            lista.dnd_bind("<<Drop>>", soltar)
        except Exception:  # noqa: BLE001
            pass

    # Controles que no se pueden tocar mientras se comprime
    bloqueables = [btn_agregar, btn_quitar, btn_limpiar, btn_estimar, btn_carpeta, btn_original,
                   btn_comprimir, btn_actualizar] + radios_tipo + radios_nivel

    def bloquear(si):
        for w in bloqueables:
            w.config(state="disabled" if si else "normal")
        btn_cancelar.config(state="normal" if si else "disabled")

    def al_terminar(resultados, omitidos, cancelado, sin_mejora=()):
        bloquear(False)
        ok = [(e, s) for e, s, err in resultados if not err]
        if ok:
            ultima_carpeta[0] = os.path.dirname(os.path.abspath(ok[-1][1]))
            btn_abrir.config(state="normal")
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
        if sin_mejora:
            texto += "\n\nSin mejora (el original ya esta optimizado; no se creo nada):\n" + "\n".join(
                f"- {os.path.basename(e)}" for e in sin_mejora[:10])
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
        try:
            extra = opciones_motor(tipo)
        except ValueError:
            return
        total = len(filas)

        cancelar.clear()
        bloquear(True)
        barra["value"] = 0
        for f in filas:
            poner_estado_fila(f, "Pendiente")

        def trabajo():
            resultados, omitidos, sin_mejora = [], [], []
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
                                           si_existe="renombrar", **extra)
                    antes, despues = os.path.getsize(entrada), os.path.getsize(out)
                    en_ui(poner_estado_fila, fila, texto_resultado(antes, despues))
                    resultados.append((entrada, out, None))
                except nucleo.SinMejora:
                    en_ui(poner_estado_fila, fila, "Sin mejora")
                    sin_mejora.append(entrada)
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
            en_ui(al_terminar, resultados, omitidos, cancelar.is_set(), sin_mejora)

        lanzar_tarea(trabajo)

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
        try:
            extra = opciones_motor(var_tipo.get())
        except ValueError:
            return
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
                    bytes_ = modulo.estimar(ruta, nivel, cancelar, **extra)
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
                    if bytes_ >= os.path.getsize(ruta):
                        texto += " (sin mejora)"
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

        lanzar_tarea(trabajo)

    btn_estimar.config(command=estimar)

    # ------------------------------------------------------------ Actualizaciones

    actualizando = [False]  # descarga/instalacion en curso (dialogo abierto)
    cancelar_descarga = threading.Event()

    def ofrecer_actualizacion(info, manual):
        btn_actualizar.config(state="normal")
        if cerrando or (info is not None and tarea_en_curso()):
            # No se interrumpe una compresion: se ofrecera al volver a abrir la app.
            if manual and not cerrando:
                messagebox.showinfo("Actualizaciones",
                                    "Hay una version nueva. Termina o cancela la tarea en curso "
                                    "y vuelve a buscar actualizaciones.")
            return
        if info is None:
            if manual:
                messagebox.showinfo("Actualizaciones", f"Ya tienes la ultima version ({VERSION}).")
            return
        if actualizando[0]:
            return
        dialogo_actualizacion(info)

    def dialogo_actualizacion(info):
        asset = info.get("asset")
        auto = bool(info.get("auto") and asset and actualizador.puede_autoinstalar())
        dlg = tk.Toplevel(ventana, name="dlg_actualizacion", padx=12, pady=12)
        dlg.title("Nueva version disponible")
        dlg.transient(ventana)
        dlg.resizable(False, False)
        resumen_ver = f"Compresorfree {VERSION}  ->  {info['version']}"
        detalle = [d for d in (info.get("fecha") or "",
                               f"{asset['tamano'] / 1048576:.1f} MB" if asset else "") if d]
        ttk.Label(dlg, text=resumen_ver, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        if detalle:
            ttk.Label(dlg, text="  -  ".join(detalle)).pack(anchor="w")
        if not info.get("verificada") and not info.get("auto"):
            ttk.Label(dlg, foreground="#b00020", wraplength=420, justify="left",
                      text="No se pudo verificar la firma de esta version. Descargala solo "
                           "desde la pagina oficial de Compresorfree en GitHub.").pack(
                anchor="w", pady=(6, 0))
        zona = ttk.Frame(dlg, name="zona_notas")
        zona.pack(fill="both", expand=True, pady=8)
        txt = tk.Text(zona, width=60, height=12, wrap="word", name="txt_notas")
        sb = ttk.Scrollbar(zona, orient="vertical", command=txt.yview)
        txt.config(yscrollcommand=sb.set)
        txt.insert("1.0", info.get("notas") or "Sin notas para esta version.")
        txt.config(state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        barra_d = ttk.Progressbar(dlg, mode="determinate", maximum=100)
        var_d = tk.StringVar(value="")
        ttk.Label(dlg, textvariable=var_d).pack(anchor="w")
        fila_b = ttk.Frame(dlg, name="botones")
        fila_b.pack(fill="x", pady=(8, 0))
        btn_si = ttk.Button(fila_b, name="btn_actualizar_ahora",
                            text="Actualizar ahora" if auto else "Abrir pagina de descarga")
        btn_no = ttk.Button(fila_b, name="btn_ahora_no", text="Ahora no")
        btn_cancel_d = ttk.Button(fila_b, name="btn_cancelar_descarga", text="Cancelar")

        def cerrar_dialogo():
            actualizando[0] = False
            with contextlib.suppress(tk.TclError):
                dlg.grab_release()
                dlg.destroy()

        def volver(mensaje=None):
            """Restaura el dialogo tras un fallo o cancelacion."""
            if cerrando:
                return
            actualizando[0] = False
            barra_d.pack_forget()
            btn_cancel_d.pack_forget()
            var_d.set(mensaje or "")
            btn_si.config(state="normal")
            btn_no.config(state="normal")

        def progreso_ui(leidos, total):
            barra_d.config(value=100 * leidos / total)
            var_d.set(f"Descargando... {leidos / 1048576:.1f} / {total / 1048576:.1f} MB")

        def trabajo_descarga():
            try:
                ruta = actualizador.descargar(
                    asset, actualizador.dir_descargas(),
                    lambda a, b: en_ui(progreso_ui, a, b), cancelar_descarga)
                en_ui(var_d.set, "Preparando la instalacion...")
                resultado = actualizador.instalar(ruta)
            except actualizador.Cancelado:
                en_ui(volver, "Descarga cancelada.")
                return
            except Exception as e:  # noqa: BLE001
                msg = str(e) or type(e).__name__

                def fallo():
                    volver()
                    messagebox.showerror("Actualizaciones",
                                         f"No se pudo actualizar:\n{msg}", parent=dlg)
                en_ui(fallo)
                return
            en_ui(terminada, resultado)

        def terminada(resultado):
            if cerrando:
                return
            if resultado == "cerrar":
                # El instalador ya arranco: se cierra por el camino normal (sin tarea).
                cerrar_dialogo()
                al_cerrar()
                return
            cerrar_dialogo()
            messagebox.showinfo(
                "Actualizar Compresorfree",
                "Se abrio la imagen de disco. Cierra Compresorfree y arrastra Compresorfree a "
                "la carpeta Aplicaciones, reemplazando la version anterior.")

        def aceptar():
            if not auto:
                import webbrowser
                webbrowser.open(info["url_pagina"])
                cerrar_dialogo()
                return
            actualizando[0] = True
            cancelar_descarga.clear()
            btn_si.config(state="disabled")
            btn_no.config(state="disabled")
            barra_d.config(value=0)
            barra_d.pack(fill="x", before=fila_b)
            btn_cancel_d.pack(side="right")
            var_d.set("Descargando...")
            threading.Thread(target=trabajo_descarga, daemon=True).start()

        def cancelar_d():
            cancelar_descarga.set()
            btn_cancel_d.config(state="disabled")

        def cerrar_x():
            if actualizando[0]:
                return  # durante la descarga solo vale Cancelar
            cerrar_dialogo()

        btn_si.config(command=aceptar)
        btn_no.config(command=cerrar_dialogo)
        btn_cancel_d.config(command=cancelar_d)
        btn_no.pack(side="right")
        btn_si.pack(side="right", padx=4)
        dlg.protocol("WM_DELETE_WINDOW", cerrar_x)
        with contextlib.suppress(tk.TclError):
            dlg.grab_set()

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

    # ------------------------------------------------------------ Cierre de la ventana

    def al_cerrar():
        nonlocal cerrando
        if cerrando or dialogo_cierre[0]:
            return
        cancelar_descarga.set()
        guardar_prefs()
        if not tarea_en_curso():
            ventana.destroy()
            return
        dialogo_cierre[0] = True
        try:
            salir = messagebox.askyesno("Tarea en curso",
                                        "Hay una tarea en curso. ¿Cancelarla y salir?")
        finally:
            dialogo_cierre[0] = False
        if not salir:
            return
        if not tarea_en_curso():  # termino mientras el dialogo estaba abierto
            ventana.destroy()
            return
        cerrando = True
        cancelar_tarea()
        var_estado.set("Cancelando...")
        bloquear(True)
        btn_cancelar.config(state="disabled")
        esperar_y_cerrar(time.monotonic() + 15)

    def esperar_y_cerrar(limite):
        if tarea_en_curso() and time.monotonic() < limite:
            ventana.after(100, esperar_y_cerrar, limite)
            return
        if tarea_en_curso():
            # Algo no interrumpible (p. ej. pdf.save): se cierra igual; el hilo
            # termina solo y no publica nada porque `cancelar` esta activo.
            procesos.terminar_todos()
        ventana.destroy()

    dialogo_cierre = [False]
    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)
    if sys.platform == "darwin":
        # Cmd+Q y "Salir" del Dock no pasan por WM_DELETE_WINDOW en macOS.
        ventana.createcommand("::tk::mac::Quit", al_cerrar)
    ventana.after(50, vaciar_cola_ui)
    ventana.after(1500, buscar_actualizacion)  # busca en silencio al abrir la app
    threading.Thread(target=actualizador.limpiar_descargas, daemon=True).start()
    ventana.mainloop()
    if hilo_tarea is not None:
        # Se espera aqui (y no en el cierre del interprete) para que los objetos de
        # Tk que usa el hilo se liberen en el hilo principal.
        hilo_tarea.join()


# ---------------------------------------------------------------- Linea de comandos

def _extra_cli(args, entrada):
    """Argumentos extra del modulo: --motor solo aplica a PDF."""
    if tipo_por_extension(entrada) == "pdf":
        return {"motor": args.motor}
    if args.max_mb:
        return {"objetivo_mb": args.max_mb}
    return {}


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
    parser.add_argument("--motor", choices=["pikepdf", "ghostscript"], default="pikepdf",
                        help="Motor de PDF: pikepdf (conservador, por defecto) o ghostscript (agresivo)")
    parser.add_argument("--max-mb", type=float, metavar="N",
                        help="Video: tamano maximo en MB (codifica en dos pasadas)")
    args = parser.parse_args()
    if args.max_mb is not None and not args.max_mb > 0:
        parser.error("--max-mb debe ser mayor que 0")

    if not args.entradas:
        iniciar_gui()
        return
    if args.salida and len(args.entradas) > 1:
        parser.error("-o/--salida solo se puede usar con un archivo; usa -d/--carpeta")
    total = len(args.entradas)
    entradas = []
    no_soportados = 0
    for entrada in args.entradas:
        if tipo_por_extension(entrada) is None:
            ext = os.path.splitext(entrada)[1]
            print(f"{entrada}: formato no soportado ({ext or 'sin extension'}). "
                  "Formatos: video (avi, mkv, mov, ...) y PDF.", file=sys.stderr)
            no_soportados += 1
        else:
            entradas.append(entrada)
    if args.estimar:
        for entrada in entradas:
            modulo = TIPOS[tipo_por_extension(entrada)]["modulo"]
            try:
                bytes_ = modulo.estimar(entrada, args.nivel, **_extra_cli(args, entrada))
            except KeyboardInterrupt:
                procesos.terminar_todos()
                print("\nCancelado.")
                sys.exit(1)
            except nucleo.ArchivoOmitido as e:
                print(f"{entrada}: {e}", file=sys.stderr)
                continue
            except Exception as e:
                print(f"{entrada}: error ({e})", file=sys.stderr)
                continue
            estimado = "?" if bytes_ is None else "~" + compresor_video.tamano_legible(bytes_)
            print(f"{entrada}: {compresor_video.tamano_legible(os.path.getsize(entrada))}"
                  f" -> {estimado} (nivel {args.nivel})")
        if no_soportados:
            sys.exit(1)
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

    errores, omitidos, sin_mejora = no_soportados, 0, 0
    # Se planifica todo el lote junto: ninguna salida puede caer sobre otra entrada.
    if args.salida:
        planes = [(e, args.salida, "error") for e in entradas]
    else:
        salidas = nucleo.planificar_lote(
            entradas,
            lambda e: TIPOS[tipo_por_extension(e)]["modulo"].ruta_salida_por_defecto(e, args.nivel),
            args.carpeta)
        planes = [(e, s, "renombrar") for e, s in zip(entradas, salidas)]
    for i, (entrada, salida, si_existe) in enumerate(planes, 1):
        modulo = TIPOS[tipo_por_extension(entrada)]["modulo"]
        if total > 1:
            print(f"[{i}/{total}] {entrada}")
        try:
            salida = modulo.comprimir(entrada, salida, args.nivel, barra, si_existe=si_existe,
                                    **_extra_cli(args, entrada))
        except KeyboardInterrupt:
            procesos.terminar_todos()
            print("\nCancelado.")
            sys.exit(1)
        except nucleo.SinMejora as e:
            print(f"\n{entrada}: {e}")
            sin_mejora += 1
            continue
        except nucleo.ArchivoOmitido as e:
            print(f"\n{e} El original queda intacto.", file=sys.stderr)
            omitidos += 1
            continue
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)
            errores += 1
            continue
        print(f"\nListo: {salida}\n{resumen(entrada, salida)}\n")
    if errores or omitidos or sin_mejora:
        print(f"{errores} con error, {omitidos} omitido(s) y {sin_mejora} sin mejora "
              f"de {total} archivo(s).", file=sys.stderr)
    if errores or omitidos:
        sys.exit(1)

if __name__ == "__main__":
    main()
