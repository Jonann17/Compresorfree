"""GUI: dialogo de nueva version (verificada o no). Necesita display (xvfb-run)."""
import faulthandler
import time

import pytest


def _hay_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:  # sin tkinter o TclError "no display"
        return False


pytestmark = pytest.mark.skipif(not _hay_display(), reason="sin tkinter o sin display (usa xvfb-run)")

NOTAS = "- Novedad uno <script>\n- Novedad dos"
URL = "https://github.com/Jonann17/Compresorfree/releases/tag/v9.9.9"
DLG = ".dlg_actualizacion"
ASSET = {"os": "windows", "arch": "x64", "formato": "exe", "nombre": "Compresorfree-Setup-9.9.9.exe",
         "url": "https://github.com/x/Compresorfree-Setup-9.9.9.exe", "sha256": "a" * 64,
         "tamano": 5 * 1048576, "tamano_expandido_max": 5 * 1048576}


def _ejecutar(monkeypatch, info, accion, puede_auto=True, descargar=None, instalar=None):
    """Abre la GUI con una busqueda que devuelve `info`. Cuando aparece el dialogo se llama
    a `accion(ventana, dlg)`; luego espera (max 15 s) a que la ventana se cierre sola."""
    import tkinter
    import webbrowser
    from tkinter import messagebox

    import actualizador
    import app

    monkeypatch.setattr(actualizador, "buscar_actualizacion", lambda: info)
    monkeypatch.setattr(actualizador, "puede_autoinstalar", lambda: puede_auto)
    monkeypatch.setattr(actualizador, "limpiar_descargas", lambda: None)
    llamadas = {"descargar": [], "instalar": [], "web": [], "info": []}

    def desc(asset, destino, progreso=None, cancelar=None):
        llamadas["descargar"].append(asset["nombre"])
        progreso(10, 20)
        return "/tmp/ruta-falsa.exe"

    monkeypatch.setattr(actualizador, "descargar", descargar or desc)
    monkeypatch.setattr(actualizador, "instalar",
                        instalar or (lambda r: llamadas["instalar"].append(r) or "cerrar"))
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: llamadas["web"].append(a))
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: llamadas["info"].append(a))
    original = tkinter.Tk.mainloop
    hecho = [False]

    def mainloop_guion(ventana, n=0):
        limite = time.monotonic() + 15

        def sondear():
            if time.monotonic() > limite:
                ventana.destroy()
                return
            try:
                dlg = ventana.nametowidget(DLG)
            except KeyError:
                ventana.after(50, sondear)
                return
            if not hecho[0]:
                hecho[0] = True
                try:
                    accion(ventana, dlg)
                except Exception:
                    ventana.after(50, ventana.destroy)  # no colgar la suite
                    raise
            ventana.after(50, sondear)

        ventana.after(100, sondear)
        original(ventana, n)

    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop_guion)
    faulthandler.dump_traceback_later(60, exit=True)
    try:
        app.iniciar_gui()
    finally:
        faulthandler.cancel_dump_traceback_later()
    return llamadas


def _info(**cambios):
    info = {"version": "9.9.9", "notas": NOTAS, "fecha": "2026-11-20", "url_pagina": URL,
            "verificada": True, "auto": True, "asset": dict(ASSET)}
    info.update(cambios)
    return info


def _boton(dlg, nombre):
    return dlg.nametowidget(f"botones.{nombre}")


def test_dialogo_muestra_notas_solo_lectura_y_ahora_no_no_hace_nada(monkeypatch):
    visto = {}

    def accion(ventana, dlg):
        txt = dlg.nametowidget("zona_notas.txt_notas")
        visto["notas"] = txt.get("1.0", "end").strip()
        visto["estado"] = str(txt.cget("state"))
        visto["boton"] = str(_boton(dlg, "btn_actualizar_ahora").cget("text"))
        _boton(dlg, "btn_ahora_no").invoke()
        ventana.after(200, ventana.destroy)

    llamadas = _ejecutar(monkeypatch, _info(), accion)
    assert visto["notas"] == NOTAS and visto["estado"] == "disabled"
    assert visto["boton"] == "Actualizar ahora"
    assert llamadas["descargar"] == [] and llamadas["instalar"] == [] and llamadas["web"] == []


def test_actualizar_ahora_descarga_instala_y_cierra_la_ventana(monkeypatch):
    def accion(ventana, dlg):
        _boton(dlg, "btn_actualizar_ahora").invoke()

    llamadas = _ejecutar(monkeypatch, _info(), accion)  # la ventana se cierra sola
    assert llamadas["descargar"] == [ASSET["nombre"]]
    assert llamadas["instalar"] == ["/tmp/ruta-falsa.exe"]
    assert llamadas["web"] == []


def test_sin_autoinstalacion_ofrece_la_pagina_y_avisa(monkeypatch):
    visto = {}

    def accion(ventana, dlg):
        visto["boton"] = str(_boton(dlg, "btn_actualizar_ahora").cget("text"))
        _boton(dlg, "btn_actualizar_ahora").invoke()
        ventana.after(200, ventana.destroy)

    info = _info(verificada=False, auto=False, asset=None)
    llamadas = _ejecutar(monkeypatch, info, accion)
    assert visto["boton"] == "Abrir pagina de descarga"
    assert llamadas["web"] == [(URL,)]
    assert llamadas["descargar"] == [] and llamadas["instalar"] == []


def test_portable_sin_registro_solo_ofrece_la_pagina(monkeypatch):
    visto = {}

    def accion(ventana, dlg):
        visto["boton"] = str(_boton(dlg, "btn_actualizar_ahora").cget("text"))
        _boton(dlg, "btn_ahora_no").invoke()
        ventana.after(200, ventana.destroy)

    _ejecutar(monkeypatch, _info(), accion, puede_auto=False)
    assert visto["boton"] == "Abrir pagina de descarga"


def test_descarga_cancelada_vuelve_al_dialogo_sin_instalar(monkeypatch):
    import actualizador

    def descargar(asset, destino, progreso=None, cancelar=None):
        raise actualizador.Cancelado()

    visto = {}

    def accion(ventana, dlg):
        _boton(dlg, "btn_actualizar_ahora").invoke()

        def revisar():
            visto["estado"] = str(_boton(dlg, "btn_actualizar_ahora").cget("state"))
            _boton(dlg, "btn_ahora_no").invoke()
            ventana.after(200, ventana.destroy)

        ventana.after(600, revisar)

    llamadas = _ejecutar(monkeypatch, _info(), accion, descargar=descargar)
    assert visto["estado"] == "normal" and llamadas["instalar"] == []
