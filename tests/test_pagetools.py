import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

import pagetools  # noqa: E402
import textedit  # noqa: E402


@pytest.fixture()
def doc():
    d = fitz.open()
    for k in range(4):
        p = d.new_page()
        p.insert_text((72, 120), f"Texto da página {k + 1} com algumas palavras para teste.", fontsize=12)
    return d


def test_watermark_is_centered_and_selectable(doc):
    assert pagetools.add_watermark(doc, "RASCUNHO", pages="2-3") == 2
    assert "RASCUNHO" not in doc[0].get_text()
    chars = "".join(c["c"] for b in doc[1].get_text("rawdict")["blocks"] if b["type"] == 0
                    for l in b["lines"] for s in l["spans"] for c in s["chars"])
    assert "RASCUNHO" in chars
    with pytest.raises(ValueError):
        pagetools.add_watermark(doc, "  ")


def test_header_footer_tokens_and_rotated_page(doc):
    doc[2].set_rotation(90)
    pagetools.add_header_footer(doc, {"bc": "Página {n} de {total}", "tl": "{arquivo}"}, filename="rel.pdf", start=5)
    assert "Página 5 de 8" in doc[0].get_text() and "Página 8 de 8" in doc[3].get_text()
    # na página girada o rodapé continua embaixo, no centro, lido na horizontal (como exibido)
    (w,) = [x for x in doc[2].get_text("words") if x[4] == "Página"]
    r = fitz.Rect(w[:4]) * doc[2].rotation_matrix
    assert r.y0 > doc[2].rect.height * 0.85 and abs((r.x0 + r.x1) / 2 - doc[2].rect.width / 2) < 80
    with pytest.raises(ValueError):
        pagetools.add_header_footer(doc, {})


def test_crop_extract_metadata(doc):
    pagetools.crop_pages(doc, 20, 10, 30, 10, pages="1")
    r = doc[0].rect
    assert abs(r.width - 575) < 0.5 and abs(r.height - 792) < 0.5
    with pytest.raises(ValueError):
        pagetools.crop_pages(doc, 500, 0, 400, 0)
    out = fitz.open(stream=pagetools.extract_pages(doc, "1,3-4"), filetype="pdf")
    assert out.page_count == 3
    doc.set_metadata({"author": "Fulano", "title": "Segredo"})
    pagetools.strip_metadata(doc)
    assert not any(doc.metadata.get(k) for k in ("author", "title"))


def test_find_replace_all(doc):
    res = textedit.replace_all(doc, "página", "folha")
    assert res["count"] == 4 and res["skipped"] == 0
    assert all(f"Texto da folha {k + 1} com algumas" in doc[k].get_text().replace("\n", " ") for k in range(4))


def test_find_replace_case_and_no_infinite_loop(doc):
    assert textedit.replace_all(doc, "Texto", "texto", case=True)["count"] == 4
    assert textedit.replace_all(doc, "PÁGINA", "x", case=True)["count"] == 0
    res = textedit.replace_all(doc, "a", "aa")        # o texto novo também contém a busca: não pode repetir
    assert 0 < res["count"] < 200
    assert textedit.replace_all(doc, "teste", "")["count"] == 4   # remover texto
    assert "teste" not in doc[0].get_text()
