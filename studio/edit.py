# ===================== edit.py: spec-driven picture edit, kid-facing graphics, soundtrack, final mux =====================
import os, json, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.io import wavfile

FPS, VW, VH = 30, 1080, 1920
INTERP = "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
GRADE_LOOK = ("unsharp=5:5:0.55:5:5:0.0,eq=contrast=1.05:saturation=1.10:gamma=1.01,"
              "colorbalance=rs=0.02:bs=-0.03:rm=0.02:bm=-0.02:rh=0.01:bh=-0.02,vignette=angle=PI/5")
def grade(): return f"scale={VW}:{VH}:flags=lanczos:force_original_aspect_ratio=increase,crop={VW}:{VH}," + GRADE_LOOK
CAP_Y = 0.69      # caption centre (fraction of height), above the Shorts UI
def set_video_size(landscape):
    """9:16 Shorts (1080x1920) or 16:9 regular videos (1920x1080)."""
    global VW, VH, CAP_Y
    VW, VH, CAP_Y = (1920, 1080, 0.85) if landscape else (1080, 1920, 0.69)
NEW_TINT = "eq=brightness=0.025:saturation=1.05,colorbalance=rs=0.03:gs=0.01:bs=-0.04:rm=0.03:bm=-0.03,"

def count_frames(path):
    import cv2
    cap = cv2.VideoCapture(path); n = 0
    while cap.grab(): n += 1
    return n

def _piece(ff, src, a, b, speed, tint, out):
    vf = f"trim=start={a}:end={b},setpts=PTS-STARTPTS,"
    vf += (f"minterpolate=fps={int(round(30 / speed))}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,setpts={1 / speed}*PTS,fps=30"
           if speed != 1.0 else INTERP)
    vf += "," + (NEW_TINT if tint else "") + grade()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "14",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p", out], check=True)

def src_fps(path):
    import cv2
    cap = cv2.VideoCapture(path); f = cap.get(cv2.CAP_PROP_FPS) or 30.0; cap.release(); return f

def shot_cut(s):
    """Default trim: the useful middle of a 5 s Wan shot, or the whole still clip."""
    return s.get("cut", [0.0, s.get("dur", 5.0)] if (s.get("still") or s.get("still_image")) else [0.3, 4.8])

def assemble(spec, shot_files, work, ff):
    """shot_files: {shot_id: mp4}. Returns timeline {shot_id: {start, dur, slow:[(a,b)]}}, body path."""
    seg = os.path.join(work, "seg"); os.makedirs(seg, exist_ok=True)
    files, tl, t = [], {}, 0.0
    for s in spec["shots"]:
        a, b = shot_cut(s); tint = not s.get("reuse", "").startswith("pilot")
        parts = [(a, b, 1.0)]
        if "slot" in s:   # music video: the shot ends exactly at slot[1] on the song clock (absorbs frame rounding)
            need = s["slot"][1] - t; have = count_frames(shot_files[s["id"]]) / src_fps(shot_files[s["id"]]) - a
            parts = [(a, a + need, 1.0)] if need <= have + 0.02 else [(a, a + have, have / need)]
        if "slowmo" in s:
            sa, sb = s["slowmo"]["at"]; fct = s["slowmo"].get("factor", 0.4)
            parts = [(a, sa, 1.0), (sa, sb, fct), (sb, b, 1.0)]
        start, slow = t, []
        for k, (pa, pb, sp) in enumerate(parts):
            if pb - pa < 0.05: continue
            f = os.path.join(seg, f"{len(files):02d}_{s['id']}_{k}.mp4")
            _piece(ff, shot_files[s["id"]], pa, pb, sp, tint, f)
            d = count_frames(f) / FPS
            if sp != 1.0: slow.append((t, t + d))
            files.append(f); t += d
        tl[s["id"]] = {"start": round(start, 3), "dur": round(t - start, 3), "slow": slow}
    lst = os.path.join(seg, "list.txt"); open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    body = os.path.join(work, "body.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", body], check=True)
    return tl, t, body

# ---------------- graphics ----------------
ORANGE, WHITE, GOLD = (240, 138, 36), (255, 255, 255), (255, 236, 120)
def _ease(x):
    c1 = 1.70158; c3 = c1 + 1; x = min(max(x, 0), 1); return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def _text(font_path, txt, sz, fill=WHITE, stroke=ORANGE, sw=10):
    f = ImageFont.truetype(font_path, sz); b = f.getbbox(txt, stroke_width=sw)
    im = Image.new("RGBA", (b[2] - b[0] + 20, b[3] - b[1] + 20), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10 - b[0], 10 - b[1]), txt, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.putalpha(im.split()[-1].point(lambda v: int(v * 0.45)))
    out = Image.new("RGBA", (im.width + 12, im.height + 12), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)), (8, 10)); out.alpha_composite(im, (0, 0)); return out
def _drop(size, filled, glow=0.0):
    SS = 4; s = size * SS; im = Image.new("RGBA", (s, int(s * 1.35)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, r = s / 2, s * 0.42; cy = im.height - r - s * 0.04
    fill = (80, 170, 255, 255) if filled else (255, 255, 255, 90)
    d.polygon([(cx, s * 0.02), (cx - r * 0.98, cy - r * 0.2), (cx + r * 0.98, cy - r * 0.2)], fill=fill)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    if filled: d.ellipse([cx - r * 0.55, cy - r * 0.55, cx - r * 0.1, cy - r * 0.05], fill=(255, 255, 255, 200))
    ol = Image.new("RGBA", im.size, WHITE + (255,)); ol.putalpha(im.split()[-1].filter(ImageFilter.MaxFilter(13)))
    ol.alpha_composite(im); ol = ol.resize((size, int(size * 1.35)), Image.LANCZOS)
    if glow <= 0: return ol
    g = Image.new("RGBA", (ol.width + 40, ol.height + 40), (0, 0, 0, 0))
    gl = Image.new("RGBA", ol.size, (150, 210, 255, 255)); gl.putalpha(ol.split()[-1].point(lambda v: int(v * glow)))
    g.alpha_composite(gl, (20, 20)); g = g.filter(ImageFilter.GaussianBlur(12)); g.alpha_composite(ol, (20, 20)); return g
def _paste(fr, layer, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01: return
    l = layer if scale == 1.0 else layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.LANCZOS)
    if alpha < 1: l = l.copy(); l.putalpha(l.split()[-1].point(lambda v: int(v * alpha)))
    fr.alpha_composite(l, (int(cx - l.width / 2), int(cy - l.height / 2)))

RAINBOW7 = [(255, 86, 86), (255, 158, 54), (255, 214, 60), (96, 204, 104), (70, 160, 255), (92, 104, 230), (176, 110, 230)]
COLOR_NAMES = ["red", "orange", "yellow", "green", "blue", "indigo", "violet"]
NAVY = (40, 50, 96)

def _smooth(x): x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)

def camera_box(cam, u, local_t):
    """cam: {move, amount, focus, shake_at}; u: 0..1 through the shot. Returns the source crop box (VW x VH frame)."""
    mv = cam.get("move", "none"); A = float(cam.get("amount", 0.10)); k = _smooth(u)
    fx, fy = cam.get("focus", [0.5, 0.5]); z, cx, cy = 1.0, 0.5, 0.5
    if mv == "push":   z = 1 + A * k; cx, cy = 0.5 + (fx - 0.5) * k, 0.5 + (fy - 0.5) * k
    elif mv == "pull": z = 1 + A * (1 - k); cx, cy = 0.5 + (fx - 0.5) * (1 - k), 0.5 + (fy - 0.5) * (1 - k)
    elif mv in ("pan_left", "pan_right", "tilt_up", "tilt_down"):
        z = 1 + A; m = (A / (2 * z)) * (1 - 2 * k)               # travel across the spare margin
        if mv == "pan_left": cx = 0.5 + m
        elif mv == "pan_right": cx = 0.5 - m
        elif mv == "tilt_up": cy = 0.5 + m
        else: cy = 0.5 - m
    elif mv == "drift": z = 1 + 0.035 * k
    elif mv == "shake": z = 1.05
    for st in cam.get("shake_at", []):
        dt = local_t - st
        if 0 <= dt < 0.6:
            z = max(z, 1.05); amp = 0.012 * math.exp(-dt * 6)
            cx += amp * math.sin(2 * math.pi * 17 * dt); cy += amp * math.cos(2 * math.pi * 13 * dt)
    w, h = VW / z, VH / z
    x0 = min(max(cx * VW - w / 2, 0), VW - w); y0 = min(max(cy * VH - h / 2, 0), VH - h)
    return (x0, y0, x0 + w, y0 + h)

def caption_chunks(voice_tl, max_words=4):
    """voice_tl: [{start, words:[[w,a,b]]}] (absolute seconds). -> [(t_on, t_off, [(word, a, b)])]"""
    chunks = []
    for v in voice_tl:
        cur = []
        for w, a, b in v["words"]:
            cur.append((w.strip(), a, b))
            if len(cur) >= max_words or w.strip()[-1:] in ".!?,":
                chunks.append(cur); cur = []
        if cur: chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        on = c[0][1] - 0.08; off = c[-1][2] + 0.35
        if i + 1 < len(chunks): off = min(off, chunks[i + 1][0][1] - 0.08)
        out.append((on, off, c))
    return out

def overlay(spec, tl, total, body, out, font_path, ff, voice_tl=(), chapter_out=None):
    """Draws camera moves, transitions and every kid-facing graphic. With chapter_out, also writes a copy without
    the end card / next teaser / loop drop (used when chapters are joined into a full episode)."""
    S = {k: v["start"] for k, v in tl.items()}
    shots = spec["shots"]
    hook = spec.get("hook", [])
    L_HOOK = ([_text(font_path, hook[0], 74)] + ([_text(font_path, hook[1], 112, fill=GOLD)] if len(hook) > 1 else [])) if hook else []
    L_HOOK = [im if im.width <= VW - 60 else im.resize((VW - 60, int(im.height * (VW - 60) / im.width)), Image.LANCZOS) for im in L_HOOK]
    tries = sorted([(S[s["id"]] + s.get("badge_at", 0.25), s["badge"]) for s in shots if "badge" in s])
    NUMS = {n: _text(font_path, f"{n}!" if n == len(tries) else str(n), 340 if n == len(tries) else 300,
                     fill=GOLD if n == len(tries) else WHITE) for _, n in tries}
    POPS = [(p["t"], _text(font_path, p["text"], p.get("size", 260), fill=GOLD if p.get("gold") else WHITE),
             p.get("pos", [VW * (0.2 if i % 2 == 0 else 0.8), VH * 0.32])) for i, p in enumerate(spec.get("pops", []))]
    bangs = [(S[s["id"]] + s["bang"].get("at", 0.15), s["bang"].get("pos", [760, 560])) for s in shots if "bang" in s]
    BANG = _text(font_path, "!", 220, fill=GOLD)
    nxt = spec.get("next")
    end_tag = spec.get("end_tag", "PUDDLE PALS")
    TAG = _text(font_path, end_tag, 96) if end_tag else None
    NEXT = [_text(font_path, "NEXT TIME...", 64, stroke=NAVY, sw=8), _text(font_path, nxt.upper(), 92, fill=GOLD)] if nxt else None
    D_ON, D_ON2, D_OFF, FALL = _drop(70, True, 0.9), _drop(70, True), _drop(70, False), _drop(64, True, 0.6)
    tr_on = tries[0][0] - 0.25 if tries else 0
    tr_off = (S[spec["tracker_until"]] - 0.3) if spec.get("tracker_until") else (tries[-1][0] + 3 if tries else 0)
    tag_t = total - 2.2; drop_t0 = total - 0.75
    head = shots[-1].get("head", [650, 470])
    loop_drop = spec.get("loop_drop", True)

    # camera + transitions
    cams = [(S[s["id"]], tl[s["id"]]["dur"], s["camera"] if isinstance(s.get("camera"), dict) else {"move": s.get("camera", "none")})
            for s in shots if s.get("camera")]
    trans = spec.get("transitions", "cut")
    cuts = [S[s["id"]] for s in shots[1:] if trans == "dip" or s.get("dip")]
    fade_ends = spec.get("fade_ends", False)
    def shade(t):
        f = 1.0
        for b in cuts: f = min(f, 1 - 0.85 * max(0.0, 1 - abs(t - b) / 0.32))
        if fade_ends: f = min(f, _smooth(t / 0.8), _smooth((total - t) / 1.4))
        return f

    # series HUD: rainbow meter with the colours earned so far (+ the one earned in this chapter)
    ser = spec.get("series")
    hud_y = 175; track_y = 265 if ser else 150
    if ser:
        have = int(ser.get("colors_before", ser.get("chapter", 1) - 1))
        earn = ser.get("earn")
        earn_t = S[earn["shot"]] + earn.get("at", 0.5) if earn else None
        CH = _text(font_path, f"CH {ser.get('chapter', '')}", 46, stroke=NAVY, sw=7)
        def seg(i, on):
            im = Image.new("RGBA", (76, 40), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle([3, 3, 72, 36], 14, fill=(RAINBOW7[i] + (255,)) if on else (255, 255, 255, 70),
                                outline=(255, 255, 255, 255), width=4)
            return im
        SEG_ON = [seg(i, True) for i in range(7)]; SEG_OFF = [seg(i, False) for i in range(7)]
        hud_on = 2.7 if hook else 0.3
        hud_off = tag_t - 0.1
    # captions
    CAP = []
    if spec.get("captions", True) and spec.get("cap_line") and voice_tl:
        # song Shorts: each lyric line whole (one line, shrunk to fit; two lines only if it must), on a soft dark band
        for li, v in enumerate(voice_tl):
            words = v["words"]; on = words[0][1] - 0.12
            off = (voice_tl[li + 1]["words"][0][1] - 0.12) if li + 1 < len(voice_tl) else words[-1][2] + 0.8
            cs = spec.get("cap_size", 60); maxw = VW * 0.88
            def build(sz):
                ims = [(_text(font_path, w, sz, stroke=NAVY, sw=6), _text(font_path, w, sz, fill=GOLD, stroke=NAVY, sw=6), a, b) for w, a, b in words]
                return ims, sum(i[0].width for i in ims) - 14 * (len(ims) - 1)
            imgs, tw = build(cs)
            while tw > maxw and cs > spec.get("cap_min", 44):
                cs -= 2; imgs, tw = build(cs)
            widths = [i[0].width for i in imgs]; space = -14
            if tw <= maxw: rows = [list(range(len(imgs)))]
            else:   # break once, at the word boundary nearest the middle
                acc, best = 0, 1
                for k in range(1, len(imgs)):
                    acc += widths[k - 1]
                    if abs(acc - tw / 2) < abs(sum(widths[:best]) - tw / 2): best = k
                rows = [list(range(best)), list(range(best, len(imgs)))]
            lh = imgs[0][0].height - 8; y0 = VH * spec.get("cap_y", CAP_Y) - lh * len(rows) / 2; pos = []
            rw = [sum(widths[k] for k in r) + space * (len(r) - 1) for r in rows]
            for ri, r in enumerate(rows):
                x = VW / 2 - rw[ri] / 2
                for k in r: pos.append((k, x, y0 + ri * lh)); x += widths[k] + space
            bw, bh = max(rw) + 70, lh * len(rows) + 34
            band = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
            ImageDraw.Draw(band).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=int(bh / 2.6), fill=(12, 16, 32, spec.get("band_alpha", 120)))
            CAP.append((on, off, imgs, pos, band, (VW / 2, y0 + lh * len(rows) / 2 + 4)))
    elif spec.get("captions", True):
        for on, off, words in caption_chunks(voice_tl):
            cs = spec.get("cap_size", 66)
            imgs = [(_text(font_path, w.upper(), cs, stroke=NAVY, sw=8), _text(font_path, w.upper(), cs, fill=GOLD, stroke=NAVY, sw=8), a, b)
                    for w, a, b in words]
            space = -4; widths = [im[0].width for im in imgs]
            lines, cur, cw = [], [], 0
            for k, wdt in enumerate(widths):
                if cur and cw + space + wdt > min(980, VW * 0.6): lines.append(cur); cur, cw = [], 0
                cur.append(k); cw += wdt + (space if len(cur) > 1 else 0)
            lines.append(cur)
            lh = imgs[0][0].height - 6; y0 = VH * spec.get("cap_y", CAP_Y) - lh * len(lines) / 2; pos = []
            for li, ln in enumerate(lines):
                lw = sum(widths[k] for k in ln) + space * (len(ln) - 1); x = VW / 2 - lw / 2
                for k in ln: pos.append((k, x, y0 + li * lh)); x += widths[k] + space
            CAP.append((on, off, imgs, pos, None, None))

    TOPL = _text(font_path, spec["top_label"], 58, stroke=NAVY, sw=8) if spec.get("top_label") else None
    # title card: the thumbnail's title (same font and colours) fades in over the first sung line and fades away
    TC = spec.get("title_card")
    if TC and TC.get("text"):
        tf = _thumb_font(TC.get("font", "jua"), font_path)
        c1, c2, olc = THUMB_COLORS.get(TC.get("colors", "warm"), THUMB_COLORS["warm"])
        TCL = [_text(tf, w, 118 if i == 0 else 96, fill=c1 if i == 0 else c2, stroke=olc, sw=12) for i, w in enumerate(TC["text"][:2])]
        TCL = [im if im.width <= VW - 80 else im.resize((VW - 80, int(im.height * (VW - 80) / im.width)), Image.LANCZOS) for im in TCL]
        tc_on, tc_off = TC.get("from", 0.2), TC.get("until", 3.6); tc_a = TC.get("alpha", 0.82); tc_y = VH * TC.get("y", 0.2)
    else: TCL = []
    def draw_common(fr, t):
        if TCL and tc_on <= t < tc_off:
            a = tc_a * min(1, (t - tc_on) / 0.45) * min(1, (tc_off - t) / 0.9)
            y = tc_y - 6 * _ease(min(1, (t - tc_on) / 0.6))
            for i, im in enumerate(TCL):
                _paste(fr, im, VW / 2, y + i * (TCL[0].height - 6), 1.0, a)
        if TOPL is not None:   # series name fixed at the top, like a title card (MIDLIFE COMMUTER shorts)
            _paste(fr, TOPL, VW / 2, 200 if VH > VW else 70, 1.0, 1.0)
        if L_HOOK and 0.15 < t < 2.55:
            a = min(1, (t - 0.15) / 0.2) * min(1, (2.55 - t) / 0.25)
            _paste(fr, L_HOOK[0], VW / 2, 250, _ease((t - 0.15) / 0.35), a)
            if len(L_HOOK) > 1: _paste(fr, L_HOOK[1], VW / 2, 370, _ease((t - 0.3) / 0.4), a)
        if ser and hud_on < t < hud_off:
            a = min(1, (t - hud_on) / 0.3) * min(1, (hud_off - t) / 0.3)
            x0 = VW / 2 - 3 * 78
            _paste(fr, CH, x0 - 120, hud_y, 1.0, a)
            for i in range(7):
                on = i < have or (earn_t is not None and i == have and t >= earn_t)
                sc = 1.0
                if earn_t is not None and i == have and 0 <= t - earn_t < 0.6: sc = 1 + 0.6 * math.sin(math.pi * (t - earn_t) / 0.6)
                _paste(fr, SEG_ON[i] if on else SEG_OFF[i], x0 + i * 78, hud_y, sc, a)
        if tries and spec.get("tracker", True) and tr_on < t < tr_off:
            a = min(1, (t - tr_on) / 0.3) * min(1, (tr_off - t) / 0.3)
            for i, (tt, n) in enumerate(tries):
                x = VW / 2 + (i - (len(tries) - 1) / 2) * 110
                if t >= tt: _paste(fr, D_ON if t - tt < 0.8 else D_ON2, x, track_y, 0.6 + 0.4 * _ease((t - tt) / 0.35), a)
                else: _paste(fr, D_OFF, x, track_y, 1.0, a)
        for tt, n in tries:
            dt = t - tt
            if 0 <= dt < 1.1: _paste(fr, NUMS[n], 230 if n < len(tries) else 270, 480, _ease(dt / 0.35) * (1 - max(0, (dt - 0.8) / 0.3)))
        for k, (pt, im, pos) in enumerate(POPS):
            dt = t - pt; life = min(1.0, (POPS[k + 1][0] - pt) if k + 1 < len(POPS) else 1.0)   # the next number replaces it
            if 0 <= dt < life: _paste(fr, im, pos[0], pos[1], _ease(min(1, dt / 0.15)) * (1 + 0.15 * max(0, 1 - dt / 0.3)), min(1, (life - dt) / 0.12))
        for bt, pos in bangs:
            dt = t - bt
            if 0 <= dt < 1.2: _paste(fr, BANG, pos[0], pos[1], _ease(dt / 0.25), min(1, (1.2 - dt) / 0.25))
        for on, off, imgs, pos, band, bpos in CAP:
            if on <= t < off:
                a = min(1, (t - on) / 0.12, (off - t) / 0.12)
                if band is not None: _paste(fr, band, bpos[0], bpos[1], 1.0, a)
                for k, x, y in pos:
                    wi, wg, wa, wb = imgs[k]; nxt_a = imgs[k + 1][2] if k + 1 < len(imgs) else wb + 0.3
                    act = wa - 0.05 <= t < nxt_a
                    im = wg if act else wi; sc = 1.08 if act else 1.0
                    _paste(fr, im, x + im.width / 2, y + im.height / 2, sc, a)
                break

    def draw_end(fr, t):
        if t > tag_t:
            if NEXT:
                _paste(fr, NEXT[0], VW / 2, 270, _ease((t - tag_t) / 0.4), min(1, (t - tag_t) / 0.2))
                _paste(fr, NEXT[1], VW / 2, 370, _ease((t - tag_t - 0.15) / 0.4), min(1, (t - tag_t) / 0.2))
            elif TAG: _paste(fr, TAG, VW / 2, 330, _ease((t - tag_t) / 0.4), min(1, (t - tag_t) / 0.2))
        if loop_drop and t > drop_t0:
            k = min(1, (t - drop_t0) / 0.72); _paste(fr, FALL, head[0], -80 + (head[1] + 80) * k ** 2)

    def enc_proc(path):
        return subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS),
                                 "-i", "-", "-c:v", "libx264", "-crf", "15", "-preset", "veryfast", "-pix_fmt", "yuv420p", path],
                                stdin=subprocess.PIPE)
    inp = subprocess.Popen([ff, "-loglevel", "error", "-i", body, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = enc_proc(out); enc2 = enc_proc(chapter_out) if chapter_out else None
    n, motion, prev = 0, [], None
    while True:
        buf = inp.stdout.read(VW * VH * 3)
        if len(buf) < VW * VH * 3: break
        arr = np.frombuffer(buf, np.uint8).reshape(VH, VW, 3)
        g = arr[::8, ::8].mean(-1).astype(np.float32)
        motion.append(0.0 if prev is None else float(np.abs(g - prev).mean())); prev = g
        t = n / FPS
        fr = Image.fromarray(arr)
        for st, du, cam in cams:
            if st <= t < st + du:
                box = camera_box(cam, (t - st) / max(du, 1e-3), t - st)
                if box != (0, 0, VW, VH): fr = fr.resize((VW, VH), Image.BICUBIC, box=box)
                break
        f = shade(t)
        if f < 0.999: fr = Image.fromarray((np.asarray(fr).astype(np.float32) * f).astype(np.uint8))
        fr = fr.convert("RGBA"); draw_common(fr, t)
        if enc2: enc2.stdin.write(fr.convert("RGB").tobytes())
        draw_end(fr, t)
        enc.stdin.write(fr.convert("RGB").tobytes()); n += 1
    for e in (enc, enc2):
        if e: e.stdin.close(); e.wait()
    inp.wait()
    return np.array(motion)

# ---------------- soundtrack ----------------
def ambience(kind, N, t, vol=1.0):
    r = np.random.default_rng(21); out = np.zeros(N)
    if kind == "night":            # crickets
        ch = np.sin(2 * np.pi * 4300 * t) * (np.sin(2 * np.pi * 28 * t) > 0.3) * (np.sin(2 * np.pi * 0.9 * t) > -0.2)
        out = ch * 0.012 + lp(r.standard_normal(N), 300) * 0.01
    elif kind == "waves":
        sw = 0.5 + 0.5 * np.sin(2 * np.pi * t / 6.5 - 1.2) ** 3
        out = lp(r.standard_normal(N), 900) * 0.05 * sw + bp(r.standard_normal(N), 2000, 7000) * 0.012 * sw
    elif kind == "wind":
        sw = 0.6 + 0.4 * np.sin(2 * np.pi * t / 5.0)
        out = bp(r.standard_normal(N), 250, 1200) * 0.05 * sw
    elif kind == "birds":
        out = lp(r.standard_normal(N), 400) * 0.006
        for at in np.arange(0.8, N / SR, 2.3) + r.uniform(0, 1.5, len(np.arange(0.8, N / SR, 2.3))):
            c = chirp() * 1.5; i = int(at * SR); out[i:i + len(c)] += c[: max(0, N - i)]
    elif kind == "cosy":            # quiet room tone with a soft crackle
        out = lp(r.standard_normal(N), 500) * 0.008 + _grains(int(N / SR * 3), N / SR, 1500, 6000, 200, 0.02, seed=4)[:N]
    return out * vol * np.clip(t / 1.0, 0, 1)

def soundtrack(spec, tl, total, motion, out_wav, voice_tl=(), chapter=False):
    N = int(SR * (total + 0.05)); t = np.arange(N) / SR
    S = {k: v["start"] for k, v in tl.items()}
    slow = np.zeros(N)
    for v in tl.values():
        for a, b in v["slow"]: slow = np.maximum(slow, np.clip((t - (a - 0.2)) / 0.3, 0, 1) * (1 - np.clip((t - b + 0.1) / 0.25, 0, 1)))
    sections = [(S[m["from"]], m["mode"]) for m in spec.get("music", [{"from": spec["shots"][0]["id"], "mode": "major"}])]
    rests = [(S[r["shot"]] + r.get("at", 0), S[r["shot"]] + r.get("at", 0) + r.get("dur", 1.5)) for r in spec.get("rests", [])]
    finale_t = S[spec.get("finale", spec["shots"][-1]["id"])]
    if spec.get("song"):   # music video: the finished song is the score (sfx sit lightly on top)
        from scipy.io import wavfile as _wf
        sp = f"/tmp/song_{spec['id']}.wav"
        subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-y", "-i", asset(spec["song"]["file"]), "-ar", str(SR), "-ac", "2", sp], check=True)
        sr_, a_ = _wf.read(sp); a_ = a_.astype(np.float32) / 32768.0
        if spec["song"].get("segments"):   # cold open: [[hook from, to], [verse from, None]] joined with short crossfades
            parts = [a_[int(x * SR): (int(y * SR) if y else None)].copy() for x, y in spec["song"]["segments"]]
            xf = int(0.12 * SR); out = parts[0]
            for q in parts[1:]:
                out[-xf:] *= np.linspace(1, 0, xf)[:, None]; q[:xf] *= np.linspace(0, 1, xf)[:, None]
                out = np.concatenate([out[:-xf], out[-xf:] + q[:xf], q[xf:]])
            a_ = out
        else:
            sk = int(spec["song"].get("skip", 0.0) * SR)   # Shorts start close to the first sung line
            if sk: a_ = a_[sk:].copy(); fi = min(len(a_), int(0.25 * SR)); a_[:fi] *= np.linspace(0, 1, fi)[:, None]
        fo = int(1.5 * SR)   # the Short may end before the song does: fade out over the last 1.5 s
        if len(a_) > N: a_ = a_[:N].copy()
        if len(a_) >= fo and len(a_) >= N - 5: a_[-fo:] *= np.linspace(1, 0, fo)[:, None]
        music = np.zeros(N); i0 = int(spec["song"].get("at", 0.0) * SR); n_ = min(N - i0, len(a_))
        song_lr = np.zeros((N, 2)); song_lr[i0:i0 + n_] = a_[:n_]
    else:
        music = make_music(N, sections, rests, slow, finale_t) * spec.get("music_vol", 1.0)
    # narration: music ducks under the voice
    talk = np.zeros(N); voice = np.zeros(N)
    for v in voice_tl:
        if not v.get("wav"): continue
        x = load_voice(v["wav"], SR) * v.get("vol", 1.0); i = int(v["start"] * SR)
        if i >= N: continue
        x = x[: N - i]; voice[i:i + len(x)] += x; talk[i:i + len(x)] = 1
    if voice_tl and talk.any():
        k = int(0.25 * SR); duck = np.convolve(talk, np.ones(k) / k, mode="same")
        music *= 1 - 0.6 * np.clip(duck * 1.5, 0, 1)
    L = music.copy(); R = music.copy()

    def add(x, at, vol=1.0, pan=0.0):
        i = int(at * SR)
        if i >= N or i < 0: return
        x = x[: N - i] * vol; L[i:i + len(x)] += x * (1 - max(0, pan)); R[i:i + len(x)] += x * (1 + min(0, pan))

    rain = spec.get("rain", {})
    if rain:
        n = np.random.default_rng(9).standard_normal(N)
        until = S[rain["until"]] if rain.get("until") else total
        gain = np.clip(t / 0.4, 0, 1) * (1 - np.clip((t - (until - 0.6)) / 1.2, 0, 1))
        for hid in rain.get("heavy", []):
            a, b = S[hid], S[hid] + tl[hid]["dur"]
            gain *= 1 + 1.4 * np.clip((t - a) / 0.5, 0, 1) * (1 - np.clip((t - b) / 0.3, 0, 1))
        r = (bp(n, 1500, 7000) * 0.05 + lp(n, 400) * 0.035) * gain * (1 - 0.6 * slow)
        L += r; R += np.roll(r, 211)
    amb = spec.get("ambience")
    if amb:
        a = ambience(amb["kind"], N, t, amb.get("vol", 1.0)); L += a; R += np.roll(a, 157)
    if spec.get("chirps", True): add(SFX["chirp"](), finale_t + 0.6, 1, 0.6); add(SFX["chirp"](), finale_t + 2.0, 1, -0.5)

    def snap(at, win=0.45):
        i0, i1 = max(1, int((at - win) * FPS)), min(len(motion) - 1, int((at + win) * FPS))
        if i1 <= i0: return at
        seg = motion[i0:i1]; return (i0 + int(np.argmax(seg))) / FPS if seg.max() > np.median(motion) * 1.3 else at

    for s in spec["shots"]:
        for e in s.get("sfx", []):
            at = S[s["id"]] + e.get("at", 0.0)
            if e.get("snap"): at = snap(at)
            fn = SFX[e["fx"]]
            add(fn(**e.get("args", {})), at, e.get("vol", 1.0), e.get("pan", 0.0))
        if "badge" in s:
            at = S[s["id"]] + s.get("badge_at", 0.25); add(SFX["popup"](), at); add(SFX["bell"](84 + 2 * s["badge"], 0.7, 0.18), at + 0.05)
        if "bang" in s: add(SFX["eep"](), S[s["id"]] + s["bang"].get("at", 0.15) + 0.03, 0.8)
        for a, b in tl[s["id"]]["slow"]: add(SFX["riser"](1.6), a - 1.4, 1)
    ser = spec.get("series", {})
    if ser.get("earn"): add(SFX["rainbow"](), S[ser["earn"]["shot"]] + ser["earn"].get("at", 0.5), 0.8); add(SFX["sparkle"](), S[ser["earn"]["shot"]] + ser["earn"].get("at", 0.5) + 0.1)
    if not chapter and spec.get("end_tag", "PUDDLE PALS"):
        for i, m in enumerate([84, 88, 91, 96]): add(SFX["bell"](m, 1.6, 0.18), total - 2.2 + i * 0.09, 1, -0.3 + i * 0.2)
    if not chapter and spec.get("loop_drop", True): add(SFX["drip_whistle"](), total - 0.75)
    mix = master(L, R)
    if spec.get("song"):
        mix = song_lr * 0.9 + mix * spec["song"].get("sfx_vol", 0.35); mix = mix / max(1.0, np.abs(mix).max() / 0.97)
    if voice_tl and talk.any():   # voice stays dry and on top of the master
        mix = mix * 0.82 + np.stack([voice, voice], 1) * 0.55
        mix = mix / max(1.0, np.abs(mix).max() / 0.95)
    wavfile.write(out_wav, SR, (mix * 32767).astype(np.int16))

def thumbnail(spec, tl, body, out_jpg, font_path, ff, ch_color=None, key_dir=None):
    """1280x720 thumbnail. Source: the shot's sharp keyframe when there is one, else a clean frame of the edit.
    The picture sits on the right over a blurred copy of itself; 1-2 big words on the left."""
    th = spec.get("thumb", {})
    sid = th.get("shot", spec.get("finale", spec["shots"][-1]["id"]))
    key = os.path.join(key_dir, f"{sid}.png") if key_dir else None
    if key and os.path.exists(key) and th.get("source", "key") == "key":
        fr = Image.open(key).convert("RGB").resize((VW, VH), Image.LANCZOS)
    else:
        at = tl[sid]["start"] + th.get("at", tl[sid]["dur"] * 0.45); tmp = out_jpg + ".png"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", body, "-frames:v", "1", tmp], check=True)
        fr = Image.open(tmp).convert("RGB"); os.remove(tmp)
    from PIL import ImageEnhance
    fr = ImageEnhance.Color(ImageEnhance.Contrast(fr).enhance(1.08)).enhance(1.15)
    if fr.width > fr.height:      # 16:9 episode: the picture fills the thumbnail, words over a soft left shade
        W2, H2 = 1280, 720; im = fr.resize((W2, H2), Image.LANCZOS).convert("RGBA")
        sh_ = Image.new("L", (W2, H2), 0); d_ = ImageDraw.Draw(sh_)
        for x in range(0, 640): d_.line([(x, 0), (x, H2)], fill=int(150 * (1 - x / 640) ** 1.4))
        im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W2, H2), 0)] * 3 + [sh_]))
        words = th.get("text") or spec.get("hook") or [spec.get("slug", "").replace("_", " ").upper()]
        col = tuple(ch_color) if ch_color else ORANGE
        Ls = []
        for i, w in enumerate(words[:2]):
            L = _text(font_path, w.upper(), 104 if i == 0 else 120, fill=WHITE if i == 0 else GOLD,
                      stroke=col if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] < 170 else NAVY, sw=14)
            if L.width > 600: L = L.resize((600, int(L.height * 600 / L.width)), Image.LANCZOS)
            Ls.append(L)
        y = H2 / 2 - sum(L.height - 20 for L in Ls) / 2 - 20
        for L in Ls: im.alpha_composite(L, (40, int(y))); y += L.height - 20
        tag = _text(font_path, spec.get("brand", "PUDDLE PALS"), 44, stroke=NAVY, sw=7); im.alpha_composite(tag, (W2 - tag.width - 24, H2 - tag.height - 16))
        ImageDraw.Draw(im).rectangle([0, 0, W2 - 1, H2 - 1], outline=col + (255,), width=10)
        im.convert("RGB").save(out_jpg, quality=92); return out_jpg
    W2, H2 = 1280, 720; band = int(VW * H2 / 760)
    y = th.get("y")
    if y is None:          # aim at the faces: a bit below the top of the characters in that shot
        shot = next(x for x in spec["shots"] if x["id"] == sid)
        mem = [m for m in shot_members(shot) if not m["char"].startswith("prop:")] if (shot.get("char") or shot.get("cast")) else []
        y = (sum(m["place"]["foot"] - 0.7 * m["place"]["h"] for m in mem) / len(mem) + 0.08) if mem else 0.6
    cy = int(min(max(y, 0.0), 1.0) * VH); y0 = min(max(cy - band // 2, 0), VH - band)
    pic = fr.crop((0, y0, VW, y0 + band)); pic = pic.resize((int(pic.width * H2 / pic.height), H2), Image.LANCZOS)
    bg = fr.resize((W2, int(VH * W2 / VW)), Image.LANCZOS).crop((0, int(cy * W2 / VW) - H2 // 2, W2, int(cy * W2 / VW) + H2 // 2))
    im = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(28))).enhance(0.8).convert("RGBA")
    px = W2 - pic.width - 10
    m = Image.new("L", pic.size, 255); ImageDraw.Draw(m).rectangle([0, 0, 60, H2], fill=0)
    m = m.filter(ImageFilter.GaussianBlur(30)); im.paste(pic, (px, 0), m)
    words = th.get("text") or spec.get("hook") or [spec.get("slug", "").replace("_", " ").upper()]
    col = tuple(ch_color) if ch_color else ORANGE
    room = px + 40; ys = []
    Ls = []
    for i, w in enumerate(words[:2]):
        L = _text(font_path, w.upper(), 120 if i == 0 else 136, fill=WHITE if i == 0 else GOLD, stroke=col if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] < 170 else NAVY, sw=14)
        if L.width > room - 30: L = L.resize((room - 30, int(L.height * (room - 30) / L.width)), Image.LANCZOS)
        Ls.append(L)
    total_h = sum(L.height - 20 for L in Ls); y = H2 / 2 - total_h / 2 - 30
    for L in Ls: im.alpha_composite(L, (int(room / 2 - L.width / 2 + 10), int(y))); y += L.height - 20
    tag = _text(font_path, spec.get("brand", "PUDDLE PALS"), 44, stroke=NAVY, sw=7)
    im.alpha_composite(tag, (W2 - tag.width - 24, H2 - tag.height - 16))
    if spec.get("series"):
        ch = _text(font_path, f"CHAPTER {spec['series'].get('chapter')}", 48, stroke=col, sw=8)
        im.alpha_composite(ch, (int(room / 2 - ch.width / 2 + 10), 40))
    d = ImageDraw.Draw(im); d.rectangle([0, 0, W2 - 1, H2 - 1], outline=col + (255,), width=10)
    im.convert("RGB").save(out_jpg, quality=92)
    return out_jpg

THUMB_FONTS = {   # Korean display fonts (OFL), downloaded on first use
    "jua": "https://github.com/google/fonts/raw/main/ofl/jua/Jua-Regular.ttf",
    "blackhan": "https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf",
    "dohyeon": "https://github.com/google/fonts/raw/main/ofl/dohyeon/DoHyeon-Regular.ttf",
    "gowun": "https://github.com/google/fonts/raw/main/ofl/gowunbatang/GowunBatang-Bold.ttf",
    "pen": "https://github.com/google/fonts/raw/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf",
}
THUMB_COLORS = {   # (main text, accent text, outline)
    "warm": ((255, 255, 255), (255, 214, 102), (120, 50, 20)),
    "night": ((255, 255, 255), (150, 210, 255), (20, 30, 70)),
    "ink": ((30, 30, 35), (190, 40, 40), (255, 255, 255)),
    "sunset": ((255, 240, 220), (255, 150, 90), (70, 20, 40)),
    "mint": ((255, 255, 255), (170, 255, 210), (20, 70, 60)),
}
THUMB_LAYOUTS = ["top", "bottom_left", "band", "split", "side"]

def _thumb_font(name, fallback):
    import urllib.request
    url = THUMB_FONTS.get(name)
    if not url: return fallback
    dst = f"/tmp/thumbfont_{name}.ttf"
    try:
        if not os.path.exists(dst): urllib.request.urlretrieve(url, dst)
        return dst
    except Exception: return fallback

def thumbnail_vertical(spec, tl, body, out_jpg, font_path, ff, ch_color=None, key_dir=None, frame=None):
    """1080x1920 cover for Shorts. thumb = {"text": [line1, line2], "shot", "layout", "font", "colors"}: the layout, font and
    colours vary per Short (make_short picks a different combination each time) so the channel grid does not look templated."""
    th = spec.get("thumb", {})
    sid = th.get("shot", spec.get("finale", spec["shots"][-1]["id"]))
    key = os.path.join(key_dir, f"{sid}.png") if key_dir else None
    if frame is not None: fr = frame.convert("RGB")
    elif key and os.path.exists(key) and th.get("source", "key") == "key": fr = Image.open(key).convert("RGB")
    else:
        at = tl[sid]["start"] + th.get("at", tl[sid]["dur"] * 0.45); tmp = out_jpg + ".png"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", body, "-frames:v", "1", tmp], check=True)
        fr = Image.open(tmp).convert("RGB"); os.remove(tmp)
    from PIL import ImageEnhance
    fr = ImageEnhance.Color(ImageEnhance.Contrast(fr.resize((VW, VH), Image.LANCZOS)).enhance(1.08)).enhance(1.15)
    im = fr.convert("RGBA")
    lay = th.get("layout", "top"); fnt = _thumb_font(th.get("font", "jua"), font_path)
    c1, c2, ol = THUMB_COLORS.get(th.get("colors", "warm"), THUMB_COLORS["warm"])
    words = (th.get("text") or spec.get("hook") or [spec.get("slug", "")])[:2]
    shade = Image.new("L", (VW, VH), 0); d = ImageDraw.Draw(shade)
    if lay in ("top", "split"):
        for y in range(0, 720): d.line([(0, y), (VW, y)], fill=int(170 * (1 - y / 720) ** 1.5))
    if lay in ("bottom_left", "split"):
        for y in range(1150, VH): d.line([(0, y), (VW, y)], fill=int(190 * ((y - 1150) / 770) ** 1.3))
    if lay == "side":
        for x in range(0, 560): d.line([(x, 0), (x, VH)], fill=int(170 * (1 - x / 560) ** 1.4))
    dark = Image.merge("RGBA", [Image.new("L", (VW, VH), 0)] * 3 + [shade]) if c1[0] > 128 else \
           Image.merge("RGBA", [Image.new("L", (VW, VH), 255)] * 3 + [shade])
    im.alpha_composite(dark)
    def fit(L, maxw):
        return L if L.width <= maxw else L.resize((maxw, int(L.height * maxw / L.width)), Image.LANCZOS)
    big = [fit(_text(fnt, w, 150 if i == 0 else 120, fill=c1 if i == 0 else c2, stroke=ol, sw=14), VW - 90) for i, w in enumerate(words)]
    if lay == "top":
        y = 170
        for L in big: im.alpha_composite(L, (int(VW / 2 - L.width / 2), y)); y += L.height - 10
    elif lay == "bottom_left":
        y = VH - 330 - sum(L.height - 10 for L in big)
        for L in big: im.alpha_composite(L, (55, y)); y += L.height - 10
    elif lay == "band":
        bh = sum(L.height for L in big) + 60; y0 = int(VH * 0.09)   # faces sit in the middle/lower half
        band = Image.new("RGBA", (VW, bh), (*ol, 175)); im.alpha_composite(band, (0, y0)); y = y0 + 30
        for L in big: im.alpha_composite(L, (int(VW / 2 - L.width / 2), y)); y += L.height
    elif lay == "split":
        im.alpha_composite(big[0], (int(VW / 2 - big[0].width / 2), 150))
        if len(big) > 1: im.alpha_composite(big[1], (int(VW / 2 - big[1].width / 2), VH - big[1].height - 330))
    else:   # side: words stacked down the left edge, one per line, smaller
        y = 150
        for w in " ".join(words).split():
            L = fit(_text(fnt, w, 104, fill=c1, stroke=ol, sw=11), 480); im.alpha_composite(L, (40, y)); y += L.height - 6
    if th.get("brand"):   # off by default (the channel name is already on the channel page); a small corner mark if asked
        tag = _text(fnt, spec.get("brand", "MIDLIFE COMMUTER"), 40, fill=c1, stroke=ol, sw=6)
        im.alpha_composite(tag, (VW - tag.width - 40, 60) if lay in ("bottom_left", "side") else (40, VH - tag.height - 60))
    im.convert("RGB").save(out_jpg, quality=92)
    return out_jpg

def finalize(video, wav, out_mp4, ff):
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, "-i", wav, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out_mp4],
                   check=True)

def review_sheet(video, out_png, ff):
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, "-vf", "fps=1,scale=180:-1,tile=12x3", "-frames:v", "1", out_png], check=True)
