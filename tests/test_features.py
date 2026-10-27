"""Testes de edição de parágrafo, anotações e assinatura digital."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import annots  # noqa: E402
import signing  # noqa: E402
import textedit  # noqa: E402

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

LONG = "Este e um paragrafo de teste com varias linhas para verificar o reflow do texto editado."


@pytest.fixture()
def page():
    doc = fitz.open()
    p = doc.new_page()
    p.insert_textbox(fitz.Rect(72, 100, 300, 200), LONG, fontsize=12, fontname="tiro")
    return p


def test_norm_family():
    assert textedit.norm_family("ABCDEF+Arial-BoldMT") == "arial"
    assert textedit.norm_family("TimesNewRomanPSMT") == "timesnewroman"
    assert textedit.norm_family("DejaVu Sans Book") == "dejavusans"


def test_block_detection(page):
    b = textedit.block_at(page, (100, 110))
    assert b and b["nlines"] >= 2 and b["text"].startswith("Este e um")
    assert textedit.block_at(page, (500, 700)) is None


def test_replace_block_reflows(page):
    b = textedit.block_at(page, (100, 110))
    textedit.replace_block(page, b, "Texto novo com acentuação: ação.", bold=True, align="center")
    text = page.get_text()
    assert "acentuação" in text and "reflow" not in text


def test_replace_block_overflow_raises(page):
    b = textedit.block_at(page, (100, 110))
    with pytest.raises(ValueError):
        textedit.replace_block(page, b, "palavra " * 5000)


def test_embedded_font_is_reused(tmp_path):
    ttf = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not ttf.exists():
        pytest.skip("DejaVu não instalada")
    doc = fitz.open()
    p = doc.new_page()
    p.insert_font(fontname="dj", fontfile=str(ttf))
    p.insert_textbox(fitz.Rect(72, 100, 300, 200), "Texto em DejaVu embutida", fontsize=12, fontname="dj")
    b = textedit.block_at(p, (100, 110))
    textedit.replace_block(p, b, "Outro texto: ação")
    assert any("DejaVu" in f[3] for f in p.get_fonts())


def test_annotations_roundtrip(page):
    annots.add_line(page, (50, 300), (200, 350), (1, 0, 0), 2, arrow=True)
    annots.add_shape(page, (50, 380, 200, 440), "rect", (0, 0, 1), 2, fill=True)
    annots.add_shape(page, (220, 380, 300, 440), "ellipse", (0, 0.6, 0), 2)
    annots.add_ink(page, [[(50, 460), (80, 480), (120, 455)]], (0, 0, 0), 2)
    annots.add_note(page, (400, 300), "Comentário")
    annots.add_freetext(page, (300, 500, 450, 540), "Caixa", 11, (0, 0, 0))
    kinds = sorted(annots.describe(a) for a in page.annots())
    assert kinds == ["Caixa de texto", "Desenho", "Elipse", "Linha/seta", "Nota", "Retângulo"]
    a = annots.annot_at(page, (400, 305))
    assert annots.describe(a) == "Nota" and annots.editable_text(a)
    annots.set_text(a, "Editado")
    assert a.info["content"] == "Editado"
    page.delete_annot(a)
    assert len(list(page.annots())) == 5


def test_digital_signature_flow(page, tmp_path):
    pfx = tmp_path / "c.pfx"
    signing.create_self_signed(str(pfx), "1234", "Fulano de Tal", "f@x.com")
    base = page.parent.tobytes()
    out = tmp_path / "s.pdf"
    signing.sign_pdf(base, str(out), str(pfx), "1234", reason="Teste", visible=True,
                     page_index=0, box=(300, 50, 520, 120))
    (r,) = signing.verify(out.read_bytes())
    assert r["intact"] and r["valid"] and not r["trusted"] and r["reason"] == "Teste"

    out2 = tmp_path / "s2.pdf"  # segunda assinatura preserva a primeira
    signing.sign_pdf(out.read_bytes(), str(out2), str(pfx), "1234")
    assert [x["intact"] for x in signing.verify(out2.read_bytes())] == [True, True]

    raw = bytearray(out.read_bytes())  # adulteração do conteúdo é detectada
    i = raw.find(b"Este e um")
    raw[i:i + 4] = b"XXXX"
    assert signing.verify(bytes(raw))[0]["intact"] is False


def test_wrong_certificate_password(page, tmp_path):
    pfx = tmp_path / "c.pfx"
    signing.create_self_signed(str(pfx), "1234", "Fulano")
    with pytest.raises(ValueError):
        signing.sign_pdf(page.parent.tobytes(), str(tmp_path / "x.pdf"), str(pfx), "errada")


def _line_page():
    import fitz
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "Você pode usar o videogame, de PC, desde que você tenha permissão.", fontsize=12, fontname="helv")
    p.insert_text((72, 118), "Segunda linha intacta aqui.", fontsize=12, fontname="helv")
    return d, p


def test_word_replace_keeps_rest():
    import fitz
    d, p = _line_page()
    w = textedit.word_at(p, fitz.Point(72 + 130, 96))
    assert w and w["text"] == "videogame" and w["tail"][0]["text"] == ","
    textedit.replace_word(p, w, "games de")
    txt = p.get_text()
    assert "games de" in txt and "videogame" not in txt
    assert ", de PC, desde que você tenha permissão." in txt
    assert "Segunda linha intacta aqui." in txt


def test_word_overflow_and_rotation():
    import fitz
    d, p = _line_page()
    w = textedit.word_at(p, fitz.Point(72 + 130, 96))
    with pytest.raises(ValueError):
        textedit.replace_word(p, w, "x" * 120)
    with pytest.raises(ValueError):
        textedit.replace_word(p, w, "   ")
    p.set_rotation(90)
    assert textedit.word_at(p, fitz.Point(100, 100)) is None


def test_word_editor_ui(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QLineEdit
    import viewer
    app = QApplication.instance() or QApplication([])
    d, p = _line_page()
    v = viewer.PdfView(d, None)
    v.resize(900, 700); v.show(); app.processEvents()
    v.set_tool("edittext")
    v.on_hover(0, QPointF(150, 96))
    assert v.labels[0].para_hover is not None
    v.on_click(0, QPointF(200, 96))
    assert v._wordbar is not None and v.labels[0].word_sel is not None
    v._wordbar.findChild(QLineEdit).setText("Teste")
    v._wordbar.findChild(QLineEdit).returnPressed.emit()
    assert v._wordbar is None
    assert "Teste" in v.doc[0].get_text()
    assert v.modified
    v.modified = False
    v._autosave_timer.stop()
    v.close()
    v.deleteLater()


def test_word_family_and_exact_size():
    import fitz
    d, p = _line_page()
    w = textedit.word_at(p, fitz.Point(72 + 130, 96))
    textedit.replace_word(p, w, "Teste", family="serif")
    fonts = {s["font"] for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"] if s["text"].strip() == "Teste"}
    assert any("Times" in f or "tiro" in f.lower() for f in fonts), fonts
