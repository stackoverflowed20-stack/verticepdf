"""Recuperação automática, refazer/histórico e instância única."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

import recovery  # noqa: E402


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DATA", str(tmp_path / "data"))


def _pdf_bytes(text="Olá mundo"):
    d = fitz.open()
    d.new_page().insert_text((72, 100), text, fontsize=12)
    return d.tobytes()


def test_recovery_roundtrip():
    recovery.write("abc", _pdf_bytes(), title="a.pdf", original="/x/a.pdf", encrypted=False)
    (item,) = recovery.pending()
    assert item["id"] == "abc" and item["original"] == "/x/a.pdf"
    assert fitz.open(item["pdf"]).page_count == 1
    recovery.discard("abc")
    assert recovery.pending() == []


def test_recovery_drops_corrupt_and_old(monkeypatch):
    d = recovery.recovery_dir()
    (d / "bad.json").write_text("{nao e json", encoding="utf-8")
    (d / "bad.pdf").write_bytes(b"x")
    recovery.write("old", _pdf_bytes(), title="o", original=None, encrypted=False)
    monkeypatch.setattr(recovery, "MAX_AGE_DAYS", -1)
    assert recovery.pending() == []
    assert not (d / "bad.json").exists() and not (d / "old.pdf").exists()


def dispose(v) -> None:
    """Encerra uma vista de teste de forma ordenada (timers parados, exclusão adiada)."""
    v._autosave_timer.stop()
    v.close()
    v.deleteLater()


@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    for w in app.topLevelWidgets():          # nada de janelas/timers sobrando para o próximo teste
        w.close()
        w.deleteLater()
    app.processEvents()


def test_undo_redo_and_autosave(qapp):
    import viewer
    d = fitz.open(stream=_pdf_bytes("um dois três"), filetype="pdf")
    v = viewer.PdfView(d, None)
    v.show(); qapp.processEvents()
    assert not v.redo_act.isEnabled()
    v._edit(0, lambda: v.doc[0].insert_text((72, 200), "NOVO", fontsize=12))
    assert "NOVO" in v.doc[0].get_text() and v.undo_act.isEnabled()
    v.autosave()
    assert [i["id"] for i in recovery.pending()] == [v.rid]
    v.do_undo()
    assert "NOVO" not in v.doc[0].get_text() and v.redo_act.isEnabled()
    v.do_redo()
    assert "NOVO" in v.doc[0].get_text() and not v.redo_act.isEnabled()
    v.do_undo()
    v._edit(0, lambda: v.doc[0].insert_text((72, 220), "OUTRO", fontsize=12))   # edição nova limpa o refazer
    assert not v.redo_stack
    v.set_modified(False)                      # salvar/descartar apaga a cópia de recuperação
    assert recovery.pending() == []
    dispose(v)


def test_failed_edit_does_not_enter_redo(qapp, monkeypatch):
    import viewer
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    v = viewer.PdfView(fitz.open(stream=_pdf_bytes(), filetype="pdf"), None)
    v._edit(0, lambda: (_ for _ in ()).throw(RuntimeError("falha")))
    assert not v.redo_stack and not v.undo_stack
    dispose(v)


def test_history_memory_cap(qapp, monkeypatch):
    import viewer
    v = viewer.PdfView(fitz.open(stream=_pdf_bytes(), filetype="pdf"), None)
    monkeypatch.setattr(viewer.PdfView, "HISTORY_BYTES", 5000)
    for _ in range(30):
        v._push_undo()
    assert 1 <= len(v.undo_stack) < 30
    dispose(v)


def test_single_instance_forwarding(qapp, tmp_path):
    import main
    got = []
    srv = main.InstanceServer()
    assert srv.ok
    srv.files.connect(got.extend)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(_pdf_bytes())
    assert main.forward_to_running([str(pdf)])
    for _ in range(50):
        qapp.processEvents()
        if got:
            break
    for _ in range(30):                 # deixa o "disconnected" chegar antes de destruir o servidor
        qapp.processEvents()
    assert got == [str(pdf)]
    srv.deleteLater()
    qapp.processEvents()


def test_offer_recovery_opens_tab(qapp, monkeypatch):
    import main
    from PySide6.QtWidgets import QMessageBox
    recovery.write("zz", _pdf_bytes("texto salvo"), title="rel.pdf", original="/x/rel.pdf", encrypted=False)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])  # "Recuperar"
    win = main.MainWindow()
    win.offer_recovery()
    view = win.tabs.widget(1)
    assert view.modified and view.suggest_path == "/x/rel.pdf" and "texto salvo" in view.doc[0].get_text()
    assert [i["id"] for i in recovery.pending()] == [view.rid]   # cópia migrou para o novo id
    view.set_modified(False)
    win.tabs.removeTab(1)
    dispose(view)
    win.deleteLater()


def test_ribbon_pagetools_flow(qapp, monkeypatch):
    import viewer
    from PySide6.QtWidgets import QDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = fitz.open()
    for k in range(3):
        d.new_page().insert_text((72, 100), f"Contrato número {k + 1} da empresa", fontsize=12)
    v = viewer.PdfView(d, None)
    v.show(); qapp.processEvents()

    class FakeFR:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.Accepted
        def values(self): return {"query": "empresa", "repl": "Vértice", "case": False}

    monkeypatch.setattr(viewer, "FindReplaceDialog", FakeFR)
    v.find_replace()
    assert all("Vértice" in v.doc[i].get_text() for i in range(3)) and v.modified
    v.do_undo()
    assert "empresa" in v.doc[0].get_text()

    class FakeWM:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.Accepted
        def values(self): return {"text": "COPIA", "size": 60, "angle": 30, "opacity": .3, "color": (.5, .5, .5),
                                  "pages": "1-2", "behind": False}

    monkeypatch.setattr(viewer, "WatermarkDialog", FakeWM)
    v.watermark()
    assert v.doc[0].get_text("rawdict") and "COPIA" in "".join(
        c["c"] for b in v.doc[1].get_text("rawdict")["blocks"] if b["type"] == 0
        for l in b["lines"] for s in l["spans"] for c in s["chars"])
    v.clean_metadata()
    v.set_modified(False)
    dispose(v)
