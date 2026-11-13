# ===================== qc.py: automatic visual check of every scene before a person sees it =====================
# A vision-language model (Qwen2.5-VL-7B) looks at each keyframe, and at three frames of each animated shot, against
# the problems found by hand in SH01 (panels, riderless scooter, pagodas, a neighbour popping in, a bench stuck to M,
# cut-off family, photo-real passengers). A shot that fails is drawn again with a new seed (main.py decides how often).
import json, os, re, subprocess

QC_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
_vlm = {}

# one short yes/no question per problem: a 7B vision model answers these far more reliably than one long checklist
# (QC01 calibration: the checklist version agreed with a person on 5 of 7 frames and gave wrong reasons)
QUESTIONS = [
    ("panels", "Look at the whole image. Is it made of two or more separate pictures stacked on top of each other or placed side by side, with straight borders between them?"),
    ("riderless", "Is there a scooter, motorbike or bicycle in this image that nobody is sitting on?"),
    ("pagoda", "Does this image show a pagoda, a temple roof, or traditional Japanese or Chinese style buildings with curved tiled roofs?"),
    ("cutoff", "Is one of the cartoon characters cut off by the left or right edge of the image, so that part of their body is missing?"),
    ("melted", "Does one of the cartoon characters have a clearly distorted face, extra arms or legs, or melted hands?"),
    ("furniture", "Is a chair or bench attached to a cartoon character's body as if it were part of them?"),
]
TEMPORAL = ("popin", "These are the first, middle and last frames of one shot. Does a person or a large object appear or disappear between them?")
LABELS = {"panels": "picture split into panels / stacked copies", "riderless": "scooter or bike with nobody riding it",
          "pagoda": "pagodas or Japanese/Chinese-style buildings", "cutoff": "a character cut off at the frame edge",
          "melted": "distorted face or extra limbs", "furniture": "a chair or bench fused to a character",
          "popin": "someone or something pops in or out during the shot"}


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


def _ask(m, ims, question):
    import torch
    content = [{"type": "image"} for _ in ims] + [{"type": "text", "text": question + " Answer only yes or no."}]
    text = m["proc"].apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
    inp = m["proc"](text=[text], images=ims, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = m["model"].generate(**inp, max_new_tokens=4, do_sample=False)
    return m["proc"].batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0].strip().lower().startswith("yes")


def qc_check(images, scene=None, who=None, only=None):
    """images: one keyframe, or the first/middle/last frames of a shot. Returns {"ok", "problems", "flags"}."""
    from PIL import Image
    m = _qc_load()
    ims = [Image.open(p).convert("RGB") for p in images]
    flags = [k for k, q in QUESTIONS if (not only or k in only) and _ask(m, ims[-1:] if len(ims) == 1 else ims[:1], q)]
    if len(ims) > 1:
        flags += [k for k, q in QUESTIONS if k in ("riderless", "cutoff", "melted") and k not in flags and _ask(m, ims[-1:], q)]
        if _ask(m, ims, TEMPORAL[1]): flags.append(TEMPORAL[0])
    return {"ok": not flags, "problems": [LABELS[k] for k in flags], "flags": flags}


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
