"""Builds a song Short spec (episodes/<id>.json) from a scene plan and the song's lyric timing.
usage: python tools/make_short.py shorts/SH01.json <timing.json from the song's prep release>
Plan: {"id", "song": "MC01", "pick": 1, "scenes": [{"lines": [0, 1] | "intro" | "outro", "end"?, "plate", "expr", "place"?, "camera"?}], ...}
Every scene is a still keyframe (plate + M cutout + light harmonising pass) with a slow camera move; captions are the
song's words, timed letter by letter from the Whisper alignment, coloured in karaoke style."""
import json, os, re, sys, difflib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plan = json.load(open(sys.argv[1], encoding="utf-8")); tm = json.load(open(sys.argv[2], encoding="utf-8"))
song = json.load(open(f"{ROOT}/songs/{plan['song']}.json", encoding="utf-8"))
norm = lambda x: re.sub(r"[\W_]", "", x.lower())
lines = [l.strip() for l in song["lyrics"].split("\n") if l.strip() and not l.strip().startswith("[")]
starts = [l["start"] for l in tm["lines"]]; ends = [l["end"] for l in tm["lines"]]
assert len(lines) == len(starts), (len(lines), len(starts))
heard = tm["heard"]
units = [(ch, i, k) for i, l in enumerate(lines) for k, w in enumerate(l.split()) for ch in norm(w)]
sm = difflib.SequenceMatcher(None, [u[0] for u in units], [h[0] for h in heard], autojunk=False)
t = [None] * len(units)
for a, b, n in sm.get_matching_blocks():
    for j in range(n): t[a + j] = (heard[b + j][1], heard[b + j][2])
lyrics_tl = []
for i, l in enumerate(lines):
    words = l.split(); s0, s1 = starts[i], ends[i]; out = []
    for k, w in enumerate(words):
        got = [t[j] for j, u in enumerate(units) if u[1] == i and u[2] == k and t[j]]
        if got: a, b = got[0][0], got[-1][1]
        else: a = s0 + (s1 - s0) * k / len(words); b = s0 + (s1 - s0) * (k + 1) / len(words)
        if a <= 0.01: a = max(0.0, b - 0.3 * len(norm(w)) - 0.15)     # Whisper pins a song's first word to 0 s
        out.append([w, round(a, 2), round(max(b, a + 0.15), 2)])
    for j in range(1, len(out)):
        if out[j][1] < out[j - 1][1] + 0.05: out[j][1] = round(out[j - 1][1] + 0.12, 2); out[j][2] = max(out[j][2], out[j][1] + 0.15)
    lyrics_tl.append(out)
# ---- pre-flight lint: the mistakes found by hand in SH01, caught before any GPU time is spent ----
import re as _re
errors, notes = [], []
for n, sc in enumerate(plan["scenes"]):
    tag = f"scene {n + 1}"
    txt = " ".join([sc.get("plate", ""), sc.get("extras", ""), sc.get("motion", "")]).lower()
    if _re.search(r"scooter|motorbike|motorcycle|bicycle|\bbike\b", txt) and not _re.search(r"rid(es|ing|er)|on his|on her|sits on", txt):
        errors.append(f"{tag}: a scooter/bike is mentioned without its rider (it would move empty)")
    if _re.search(r"\b(appears?|walks in|pops? up|comes into view|enters)\b", sc.get("motion", "").lower()):
        errors.append(f"{tag}: the motion makes someone appear mid-shot; put them in the picture from the first frame")
    if plan.get("strict", True) and sc.get("motion") and not sc.get("must"):
        errors.append(f"{tag}: list in 'must' the objects the motion animates (they are checked in the keyframe before animating)")
    for w in ("steam", "smoke", "pot", "laptop", "phone", "swing", "slide", "door", "window", "clock", "tree", "leaves"):
        if _re.search(rf"\b{w}", sc.get("motion", "").lower()) and sc.get("must") and not any(w in m.lower() for m in sc["must"]) \
                and not (w == "steam" and any("pot" in m.lower() or "kettle" in m.lower() for m in sc["must"])) and w not in ("leaves",):
            errors.append(f"{tag}: the motion animates '{w}' but 'must' does not list it")
    if not _re.search(r"korea|seoul|busan|daegu", sc.get("plate", "").lower()):
        sc["plate"] = sc["plate"] + ", in present-day South Korea"; notes.append(f"{tag}: added 'present-day South Korea' to the place")
    for c in sc.get("cast", []) or [{"char": sc.get("char", plan.get("lead", "m")), "expr": sc.get("expr"), "place": sc.get("place", {})}]:
        if plan.get("lead") == "mh" and c["char"] == "m":
            errors.append(f"{tag}: this song is after M left the company; use 'mh' (everyday clothes), not 'm' (suit, badge, briefcase)")
        if c["char"] == "m" and _re.search(r"bedroom|kitchen|living room|bathroom|at home|apartment entrance|hyeongwan", sc.get("plate", "").lower()):
            errors.append(f"{tag}: M in his office suit inside the home; use 'mh' (everyday clothes)")
        if c.get("expr") == "seated":
            errors.append(f"{tag}: the 'seated' pose carries its own bench; use a standing pose or a seat drawn in the place")
        pl = {"h": 0.5, "cx": 0.5, "foot": 0.95, **c.get("place", {})}
        half = pl["h"] * 1920 * (1.85 if c.get("expr") == "bed" else 0.45) / 1080 / 2   # a person is about 0.45 of their height wide; a bed about 1.85
        if pl["cx"] - half < 0.02 or pl["cx"] + half > 0.98:
            errors.append(f"{tag}: {c['char']} would be cut off at the frame edge (cx {pl['cx']}, h {pl['h']})")
        if pl["foot"] - pl["h"] < 0.08:
            errors.append(f"{tag}: {c['char']}'s head would hit the top of the frame")
up = plan.get("upload", {})   # every Short ships with its own title, description and tags
if not up.get("title") or len(up["title"]) > 100: errors.append("upload: a title of at most 100 characters is needed")
if "#shorts" not in up.get("title", "").lower() + up.get("description", "").lower(): errors.append("upload: add #shorts to the title or description")
if len(up.get("description", "")) < 80: errors.append("upload: write a description (lyrics hook, story line, comment question, AI note, hashtags)")
if not up.get("tags"): errors.append("upload: add tags")
for x in notes: print("note:", x)
if errors:
    print("\n".join("LINT: " + e for e in errors)); sys.exit("scene plan has problems; fix them before spending GPU time")
total = plan["seconds"]
shots = []
for n, sc in enumerate(plan["scenes"]):
    ls = sc["lines"]
    a = 0.0 if n == 0 else shots[-1]["slot"][1]
    nxt = plan["scenes"][n + 1]["lines"] if n + 1 < len(plan["scenes"]) else None
    if sc.get("end"): b = sc["end"]   # split a long instrumental intro into several scenes ("lines": "intro", "end": s)
    else: b = total if nxt is None else (ends[-1] + 0.3 if nxt == "outro" else starts[nxt[0]] - 0.15)
    place = {"h": 0.5, "cx": 0.5, "foot": 0.95, "shadow": 0.45, **sc.get("place", {})}
    shot = {"id": f"S{n + 1}", "slot": [round(a, 2), round(b, 2)], "plate": sc["plate"],
            "camera": sc.get("camera", {"move": "push", "amount": 0.04})}
    if sc.get("motion"):   # animated with Wan 2.2 (16 fps): enough frames to cover the slot, 4k+1
        fr = min(121, 4 * int(((b - a) * 16 + 3) // 4) + 5)
        shot.update({"motion": sc["motion"], "frames": fr})
    else:
        shot.update({"still": True, "dur": round(b - a + 0.6, 2)})
    if sc.get("cast"):   # several people: M's family, colleagues, friends ...
        shot["cast"] = [{"char": c["char"], "expr": c.get("expr"), "flip": c.get("flip", False),
                         "place": {"h": 0.5, "cx": 0.5, "foot": 0.93, "shadow": 0.45, **c.get("place", {})}} for c in sc["cast"]]
    else:
        shot.update({"char": sc.get("char", plan.get("lead", "m")), "expr": sc.get("expr"), "place": place})
    if sc.get("extras"): shot["extras"] = sc["extras"]   # passers-by, commuters, elderly people in the background
    for k in ("must", "avoid", "avoid_key", "props", "key_seed"):   # scene-specific checks: what the keyframe must show, what must not happen in the shot
        if sc.get(k): shot[k] = sc[k]
    shots.append(shot)
spec = {"id": plan["id"], "slug": plan["slug"], "format": "mv", "aspect": "9:16", "lead": plan.get("lead", "m"),
        "song": {"file": f"{plan['song']}_v{plan['pick']}", "at": 0.0, "sfx_vol": 0.0},
        "lyrics_tl": lyrics_tl, "font": "Jua-Regular",
        "font_url": "https://github.com/google/fonts/raw/main/ofl/jua/Jua-Regular.ttf",
        "brand": "MIDLIFE COMMUTER", "cap_y": plan.get("cap_y", 0.83), "cap_size": plan.get("cap_size", 60), "cap_line": True, "top_label": plan.get("top_label"),
        "budget_min": plan.get("budget_min", 220), "wan_min": plan.get("wan_min", 8), "hook": plan.get("hook", []),
        "end_tag": "", "loop_drop": False, "chirps": False, "tracker": False, "captions": True,
        "props": plan.get("props", {}), "thumb": plan.get("thumb", {}), "retake": plan.get("retake", []), "upload": plan["upload"], "gpu": plan.get("gpu", "T4"), "shots": shots}
dst = f"{ROOT}/episodes/{plan['id']}.json"
json.dump(spec, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(dst, len(shots), "scenes,", sum(len(x) for x in lyrics_tl), "caption words")
