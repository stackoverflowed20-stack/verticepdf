"""Testes do motor de PDF.  Rode:  pip install pytest  &&  pytest -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ops  # noqa: E402

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


@pytest.fixture()
def sample(tmp_path):
    doc = fitz.open()
    for i in range(6):
        doc.new_page().insert_text((72, 100), f"Pagina {i + 1} acao", fontsize=14)
    path = tmp_path / "a.pdf"
    doc.save(path)
    return path


def pages(p):
    with fitz.open(p) as d:
        return d.page_count


def test_parse_ranges():
    assert ops.parse_ranges("1-2, 4, 6-", 6) == [(0, 1), (3, 3), (5, 5)]
    for bad in ("", "0-2", "5-9", "abc", "4-2"):
        with pytest.raises(ValueError):
            ops.parse_ranges(bad, 6)


def test_groups_every():
    assert ops.groups_every(6, 4) == [(0, 3), (4, 5)]


def test_merge_split(sample, tmp_path):
    out = tmp_path / "m.pdf"
    ops.merge([str(sample)] * 2, str(out))
    assert pages(out) == 12
    parts = ops.split(str(sample), ops.parse_ranges("1-2,5-", 6), str(tmp_path / "o"))
    assert [pages(p) for p in parts] == [2, 2]


def test_encrypt_roundtrip(sample, tmp_path):
    enc, dec = tmp_path / "e.pdf", tmp_path / "d.pdf"
    ops.encrypt(str(sample), str(enc), "segredo")
    with pytest.raises(ops.PasswordRequired):
        ops.open_pdf(enc)
    ops.decrypt(str(enc), str(dec), "segredo")
    assert pages(dec) == 6


def test_compress_never_grows(sample, tmp_path):
    out = tmp_path / "c.pdf"
    before, after = ops.compress(str(sample), str(out), "forte")
    assert after <= before and pages(out) == 6


def test_edit_helpers(sample):
    page = ops.open_pdf(sample)[0]
    line = ops.line_at(page, (80, 95))
    assert line and "Pagina 1" in line["text"]
    ops.replace_line(page, line, "Texto novo")
    assert "Texto novo" in page.get_text() and "Pagina 1" not in page.get_text()
    ops.highlight(page, (60, 80, 300, 110))
    assert len(list(page.annots())) == 1


def test_build_from_items(sample, tmp_path):
    src = ops.open_pdf(sample)
    items = [{"src": src, "pno": 2, "rot": 90}, {"blank": (200, 300)}, {"src": src, "pno": 0, "rot": 0}]
    out = tmp_path / "o.pdf"
    ops.build_from_items(items, str(out))
    with fitz.open(out) as d:
        assert d.page_count == 3 and d[0].rotation == 90 and "Pagina 3" in d[0].get_text()


def test_create(tmp_path):
    data = ops.blank_pdf("letter", True, 2)
    with fitz.open("pdf", data) as d:
        assert d.page_count == 2 and d[0].rect.width > d[0].rect.height
