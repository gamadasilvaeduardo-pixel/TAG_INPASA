# pdf_engine.py
# -*- coding: utf-8 -*-

import io
import base64
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm as U
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

import qrcode
from PIL import Image
from xml.sax.saxutils import escape as xml_escape

# =========================================================
# LOGO embutido (fallback)
# =========================================================
LOGO_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAARgAAAB4CAYAAACD9l0bAAAACXBIWXMAAAsSAAALEgHS3X78AAAB"
    "R0lEQVR4nO3QoQ2DQBBF0Rm3pQJzT3EoJ2C0ahC+2UCRQk0xJb3p2L8B3hYrxQAAAAAAAAAAAOAD"
    "8w2m2b1S3y1Qkjt3P7H9e3iP7WJQmPz9b7w1f8tWqQ7v8z4h3e+gNw7R5fQeD6w0fQdD6w0fQdD6"
    "w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w8cHAAAAAAAAAAAAAHB3"
    "+g3r8l22m7S3+o7c3n3r3mO9wAAAABJRU5ErkJggg=="
)

# =========================================================
# PRESETS (iguais ao print) — só SMALL e SQUARE
# =========================================================
DEFAULTS = {
    "small": {
    ...
    "tag_top_mm": 3.0
},

"square": {
    ...
    "tag_top_mm": 10.0
}
    "gap_mm": 0.5,
    "font_tag": "Helvetica-Bold",
    "font_foot": "Helvetica-Bold",

    # TAG 50x100 (2x5) — W=100 / H=50
    "small": {
        "cols": 2, "rows": 5,
        "W": 100.0, "H": 50.0, "footer": 15.0,
        "pad": 4.0, "thick": 1.0,
        "qr": 18.0, "qr_margin": 2.0,
        "logo_w": 50.0,
        "tag_fs_max": 32.0,   # do print
        "tag_fs_min": 14.0,   # do print
        "foot_fs_min": 8.0, "foot_fs_max": 14.0,
        # ✅ regra nova: topo do texto a 3mm da borda superior (não precisa offset)
    },

    # TAG QUADRADA (150x150)
    "square": {
        "cols": 1, "rows": 1,
        "W": 150.0, "H": 150.0, "footer": 46.0,
        "pad": 15.0, "thick": 1.8,
        "qr": 38.0, "qr_margin": 10.0,
        "logo_w": 85.0,
        "tag_fs_max": 52.0,   # do print
        "tag_fs_min": 22.0,   # do print
        "foot_fs_min": 8.0, "foot_fs_max": 20.0,
        "logo_between_left_and_qr": 1.0,
        # ✅ regra nova: topo do texto a 3mm da borda superior
    }
}

# =========================================================
# Helpers
# =========================================================
def safe_paragraph_text(s: str) -> str:
    return xml_escape(s or "")

def _clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))

def _string_width(text: str, font_name: str, font_size: float) -> float:
    return pdfmetrics.stringWidth(text or "", font_name, float(font_size))

def _fit_tag_font(tag_text: str, font_name: str, fs_max: float, fs_min: float, max_width_pt: float) -> float:
    """
    Sem truncar/sem "..."
    Só reduz fonte até caber na largura útil.
    """
    t = (tag_text or "").strip()
    if not t:
        return fs_min
    fs = float(fs_max)
    fs_min = float(fs_min)
    while fs > fs_min + 1e-9:
        if _string_width(t, font_name, fs) <= max_width_pt:
            return fs
        fs -= 0.5
    return fs_min

def _font_ascent_pt(font_name: str, font_size: float) -> float:
    """
    Retorna ascent em pontos (pt) para posicionar o TOPO do texto com precisão.
    """
    try:
        a = pdfmetrics.getAscent(font_name)  # em 1/1000 em
        return (a / 1000.0) * float(font_size)
    except Exception:
        # fallback razoável (Helvetica costuma ser ~0.72-0.75)
        return float(font_size) * 0.75

def qr_bytes(text, box_size=8, border=1):
    img = qrcode.make(
        text,
        box_size=box_size,
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

def load_logo_image():
    """
    - se existir LOGO_INPASA.png ao lado do pdf_engine.py, usa
    - senão, usa base64 fallback
    """
    here = Path(__file__).resolve().parent
    fpath = here / "LOGO_INPASA.png"
    if fpath.exists():
        try:
            img = Image.open(str(fpath)).convert("RGBA")
            bio = io.BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return bio
        except Exception:
            pass
    return io.BytesIO(base64.b64decode(LOGO_PNG_B64))

# =========================================================
# Desenho da etiqueta (igual sua lógica; TAG agora tem regra 3mm)
# =========================================================
def draw_one_label(c: canvas.Canvas, layout: dict, cfg: dict, tag_text: str, desc_text: str):
    W = layout["W"] * U
    H = layout["H"] * U
    foot = layout["footer"] * U
    pad = layout["pad"] * U
    qr_s = layout["qr"] * U
    qr_m = layout["qr_margin"] * U
    thick = layout["thick"] * U

    font_tag = cfg["font_tag"]
    font_foot = cfg["font_foot"]

    # Moldura + rodapé
    c.setLineWidth(thick)
    c.rect(0, 0, W, H)
    c.line(0, foot, W, foot)

    avail = H - foot

    # QR (direita)
    qx = W - qr_m - qr_s
    qy = foot + qr_m
    c.drawImage(ImageReader(qr_bytes(tag_text)), qx, qy, width=qr_s, height=qr_s, mask="auto")

    # ---------- TAG (REGRA NOVA):
    # topo do texto sempre a 3mm da borda superior da etiqueta
    center_x = W / 2.0

    # largura útil: não encosta na borda
    max_w = W - (2.0 * pad)

    tag_fs = _fit_tag_font(
        tag_text,
        font_tag,
        float(layout.get("tag_fs_max", 32.0)),
        float(layout.get("tag_fs_min", 14.0)),
        max_w
    )

    c.setFont(font_tag, tag_fs)

    # topo do texto (ascent) a 3mm do topo da etiqueta
    top_target_y = H - (3.0 * U)  # 3mm da borda superior
    ascent = _font_ascent_pt(font_tag, tag_fs)
    ty = top_target_y - ascent  # baseline

    # trava pra não invadir rodapé e não sair pela borda
    ty_min = foot + 2.0 * U
    ty_max = H - (3.0 * U)  # baseline nunca pode passar do topo alvo
    ty = _clamp(ty, ty_min, ty_max)

    c.drawCentredString(center_x, ty, (tag_text or "").strip())

    # ---------- LOGO (igual seu script)
    logo_bio = load_logo_image()
    try:
        img = Image.open(logo_bio)
        lw = float(layout["logo_w"]) * U
        ar = img.height / img.width
        lh = lw * ar

        # área vertical útil (entre rodapé e o TAG)
        y_low = foot
        y_high = max(ty - 2 * U, y_low + 2 * U)
        max_h = max(4 * U, (y_high - y_low))

        if lh > max_h:
            scale = max_h / lh
            lw *= scale
            lh *= scale

        gap_txt = (2.0 if float(layout["W"]) <= 110.0 else 4.0) * U
        use_between = float(layout.get("logo_between_left_and_qr", 0.0)) >= 0.5
        if use_between:
            area_left = (thick / 2.0) + gap_txt
            area_right = qx - gap_txt
            usable = max(0.0, area_right - area_left)
            if usable >= lw:
                x_logo = area_left + (usable - lw) / 2.0
            else:
                x_logo = area_left
        else:
            x_logo = (W - lw) / 2.0

        # alinhar no centro vertical do QR
        qr_cy = qy + (qr_s / 2.0)
        y_logo = qr_cy - (lh / 2.0)
        y_logo = _clamp(y_logo, y_low + 1 * U, (y_high - lh))

        logo_bio.seek(0)
        c.drawImage(
            ImageReader(logo_bio),
            x_logo, y_logo,
            width=lw, height=lh,
            mask="auto",
            preserveAspectRatio=True
        )
    except Exception:
        pass

    # ---------- Rodapé (igual seu script)
    fw = W - 2 * pad
    fh = foot - 2 * pad
    if fh < 4:
        return

    desc_safe = safe_paragraph_text(desc_text)

    style = ParagraphStyle(
        "foot",
        fontName=font_foot,
        fontSize=10,
        leading=12,
        alignment=1,        # CENTER
        wordWrap="CJK",
        splitLongWords=1,
    )

    fs_max = float(layout.get("foot_fs_max", 14.0))
    fs_min = float(layout.get("foot_fs_min", 8.0))

    placed = False
    fs_try = fs_max
    while fs_try >= fs_min - 1e-9:
        style.fontSize = fs_try
        style.leading = fs_try + 2
        p = Paragraph(desc_safe, style)
        w, h = p.wrap(fw, fh)
        if h <= fh + 0.1:
            y = pad + (fh - h) / 2.0
            p.drawOn(c, pad, y)
            placed = True
            break
        fs_try -= 0.5

    if not placed:
        style.fontSize = fs_min
        style.leading = fs_min + 2
        p = Paragraph(desc_safe, style)
        w, h = p.wrap(fw, fh)
        y = pad + max(0, (fh - h) / 2.0)
        p.drawOn(c, pad, y)

# =========================================================
# API pro Streamlit
# =========================================================
def build_pdf_bytes_mixed(items):
    """
    items: list[(tag, desc, layout)]
      layout: "small" ou "square"
    Retorna bytes do PDF (A4 preenchendo grid).
    """
    cfg = {"font_tag": DEFAULTS["font_tag"], "font_foot": DEFAULTS["font_foot"]}

    small_items = []
    square_items = []

    for (tag, desc, layout) in (items or []):
        lay = (layout or "small").strip().lower()
        if lay == "square":
            square_items.append((tag, desc))
        else:
            small_items.append((tag, desc))

    A4W, A4H = 210.0, 297.0
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=(A4W * U, A4H * U))

    def _render_block(layout_key: str, block_items):
        layout = DEFAULTS[layout_key]
        cols, rows = int(layout["cols"]), int(layout["rows"])
        W, H = float(layout["W"]), float(layout["H"])
        g = float(DEFAULTS["gap_mm"])
        t = float(layout["thick"])

        stepX = W + (g + t)
        stepY = H + (g + t)
        need_w = cols * W + (cols - 1) * (g + t)
        need_h = rows * H + (rows - 1) * (g + t)
        ml = (A4W - need_w) / 2.0
        mt = (A4H - need_h) / 2.0

        idx = 0
        total = len(block_items)
        while idx < total:
            for r in range(rows):
                for cc in range(cols):
                    if idx >= total:
                        continue
                    x0 = (ml + cc * stepX) * U
                    y0 = (A4H - mt - H - r * stepY) * U
                    c.saveState()
                    c.translate(x0, y0)
                    tag, desc = block_items[idx]
                    draw_one_label(c, layout, cfg, str(tag).strip(), str(desc).strip())
                    idx += 1
                    c.restoreState()
            c.showPage()

    if small_items:
        _render_block("small", small_items)
    if square_items:
        _render_block("square", square_items)

    c.save()
    bio.seek(0)
    return bio.getvalue()

