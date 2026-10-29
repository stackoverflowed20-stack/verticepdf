"""Menu Arquivo (exportar, propriedades) e barra de título própria."""
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

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QToolButton

import viewer


def _view():
    d = fitz.open()
    for k in range(2):
        d.new_page().insert_text((72, 100), f"Pagina {k + 1}", fontsize=14)
    return viewer.PdfView(d, None)


def _dispose(v):
    v._autosave_timer.stop()
    v.modified = False
    v.close()
    v.deleteLater()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DATA", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])


def test_file_menu_structure():
    v = _view()
    btn = v.findChild(QToolButton, "filebtn")
    labels = [a.text().split("\t")[0] for a in btn.menu().actions() if not a.isSeparator()]
    assert labels == ["Abrir", "Abrir recentes", "Criar PDF", "Salvar", "Salvar como…", "Exportar para",
                      "Abrir local do arquivo", "Propriedades do documento", "Imprimir", "Preferências"]
    exp = [a for a in btn.menu().actions() if a.text() == "Exportar para"][0].menu()
    assert [a.text() for a in exp.actions()] == ["Word", "Excel", "PowerPoint", "Imagem"]
    _dispose(v)


@pytest.mark.parametrize("kind,ext", [("docx", ".docx"), ("xlsx", ".xlsx"), ("pptx", ".pptx")])
def test_export_creates_file(tmp_path, monkeypatch, kind, ext):
    v = _view()
    out = str(tmp_path / ("saida" + ext))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    v.export_as(kind)
    assert Path(out).is_file() and Path(out).stat().st_size > 500
    _dispose(v)


def test_export_image_adds_extension(tmp_path, monkeypatch):
    v = _view()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "img"), "Imagem PNG (*.png)")))
    v.export_as("image")
    assert sorted(p.name for p in tmp_path.glob("img_*.png")) == ["img_001.png", "img_002.png"]
    _dispose(v)


def test_recent_menu_lists_files(tmp_path):
    f = tmp_path / "a.pdf"
    d = fitz.open(); d.new_page(); d.save(str(f))
    v = _view()
    v.recent_provider = lambda: [str(f), str(tmp_path / "sumiu.pdf")]
    v._fill_recent_menu()
    assert [a.text() for a in v._recent_menu.actions()] == ["a.pdf"]
    got = []
    v.open_requested.connect(got.append)
    v._recent_menu.actions()[0].trigger()
    assert got == [str(f)]
    _dispose(v)


def test_properties_change_metadata(monkeypatch):
    import dialogs
    v = _view()

    class Fake(dialogs.PropertiesDialog):
        def exec(self):
            self.fields["title"].setText("Meu título")
            self.fields["author"].setText("Anderson")
            return 1

    monkeypatch.setattr(viewer, "PropertiesDialog", Fake)
    v.show_properties()
    assert v.doc.metadata["title"] == "Meu título" and v.doc.metadata["author"] == "Anderson"
    assert v.modified
    v.do_undo()
    assert v.doc.metadata["title"] != "Meu título"
    _dispose(v)


def test_window_controls_and_edges(monkeypatch, tmp_path):
    import main
    win = main.MainWindow()
    win.resize(1000, 700)
    win.show()
    QApplication.instance().processEvents()
    assert win.windowFlags() & Qt.FramelessWindowHint
    r = win.frameGeometry()
    assert win._edges_at(QPoint(r.left() + 2, r.top() + 2)) == (Qt.LeftEdge | Qt.TopEdge)
    assert win._edges_at(QPoint(r.right() - 1, r.center().y())) == Qt.RightEdge
    assert not win._edges_at(r.center())
    win.btn_max.click()
    QApplication.instance().processEvents()
    win.btn_max.click()
    win.settings.setValue("geometry", None)
    win.close()
    win.deleteLater()
