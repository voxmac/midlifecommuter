# ===================== wangp.py: run WanGP (deepbeepmeep/Wan2GP) headless on a Kaggle T4 =====================
# Lab jobs (labs/LABn.json): a list of WanGP tasks (InfiniteTalk lip-sync, TTS, songs, ...) to judge quality and speed
# before deciding on new hardware. WanGP needs Python 3.10-3.12; uv builds that next to Kaggle's 3.13.
import os, json, subprocess, time, glob, shutil

WGP_DIR, WGP_ENV = "/tmp/Wan2GP", "/tmp/wgpenv"
OUT = os.environ.get("STUDIO_OUT", "/kaggle/working/out")

RUNNER = r'''
import json, os, sys, time, traceback
from pathlib import Path
os.chdir("/tmp/Wan2GP"); sys.path.insert(0, "/tmp/Wan2GP")
from shared.api import init
spec, out = json.load(open(sys.argv[1])), sys.argv[2]
session = init(root=Path("/tmp/Wan2GP"), cli_args=["--attention", "sdpa", "--profile", str(spec.get("profile", 4))])
rep = []
for t in spec["tasks"]:
    t0 = time.time(); mt = t["model_type"]; row = {"name": t["name"], "model_type": mt}
    try:
        meta = session.list_model_metadata(query=mt)
        print("META", mt, json.dumps(meta, default=str)[:1500], flush=True)
        st = dict(session.get_default_settings(mt)); st.update(t["settings"]); st["model_type"] = mt
        print("SETTINGS", json.dumps({k: v for k, v in st.items() if not isinstance(v, (list, dict)) or k in t["settings"]}, default=str)[:2500], flush=True)
        job = session.submit_task(st)
        for ev in job.events.iter(timeout=1.0):
            if ev.kind == "progress":
                d = ev.data; print("progress", getattr(d, "phase", ""), getattr(d, "current_step", ""), getattr(d, "total_steps", ""), flush=True)
            elif ev.kind == "stream": print("[%s] %s" % (ev.data.stream, ev.data.text), flush=True)
        res = job.result()
        row["ok"] = bool(res.success); row["errors"] = [e.message for e in (res.errors or [])]
        files = []
        for f in (res.generated_files or []):
            dst = f"{out}/{t['name']}{os.path.splitext(f)[1]}"; os.system(f'cp "{f}" "{dst}"'); files.append(os.path.basename(dst))
        row["files"] = files
    except Exception as ex:
        row["ok"] = False; row["errors"] = [repr(ex)]; traceback.print_exc()
    row["minutes"] = round((time.time() - t0) / 60, 1); rep.append(row); print("TASK", json.dumps(row), flush=True)
    json.dump(rep, open(f"{out}/tasks.json", "w"), indent=1)
'''

def sh(cmd):
    print("$", cmd, flush=True); subprocess.run(cmd, shell=True, check=True)

def find_input(name):
    hits = sorted(glob.glob(f"/kaggle/input/**/{name}*", recursive=True))
    return hits[0] if hits else None

def prepare_inputs(spec, E):
    """'image_from_video': {video, at} → first-frame png; 'image'/'audio' name → file from the datasets."""
    for t in spec["tasks"]:
        s = t["settings"]
        if "image_from_video" in t:
            v = find_input(t["image_from_video"]["video"]); png = f"{E}/{t['name']}_start.png"
            sh(f'ffmpeg -loglevel error -y -ss {t["image_from_video"].get("at", 0.2)} -i "{v}" -frames:v 1 "{png}"')
            s["image_start"] = png
        if t.get("ref_from_start") and s.get("image_start"):   # InfiniteTalk's default mode ("0KI") also wants it as reference
            s["image_refs"] = [s["image_start"]]
        for k in ("image_start", "audio_guide", "audio_guide2"):
            if k in t.get("inputs", {}): s[k] = find_input(t["inputs"][k])

def install_wangp():
    if os.path.exists(f"{WGP_ENV}/bin/python"): return
    sh("pip install -q uv")
    sh(f"git clone -q --depth 1 https://github.com/deepbeepmeep/Wan2GP.git {WGP_DIR}")
    # PyPI torch 2.10 = CUDA 12.8 build (T4 = sm75); the requirements' CUDA-13 nightly onnxruntime is swapped for 1.22
    sh(f"grep -v 'extra-index-url\\|onnxruntime-gpu==1.25' {WGP_DIR}/requirements.txt > /tmp/req.txt && "
       "echo 'onnxruntime-gpu==1.22.0' >> /tmp/req.txt")
    sh(f"uv venv -q -p 3.11 {WGP_ENV}")
    sh(f"uv pip install -q --python {WGP_ENV}/bin/python torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 -r /tmp/req.txt")

def run_wangp(spec, E):
    """spec = {"tasks": [...], "profile": n}; outputs land in E as <task name>.<ext>; returns the per-task report."""
    open("/tmp/wgp_run.py", "w").write(RUNNER); json.dump(spec, open("/tmp/wgp_spec.json", "w"))
    r = subprocess.run(f"{WGP_ENV}/bin/python /tmp/wgp_run.py /tmp/wgp_spec.json {E}", shell=True)
    return (json.load(open(f"{E}/tasks.json")) if os.path.exists(f"{E}/tasks.json") else []), r.returncode

def lipsync_shots(items, preset, vocals, E):
    """Music video: each item {id, image, from, to} → the character in `image` sings vocals[from:to] (InfiniteTalk)."""
    os.makedirs(E, exist_ok=True); install_wangp(); tasks = []
    for it in items:
        dur = it["to"] - it["from"]; frames = int(round(dur * 25 / 4)) * 4 + 1   # 25 fps, 4k+1 frames
        wav = f"{E}/{it['id']}_vocals.wav"
        sh(f'ffmpeg -loglevel error -y -ss {it["from"]} -t {dur + 0.2:.2f} -i "{vocals}" -ac 1 -ar 16000 "{wav}"')
        st = dict(preset["settings"]); st.update({"image_start": it["image"], "image_refs": [it["image"]], "audio_guide": wav,
                                                  "video_length": frames, "prompt": it.get("prompt", st.get("prompt", ""))})
        if it.get("resolution"): st["resolution"] = it["resolution"]
        tasks.append({"name": it["id"], "model_type": preset["model_type"], "settings": st})
    rep, code = run_wangp({"tasks": tasks, "profile": preset.get("profile", 4)}, E)
    return {r["name"]: r for r in rep}

def produce_lab(spec):
    t0 = time.time(); E = f"{OUT}/{spec['id']}"; os.makedirs(E, exist_ok=True)
    sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv")
    install_wangp()
    t_install = round((time.time() - t0) / 60, 1)
    prepare_inputs(spec, E)
    tasks, code = run_wangp(spec, E)
    json.dump({"episode": spec["id"], "type": "lab", "install_minutes": t_install, "tasks": tasks, "exit": code,
               "minutes_total": round((time.time() - t0) / 60, 1)}, open(f"{E}/report.json", "w"), indent=1)
    print("DONE", E, flush=True)

if SPEC.get("type") == "lab":
    produce_lab(SPEC)
