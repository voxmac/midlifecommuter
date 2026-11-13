# ===================== voice.py: narrator (Kokoro-82M, Apache-2.0, CPU) and helper venvs =====================
# Extra tools run in their own virtualenv (sharing torch from the system) so their pins can't break numpy here.
import os, sys, json, subprocess, time
import numpy as np

NARRATOR = "af_heart"          # warm, clear US-English voice
VOICE_SR = 24000

def venv(name, packages, apt=()):
    """A virtualenv at /tmp/<name> that sees system packages (torch) but installs its own pins."""
    py = f"/tmp/{name}/bin/python"
    if not os.path.exists(py):
        for a in apt: subprocess.run(f"apt-get -qq install -y {a} >/dev/null 2>&1", shell=True)
        # Kaggle's Python has no ensurepip: make the venv without pip and install into it with the system pip
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", "--without-pip", f"/tmp/{name}"], check=True)
        r = subprocess.run([sys.executable, "-m", "pip", "--python", py, "install", "-q", *packages], capture_output=True, text=True)
        if r.returncode: print(r.stdout[-2000:], r.stderr[-2000:]); raise RuntimeError(f"pip install failed for {name}")
    return py

# Kokoro-82M through kokoro-onnx (runs on Python 3.13, no torch/spacy pins); model files from its GitHub release
KOKORO_FILES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
TTS_SCRIPT = r'''
import json, os, sys, urllib.request, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
M = "/tmp/kokoro_models"; os.makedirs(M, exist_ok=True)
for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
    if not os.path.exists(f"{M}/{f}"): urllib.request.urlretrieve(sys.argv[2] + f, f"{M}/{f}.part"); os.rename(f"{M}/{f}.part", f"{M}/{f}")
k = Kokoro(f"{M}/kokoro-v1.0.onnx", f"{M}/voices-v1.0.bin")
for j in json.load(open(sys.argv[1])):
    a, sr = k.create(j["text"], voice=j["voice"], speed=j["speed"], lang="en-us")
    sf.write(j["out"], np.asarray(a, np.float32), sr, subtype="PCM_16")
'''

def _even_words(text, dur):
    w = text.split(); n = max(1, len(w)); weights = np.array([len(x) + 2 for x in w], float)
    edges = np.concatenate([[0], np.cumsum(weights) / weights.sum() * dur])
    return [[x, float(edges[i]), float(edges[i + 1])] for i, x in enumerate(w)]

def estimate_seconds(text, speed=0.92):
    return len(text.split()) / (2.55 * speed) + 0.35

def narrate(lines, out_dir):
    """lines: [{key, text, speed?, voice?}] -> {key: {"wav": path, "dur": s, "words": [[w, a, b], ...]}}"""
    os.makedirs(out_dir, exist_ok=True)
    jobs = [{"text": l["text"], "voice": l.get("voice", NARRATOR), "speed": l.get("speed", 0.92),
             "out": f"{out_dir}/{l['key']}.wav"} for l in lines]
    out = {}
    if not jobs: return out
    if os.environ.get("STUDIO_LOCAL") and not os.environ.get("STUDIO_TTS"):
        # local engine test: silent placeholder of the expected length (captions and ducking still exercised)
        from scipy.io import wavfile
        for j, l in zip(jobs, lines):
            d = estimate_seconds(j["text"], j["speed"]); wavfile.write(j["out"], VOICE_SR, np.zeros(int(d * VOICE_SR), np.int16))
            out[l["key"]] = {"wav": j["out"], "dur": d, "words": _even_words(j["text"], d - 0.2), "placeholder": True}
        return out
    t0 = time.time()
    py = venv("tts", ["kokoro-onnx>=0.4", "soundfile"])
    open("/tmp/tts_run.py", "w").write(TTS_SCRIPT); json.dump(jobs, open("/tmp/tts_jobs.json", "w"))
    r = subprocess.run([py, "/tmp/tts_run.py", "/tmp/tts_jobs.json", KOKORO_FILES], capture_output=True, text=True)
    if r.returncode: print(r.stdout[-2000:], r.stderr[-3000:]); raise RuntimeError("narration (Kokoro) failed")
    from scipy.io import wavfile
    for j, l in zip(jobs, lines):
        sr, a = wavfile.read(j["out"]); d = len(a) / sr
        lead = np.argmax(np.abs(a) > 300) / sr if np.abs(a).max() > 300 else 0.0   # skip leading silence
        words = _even_words(j["text"], d - lead - 0.15); words = [[w, x + lead, y + lead] for w, x, y in words]
        out[l["key"]] = {"wav": j["out"], "dur": d, "words": words}
    print(f"narration: {len(jobs)} lines in {time.time() - t0:.0f}s", flush=True)
    return out

def load_voice(path, sr_out):
    """wav -> float mono at sr_out"""
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    sr, a = wavfile.read(path)
    is_int = np.issubdtype(a.dtype, np.integer)
    a = a.astype(np.float32); a = a.mean(1) if a.ndim > 1 else a
    if is_int: a = a / 32768.0
    if sr != sr_out: a = resample_poly(a, sr_out, sr)
    pk = np.abs(a).max()
    return a / pk * 0.8 if pk > 1e-4 else a

CUTOUT_SCRIPT = r'''
import sys, numpy as np
from PIL import Image
from scipy import ndimage
from rembg import remove, new_session
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
al = np.array(remove(im, session=new_session("isnet-general-use")))[..., 3].copy()
rgb = np.array(im).astype(np.float32)
border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
bgc = np.median(border, 0); low = al < 128
lab, n = ndimage.label(np.pad(low, 1, constant_values=True)); outside = lab[0, 0]; lab = lab[1:-1, 1:-1]
for i in range(1, n + 1):
    if i != outside and np.linalg.norm(rgb[lab == i].mean(0) - bgc) >= 30: al[lab == i] = 255
al[ndimage.binary_erosion(al > 40, iterations=6) & (np.linalg.norm(rgb - bgc, axis=-1) > 30)] = 255
al[al < 12] = 0
out = Image.fromarray(np.dstack([np.array(im), al]).astype(np.uint8)); out.crop(out.getbbox()).save(dst)
'''

def make_cutout(src, dst):
    """Background removal (rembg isnet) in its own venv; fills wrongly cleared holes inside the object."""
    py = venv("rbg", ["rembg[cpu]"])
    open("/tmp/cutout_run.py", "w").write(CUTOUT_SCRIPT)
    r = subprocess.run([py, "/tmp/cutout_run.py", src, dst], capture_output=True, text=True)
    if r.returncode: print(r.stderr[-3000:]); raise RuntimeError("cutout failed for " + src)
    return dst
