import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import exporters


def make_doc(pages=2):
    d = fitz.open()
    for k in range(pages):
        p = d.new_page()
        p.insert_text((72, 100), f"Contrato numero {k + 1}", fontsize=16, fontname="hebo")
        p.insert_text((72, 140), "Valor 1234 e 5,50 & <teste>", fontsize=11)
    return d


def test_docx(tmp_path):
    docx = pytest.importorskip("docx")
    out = tmp_path / "a.docx"
    info = exporters.export_docx(make_doc(), str(out))
    assert info["paragraphs"] >= 2 and info["empty_pages"] == 0
    text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
    assert "Contrato numero 1" in text and "Contrato numero 2" in text and "& <teste>" in text


def test_docx_blank_page_keeps_count(tmp_path):
    d = make_doc(1)
    d.new_page()
    info = exporters.export_docx(d, str(tmp_path / "b.docx"))
    assert info["empty_pages"] == 1


def test_xlsx_text_fallback(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "a.xlsx"
    info = exporters.export_xlsx(make_doc(), str(out))
    assert info["sheets"] >= 1
    wb = openpyxl.load_workbook(str(out))
    cells = [c.value for ws in wb for row in ws.iter_rows() for c in row if c.value is not None]
    assert any("Contrato" in str(c) for c in cells)


def test_xlsx_table(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    d = fitz.open()
    p = d.new_page()
    y = 100
    for r in range(4):
        for c in range(3):
            p.draw_rect(fitz.Rect(72 + c * 90, y, 162 + c * 90, y + 24), color=(0, 0, 0), width=0.8)
            p.insert_text((78 + c * 90, y + 16), f"{r}{c}" if r else f"H{c}", fontsize=10)
        y += 24
    out = tmp_path / "t.xlsx"
    info = exporters.export_xlsx(d, str(out))
    wb = openpyxl.load_workbook(str(out))
    assert info["tables"] >= 1 and wb.sheetnames[0].startswith("Pág 1")


def test_pptx(tmp_path):
    pptx = pytest.importorskip("pptx")
    out = tmp_path / "a.pptx"
    info = exporters.export_pptx(make_doc(3), str(out), dpi=60)
    prs = pptx.Presentation(str(out))
    assert info["slides"] == 3 and len(prs.slides) == 3
    assert all(len(s.shapes) == 1 for s in prs.slides)


def test_images(tmp_path):
    files = exporters.export_images(make_doc(2), str(tmp_path / "pg.png"), "png", 50)
    assert [f.endswith(("_001.png", "_002.png")) for f in files] == [True, True]
    one = exporters.export_images(make_doc(1), str(tmp_path / "um.jpg"), "jpg", 50)
    assert one[0].endswith("um.jpg")
