"""Generates a cover image for the AI Crypto Trading Bot project. Same
dark/green visual language as the other bot covers, for brand consistency.
Deliberately shows ARCHITECTURE/FEATURES ONLY - no profit/loss numbers or
trade results, since this is a financial tool and fabricated performance
figures would be misleading."""

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = "C:/Windows/Fonts/"

BG1 = (7, 18, 23)
BG2 = (12, 36, 44)
GREEN = (86, 232, 150)
GREEN_DIM = (58, 150, 105)
AMBER = (240, 196, 64)
WHITE = (240, 246, 248)
MUTED = (146, 176, 182)
PANEL = (13, 40, 47)


def f(path, size):
    return ImageFont.truetype(FONTS + path, size)


def base_canvas(w, h):
    img = Image.new("RGB", (w, h), BG1)
    grad = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(grad)
    for y in range(h):
        gd.line([(0, y), (w, y)], fill=int(255 * (y / h) ** 0.7))
    grad = grad.filter(ImageFilter.GaussianBlur(2))
    panel_bg = Image.new("RGB", (w, h), BG2)
    img = Image.composite(panel_bg, img, grad)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    import random
    random.seed(11)
    for _ in range(40):
        x, y = random.randint(0, w), random.randint(0, h)
        r = random.randint(2, 4)
        gdraw.ellipse([x - r, y - r, x + r, y + r], fill=(*GREEN_DIM, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(1.2))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    return img


def make_cover(out_path):
    W = H = 1200
    img = base_canvas(W, H)
    draw = ImageDraw.Draw(img, "RGBA")

    f_h1 = f("impact.ttf", 80)
    f_sub = f("verdanab.ttf", 26)
    f_tag = f("consola.ttf", 20)
    f_chip = f("verdanab.ttf", 19)
    f_step = f("verdanab.ttf", 18)

    M = 70
    tag = "BINANCE SPOT \u00b7 AUTOMATED"
    tw_tag = draw.textlength(tag, font=f_tag)
    draw.text((W - M - tw_tag, 50), tag, font=f_tag, fill=MUTED)

    draw.text((M, 70), "AI CRYPTO", font=f_h1, fill=WHITE)
    draw.text((M, 160), "TRADING BOT", font=f_h1, fill=GREEN)

    draw.text((M, 270), "Scans, enters, protects, and exits positions ", font=f_sub, fill=AMBER)
    draw.text((M, 305), "on its own, with risk management built in.", font=f_sub, fill=MUTED)

    # Pipeline: SCAN -> SCORE -> ENTER -> PROTECT -> EXIT
    fy = 460
    xs = [150, 350, 550, 790, 1030]
    labels = ["SCAN", "SCORE", "ENTER", "PROTECT", "EXIT"]
    r = 68
    for i, (x, lab) in enumerate(zip(xs, labels)):
        active = i in (0, 4)
        fill = (*GREEN, 255) if active else (*PANEL, 255)
        outline = GREEN if active else GREEN_DIM
        draw.ellipse([x - r, fy - r, x + r, fy + r], outline=outline, width=3, fill=fill)
        tw_ = draw.textlength(lab, font=f_step)
        col = BG1 if active else WHITE
        draw.text((x - tw_ / 2, fy - 9), lab, font=f_step, fill=col)
        if i < len(xs) - 1:
            x0 = x + r
            x1 = xs[i + 1] - r
            draw.line([(x0, fy), (x1, fy)], fill=GREEN_DIM, width=3)

    chips = ["RSI / MFI / ATR", "OCO STOP-LOSS", "TELEGRAM ALERTS", "NEWS SANITY CHECK", "DAILY LOSS LIMIT"]
    cx = M
    cyy = 620
    for c in chips:
        tw_ = draw.textlength(c, font=f_chip)
        pad = 18
        if cx + tw_ + 2 * pad > W - M:
            cx = M
            cyy += 60
        draw.rounded_rectangle([cx, cyy, cx + tw_ + 2 * pad, cyy + 46], radius=23, outline=GREEN_DIM, width=2)
        draw.text((cx + pad, cyy + 11), c, font=f_chip, fill=GREEN)
        cx += tw_ + 2 * pad + 18

    py = H - 150
    f_name = f("verdanab.ttf", 22)
    draw.text((M, py), "Built by Muhammad Bilal", font=f_name, fill=WHITE)

    note = "Architecture demo - no performance figures shown. Trading involves risk."
    f_note = f("consolab.ttf", 15)
    draw.text((M, py + 40), note, font=f_note, fill=MUTED)

    img.save(out_path, "PNG")
    print("saved", out_path, img.size)


if __name__ == "__main__":
    make_cover("Project_Cover_TradingBot.png")
