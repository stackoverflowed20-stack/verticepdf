"""Edição por palavra em PDFs reais (Chrome, LibreOffice, wkhtmltopdf, ReportLab): nada além da palavra pode mudar."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz
import textedit  # noqa: E402

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("name", ["chrome", "lo", "wk", "rl"])
@pytest.mark.parametrize("new", ["Teste", "Instalação"])
def test_replace_every_word(name, new):
    raw = (DATA / f"{name}.pdf").read_bytes()
    words = fitz.open(stream=raw, filetype="pdf")[0].get_text("words")
    done = 0
    for wd in words:
        doc = fitz.open(stream=raw, filetype="pdf")
        page = doc[0]
        w = textedit.word_at(page, fitz.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2))
        if not w:
            continue
        cy = (w["y0"] + w["y1"]) / 2
        band = lambda p: sorted((x for x in p.get_text("words") if abs((x[1] + x[3]) / 2 - cy) < (w["y1"] - w["y0"]) * 0.5),  # noqa: E731
                                key=lambda x: x[0])
        before = band(fitz.open(stream=raw, filetype="pdf")[0])
        try:
            textedit.replace_word(page, w, new)
        except ValueError:
            continue  # recusa segura (invadiria coluna ao lado / margem)
        done += 1
        left = [x for x in before if x[2] <= w["x0"] + 0.8]
        tok = [x for x in before if x[0] - 0.8 <= w["x0"] < x[2]]
        pre = "".join(x[4] for x in (left if not tok or tok[0] in left else
                                     [x for x in before if x[2] <= tok[0][0] + 0.1]))
        off = max(tok[0][4].find(w["text"]), 0) if tok else 0
        flat = "".join(x[4] for x in before)
        exp = flat[:len(pre) + off] + new + flat[len(pre) + off + len(w["text"]):]
        assert "".join(x[4] for x in band(page)) == exp, (name, w["text"])
    assert done > 20
