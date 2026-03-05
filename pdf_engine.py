# pdf_engine.py
# -*- coding: utf-8 -*-

import io
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.utils import ImageReader

# ✅ QR compatível (ReportLab 4.4+)
from reportlab.graphics.barcode import qr as _qr
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing


# =========================================================
# CONFIG
# =========================================================

# TAG pequena (100x50): subir TAG (mm)
TAG_SMALL_Y_OFFSET_MM = 3.0  # ajuste aqui (ex: 4.0 sobe mais)

# Margens do A4 (mm)
PAGE_MARGIN_MM = 6.0

# Logo (arquivo)
HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE / "assets"
LOGO_CANDIDATES = [
    ASSETS_DIR / "logo.png",
    ASSETS_DIR / "logo.jpg",
    ASSETS_DIR / "logo.jpeg",
]

# Aparência
BORDER_LINE_WIDTH = 1.0

# QR sizes
QR_SMALL_MM = 34.0
QR_BIG_MM = 60.0

# Gaps internos
INNER_PAD_MM = 3.0
GAP_LOGO_QR_MM = 3.0

# Texto
TAG_FONT = "Helvetica-Bold"
DESC_FONT = "Helvetica"
TAG_FONT_MAX = 16
TAG_FONT_MIN = 6
DESC_FONT_MAX = 9
DESC_FONT_MIN = 5


# =========================================================
# Helpers
# =========================================================

def _try_load_logo_reader():
    for p in LOGO_CANDIDATES:
        if p.exists():
            try:
                return ImageReader(str(p))
            except Exception:
                pass
    return None


def _string_width(text: str, font_name: str, font_size: int) -> float:
    return pdfmetrics.stringWidth(text or "", font_name, font_size)


def _fit_font_size(text: str, font_name: str, max_size: int, min_size: int, max_width_pt: float) -> int:
    text = (text or "").strip()
    if not text:
        return min_size
    size = max_size
    while size > min_size:
        if _string_width(text, font_name, size) <= max_width_pt:
            return size
        size -= 1
    return min_size


def _draw_qr(c: canvas.Canvas, data: str, x: float, y: float, size_pt: float):
    """
    QR compatível com ReportLab 4.4+ (sem usar .scale() no widget).
    """
    qrw = _qr.QrCodeWidget(data or "")
    bounds = qrw.getBounds()
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    if w <= 0 or h <= 0:
        return

    sx = size_pt / w
    sy = size_pt / h

    d = Drawing(size_pt, size_pt)
    d.add(qrw)

    # Ajusta origem do widget (ele não nasce em 0,0)
    qrw.x = -bounds[0]
    qrw.y = -bounds[1]

    # Escala no drawing (não no widget)
    try:
        d.scale(sx, sy)
        renderPDF.draw(d, c, x, y)
    except Exception:
        # fallback ultra-compatível
        renderPDF.draw(d, c, x, y, showBoundary=False, transform=[sx, 0, 0, sy, 0, 0])


def _draw_border(c: canvas.Canvas, x: float, y: float, w: float, h: float):
    c.setLineWidth(BORDER_LINE_WIDTH)
    c.setStrokeColor(black)
    c.rect(x, y, w, h, stroke=1, fill=0)


# =========================================================
# Layout: SMALL (100x50mm)
# =========================================================

def _draw_label_small(c: canvas.Canvas, x: float, y: float, tag: str, desc: str, logo_reader):
    W = 100 * mm
    H = 50 * mm

    pad = INNER_PAD_MM * mm
    qr_size = QR_SMALL_MM * mm
    gap_logo_qr = GAP_LOGO_QR_MM * mm

    _draw_border(c, x, y, W, H)

    # QR direita, central vertical
    qr_x = x + W - pad - qr_size
    qr_y = y + (H - qr_size) / 2

    # área esquerda do QR
    left_area_x0 = x + pad
    left_area_x1 = qr_x - gap_logo_qr
    left_area_w = max(10, left_area_x1 - left_area_x0)

    # faixa descrição
    desc_band_h = 16 * mm
    desc_x = x + pad
    desc_y = y + pad
    desc_w = W - 2 * pad

    tag_txt = (tag or "").strip().upper()
    desc_txt = (desc or "").strip().upper()

    # TAG topo (subida pelo offset)
    tag_band_top = y + H - pad
    tag_y = tag_band_top - 7.5 * mm + (TAG_SMALL_Y_OFFSET_MM * mm)
    tag_max_w = W - 2 * pad

    tag_fs = _fit_font_size(tag_txt, TAG_FONT, TAG_FONT_MAX, TAG_FONT_MIN, tag_max_w)
    c.setFont(TAG_FONT, tag_fs)
    c.setFillColor(black)
    c.drawCentredString(x + W / 2, tag_y, tag_txt)

    # descrição (até 2 linhas)
    desc_fs = _fit_font_size(desc_txt, DESC_FONT, DESC_FONT_MAX, DESC_FONT_MIN, desc_w)
    c.setFont(DESC_FONT, desc_fs)

    words = desc_txt.split()
    line1 = ""
    line2 = ""
    for w_ in words:
        test = (line1 + " " + w_).strip()
        if _string_width(test, DESC_FONT, desc_fs) <= desc_w:
            line1 = test
        else:
            test2 = (line2 + " " + w_).strip()
            if _string_width(test2, DESC_FONT, desc_fs) <= desc_w:
                line2 = test2
            else:
                break

    line_gap = (desc_fs + 1)
    c.drawString(desc_x, desc_y + line_gap, line1)
    if line2:
        c.drawString(desc_x, desc_y, line2)

    # Logo (se existir) — na área esquerda, acima da descrição
    if logo_reader:
        logo_area_y0 = y + desc_band_h + pad
        logo_area_y1 = y + H - (10 * mm)
        logo_area_h = max(10, logo_area_y1 - logo_area_y0)

        logo_h = min(logo_area_h, 18 * mm)
        logo_w = left_area_w * 0.95

        lx = left_area_x0 + (left_area_w - logo_w) / 2
        ly = logo_area_y0 + (logo_area_h - logo_h) / 2

        try:
            c.drawImage(
                logo_reader,
                lx, ly,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    _draw_qr(c, tag_txt, qr_x, qr_y, qr_size)


# =========================================================
# Layout: BIG (150x150mm)
# =========================================================

def _draw_label_big(c: canvas.Canvas, x: float, y: float, tag: str, desc: str, logo_reader):
    W = 150 * mm
    H = 150 * mm

    pad = INNER_PAD_MM * mm
    qr_size = QR_BIG_MM * mm
    gap_logo_qr = GAP_LOGO_QR_MM * mm

    _draw_border(c, x, y, W, H)

    # QR topo direito
    qr_x = x + W - pad - qr_size
    qr_y = y + H - pad - qr_size

    # área esquerda do QR
    left_area_x0 = x + pad
    left_area_x1 = qr_x - gap_logo_qr
    left_area_w = max(10, left_area_x1 - left_area_x0)

    tag_txt = (tag or "").strip().upper()
    desc_txt = (desc or "").strip().upper()

    # TAG topo
    tag_max_w = W - 2 * pad
    tag_fs = _fit_font_size(tag_txt, TAG_FONT, 22, 8, tag_max_w)
    c.setFont(TAG_FONT, tag_fs)
    c.drawCentredString(x + W / 2, y + H - pad - (8 * mm), tag_txt)

    # Logo (se existir)
    if logo_reader:
        logo_area_y0 = y + H - pad - qr_size
        logo_area_y1 = y + H - pad - (18 * mm)
        if logo_area_y1 < logo_area_y0:
            logo_area_y0, logo_area_y1 = logo_area_y1, logo_area_y0

        logo_area_h = max(10, logo_area_y1 - logo_area_y0)
        logo_h = min(logo_area_h, 30 * mm)
        logo_w = left_area_w * 0.95

        lx = left_area_x0 + (left_area_w - logo_w) / 2
        ly = logo_area_y0 + (logo_area_h - logo_h) / 2

        try:
            c.drawImage(
                logo_reader,
                lx, ly,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # Descrição (até 4 linhas)
    desc_area_x = x + pad
    desc_area_y = y + pad
    desc_area_w = W - 2 * pad
    desc_area_h = H - (qr_size + 3 * pad + 20 * mm)

    desc_fs = _fit_font_size(desc_txt, DESC_FONT, 12, 7, desc_area_w)
    c.setFont(DESC_FONT, desc_fs)

    words = desc_txt.split()
    lines = []
    cur = ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if _string_width(test, DESC_FONT, desc_fs) <= desc_area_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w_
        if len(lines) >= 4:
            break
    if cur and len(lines) < 4:
        lines.append(cur)

    line_gap = desc_fs + 2
    start_y = desc_area_y + (min(desc_area_h, (len(lines) * line_gap)) - line_gap)
    for i, line in enumerate(lines):
        yy = start_y - i * line_gap
        if yy < desc_area_y:
            break
        c.drawString(desc_area_x, yy, line)

    _draw_qr(c, tag_txt, qr_x, qr_y, qr_size)


# =========================================================
# PDF builder (mixed)
# =========================================================

def build_pdf_bytes_mixed(items):
    """
    items: list of tuples -> (tag, desc, layout)
      layout: "small" or "big"
    Retorna bytes do PDF.
    """
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)

    logo_reader = _try_load_logo_reader()

    page_w, page_h = A4
    margin = PAGE_MARGIN_MM * mm

    # grid small: 2 col x 5 rows
    small_w = 100 * mm
    small_h = 50 * mm
    cols = 2
    rows = 5
    gap_x = (page_w - 2 * margin - cols * small_w) / max(1, (cols - 1))
    gap_y = (page_h - 2 * margin - rows * small_h) / max(1, (rows - 1))
    gap_x = max(0, gap_x)
    gap_y = max(0, gap_y)

    # big: 1 por página, centralizado
    big_w = 150 * mm
    big_h = 150 * mm

    def new_page():
        c.showPage()

    # slots small
    small_slots = []
    for r in range(rows):
        for col in range(cols):
            x = margin + col * (small_w + gap_x)
            y = page_h - margin - (r + 1) * small_h - r * gap_y
            small_slots.append((x, y))

    slot_i = 0
    small_page_open = False

    for (tag, desc, layout) in (items or []):
        layout = (layout or "small").strip().lower()

        if layout == "big":
            if small_page_open:
                new_page()
                small_page_open = False
                slot_i = 0

            bx = (page_w - big_w) / 2
            by = (page_h - big_h) / 2
            _draw_label_big(c, bx, by, tag, desc, logo_reader)
            new_page()
            continue

        # small
        if slot_i == 0:
            small_page_open = True

        if slot_i >= len(small_slots):
            new_page()
            slot_i = 0
            small_page_open = True

        x, y = small_slots[slot_i]
        _draw_label_small(c, x, y, tag, desc, logo_reader)
        slot_i += 1

    c.save()
    bio.seek(0)
    return bio.getvalue()
