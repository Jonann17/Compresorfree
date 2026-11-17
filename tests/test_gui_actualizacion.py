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

NOTAS = "NOTAS-SIN-FIRMAR <script>"
URL = "https://github.com/Jonann17/Compresorfree/releases/tag/v9.9.9"


def _ejecutar(monkeypatch, info, acepta=True):
    """Abre la GUI con una busqueda automatica que devuelve `info`; cierra al ver el dialogo."""
    import tkinter
    import webbrowser
    from tkinter import messagebox

    import actualizador
    import app

    monkeypatch.setattr(actualizador, "buscar_actualizacion", lambda: info)
    preguntas, abiertas = [], []
    monkeypatch.setattr(messagebox, "askyesno",
                        lambda titulo, mensaje, *a, **k: preguntas.append((titulo, mensaje)) or acepta)
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: abiertas.append(a))
    original = tkinter.Tk.mainloop

    def mainloop_guion(ventana, n=0):
        limite = time.monotonic() + 15

        def sondear():
            if preguntas or time.monotonic() > limite:
                ventana.after(200, ventana.destroy)  # deja terminar ofrecer_actualizacion
            else:
                ventana.after(50, sondear)

        ventana.after(100, sondear)
        original(ventana, n)

    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop_guion)
    faulthandler.dump_traceback_later(60, exit=True)
    try:
        app.iniciar_gui()
    finally:
        faulthandler.cancel_dump_traceback_later()
    return preguntas, abiertas


def test_version_no_verificada_avisa_y_abre_la_pagina_oficial(monkeypatch):
    info = {"version": "9.9.9", "notas": NOTAS, "url_pagina": URL, "verificada": False}
    preguntas, abiertas = _ejecutar(monkeypatch, info)
    assert len(preguntas) == 1
    titulo, texto = preguntas[0]
    assert titulo == "Nueva version disponible"
    assert "no se pudo verificar" in texto
    assert "9.9.9" in texto
    assert NOTAS not in texto and "script" not in texto  # notas sin firmar: nunca se muestran
    assert abiertas == [(URL,)]


def test_version_no_verificada_rechazada_no_abre_nada(monkeypatch):
    info = {"version": "9.9.9", "notas": NOTAS, "url_pagina": URL, "verificada": False}
    preguntas, abiertas = _ejecutar(monkeypatch, info, acepta=False)
    assert len(preguntas) == 1 and abiertas == []


def test_version_verificada_no_muestra_las_notas(monkeypatch):
    info = {"version": "9.9.9", "notas": NOTAS, "url_pagina": URL, "verificada": True}
    preguntas, abiertas = _ejecutar(monkeypatch, info)
    assert len(preguntas) == 1
    _, texto = preguntas[0]
    assert "verificada" in texto
    assert "no se pudo verificar" not in texto
    assert NOTAS not in texto and "script" not in texto
    assert abiertas == [(URL,)]
