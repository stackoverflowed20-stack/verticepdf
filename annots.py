"""Anotações: setas, linhas, formas, caneta, notas, caixas de texto e carimbos."""
from __future__ import annotations

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from ops import _pt, _rect

Color = tuple[float, float, float]


def add_line(page, p1, p2, color: Color, width: float, arrow: bool = False) -> None:
    a = page.add_line_annot(_pt(page, p1), _pt(page, p2))
    a.set_colors(stroke=color)
    a.set_border(width=width)
    if arrow:
        a.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
    a.update()


def add_shape(page, rect, kind: str, color: Color, width: float, fill: bool = False) -> None:
    r = _rect(page, rect)
    a = page.add_circle_annot(r) if kind == "ellipse" else page.add_rect_annot(r)
    a.set_colors(stroke=color, fill=color if fill else None)
    a.set_border(width=width)
    if fill:
        a.set_opacity(0.35)
    a.update()


def add_ink(page, strokes: list[list[tuple[float, float]]], color: Color, width: float) -> None:
    pts = [[tuple(_pt(page, p)) for p in s] for s in strokes if len(s) > 1]
    if not pts:
        return
    a = page.add_ink_annot(pts)
    a.set_colors(stroke=color)
    a.set_border(width=width)
    a.update()


def add_note(page, pt, text: str) -> None:
    a = page.add_text_annot(_pt(page, pt), text, icon="Note")
    a.set_colors(stroke=(1, 0.78, 0.1))
    a.set_info(title="Vértice PDF")
    a.update()


def add_freetext(page, rect, text: str, size: float, color: Color) -> None:
    a = page.add_freetext_annot(_rect(page, rect), text, fontsize=size, text_color=color,
                                fill_color=(1, 1, 0.85))
    a.set_border(width=1)
    a.update()


# ---- gerenciamento ----------------------------------------------------------
KIND = {fitz.PDF_ANNOT_TEXT: "Nota", fitz.PDF_ANNOT_FREE_TEXT: "Caixa de texto",
        fitz.PDF_ANNOT_LINE: "Linha/seta", fitz.PDF_ANNOT_SQUARE: "Retângulo",
        fitz.PDF_ANNOT_CIRCLE: "Elipse", fitz.PDF_ANNOT_INK: "Desenho",
        fitz.PDF_ANNOT_HIGHLIGHT: "Realce", fitz.PDF_ANNOT_STAMP: "Carimbo"}


def annot_at(page, pt):
    """Anotação sob o ponto (coords. exibidas) ou None; a mais recente tem prioridade."""
    p = _pt(page, pt)
    for a in reversed(list(page.annots())):
        if fitz.Rect(a.rect).irect.contains(p) or (fitz.Rect(a.rect) + (-4, -4, 4, 4)).contains(p):
            return a
    return None


def describe(a) -> str:
    return KIND.get(a.type[0], a.type[1])


def editable_text(a) -> bool:
    return a.type[0] in (fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_FREE_TEXT)


def set_text(a, text: str) -> None:
    a.set_info(content=text)
    a.update()


def set_stroke(a, color: Color) -> None:
    a.set_colors(stroke=color)
    a.update()
