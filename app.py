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

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing


# =========================================================
# CONFIG (ajuste fino aqui)
# =========================================================

# TAG pequena (100x50): subir TAG um pouco (mm)
TAG_SMALL_Y_OFFSET_MM = 3.0  # <<<<< AQUI você sobe/baixa (3mm é um bom começo)

# Margens do A4 (mm)
PAGE_MARGIN_MM = 6.0

# Logo (arquivo)
HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE / "assets"

# Tenta em ordem
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

# Limites de fonte
TAG_FONT_MAX = 16
TAG_FONT_MIN = 6

DESC_FONT_MAX = 9
DESC_FONT_MIN = 5


# =========================================================
# Helpers
# =========================================================

def _try_load_logo_reader():
    """Carrega logo de assets/logo.(png|jpg|jpeg). Retorna ImageReader ou None."""
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
    """Retorna maior font_size que cabe no max_width_pt."""
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
    """Desenha QR code quadrado (size_pt x size_pt)."""
    qr = QrCodeWidget(data or "")
    bounds = qr.getBounds()
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    if w <= 0 or h <= 0:
        return
    d = Drawing(size_pt, size_pt)
    # escala QR para caber no quadrado
    d.add(qr)
    qr.scale(size_pt / w, size_pt / h)
    renderPDF.draw(d, c, x, y)


def _draw_border(c: canvas.Canvas, x: float, y: float, w: float, h: float):
    c.setLineWidth(BORDER_LINE_WIDTH)
    c.setStrokeColor(black)
    c.rect(x, y, w, h, stroke=1, fill=0)


# =========================================================
# Layout: SMALL (100x50mm)
# =========================================================

def _draw_label_small(c: canvas.Canvas, x: float, y: float, tag: str, desc: str, logo_reader):
    """
    Label 100x50mm:
    - TAG no topo (centralizada) com offset para subir
    - QR na direita
    - Logo à esquerda do QR (se existir)
    - Descrição embaixo (faixa inferior)
    """
    W = 100 * mm
    H = 50 * mm

    pad = INNER_PAD_MM * mm
    qr_size = QR_SMALL_MM * mm
    gap_logo_qr = GAP_LOGO_QR_MM * mm

    # borda
    _draw_border(c, x, y, W, H)

    # áreas
    # QR à direita, centralizado verticalmente
    qr_x = x + W - pad - qr_size
    qr_y = y + (H - qr_size) / 2

    # área à esquerda do QR (logo + respiros)
    left_area_x0 = x + pad
    left_area_x1 = qr_x - gap_logo_qr
    left_area_w = max(10, left_area_x1 - left_area_x0)

    # faixa de descrição (parte de baixo)
    desc_band_h = 16 * mm
    desc_x = x + pad
    desc_y = y + pad
    desc_w = W - 2 * pad
    desc_h = desc_band_h - pad

    # TAG (topo)
    tag_band_top = y + H - pad
    tag_y = tag_band_top - 7.5 * mm + (TAG_SMALL_Y_OFFSET_MM * mm)  # <<< sobe aqui
    tag_max_w = W - 2 * pad

    tag_txt = (tag or "").strip().upper()
    desc_txt = (desc or "").strip().upper()

    # TAG font auto-fit
    tag_fs = _fit_font_size(tag_txt, TAG_FONT, TAG_FONT_MAX, TAG_FONT_MIN, tag_max_w)
    c.setFont(TAG_FONT, tag_fs)
    c.setFillColor(black)
    c.drawCentredString(x + W / 2, tag_y, tag_txt)

    # Descrição: 1–2 linhas simples com corte (sem quebrar demais)
    # (para não complicar, fazemos 2 linhas no máximo)
    c.setFont(DESC_FONT, DESC_FONT_MAX)
    # reduz se muito grande
    desc_fs = _fit_font_size(desc_txt, DESC_FONT, DESC_FONT_MAX, DESC_FONT_MIN, desc_w)
    c.setFont(DESC_FONT, desc_fs)

    # quebra em até 2 linhas por largura
    words = desc_txt.split()
    line1 = ""
    line2 = ""
    for w in words:
        test = (line1 + " " + w).strip()
        if _string_width(test, DESC_FONT, desc_fs) <= desc_w:
            line1 = test
        else:
            # vai pra linha2
            test2 = (line2 + " " + w).strip()
            if _string_width(test2, DESC_FONT, desc_fs) <= desc_w:
                line2 = test2
            else:
                # corta o restante
                break

    # posicionamento das linhas
    # escreve da base pra cima um pouquinho
    line_gap = (desc_fs + 1)
    c.drawString(desc_x, desc_y + line_gap, line1)
    if line2:
        c.drawString(desc_x, desc_y, line2)

    # Logo (se existir) — centralizado na área esquerda (acima da descrição)
    if logo_reader:
        # área disponível para logo: do topo até acima da faixa descrição
        logo_area_y0 = y + desc_band_h + pad
        logo_area_y1 = y + H - (10 * mm)  # respiro do topo (não encostar na TAG)
        logo_area_h = max(10, logo_area_y1 - logo_area_y0)

        # Queremos o logo cabendo nesse retângulo
        # Define um tamanho alvo (altura manda)
        logo_h = min(logo_area_h, 18 * mm)
        logo_w = left_area_w * 0.95  # quase toda largura

        # Centraliza
        lx = left_area_x0 + (left_area_w - logo_w) / 2
        ly = logo_area_y0 + (logo_area_h - logo_h) / 2

        try:
            c.drawImage(
                logo_reader,
                lx, ly,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True,
                anchor='c',
                mask="auto",
            )
        except Exception:
            pass

    # QR
    _draw_qr(c, tag_txt, qr_x, qr_y, qr_size)


# =========================================================
# Layout: BIG (150x150mm)
# =========================================================

def _draw_label_big(c: canvas.Canvas, x: float, y: float, tag: str, desc: str, logo_reader):
    """
    Label 150x150mm:
    - TAG topo central
    - QR direita
    - Logo à esquerda do QR
    - Descrição embaixo (2–3 linhas)
    """
    W = 150 * mm
    H = 150 * mm

    pad = INNER_PAD_MM * mm
    qr_size = QR_BIG_MM * mm
    gap_logo_qr = GAP_LOGO_QR_MM * mm

    _draw_border(c, x, y, W, H)

    qr_x = x + W - pad - qr_size
    qr_y = y + H - pad - qr_size  # QR no topo direito

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

    # Logo (se existir) — grande e bem visível
    if logo_reader:
        logo_area_y0 = y + H - pad - qr_size  # abaixo do QR
        logo_area_y1 = y + H - pad - (18 * mm)  # abaixo da TAG
        # se inverter, corrige
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
                anchor='c',
                mask="auto",
            )
        except Exception:
            pass

    # Descrição (parte inferior)
    desc_area_x = x + pad
    desc_area_y = y + pad
    desc_area_w = W - 2 * pad
    desc_area_h = H - (qr_size + 3 * pad + 20 * mm)

    # fonte auto-fit por largura
    desc_fs = _fit_font_size(desc_txt, DESC_FONT, 12, 7, desc_area_w)
    c.setFont(DESC_FONT, desc_fs)

    # quebra em até 4 linhas simples
    words = desc_txt.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if _string_width(test, DESC_FONT, desc_fs) <= desc_area_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= 4:
            break
    if cur and len(lines) < 4:
        lines.append(cur)

    # desenha de cima pra baixo dentro da área
    line_gap = desc_fs + 2
    start_y = desc_area_y + (min(desc_area_h, (len(lines) * line_gap)) - line_gap)
    for i, line in enumerate(lines):
        yy = start_y - i * line_gap
        if yy < desc_area_y:
            break
        c.drawString(desc_area_x, yy, line)

    # QR topo direito
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

    # grid small: 2 col x 5 rows = 10 por página
    small_w = 100 * mm
    small_h = 50 * mm
    cols = 2
    rows = 5
    gap_x = (page_w - 2 * margin - cols * small_w) / max(1, (cols - 1))
    gap_y = (page_h - 2 * margin - rows * small_h) / max(1, (rows - 1))

    # defensivo: se gap ficar negativo, zera
    gap_x = max(0, gap_x)
    gap_y = max(0, gap_y)

    # big: 1 por página, centralizado
    big_w = 150 * mm
    big_h = 150 * mm

    def new_page():
        c.showPage()

    # cursor para small
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
            # se tiver small pendente na página, fecha página
            if small_page_open:
                new_page()
                small_page_open = False
                slot_i = 0

            # desenha big no centro
            bx = (page_w - big_w) / 2
            by = (page_h - big_h) / 2
            _draw_label_big(c, bx, by, tag, desc, logo_reader)
            new_page()
            continue

        # SMALL
        if slot_i == 0:
            small_page_open = True

        if slot_i >= len(small_slots):
            # página cheia
            new_page()
            slot_i = 0
            small_page_open = True

        x, y = small_slots[slot_i]
        _draw_label_small(c, x, y, tag, desc, logo_reader)
        slot_i += 1

    # se terminou com smalls na página, finaliza sem página extra
    c.save()
    bio.seek(0)
    return bio.getvalue()
