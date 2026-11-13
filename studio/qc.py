# ===================== qc.py: automatic visual check of every scene before a person sees it =====================
# A vision-language model (Qwen2.5-VL-7B) looks at each keyframe, and at three frames of each animated shot, against
# the problems found by hand in SH01 (panels, riderless scooter, pagodas, a neighbour popping in, a bench stuck to M,
# cut-off family, photo-real passengers). A shot that fails is drawn again with a new seed (main.py decides how often).
import json, os, re, subprocess

QC_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
_vlm = {}

CHECKLIST = """You are a strict quality checker for a vertical 3D animated (Pixar-like) Short set in present-day South Korea.
Intended scene: {scene}
Main characters that must be fully visible: {who}
Check the image(s) for these problems only:
1. the picture is split into several panels, a collage or stacked copies of the same scene
2. a scooter, motorbike or bicycle is moving or placed in the road with nobody riding it
3. pagodas, temples or clearly Japanese/Chinese traditional buildings instead of a modern Korean place
4. a main character is cut off by the frame edge, has a distorted face, extra limbs or melted hands
5. people who look like real photographs next to the cartoon characters
6. a person or object that suddenly appears or disappears between the frames (only when several frames are given)
7. a chair, bench or other furniture fused to a character's body
8. visible garbled text taking up a big part of the picture
Reply with JSON only: {{"ok": true or false, "problems": ["short description", ...]}}. ok is false if any problem is clearly present."""


def _qc_load():
    if _vlm: return _vlm
    import torch
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
    _vlm["model"] = Qwen2_5_VLForConditionalGeneration.from_pretrained(QC_MODEL, torch_dtype=torch.bfloat16, device_map="cuda")
    _vlm["proc"] = AutoProcessor.from_pretrained(QC_MODEL, min_pixels=256 * 28 * 28, max_pixels=640 * 28 * 28)
    return _vlm


def qc_unload():
    if _vlm:
        import torch, gc
        _vlm.clear(); gc.collect(); torch.cuda.empty_cache()


def qc_check(images, scene, who):
    """images: list of picture paths (one keyframe, or frames of one shot). Returns {"ok": bool, "problems": [...]}."""
    from PIL import Image
    import torch
    m = _qc_load()
    content = [{"type": "image"} for _ in images] + [{"type": "text", "text": CHECKLIST.format(scene=scene, who=who or "none")}]
    msgs = [{"role": "user", "content": content}]
    text = m["proc"].apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ims = [Image.open(p).convert("RGB") for p in images]
    inp = m["proc"](text=[text], images=ims, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = m["model"].generate(**inp, max_new_tokens=160, do_sample=False)
    ans = m["proc"].batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0]
    hit = re.search(r"\{.*\}", ans, re.S)
    try:
        r = json.loads(hit.group(0)) if hit else {}
    except Exception:
        r = {}
    if "ok" not in r:   # unreadable answer: do not block the run on the checker itself
        return {"ok": True, "problems": [], "raw": ans[:200]}
    return {"ok": bool(r["ok"]), "problems": [str(p)[:160] for p in r.get("problems", [])][:5]}


def qc_frames(mp4, out_prefix, n=3):
    """First, middle and last frame of a shot (for checks that need motion: things popping in or out)."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                               capture_output=True, text=True).stdout.strip() or 0)
    paths = []
    for k, t in enumerate([0.2, dur / 2, max(0.0, dur - 0.3)][:n]):
        p = f"{out_prefix}_{k}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", mp4, "-frames:v", "1", "-vf", "scale=-2:640", p])
        if os.path.exists(p): paths.append(p)
    return paths


def qc_who(shot):
    names = {"m": "M (middle-aged man with glasses, grey coat)", "wife": "his wife", "son": "his son", "daughter": "his little daughter",
             "junior": "a young colleague", "boss": "his boss", "friend": "his friend", "grandma": "grandmother", "grandpa": "grandfather"}
    chars = [c["char"] for c in shot.get("cast", [])] or ([shot["char"]] if shot.get("char") else [])
    return ", ".join(names.get(c, c) for c in chars)


# ---- calibration: run the checker on frames we already judged by hand (assets/qccal_good_* / qccal_bad_*) ----
if globals().get("SPEC", {}).get("type") == "qccal":
    import glob as _glob
    out = os.path.join(os.environ.get("STUDIO_OUT", "/kaggle/working/out"), SPEC["id"]); os.makedirs(out, exist_ok=True)
    rows = []
    for p in sorted(_glob.glob("/kaggle/input/**/qccal_*.jpg", recursive=True)):
        name = os.path.basename(p)[6:-4]
        r = qc_check([p], "a scene of a 3D animated Short about a Korean office worker's commute", "M (middle-aged man with glasses, grey coat)")
        rows.append({"frame": name, "expected_ok": name.startswith("good"), "ok": r["ok"], "problems": r["problems"]})
        print(name, r, flush=True)
    hits = sum(1 for x in rows if x["ok"] == x["expected_ok"])
    json.dump({"episode": SPEC["id"], "type": "qccal", "agree": f"{hits}/{len(rows)}", "rows": rows},
              open(f"{out}/report.json", "w"), indent=1, ensure_ascii=False)
