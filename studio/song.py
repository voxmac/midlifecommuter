# ===================== song.py: original Puddle Pals songs with ACE-Step 1.5 (MIT) on a Kaggle T4 =====================
# ACE-Step needs Python 3.11-3.12; Kaggle runs 3.13, so uv builds its own environment (Python 3.12 + torch cu128).
import os, json, subprocess, time, shutil

ACE_DIR = "/tmp/ace"
OUT = os.environ.get("STUDIO_OUT", "/kaggle/working/out")

GEN = r'''
import json, os, sys, time
sys.path.insert(0, "/tmp/ace")
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music
spec, out = json.load(open(sys.argv[1])), sys.argv[2]
dit = AceStepHandler()
msg, ok = dit.initialize_service(project_root="/tmp/ace", config_path=spec.get("dit", "acestep-v15-turbo"), device="cuda", offload_to_cpu=True)
print("DiT:", msg, flush=True); assert ok, msg
from acestep.model_downloader import ensure_lm_model
from pathlib import Path
print("LM model:", ensure_lm_model(spec.get("lm", "acestep-5Hz-lm-0.6B"), Path("/tmp/ace/checkpoints")), flush=True)
llm = LLMHandler()
msg, ok = llm.initialize(checkpoint_dir="/tmp/ace/checkpoints", lm_model_path=spec.get("lm", "acestep-5Hz-lm-0.6B"),
                         backend="pt", device="cuda", offload_to_cpu=True, dtype=None)
print("LM:", msg, flush=True); assert ok, msg
rep = []
ext = spec.get("extend")   # keep a chosen take and redo only its tail (e.g. a last line that was cut off), longer if needed
for i, seed in enumerate(spec.get("seeds", [11, 22, 33, 44])):
    t0 = time.time()
    if ext:
        p = GenerationParams(task_type="repaint", src_audio=spec["_src"], repainting_start=ext["start"],
                             repainting_end=ext["end"], chunk_mask_mode="explicit", thinking=False,
                             caption=spec["style"] + ", " + ext.get("caption", "the last line is sung completely, then a gentle short outro that ends naturally"),
                             lyrics=spec["lyrics"], bpm=spec.get("bpm"), keyscale=spec.get("key", ""),
                             timesignature=spec.get("time", "4"), vocal_language=spec.get("lang", "en"),
                             duration=ext.get("total", ext["end"]), inference_steps=8, guidance_scale=1.0, seed=seed)
    else:
        p = GenerationParams(task_type="text2music", thinking=True, caption=spec["style"], lyrics=spec["lyrics"],
                         bpm=spec.get("bpm"), keyscale=spec.get("key", ""), timesignature=spec.get("time", "4"),
                         vocal_language=spec.get("lang", "en"), duration=spec.get("duration", 120), inference_steps=8,
                         guidance_scale=1.0, seed=seed)
    import torch; torch.cuda.empty_cache()
    r = generate_music(dit, llm, params=p, config=GenerationConfig(batch_size=1, audio_format="wav"), save_dir=out)
    if not r.success: print("FAILED", seed, r.status_message, flush=True); continue
    a = r.audios[0]; dst = f"{out}/{spec['id']}_v{i + 1}.wav"; os.replace(a["path"], dst)
    rep.append({"version": i + 1, "seed": seed, "file": os.path.basename(dst), "key": a.get("key"),
                "seconds_to_make": round(time.time() - t0)})
    print("made", dst, round(time.time() - t0), "s", flush=True)
json.dump(rep, open(f"{out}/versions.json", "w"), indent=1)
'''

def sh(cmd):
    print("$", cmd, flush=True); subprocess.run(cmd, shell=True, check=True)

def fit_seconds(spec):
    """Seconds the lyrics need: about two bars per sung line, plus two bars of intro and four of outro."""
    lines = [l for l in spec["lyrics"].split("\n") if l.strip() and not l.strip().startswith("[")]
    bar = 4 * 60 / spec.get("bpm", 90)
    return int(round((len(lines) * 2 + 6) * bar))

def produce_song(spec):
    t0 = time.time(); E = f"{OUT}/{spec['id']}"; os.makedirs(E, exist_ok=True)
    if not os.path.exists(f"{ACE_DIR}/.venv/bin/python"):
        sh("pip install -q uv")
        sh(f"git clone -q --depth 1 https://github.com/ace-step/ACE-Step-1.5 {ACE_DIR}")
        sh(f"cd {ACE_DIR} && uv sync -q")
        # T4 has no bfloat16: ACE-Step falls back to float16, whose latents overflow to NaN. Use float32 instead.
        sh(f"sed -i 's/self.dtype = torch.float16/self.dtype = torch.float32/' {ACE_DIR}/acestep/core/generation/handler/init_service_orchestrator.py")
    if spec.get("extend"):
        src = find_input(spec["extend"]["from"]); assert src, "extend: source take not in assets"
        spec = {**spec, "_src": "/tmp/extend_src.wav"}; sh(f'ffmpeg -loglevel error -y -i "{src}" -ar 48000 -ac 2 -t {spec["extend"].get("total", spec["extend"]["end"])} /tmp/extend_src.wav')
    else:
        need = fit_seconds(spec)
        if spec.get("duration", 120) < need:   # a short duration cuts the last lines off: give every lyric line room
            print(f"duration {spec.get('duration')} s is too short for the lyrics, using {need} s", flush=True)
            spec = {**spec, "duration": need}
    open("/tmp/song_gen.py", "w").write(GEN); json.dump(spec, open("/tmp/song_spec.json", "w"))
    sh(f"cd {ACE_DIR} && PYTORCH_ALLOC_CONF=expandable_segments:True .venv/bin/python /tmp/song_gen.py /tmp/song_spec.json {E}")   # T4 (pre-Ampere): fp16 overflows to NaN
    vers = json.load(open(f"{E}/versions.json"))
    for v in vers:   # mp3 for listening on a phone, wav kept for the edit
        w = f"{E}/{v['file']}"; sh(f'ffmpeg -loglevel error -y -i "{w}" -af loudnorm=I=-14:TP=-1.5 -b:a 192k "{w[:-4]}.mp3"')
    json.dump({"episode": spec["id"], "type": "song", "title": spec.get("title"), "versions": vers,
               "minutes_total": round((time.time() - t0) / 60, 1)}, open(f"{E}/report.json", "w"), indent=1)
    print("DONE", E, flush=True)

def voice_check(E, vers, spec):
    """Separate each version's vocals (demucs) and flag passages sung clearly above a male chest voice: ACE-Step sometimes
    lets a high chorus slide into a female voice. v["voice"] = {"high_share", "high": [[start, end], ...]}."""
    sh("pip install -q demucs librosa soundfile")
    import numpy as np, librosa
    lim = spec.get("voice_max_hz", 370.0)   # ~F#4: a baritone rarely holds notes above this
    for v in vers:
        w = f"{E}/{v['file']}"; sh(f'python -m demucs --two-stems=vocals -n htdemucs -o /tmp/sep "{w}"')
        voc = glob.glob(f"/tmp/sep/htdemucs/{os.path.basename(w)[:-4]}/vocals.wav")[0]
        y, sr = librosa.load(voc, sr=16000, mono=True)
        f0, _, _ = librosa.pyin(y, fmin=70, fmax=1000, sr=sr, frame_length=1024, hop_length=320)
        t = librosa.times_like(f0, sr=sr, hop_length=320); ok = ~np.isnan(f0)
        hi = ok & (f0 > lim); segs, a = [], None
        for i, h in enumerate(list(hi) + [False]):
            if h and a is None: a = i
            if not h and a is not None:
                if t[min(i, len(t) - 1)] - t[a] >= 1.0: segs.append([round(float(t[a]), 1), round(float(t[min(i, len(t) - 1)]), 1)])
                a = None
        v["voice"] = {"high_share": round(float(hi.sum() / max(1, ok.sum())), 2), "high": segs}
        print("voice", v["file"], v["voice"], flush=True)

PREP = r'''
import json, re, sys, difflib, subprocess
spec, src, out = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", "/tmp/sep", src], check=True)
voc = next(__import__("glob").iglob("/tmp/sep/htdemucs/*/vocals.wav"))
subprocess.run(f"cp {voc} {out}/{spec['id']}_vocals.wav", shell=True, check=True)
from faster_whisper import WhisperModel
lines = [l.strip() for l in spec["lyrics"].split("\n")]
import torch; gpu = torch.cuda.is_available()
lang = spec.get("lang", "en")   # Korean (and other non-English) songs: multilingual model, matched letter by letter
m = WhisperModel("small.en" if lang == "en" else "small", device="cuda" if gpu else "cpu", compute_type="float16" if gpu else "int8")
def norm(x): return re.sub(r"[^a-z0-9]", "", x.lower()) if lang == "en" else re.sub(r"[\W_]", "", x.lower())
def units(x): n = norm(x); return [n] if lang == "en" else list(n)
subprocess.run(f"ffmpeg -loglevel error -y -i {voc} -ac 1 -ar 16000 /tmp/voc16.wav", shell=True, check=True)
import soundfile as sf; pcm = sf.read("/tmp/voc16.wav", dtype="float32")[0]   # skip PyAV decoding (version clashes)
segs, _ = m.transcribe(pcm, language=lang, word_timestamps=True, vad_filter=False,
                       initial_prompt=" ".join(l for l in lines if l and not l.startswith("[")))
heard = []
for sg in segs:
    for w in sg.words:
        u = [x for x in units(w.word) if x]
        for k, x in enumerate(u):   # letters share their word's time span evenly
            heard.append((x, w.start + (w.end - w.start) * k / len(u), w.start + (w.end - w.start) * (k + 1) / len(u)))
# lyric words in order, each tagged with its line; align to what was heard
lw, sec = [], ""
for i, l in enumerate(lines):
    if l.startswith("["): sec = l.strip("[]"); continue
    for w in l.split():
        for n in units(w):
            if n: lw.append((n, i, sec))
sm = difflib.SequenceMatcher(None, [w[0] for w in lw], [h[0] for h in heard], autojunk=False)
t = [None] * len(lw)
for a, b, size in sm.get_matching_blocks():
    for k in range(size): t[a + k] = (heard[b + k][1], heard[b + k][2])
res = []
for i, l in enumerate(lines):
    idx = [k for k, w in enumerate(lw) if w[1] == i]
    if not idx: continue
    got = [t[k] for k in idx if t[k]]
    res.append({"line": l, "section": lw[idx[0]][2], "words": len(idx), "matched": len(got),
                "start": round(got[0][0], 2) if got else None, "end": round(got[-1][1], 2) if got else None})
json.dump({"lines": res, "heard": [[h[0], round(h[1], 2), round(h[2], 2)] for h in heard]}, open(f"{out}/timing.json", "w"), indent=1)
print("matched", sum(r["matched"] for r in res), "of", len(lw), "lyric words", flush=True)
'''

def find_input(name):
    import glob
    hits = sorted(glob.glob(f"/kaggle/input/**/{name}", recursive=True)); return hits[0] if hits else None

def prep_song(spec):
    """Chosen version → separated vocals (drive lip-sync) + time of every lyric line (cut the music video)."""
    t0 = time.time(); E = f"{OUT}/{spec['id']}"; os.makedirs(E, exist_ok=True)
    src = find_input(f"{spec['id']}_v{spec['pick']}.mp3"); assert src, "chosen song not in the assets dataset"
    sh("pip install -q uv && uv venv -q -p 3.11 /tmp/prepenv")
    sh("uv pip install -q --python /tmp/prepenv/bin/python torch==2.5.1 torchaudio==2.5.1 demucs faster-whisper soundfile")
    open("/tmp/song_prep.py", "w").write(PREP); json.dump(spec, open("/tmp/song_spec.json", "w"))
    # faster-whisper (CTranslate2) needs cuBLAS/cuDNN 12 on the loader path: use the copies torch's wheels brought along
    libs = ":".join(sorted(__import__("glob").glob("/tmp/prepenv/lib/python3.11/site-packages/nvidia/*/lib")))
    sh(f'LD_LIBRARY_PATH={libs}:$LD_LIBRARY_PATH /tmp/prepenv/bin/python /tmp/song_prep.py /tmp/song_spec.json "{src}" {E}')
    sh(f'cp "{src}" {E}/')
    sh(f'ffmpeg -loglevel error -y -i {E}/{spec["id"]}_vocals.wav -b:a 160k {E}/{spec["id"]}_vocals.mp3')
    tm = json.load(open(f"{E}/timing.json"))
    json.dump({"episode": spec["id"], "type": "songprep", "title": spec.get("title"), "pick": spec["pick"], "lines": tm["lines"],
               "minutes_total": round((time.time() - t0) / 60, 1)}, open(f"{E}/report.json", "w"), indent=1)
    print("DONE", E, flush=True)

if SPEC.get("type") == "song":
    prep_song(SPEC) if SPEC.get("pick") else produce_song(SPEC)
