"""Ferramentas de página: marca d'água, cabeçalho/rodapé/numeração, recorte, extração, metadados."""
from __future__ import annotations

import math
from datetime import datetime

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

import ops

POSITIONS = ("tl", "tc", "tr", "bl", "bc", "br")
_FONTS = {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"}


def _targets(doc, spec: str | None) -> list[int]:
    if not spec or not spec.strip():
        return list(range(doc.page_count))
    out: list[int] = []
    for a, b in ops.parse_ranges(spec, doc.page_count):
        out += [i for i in range(a, b + 1) if i not in out]
    return out


def _text_width(text: str, size: float, bold=False, italic=False) -> float:
    return fitz.Font(_FONTS[(int(bold), int(italic))]).text_length(text, fontsize=size)


def _put(page, x: float, baseline: float, text: str, size: float, color, *, bold=False, italic=False,
         opacity: float = 1.0, angle: float = 0.0, overlay: bool = True) -> None:
    """Escreve `text` na posição EXIBIDA (x, baseline), respeitando a rotação da página."""
    pt = fitz.Point(x, baseline) * page.derotation_matrix
    kw = dict(fontsize=size, fontname=_FONTS[(int(bold), int(italic))], color=color,
              fill_opacity=opacity, overlay=overlay, rotate=page.rotation)
    if angle:
        pivot = fitz.Point(x, baseline) * page.derotation_matrix
        page.insert_text(pt, text, morph=(pivot, fitz.Matrix(angle)), **kw)   # +ângulo = anti-horário na tela
    else:
        page.insert_text(pt, text, **kw)


# --------------------------------------------------------------------------
# Marca d'água
# --------------------------------------------------------------------------
def add_watermark(doc, text: str, *, size: float = 72, color=(0.6, 0.6, 0.6), opacity: float = 0.25,
                  angle: float = 45, pages: str | None = None, behind: bool = False, bold: bool = True) -> int:
    text = text.strip()
    if not text:
        raise ValueError("Digite o texto da marca d'água.")
    n = 0
    for i in _targets(doc, pages):
        page = doc[i]
        r = page.rect
        w = _text_width(text, size, bold)
        # centraliza o texto girado no meio da página (a base fica 0,35·tamanho abaixo do centro óptico)
        cx, cy = r.x0 + r.width / 2, r.y0 + r.height / 2
        a = math.radians(angle)
        x = cx - (w / 2) * math.cos(a) - (size * 0.35) * math.sin(a)
        y = cy + (w / 2) * math.sin(a) + (size * 0.35) * math.cos(a)
        _put(page, x, y, text, size, color, bold=bold, opacity=opacity, angle=angle, overlay=not behind)
        n += 1
    return n


# --------------------------------------------------------------------------
# Cabeçalho, rodapé e numeração
# --------------------------------------------------------------------------
def expand(template: str, n: int, total: int, filename: str = "") -> str:
    return (template.replace("{n}", str(n)).replace("{total}", str(total))
            .replace("{data}", datetime.now().strftime("%d/%m/%Y")).replace("{arquivo}", filename))


def add_header_footer(doc, texts: dict[str, str], *, size: float = 10, color=(0, 0, 0), margin: float = 28,
                      pages: str | None = None, start: int = 1, filename: str = "", bold=False) -> int:
    """texts: {'tl','tc','tr','bl','bc','br': modelo}. Modelos aceitam {n}, {total}, {data}, {arquivo}."""
    texts = {k: v for k, v in texts.items() if k in POSITIONS and v and v.strip()}
    if not texts:
        raise ValueError("Preencha ao menos um campo de cabeçalho ou rodapé.")
    targets = _targets(doc, pages)
    total = start + len(targets) - 1
    for k, i in enumerate(targets):
        page = doc[i]
        r = page.rect
        for pos, tpl in texts.items():
            t = expand(tpl, start + k, total, filename)
            w = _text_width(t, size, bold)
            x = {"l": r.x0 + margin, "c": r.x0 + (r.width - w) / 2, "r": r.x1 - margin - w}[pos[1]]
            y = r.y0 + margin + size * 0.8 if pos[0] == "t" else r.y1 - margin
            _put(page, x, y, t, size, color, bold=bold)
    return len(targets)


# --------------------------------------------------------------------------
# Recorte, extração, inserção, metadados
# --------------------------------------------------------------------------
def crop_pages(doc, top: float, right: float, bottom: float, left: float, pages: str | None = None) -> int:
    n = 0
    for i in _targets(doc, pages):
        page = doc[i]
        r = page.rect
        box = fitz.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom)
        if box.width < 36 or box.height < 36:
            raise ValueError(f"As margens deixam a página {i + 1} pequena demais.")
        page.set_cropbox(box * page.derotation_matrix)
        n += 1
    return n


def extract_pages(doc, spec: str) -> bytes:
    out = fitz.open()
    for a, b in ops.parse_ranges(spec, doc.page_count):
        out.insert_pdf(doc, from_page=a, to_page=b)
    return out.tobytes(garbage=3, deflate=True)


def insert_pdf(doc, src_path: str, after: int, password: str | None = None) -> int:
    src = ops.open_pdf(src_path, password)
    doc.insert_pdf(src, start_at=after + 1)
    return src.page_count


def strip_metadata(doc) -> None:
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except Exception:  # noqa: BLE001
        pass
