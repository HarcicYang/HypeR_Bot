import asyncio
import os
import platform
import re
from io import BytesIO
from typing import Any

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_Font = ImageFont.ImageFont | ImageFont.FreeTypeFont

if platform.system() == "Windows":
    _WIN_FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    FONT_BOLD = os.path.join(_WIN_FONT_DIR, "msyhbd.ttc")
    FONT_REGULAR = os.path.join(_WIN_FONT_DIR, "msyh.ttc")
    FONT_MEDIUM = os.path.join(_WIN_FONT_DIR, "msyh.ttc")
else:
    FONT_BOLD = "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"
    FONT_REGULAR = "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"
    FONT_MEDIUM = "/usr/share/fonts/noto-cjk/NotoSansCJK-Medium.ttc"

_TWEMOJI_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "twemoji")
_TWEMOJI_CDN = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg"
_http_session: aiohttp.ClientSession | None = None
_emoji_img_cache: dict[str, tuple[Image.Image, int]] = {}


# -- SVG icon data from bili.html --

_SVG_VIEWS = {
    "viewBox": (0, 0, 20, 20),
    "paths": [
        "M10 4.040041666666666C7.897383333333334 4.040041666666666 6.061606666666667 4.147 4.765636666666667 4.252088333333334C3.806826666666667 4.32984 3.061106666666667 5.0637316666666665 2.9755000000000003 6.015921666666667C2.8803183333333333 7.074671666666667 2.791666666666667 8.471183333333332 2.791666666666667 9.998333333333333C2.791666666666667 11.525566666666668 2.8803183333333333 12.922083333333333 2.9755000000000003 13.9808C3.061106666666667 14.932983333333334 3.806826666666667 15.666916666666667 4.765636666666667 15.744683333333336C6.061611666666668 15.849716666666666 7.897383333333334 15.956666666666667 10 15.956666666666667C12.10285 15.956666666666667 13.93871666666667 15.849716666666666 15.234766666666667 15.74461666666667C16.193416666666668 15.66685 16.939000000000004 14.933216666666667 17.024583333333336 13.981216666666668C17.11975 12.922916666666667 17.208333333333332 11.526666666666666 17.208333333333332 9.998333333333333C17.208333333333332 8.470083333333333 17.11975 7.073818333333334 17.024583333333336 6.015513333333334C16.939000000000004 5.063538333333333 16.193416666666668 4.329865000000001 15.234766666666667 4.252118333333334C13.93871666666667 4.147016666666667 12.10285 4.040041666666666 10 4.040041666666666zM4.684808333333334 3.255365C6.001155 3.14862 7.864583333333334 3.0400416666666668 10 3.0400416666666668C12.13565 3.0400416666666668 13.999199999999998 3.148636666666667 15.315566666666667 3.2553900000000002C16.753416666666666 3.3720016666666672 17.890833333333333 4.483195 18.020583333333335 5.925965000000001C18.11766666666667 7.005906666666667 18.208333333333336 8.433 18.208333333333336 9.998333333333333C18.208333333333336 11.56375 18.11766666666667 12.990833333333335 18.020583333333335 14.0708C17.890833333333333 15.513533333333331 16.753416666666666 16.624733333333335 15.315566666666667 16.74138333333333C13.999199999999998 16.848116666666666 12.13565 16.95666666666667 10 16.95666666666667C7.864583333333334 16.95666666666667 6.001155 16.848116666666666 4.684808333333334 16.74135C3.246925 16.624666666666667 2.1091833333333335 15.513483333333333 1.9795 14.0708C1.8824166666666665 12.990833333333335 1.7916666666666667 11.56375 1.7916666666666667 9.998333333333333C1.7916666666666667 8.433 1.8824166666666665 7.005906666666667 1.9795 5.925965000000001C2.1091833333333335 4.483195 3.246925 3.372031666666666 4.684808333333334 3.255365z",
        "M12.23275 9.1962C12.851516666666667 9.553483333333332 12.851516666666667 10.44665 12.232683333333332 10.803866666666666L9.57975 12.335600000000001C8.960983333333335 12.692816666666667 8.1875 12.246250000000002 8.187503333333334 11.531733333333333L8.187503333333334 8.4684C8.187503333333334 7.753871666666667 8.960983333333335 7.307296666666667 9.57975 7.66456L12.23275 9.1962z",
    ],
    "evenodd": [True, False],
}

_SVG_LIKES = {
    "viewBox": (0, 0, 36, 36),
    "paths": [
        "M9.77234 30.8573V11.7471H7.54573C5.50932 11.7471 3.85742 13.3931 3.85742 15.425V27.1794C3.85742 29.2112 5.50932 30.8573 7.54573 30.8573H9.77234ZM11.9902 30.8573V11.7054C14.9897 10.627 16.6942 7.8853 17.1055 3.33591C17.2666 1.55463 18.9633 0.814421 20.5803 1.59505C22.1847 2.36964 23.243 4.32583 23.243 6.93947C23.243 8.50265 23.0478 10.1054 22.6582 11.7471H29.7324C31.7739 11.7471 33.4289 13.402 33.4289 15.4435C33.4289 15.7416 33.3928 16.0386 33.3215 16.328L30.9883 25.7957C30.2558 28.7683 27.5894 30.8573 24.528 30.8573H11.9911H11.9902Z",
    ],
    "evenodd": [True],
}

_SVG_COINS = {
    "viewBox": (0, 0, 28, 28),
    "paths": [
        "M14.045 25.5454C7.69377 25.5454 2.54504 20.3967 2.54504 14.0454C2.54504 7.69413 7.69377 2.54541 14.045 2.54541C20.3963 2.54541 25.545 7.69413 25.545 14.0454C25.545 17.0954 24.3334 20.0205 22.1768 22.1771C20.0201 24.3338 17.095 25.5454 14.045 25.5454ZM9.66202 6.81624H18.2761C18.825 6.81624 19.27 7.22183 19.27 7.72216C19.27 8.22248 18.825 8.62807 18.2761 8.62807H14.95V10.2903C17.989 10.4444 20.3766 12.9487 20.3855 15.9916V17.1995C20.3854 17.6997 19.9799 18.1052 19.4796 18.1052C18.9793 18.1052 18.5738 17.6997 18.5737 17.1995V15.9916C18.5667 13.9478 16.9882 12.2535 14.95 12.1022V20.5574C14.95 21.0577 14.5444 21.4633 14.0441 21.4633C13.5437 21.4633 13.1382 21.0577 13.1382 20.5574V12.1022C11.1 12.2535 9.52148 13.9478 9.51448 15.9916V17.1995C9.5144 17.6997 9.10883 18.1052 8.60856 18.1052C8.1083 18.1052 7.70273 17.6997 7.70265 17.1995V15.9916C7.71158 12.9487 10.0992 10.4444 13.1382 10.2903V8.62807H9.66202C9.11309 8.62807 8.66809 8.22248 8.66809 7.72216C8.66809 7.22183 9.11309 6.81624 9.66202 6.81624Z",
    ],
    "evenodd": [True],
}

_SVG_FAVS = {
    "viewBox": (0, 0, 28, 28),
    "paths": [
        "M19.8071 9.26152C18.7438 9.09915 17.7624 8.36846 17.3534 7.39421L15.4723 3.4972C14.8998 2.1982 13.1004 2.1982 12.4461 3.4972L10.6468 7.39421C10.1561 8.36846 9.25639 9.09915 8.19315 9.26152L3.94016 9.91102C2.63155 10.0734 2.05904 11.6972 3.04049 12.6714L6.23023 15.9189C6.96632 16.6496 7.29348 17.705 7.1299 18.7605L6.39381 23.307C6.14844 24.6872 7.62063 25.6614 8.84745 25.0119L12.4461 23.0634C13.4276 22.4951 14.6544 22.4951 15.6359 23.0634L19.2345 25.0119C20.4614 25.6614 21.8518 24.6872 21.6882 23.307L20.8703 18.7605C20.7051 17.705 21.0339 16.6496 21.77 15.9189L24.9597 12.6714C25.9412 11.6972 25.3687 10.0734 24.06 9.91102L19.8071 9.26152Z",
    ],
    "evenodd": [True],
}


# -- SVG path parser --


def _parse_svg_d(d: str) -> list[list[tuple[str, list[float]]]]:
    tokens = re.findall(r"[MmZzLlHhVvCcSsQqTtAa]|[\d.eE+-]+", d)
    subpaths: list[list[tuple[str, list[float]]]] = []
    current: list[tuple[str, list[float]]] = []
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        args: list[float] = []
        while i < len(tokens) and re.match(r"^[\d.eE+-]+$", tokens[i]):
            args.append(float(tokens[i]))
            i += 1
        current.append((cmd, args))
        if cmd.upper() == "Z":
            subpaths.append(current)
            current = []
    if current:
        subpaths.append(current)
    return subpaths


def _eval_cubic(
    cx: float, cy: float, x1: float, y1: float, x2: float, y2: float, ex: float, ey: float, steps: int = 12
):
    for s in range(1, steps + 1):
        t = s / steps
        u = 1 - t
        px = u**3 * cx + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * ex
        py = u**3 * cy + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * ey
        yield px, py


def _svg_path_to_polygons(path_d: str, scale: float, ox: float, oy: float) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    for subpath in _parse_svg_d(path_d):
        current: list[tuple[float, float]] = []
        cx = cy = sx = sy = 0.0
        for cmd, args in subpath:
            cmd_u = cmd.upper()
            if cmd_u == "M":
                if current:
                    polygons.append(current)
                    current = []
                cx = args[0] * scale + ox
                cy = args[1] * scale + oy
                sx, sy = cx, cy
                current.append((cx, cy))
            elif cmd_u == "L":
                for j in range(0, len(args), 2):
                    cx = args[j] * scale + ox
                    cy = args[j + 1] * scale + oy
                    current.append((cx, cy))
            elif cmd_u == "H":
                cx = args[0] * scale + ox
                current.append((cx, cy))
            elif cmd_u == "V":
                cy = args[0] * scale + oy
                current.append((cx, cy))
            elif cmd_u == "C":
                x1 = args[0] * scale + ox
                y1 = args[1] * scale + oy
                x2 = args[2] * scale + ox
                y2 = args[3] * scale + oy
                ex = args[4] * scale + ox
                ey = args[5] * scale + oy
                for px, py in _eval_cubic(cx, cy, x1, y1, x2, y2, ex, ey):
                    current.append((px, py))
                cx, cy = ex, ey
            elif cmd_u == "Z":
                current.append((sx, sy))
        if current:
            polygons.append(current)
    return polygons


def _polygon_area(poly: list[tuple[float, float]]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _point_in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _svg_def_to_image(defn: dict[str, Any], size: int) -> Image.Image:
    vbx, vby, vbw, vbh = defn["viewBox"]
    scale = size / max(vbw, vbh)
    ox = (size - vbw * scale) / 2
    oy = (size - vbh * scale) / 2
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for pi, path_d in enumerate(defn["paths"]):
        polygons = _svg_path_to_polygons(path_d, scale, ox, oy)
        evenodd = defn["evenodd"][pi] if pi < len(defn["evenodd"]) else False
        if evenodd and len(polygons) >= 2:
            polygons.sort(key=_polygon_area, reverse=True)
            outer = polygons[0]
            draw.polygon(outer, fill=(255, 255, 255, 255))
            px_map = img.load()
            for inner in polygons[1:]:
                if len(inner) < 3:
                    continue
                if _point_in_polygon(inner[0][0], inner[0][1], outer):
                    mask = Image.new("L", (size, size), 0)
                    ImageDraw.Draw(mask).polygon(inner, fill=255)
                    mk = mask.load()
                    if mk is None:
                        continue
                    px_map = img.load()
                    if px_map is None:
                        continue
                    for y in range(size):
                        for x in range(size):
                            if mk[x, y]:
                                px_map[x, y] = (0, 0, 0, 0)
                else:
                    draw.polygon(inner, fill=(255, 255, 255, 255))
        else:
            for poly in polygons:
                if len(poly) >= 3:
                    draw.polygon(poly, fill=(255, 255, 255, 255))
    return img


_ICON_SIZE = 128
_ICON_VIEWS = _svg_def_to_image(_SVG_VIEWS, _ICON_SIZE)
_ICON_LIKES = _svg_def_to_image(_SVG_LIKES, _ICON_SIZE)
_ICON_COINS = _svg_def_to_image(_SVG_COINS, _ICON_SIZE)
_ICON_FAVS = _svg_def_to_image(_SVG_FAVS, _ICON_SIZE)
_ICON_MAP = {"views": _ICON_VIEWS, "likes": _ICON_LIKES, "coins": _ICON_COINS, "favs": _ICON_FAVS}


# -- emoji rendering --


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    if cp > 0xFFFF:
        return True
    return cp in (
        0x00A9,
        0x00AE,
        0x200D,
        0x203C,
        0x2049,
        0x20E3,
        0x2122,
        0x2139,
        0x2194,
        0x2195,
        0x2196,
        0x2197,
        0x2198,
        0x2199,
        0x21A9,
        0x21AA,
        0x231A,
        0x231B,
        0x2328,
        0x23CF,
        0x23E9,
        0x23EA,
        0x23EB,
        0x23EC,
        0x23ED,
        0x23EE,
        0x23EF,
        0x23F0,
        0x23F1,
        0x23F2,
        0x23F3,
        0x23F8,
        0x23F9,
        0x23FA,
        0x24C2,
        0x25AA,
        0x25AB,
        0x25B6,
        0x25C0,
        0x25FB,
        0x25FC,
        0x25FD,
        0x25FE,
        0x2600,
        0x2601,
        0x2602,
        0x2603,
        0x2604,
        0x260E,
        0x2611,
        0x2614,
        0x2615,
        0x2618,
        0x261D,
        0x2620,
        0x2622,
        0x2623,
        0x2626,
        0x262A,
        0x262E,
        0x262F,
        0x2638,
        0x2639,
        0x263A,
        0x2640,
        0x2642,
        0x2648,
        0x2649,
        0x264A,
        0x264B,
        0x264C,
        0x264D,
        0x264E,
        0x264F,
        0x2650,
        0x2651,
        0x2652,
        0x2653,
        0x265F,
        0x2660,
        0x2663,
        0x2665,
        0x2666,
        0x2668,
        0x267B,
        0x267E,
        0x267F,
        0x2692,
        0x2693,
        0x2694,
        0x2695,
        0x2696,
        0x2697,
        0x2699,
        0x269B,
        0x269C,
        0x26A0,
        0x26A1,
        0x26A7,
        0x26AA,
        0x26AB,
        0x26B0,
        0x26B1,
        0x26BD,
        0x26BE,
        0x26C4,
        0x26C5,
        0x26C8,
        0x26CE,
        0x26CF,
        0x26D1,
        0x26D3,
        0x26D4,
        0x26E9,
        0x26EA,
        0x26F0,
        0x26F1,
        0x26F2,
        0x26F3,
        0x26F4,
        0x26F5,
        0x26F7,
        0x26F8,
        0x26F9,
        0x26FA,
        0x26FD,
        0x2702,
        0x2705,
        0x2708,
        0x2709,
        0x270A,
        0x270B,
        0x270C,
        0x270D,
        0x270F,
        0x2712,
        0x2714,
        0x2716,
        0x271D,
        0x2721,
        0x2728,
        0x2733,
        0x2734,
        0x2744,
        0x2747,
        0x274C,
        0x274E,
        0x2753,
        0x2754,
        0x2755,
        0x2757,
        0x2763,
        0x2764,
        0x2795,
        0x2796,
        0x2797,
        0x27A1,
        0x27B0,
        0x27BF,
        0x2934,
        0x2935,
        0x2B05,
        0x2B06,
        0x2B07,
        0x2B1B,
        0x2B1C,
        0x2B50,
        0x2B55,
        0x3030,
        0x303D,
        0x3297,
        0x3299,
        0xFE0F,
    )


def _twemoji_svg(codepoint: str) -> bytes:
    path = os.path.join(_TWEMOJI_DIR, f"{codepoint}.svg")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    import urllib.request

    url = f"{_TWEMOJI_CDN}/{codepoint}.svg"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read()
    except Exception:
        return b""
    with open(path, "wb") as f:
        f.write(data)
    return data


def _emoji_image(codepoint: str, size: int) -> tuple[Image.Image, int]:
    key = f"{codepoint}_{size}"
    if key in _emoji_img_cache:
        return _emoji_img_cache[key]
    svg_data = _twemoji_svg(codepoint)
    if not svg_data:
        empty = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _emoji_img_cache[key] = (empty, 0)
        return empty, 0
    try:
        import cairosvg

        png = cairosvg.svg2png(bytestring=svg_data, output_width=size, output_height=size)
    except (ImportError, OSError):
        empty = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _emoji_img_cache[key] = (empty, 0)
        return empty, 0
    if png is None:
        empty = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _emoji_img_cache[key] = (empty, 0)
        return empty, 0
    img = Image.open(BytesIO(png)).convert("RGBA")
    bbox = img.getbbox()
    content_w = bbox[2] - bbox[0] if bbox else size
    _emoji_img_cache[key] = (img, content_w)
    return img, content_w


# -- rendering helpers --


def _scale(h: int, ratio: float) -> int:
    return max(1, round(h * ratio))


def _load_font(path: str, size: int) -> _Font:
    try:
        return ImageFont.truetype(path, size, index=0)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(text: str, font: _Font, max_width: float) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        if font.getlength(test) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def _fmt_num(n: int) -> str:
    if n < 1000:
        return str(n)
    units = ["", "k", "M", "B"]
    magnitude = min(len(units) - 1, (len(str(n)) - 1) // 3)
    val = n / (1000.0**magnitude)
    return f"{int(val)}{units[magnitude]}" if val == int(val) else f"{val:.1f}{units[magnitude]}"


def _gradient(w: int, h: int) -> Image.Image:
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    bar_start = h * 0.35
    steps = 20
    for i in range(steps):
        t = i / steps
        y0 = int(bar_start + (h - bar_start) * t)
        y1 = int(bar_start + (h - bar_start) * (t + 0.05)) + 1
        if y0 >= h:
            break
        alpha = int(255 * min(t**1.8, 1.0) * 0.88)
        if y1 > h:
            y1 = h
        if y1 > y0:
            draw.rectangle([(0, y0), (w, y1)], fill=(0, 0, 0, alpha))
    return overlay


def _circle_avatar(avatar: Image.Image, target_size: int) -> Image.Image:
    avatar = avatar.resize((target_size, target_size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (target_size, target_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, target_size, target_size), fill=255)
    result = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    result.paste(avatar, (0, 0), mask)
    return result


def _draw_mixed(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fill: Any, font: _Font, emoji_size: int):
    if not _has_emoji(text):
        draw.text(xy, text, fill=fill, font=font)
        return

    x, y = xy
    bb = font.getbbox(text) if text else font.getbbox("Ag")
    text_top = bb[1]
    text_h = bb[3] - bb[1]
    emoji_y = y + text_top + (text_h - emoji_size) // 2

    for ch in text:
        if _is_emoji(ch):
            emoji, content_w = _emoji_image(f"{ord(ch):x}", emoji_size)
            canvas = draw._image
            canvas.paste(emoji, (round(x), round(emoji_y)), emoji)
            x += content_w + 1
        else:
            draw.text((round(x), y), ch, fill=fill, font=font)
            bb = _cached_bbox(font, ch)
            x += (bb[2] - bb[0]) if bb else 0


_bbox_cache: dict[tuple[int, int], tuple[Any, ...]] = {}
_cjk_char_w: dict[int, float] = {}


def _cached_bbox(font: _Font, ch: str) -> tuple[Any, ...]:
    key = (id(font), ord(ch))
    if key in _bbox_cache:
        return _bbox_cache[key]
    bb = font.getbbox(ch)
    _bbox_cache[key] = bb
    return bb


def _cjk_width(font: _Font) -> float:
    key = id(font)
    if key not in _cjk_char_w:
        _cjk_char_w[key] = font.getbbox("测")[2] - font.getbbox("测")[0]
    return _cjk_char_w[key]


def _has_emoji(text: str) -> bool:
    return any(_is_emoji(ch) for ch in text)


def _mixed_width(text: str, font: _Font, emoji_size: int) -> float:
    if not _has_emoji(text):
        return font.getlength(text)
    w = 0.0
    for ch in text:
        if _is_emoji(ch):
            _, content_w = _emoji_image(f"{ord(ch):x}", emoji_size)
            w += content_w + 1
        else:
            bb = _cached_bbox(font, ch)
            w += (bb[2] - bb[0]) if bb else 0
    return w


def _wrap_text_mixed(text: str, font: _Font, max_width: float, emoji_size: int) -> list[str]:
    if not text:
        return []
    if not _has_emoji(text):
        return _wrap_text(text, font, max_width)
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        w = _mixed_width(test, font, emoji_size)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


# -- public API --


class BVideoException(Exception):
    def __init__(self, info: Any):
        self.info = info


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


async def fetch_bytes(url: str) -> bytes:
    session = await _get_session()
    async with session.get(url) as response:
        return await response.content.read()


async def fetch_json(url: str) -> dict[str, Any]:
    session = await _get_session()
    async with session.get(url, headers={"User-Agent": ""}) as response:
        return await response.json()


async def open_from_url(url: str) -> Image.Image:
    return Image.open(BytesIO(await fetch_bytes(url)))


async def video_info(bv: str) -> tuple[dict[str, Any], bool]:
    try:
        info = await fetch_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")
        if info["code"] != 0:
            raise BVideoException(info.get("message"))
        return info["data"], True
    except BVideoException as err:
        return {
            "pic": "https://i0.hdslb.com/bfs/new_dyn/7afd4c057eba6152836a52fbb4b126e9686607596.png",
            "title": f"(╯°□°）╯︵ ┻━┻ {err.info or '?????'}",
            "owner": {"name": "", "face": "https://i0.hdslb.com/bfs/app/8920e6741fc2808cce5b81bc27abdbda291655d3.png"},
            "stat": {"view": -1, "reply": -1, "like": -1, "coin": -1, "favorite": -1},
            "desc": "",
        }, False
    except (TimeoutError, aiohttp.ClientError, OSError):
        return {
            "pic": "https://i0.hdslb.com/bfs/new_dyn/7afd4c057eba6152836a52fbb4b126e9686607596.png",
            "title": "(╯°□°）╯︵ ┻━┻ 网络请求失败",
            "owner": {"name": "", "face": "https://i0.hdslb.com/bfs/app/8920e6741fc2808cce5b81bc27abdbda291655d3.png"},
            "stat": {"view": -1, "reply": -1, "like": -1, "coin": -1, "favorite": -1},
            "desc": "",
        }, False


async def fetch_resources(data: dict[str, Any]) -> tuple[Image.Image, Image.Image]:
    cover_url = data["pic"] + "@672w_378h_1c"
    avatar_url = data["owner"]["face"] + "@170w_170h_1c"
    cover, avatar = await asyncio.gather(open_from_url(cover_url), open_from_url(avatar_url))
    return cover, avatar


def render(info: dict[str, Any], cover: Image.Image, avatar: Image.Image) -> bytes:
    max_w = 1920
    if cover.width > max_w:
        ratio = max_w / cover.width
        cover = cover.resize((max_w, round(cover.height * ratio)), Image.Resampling.LANCZOS)

    w, h = cover.size
    canvas = cover.convert("RGBA")
    grad = _gradient(w, h)
    canvas.paste(grad, (0, 0), grad)

    pad_x = _scale(h, 0.05)
    pad_bottom = _scale(h, 0.04)
    avatar_size = _scale(h, 0.12)
    av = _circle_avatar(avatar.convert("RGBA"), avatar_size)

    font_name = _load_font(FONT_BOLD, _scale(h, 0.07))
    font_stat = _load_font(FONT_REGULAR, _scale(h, 0.034))
    font_title = _load_font(FONT_BOLD, _scale(h, 0.09))
    font_desc = _load_font(FONT_REGULAR, _scale(h, 0.028))

    uploader = info.get("owner", {}).get("name", "")
    title = info.get("title", "")
    desc = info.get("desc", "")
    stat = info.get("stat", {})
    plays = _fmt_num(stat.get("view", 0))
    likes = _fmt_num(stat.get("like", 0))
    coins = _fmt_num(stat.get("coin", 0))
    favs = _fmt_num(stat.get("favorite", 0))

    draw = ImageDraw.Draw(canvas)

    icon_h = _scale(h, 0.034)
    icon_gap = _scale(h, 0.008)
    stat_gap = _scale(h, 0.04)
    bar_pad_x = _scale(h, 0.04)
    bar_pad_y = _scale(h, 0.016)

    stat_parts = [
        (_ICON_MAP["views"].resize((icon_h, icon_h), Image.Resampling.LANCZOS), plays),
        (_ICON_MAP["likes"].resize((icon_h, icon_h), Image.Resampling.LANCZOS), likes),
        (_ICON_MAP["coins"].resize((icon_h, icon_h), Image.Resampling.LANCZOS), coins),
        (_ICON_MAP["favs"].resize((icon_h, icon_h), Image.Resampling.LANCZOS), favs),
    ]

    item_widths: list[float] = []
    for icon, val in stat_parts:
        iw = icon.width
        vw = draw.textbbox((0, 0), val, font=font_stat)[2]
        item_widths.append(iw + icon_gap + vw)

    bar_w = bar_pad_x * 2 + sum(item_widths) + stat_gap * (len(stat_parts) - 1)
    bar_h = icon_h + bar_pad_y * 2
    if bar_h < avatar_size // 3:
        bar_h = avatar_size // 3
    bar_h = round(bar_h)
    bar_w = round(bar_w)

    title_emoji_h = _scale(h, 0.09)
    title_max_w = w - pad_x * 2 - w * 0.42
    title_lines = _wrap_text_mixed(title, font_title, title_max_w, title_emoji_h)[:2]

    desemoji_h = _scale(h, 0.028)
    desc_max_w = w * 0.38
    desc_lines: list[str] = []
    if desc:
        desc_lines = _wrap_text_mixed(desc, font_desc, desc_max_w, desemoji_h)[:3]
    desc_h = 0
    for line in desc_lines:
        desc_h += max(draw.textbbox((0, 0), line, font=font_desc)[3], desemoji_h) + 2

    gap = _scale(h, 0.025)
    current_y = h - pad_bottom - desc_h

    if desc_lines:
        for line in desc_lines:
            tw = _mixed_width(line, font_desc, desemoji_h)
            lh = max(draw.textbbox((0, 0), line, font=font_desc)[3], desemoji_h) + 2
            _draw_mixed(
                draw,
                (w - pad_x - tw, round(current_y)),
                line,
                fill=(255, 255, 255, 102),
                font=font_desc,
                emoji_size=desemoji_h,
            )
            current_y += lh

    current_y -= gap
    for line in reversed(title_lines):
        current_y -= max(draw.textbbox((0, 0), line, font=font_title)[3], title_emoji_h) + 4
    for line in title_lines:
        _draw_mixed(
            draw, (pad_x, round(current_y)), line, fill=(255, 255, 255), font=font_title, emoji_size=title_emoji_h
        )
        current_y += max(draw.textbbox((0, 0), line, font=font_title)[3], title_emoji_h) + 4

    current_y = (
        current_y
        - sum(max(draw.textbbox((0, 0), ln, font=font_title)[3], title_emoji_h) + 4 for ln in title_lines)
        - gap
    )
    bar_y = current_y - bar_h

    bar = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar)
    bar_draw.rounded_rectangle((0, 0, bar_w - 1, bar_h - 1), radius=round(bar_h / 2), fill=(255, 255, 255, 30))
    bar = bar.filter(ImageFilter.GaussianBlur(radius=1))
    canvas.paste(bar, (pad_x, bar_y), bar)

    cursor_x = pad_x + bar_pad_x
    for icon, val in stat_parts:
        icon_y = bar_y + (bar_h - icon.height) // 2
        canvas.paste(icon, (round(cursor_x), icon_y), icon)
        cursor_x += icon.width + icon_gap
        bbox = draw.textbbox((0, 0), val, font=font_stat)
        val_h = bbox[3] - bbox[1]
        val_y = bar_y + (bar_h - val_h) // 2 - bbox[1]
        draw.text((round(cursor_x), val_y), val, fill=(255, 255, 255), font=font_stat)
        cursor_x += bbox[2] + stat_gap

    row1_y = bar_y - gap - avatar_size
    canvas.paste(av, (pad_x, row1_y), av)

    name_x = pad_x + avatar_size + _scale(h, 0.03)
    name_bbox = draw.textbbox((0, 0), uploader or "Ag", font=font_name)
    name_h = name_bbox[3] - name_bbox[1]
    name_y = row1_y + (avatar_size - name_h) // 2 - name_bbox[1]
    _draw_mixed(draw, (name_x, name_y), uploader, fill=(255, 255, 255), font=font_name, emoji_size=name_h)

    canvas = canvas.convert("RGB")
    buf = BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf.read()
