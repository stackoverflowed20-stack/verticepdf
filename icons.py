"""Ícones vetoriais desenhados em código (consistentes em qualquer Windows/DPI)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def _line(p, *pts):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    p.drawPath(path)


def _poly(p, *pts):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)


def _save(p):
    p.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2); p.drawRect(QRectF(8, 3, 8, 6)); p.drawRect(QRectF(7, 13, 10, 8))

def _undo(p):
    _line(p, (9, 4), (5, 8), (9, 12))
    path = QPainterPath(QPointF(5, 8)); path.cubicTo(16, 5, 21, 10, 19, 17); p.drawPath(path)

def _redo(p):
    _line(p, (15, 4), (19, 8), (15, 12))
    path = QPainterPath(QPointF(19, 8)); path.cubicTo(8, 5, 3, 10, 5, 17); p.drawPath(path)

def _menu(p):
    _line(p, (4, 7), (20, 7)); _line(p, (4, 12), (20, 12)); _line(p, (4, 17), (20, 17))

def _print(p):
    p.drawRect(QRectF(7, 3, 10, 5)); p.drawRoundedRect(QRectF(3, 8, 18, 9), 2, 2); p.drawRect(QRectF(7, 14, 10, 7))

def _prev(p): _line(p, (15, 5), (8, 12), (15, 19))
def _next(p): _line(p, (9, 5), (16, 12), (9, 19))

def _zoom_out(p):
    p.drawEllipse(QPointF(11, 11), 6.5, 6.5); _line(p, (16, 16), (20, 20)); _line(p, (8, 11), (14, 11))

def _zoom_in(p):
    _zoom_out(p); _line(p, (11, 8), (11, 14))

def _fit(p):
    p.drawRect(QRectF(3, 5, 18, 14)); _line(p, (7, 12), (17, 12)); _line(p, (7, 12), (9.5, 9.5)); _line(p, (7, 12), (9.5, 14.5))
    _line(p, (17, 12), (14.5, 9.5)); _line(p, (17, 12), (14.5, 14.5))

def _select(p): _poly(p, (6, 3), (6, 18), (10, 14), (13, 20), (15, 19), (12, 13), (17, 13))
def _edit(p): _poly(p, (5, 19), (6, 14), (16, 4), (20, 8), (10, 18)); _line(p, (14, 6), (18, 10))
def _text(p): _line(p, (6, 6), (18, 6)); _line(p, (12, 6), (12, 19)); _line(p, (9, 19), (15, 19))
def _highlight(p): _poly(p, (5, 14), (14, 5), (19, 10), (10, 19), (6, 19)); _line(p, (4, 22), (20, 22))
def _erase(p): _poly(p, (4, 15), (12, 5), (20, 12), (13, 19), (8, 19)); _line(p, (9, 12), (16, 17))

def _sign(p):
    path = QPainterPath(QPointF(3, 16)); path.cubicTo(7, 3, 10, 4, 9, 12); path.cubicTo(8, 19, 13, 18, 15, 12)
    path.cubicTo(16, 9, 18, 14, 21, 11); p.drawPath(path); _line(p, (3, 21), (21, 21))

def _form(p): p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2); _line(p, (8, 12), (11, 15), (16, 9))
def _panel(p): p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2); _line(p, (9, 4), (9, 20))
def _info(p): p.drawEllipse(QPointF(12, 12), 9, 9); _line(p, (12, 11), (12, 17)); _line(p, (12, 7.5), (12, 7.6))

def _arrow(p):
    _line(p, (5, 19), (19, 5)); _line(p, (10, 5), (19, 5), (19, 14))

def _segment(p): _line(p, (5, 19), (19, 5))
def _rect(p): p.drawRect(QRectF(4, 6, 16, 12))
def _ellipse(p): p.drawEllipse(QPointF(12, 12), 8.5, 6.5)

def _ink(p):
    path = QPainterPath(QPointF(3, 15)); path.cubicTo(6, 4, 9, 4, 11, 12); path.cubicTo(13, 20, 17, 18, 21, 7); p.drawPath(path)

def _note(p):
    _poly(p, (4, 4), (20, 4), (20, 15), (14, 21), (4, 21)); _line(p, (14, 21), (14, 15), (20, 15)); _line(p, (8, 9), (16, 9)); _line(p, (8, 13), (12, 13))

def _freetext(p): p.drawRect(QRectF(3, 5, 18, 14)); _line(p, (8, 9), (16, 9)); _line(p, (12, 9), (12, 16))

def _stamp(p):
    _poly(p, (9, 4), (15, 4), (15, 9), (18, 13), (6, 13), (9, 9)); p.drawRect(QRectF(4, 16, 16, 4))

def _cert(p):
    p.drawEllipse(QPointF(12, 9), 6, 6); _line(p, (9, 14), (7, 21), (12, 18), (17, 21), (15, 14)); _line(p, (9.5, 9), (11.5, 11), (14.5, 7))

def _verify(p):
    _poly(p, (12, 3), (20, 6), (20, 12), (12, 21), (4, 12), (4, 6)); _line(p, (8.5, 11.5), (11, 14), (15.5, 8.5))


def _scan(p):
    for pts in (((4, 8), (4, 4), (8, 4)), ((16, 4), (20, 4), (20, 8)),
                ((20, 16), (20, 20), (16, 20)), ((8, 20), (4, 20), (4, 16))):
        _line(p, *pts)
    _line(p, (8, 10), (16, 10)); _line(p, (8, 14), (14, 14))

def _layers(p):
    _poly(p, (12, 3), (21, 8), (12, 13), (3, 8)); _line(p, (3, 12.5), (12, 17.5), (21, 12.5)); _line(p, (3, 17), (12, 22), (21, 17))

def _compress(p):
    _line(p, (6, 4), (12, 10), (18, 4)); _line(p, (6, 20), (12, 14), (18, 20)); _line(p, (4, 12), (20, 12))

def _plus(p): _line(p, (12, 5), (12, 19)); _line(p, (5, 12), (19, 12))

def _lock(p):
    p.drawRoundedRect(QRectF(5, 11, 14, 10), 2.5, 2.5)
    path = QPainterPath(QPointF(8, 11)); path.lineTo(8, 8); path.cubicTo(8, 2, 16, 2, 16, 8); path.lineTo(16, 11); p.drawPath(path)

def _pages(p): p.drawRoundedRect(QRectF(4, 3, 11, 14), 2, 2); p.drawRoundedRect(QRectF(9, 7, 11, 14), 2, 2)
def _folder(p): _poly(p, (3, 6), (9, 6), (11, 8.5), (21, 8.5), (21, 19), (3, 19))

def _home(p):
    _line(p, (3, 11), (12, 4), (21, 11)); _line(p, (5.5, 9.5), (5.5, 20), (18.5, 20), (18.5, 9.5)); _line(p, (10, 20), (10, 14), (14, 14), (14, 20))

def _close(p): _line(p, (6, 6), (18, 18)); _line(p, (18, 6), (6, 18))
def _search(p): p.drawEllipse(QPointF(11, 11), 6.5, 6.5); _line(p, (16, 16), (20, 20))
def _download(p): _line(p, (12, 4), (12, 15)); _line(p, (7, 11), (12, 16), (17, 11)); _line(p, (5, 20), (19, 20))


def _image(p):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2); p.drawEllipse(QPointF(9, 10), 2, 2); _line(p, (4, 18), (10, 13), (14, 17), (17, 14), (20, 17))

def _rotate_l(p):
    path = QPainterPath(QPointF(6, 9)); path.cubicTo(9, 4, 17, 4, 19, 11); path.cubicTo(20, 16, 15, 20, 10, 19); p.drawPath(path)
    _line(p, (3, 6), (6, 9), (10, 8))

def _rotate_r(p):
    path = QPainterPath(QPointF(18, 9)); path.cubicTo(15, 4, 7, 4, 5, 11); path.cubicTo(4, 16, 9, 20, 14, 19); p.drawPath(path)
    _line(p, (21, 6), (18, 9), (14, 8))

def _trash(p):
    _line(p, (4, 7), (20, 7)); _line(p, (9, 7), (9, 4), (15, 4), (15, 7)); _poly(p, (6, 7), (7, 20), (17, 20), (18, 7))
    _line(p, (10, 11), (10, 16)); _line(p, (14, 11), (14, 16))

def _split(p):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2); _line(p, (12, 3), (12, 21)); _line(p, (7, 12), (10, 12)); _line(p, (14, 12), (17, 12))

def _merge(p):
    p.drawRoundedRect(QRectF(3, 4, 8, 16), 2, 2); p.drawRoundedRect(QRectF(13, 4, 8, 16), 2, 2); _line(p, (9, 12), (15, 12))

def _to_image(p):
    p.drawRoundedRect(QRectF(4, 3, 14, 18), 2, 2); p.drawEllipse(QPointF(9, 9), 1.8, 1.8); _line(p, (5, 18), (10, 13), (13, 16), (16, 13))

def _to_text(p):
    p.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2); _line(p, (8, 8), (16, 8)); _line(p, (8, 12), (16, 12)); _line(p, (8, 16), (13, 16))

def _unlock(p):
    p.drawRoundedRect(QRectF(5, 11, 14, 9), 2, 2)
    path = QPainterPath(QPointF(8, 11)); path.lineTo(8, 8); path.cubicTo(8, 2, 16, 2, 16, 6); p.drawPath(path)

def _blank(p):
    _poly(p, (6, 3), (14, 3), (19, 8), (19, 21), (6, 21)); _line(p, (14, 3), (14, 8), (19, 8)); _line(p, (12.5, 12), (12.5, 18)); _line(p, (9.5, 15), (15.5, 15))

def _convert(p):
    _line(p, (4, 8), (18, 8)); _line(p, (14, 4), (18, 8), (14, 12)); _line(p, (20, 16), (6, 16)); _line(p, (10, 12), (6, 16), (10, 20))

def _watermark(p):
    p.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2); _line(p, (8, 16), (16, 8)); _line(p, (8, 12), (12, 8)); _line(p, (12, 16), (16, 12))

def _headfoot(p):
    p.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2); _line(p, (4, 8), (20, 8)); _line(p, (4, 16), (20, 16))

def _hash(p):
    _line(p, (9, 4), (7, 20)); _line(p, (17, 4), (15, 20)); _line(p, (4, 9), (20, 9)); _line(p, (4, 15), (20, 15))

def _crop(p):
    _line(p, (7, 2), (7, 17), (22, 17)); _line(p, (2, 7), (17, 7), (17, 22))

def _extract(p):
    _poly(p, (5, 3), (14, 3), (19, 8), (19, 21), (5, 21)); _line(p, (12, 17), (12, 11)); _line(p, (9, 14), (12, 11), (15, 14))

def _replace(p):
    p.drawEllipse(QPointF(10, 10), 5.5, 5.5); _line(p, (14, 14), (20, 20)); _line(p, (8, 10), (12, 10))

def _share(p):
    p.drawEllipse(QPointF(6, 12), 2.6, 2.6); p.drawEllipse(QPointF(18, 5.5), 2.6, 2.6); p.drawEllipse(QPointF(18, 18.5), 2.6, 2.6)
    _line(p, (8.3, 10.8), (15.7, 6.7)); _line(p, (8.3, 13.2), (15.7, 17.3))


def _clock(p):
    p.drawEllipse(QPointF(12, 12), 9, 9); _line(p, (12, 7), (12, 12), (16, 14))


def _gear(p):
    import math
    p.drawEllipse(QPointF(12, 12), 3, 3)
    for k in range(8):
        a = k * math.pi / 4
        _line(p, (12 + 6.2 * math.cos(a), 12 + 6.2 * math.sin(a)), (12 + 9 * math.cos(a), 12 + 9 * math.sin(a)))
    p.drawEllipse(QPointF(12, 12), 6.2, 6.2)


def _export(p):
    _line(p, (12, 15), (12, 4)); _line(p, (8, 8), (12, 4), (16, 8)); _line(p, (5, 12), (5, 20), (19, 20), (19, 12))


def _word(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2); _line(p, (7.5, 8.5), (9.7, 15.5), (12, 10), (14.3, 15.5), (16.5, 8.5))


def _excel(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2); _line(p, (8, 8), (16, 16)); _line(p, (16, 8), (8, 16))


def _ppt(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2); _line(p, (9.5, 16), (9.5, 8), (13, 8), (15, 9.8), (13, 12), (9.5, 12))


def _win_min(p): _line(p, (5, 12), (19, 12))
def _win_max(p): p.drawRect(QRectF(5.5, 5.5, 13, 13))


def _win_restore(p):
    p.drawRect(QRectF(5.5, 8.5, 10, 10)); _line(p, (8.5, 8.5), (8.5, 5.5), (18.5, 5.5), (18.5, 15.5), (15.5, 15.5))


def _broom(p):
    _line(p, (19, 3), (11, 12)); _poly(p, (11, 12), (5, 11), (3, 20), (13, 18))

_DRAW = {k[1:]: v for k, v in globals().items()
         if k.startswith("_") and callable(v) and k not in ("_line", "_poly")}


def render(name: str, color: str, px: int, pen: float = 1.8) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(px / 24, px / 24)
    p.setPen(QPen(QColor(color), pen, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    _DRAW[name](p)
    p.end()
    return pm


ICON_COLOR = "#3d4b5e"       # cor padrão dos ícones (muda com o tema)
ICON_DISABLED = "#b4bdca"
_KNOWN: dict[int, tuple[str, int]] = {}   # cacheKey do QIcon -> (nome, tamanho): permite recolorir ao trocar o tema


def set_icon_theme(color: str, disabled: str) -> None:
    global ICON_COLOR, ICON_DISABLED
    ICON_COLOR, ICON_DISABLED = color, disabled


def icon(name: str, size: int = 20, color: str | None = None) -> QIcon:
    ic = QIcon()
    for mode, state, col in ((QIcon.Normal, QIcon.Off, color or ICON_COLOR),
                             (QIcon.Disabled, QIcon.Off, ICON_DISABLED),
                             (QIcon.Normal, QIcon.On, "#ffffff")):
        ic.addPixmap(render(name, col, size * 2), mode, state)
    if color is None:
        _KNOWN[ic.cacheKey()] = (name, size)
    return ic


def refresh_icons(app) -> None:
    """Recolore todos os ícones padrão já aplicados a botões e ações (após trocar o tema)."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton
    seen: set[int] = set()
    cache: dict[int, QIcon] = {}

    def fresh(old: QIcon):
        info = _KNOWN.get(old.cacheKey())
        if info is None:
            return None
        if info not in cache:
            cache[info] = icon(*info)
        return cache[info]

    for w in app.allWidgets():
        objs = [w] if isinstance(w, QAbstractButton) else []
        objs += [a for a in w.actions()] if hasattr(w, "actions") else []
        for o in objs:
            if id(o) in seen:
                continue
            seen.add(id(o))
            new = fresh(o.icon())
            if new is not None:
                o.setIcon(new)
    for a in app.findChildren(QAction):
        if id(a) not in seen:
            seen.add(id(a))
            new = fresh(a.icon())
            if new is not None:
                a.setIcon(new)


def tile_pixmap(name: str, color: str, size: int = 44) -> QPixmap:
    """Ícone branco sobre um quadrado arredondado com leve degradê."""
    px = size * 2
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, px, px)
    base = QColor(color)
    grad.setColorAt(0, base.lighter(118))
    grad.setColorAt(1, base.darker(108))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(0, 0, px, px, px * 0.27, px * 0.27)
    p.end()
    glyph = render(name, "#ffffff", int(px * 0.58), 2.0)
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    off = (px - glyph.width()) // 2
    p.drawPixmap(off, off, glyph)
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


def soft_tile_pixmap(name: str, bg: str, fg: str, size: int = 40, radius: float = 0.25) -> QPixmap:
    """Ícone na cor de destaque sobre um quadrado arredondado de fundo suave."""
    px = size * 2
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(0, 0, px, px, px * radius, px * radius)
    p.end()
    glyph = render(name, fg, int(px * 0.5), 2.0)
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    off = (px - glyph.width()) // 2
    p.drawPixmap(off, off, glyph)
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


def color_dot(color: QColor, size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#8794a7"), 1))
    p.setBrush(color)
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.end()
    return QIcon(pm)


_BRAND_V = [(0.23, 0.27), (0.40, 0.27), (0.50, 0.58), (0.60, 0.27), (0.77, 0.27), (0.585, 0.76), (0.415, 0.76)]
_BRAND_FACET = [(0.50, 0.58), (0.585, 0.76), (0.415, 0.76)]


def brand_pixmap(size: int = 64) -> QPixmap:
    """Logotipo do Vértice PDF (mesma arte de assets/verticepdf.png)."""
    px = size * 2
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, px, px)
    grad.setColorAt(0, QColor("#2f6fe0"))
    grad.setColorAt(1, QColor("#174aa6"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(0, 0, px, px, px * 0.22, px * 0.22)

    def poly(points, color):
        path = QPainterPath(QPointF(points[0][0] * px, points[0][1] * px))
        for x, y in points[1:]:
            path.lineTo(x * px, y * px)
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)

    poly(_BRAND_V, "#ffffff")
    poly(_BRAND_FACET, "#9cc0ff")
    p.end()
    pm.setDevicePixelRatio(2)
    return pm
