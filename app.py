"""Compresor de archivos: video (a MP4) y PDF, con niveles baja/media/alta.

Uso:
    python app.py                               -> abre la interfaz grafica
    python app.py archivo.mkv -n alta [-o salida.mp4]
    python app.py documento.pdf -n media [-o salida.pdf]
"""

import argparse
import os
import sys
import threading

import compresor_pdf
import compresor_video
from compresor_video import resumen

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


# ---------------------------------------------------------------- Interfaz grafica

def iniciar_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    ventana = tk.Tk()
    ventana.title("Compresorfree")
    ventana.resizable(False, False)

    var_tipo = tk.StringVar(value="video")
    var_entrada = tk.StringVar()
    var_salida = tk.StringVar()
    var_nivel = tk.StringVar(value="media")
    var_estado = tk.StringVar(value="Elige el tipo de archivo y selecciona uno.")
    cancelar = threading.Event()

    marco = ttk.Frame(ventana, padding=12)
    marco.grid()

    def salida_por_defecto():
        entrada = var_entrada.get().strip()
        if entrada:
            modulo = TIPOS[var_tipo.get()]["modulo"]
            var_salida.set(modulo.ruta_salida_por_defecto(entrada, var_nivel.get()))

    def cambiar_tipo():
        var_entrada.set("")
        var_salida.set("")
        barra["value"] = 0
        var_estado.set(f"Selecciona un archivo: {TIPOS[var_tipo.get()]['nombre']}.")

    def elegir_entrada():
        tipo = TIPOS[var_tipo.get()]
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo",
            filetypes=tipo["filtro"] + [("Todos los archivos", "*.*")],
        )
        if ruta:
            var_entrada.set(ruta)
            salida_por_defecto()

    def elegir_salida():
        ext = TIPOS[var_tipo.get()]["extension"]
        ruta = filedialog.asksaveasfilename(
            title="Guardar como", defaultextension=ext,
            filetypes=[(ext[1:].upper(), "*" + ext)],
        )
        if ruta:
            var_salida.set(ruta)

    def cambiar_nivel():
        entrada = var_entrada.get()
        if entrada and var_salida.get().startswith(os.path.splitext(entrada)[0] + "_comprimido_"):
            salida_por_defecto()

    grupo_tipo = ttk.LabelFrame(marco, text="Que quieres comprimir?", padding=8)
    grupo_tipo.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    for clave, tipo in TIPOS.items():
        ttk.Radiobutton(grupo_tipo, text=tipo["nombre"], value=clave,
                        variable=var_tipo, command=cambiar_tipo).pack(side="left", padx=(0, 20))

    ttk.Label(marco, text="Archivo de entrada:").grid(row=1, column=0, sticky="w")
    ttk.Entry(marco, textvariable=var_entrada, width=55).grid(row=2, column=0, padx=(0, 6))
    ttk.Button(marco, text="Buscar...", command=elegir_entrada).grid(row=2, column=1)

    ttk.Label(marco, text="Guardar en:").grid(row=3, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(marco, textvariable=var_salida, width=55).grid(row=4, column=0, padx=(0, 6))
    ttk.Button(marco, text="Cambiar...", command=elegir_salida).grid(row=4, column=1)

    grupo = ttk.LabelFrame(marco, text="Nivel de compresion", padding=8)
    grupo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
    for nombre, texto in DESCRIPCION_NIVELES.items():
        ttk.Radiobutton(grupo, text=texto, value=nombre,
                        variable=var_nivel, command=cambiar_nivel).pack(anchor="w")

    barra = ttk.Progressbar(marco, length=420, maximum=100)
    barra.grid(row=6, column=0, columnspan=2, sticky="ew")
    ttk.Label(marco, textvariable=var_estado).grid(row=7, column=0, columnspan=2, sticky="w", pady=4)

    botones = ttk.Frame(marco)
    botones.grid(row=8, column=0, columnspan=2, sticky="e")
    btn_comprimir = ttk.Button(botones, text="Comprimir")
    btn_cancelar = ttk.Button(botones, text="Cancelar", state="disabled",
                              command=cancelar.set)
    btn_comprimir.pack(side="left", padx=4)
    btn_cancelar.pack(side="left")

    def al_terminar(error=None, salida=None, entrada=None):
        btn_comprimir.config(state="normal")
        btn_cancelar.config(state="disabled")
        if error:
            var_estado.set("Cancelado." if "cancelada" in error else "Error.")
            barra["value"] = 0
            messagebox.showerror("Error", error)
        else:
            var_estado.set("Listo.")
            messagebox.showinfo("Compresion terminada",
                                f"Archivo guardado en:\n{salida}\n\n{resumen(entrada, salida)}")

    def iniciar():
        entrada, salida = var_entrada.get().strip(), var_salida.get().strip()
        if not entrada:
            messagebox.showwarning("Falta el archivo", "Selecciona un archivo de entrada.")
            return
        modulo = TIPOS[var_tipo.get()]["modulo"]
        nivel = var_nivel.get()
        cancelar.clear()
        btn_comprimir.config(state="disabled")
        btn_cancelar.config(state="normal")
        barra["value"] = 0
        var_estado.set("Comprimiendo...")

        def actualizar(p):
            ventana.after(0, lambda: (barra.configure(value=p),
                                      var_estado.set(f"Comprimiendo... {p:.0f}%")))

        def trabajo():
            try:
                out = modulo.comprimir(entrada, salida or None, nivel, actualizar, cancelar)
                ventana.after(0, lambda: al_terminar(salida=out, entrada=entrada))
            except Exception as e:
                msg = str(e)
                ventana.after(0, lambda: al_terminar(error=msg))

        threading.Thread(target=trabajo, daemon=True).start()

    btn_comprimir.config(command=iniciar)
    ventana.mainloop()


# ---------------------------------------------------------------- Linea de comandos

def main():
    parser = argparse.ArgumentParser(
        description="Comprime videos (a MP4) y PDF. Sin argumentos abre la interfaz grafica."
    )
    parser.add_argument("entrada", nargs="?", help="Video (cualquier formato) o PDF")
    parser.add_argument("-o", "--salida", help="Archivo de salida")
    parser.add_argument("-n", "--nivel", choices=list(DESCRIPCION_NIVELES), default="media",
                        help="Nivel de compresion (por defecto: media)")
    args = parser.parse_args()

    if not args.entrada:
        iniciar_gui()
        return

    modulo = TIPOS[tipo_por_extension(args.entrada)]["modulo"]

    def barra(p):
        llenos = int(p / 2.5)
        print(f"\r[{'#' * llenos}{'.' * (40 - llenos)}] {p:5.1f}%", end="", flush=True)

    try:
        salida = modulo.comprimir(args.entrada, args.salida, args.nivel, barra)
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"\nListo: {salida}\n{resumen(args.entrada, salida)}")


if __name__ == "__main__":
    main()
