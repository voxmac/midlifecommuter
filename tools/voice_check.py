"""Vocal-pitch check for song versions (CPU, GitHub runner): separate each version's vocals with demucs and flag passages
held above a male chest voice (ACE-Step sometimes lets a high chorus slide into a female voice).
usage: voice_check.py OUTDIR  -> adds v["voice"] = {"high_share", "high": [[start, end], ...]} to OUTDIR/report.json"""
import glob, json, os, subprocess, sys
import numpy as np, librosa
O = sys.argv[1]; r = json.load(open(f"{O}/report.json")); lim = float(os.environ.get("VOICE_MAX_HZ", 370))
for v in r["versions"]:
    src = f"{O}/{v['file']}" if os.path.exists(f"{O}/{v['file']}") else f"{O}/{v['file'][:-4]}.mp3"
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-d", "cpu", "-o", "/tmp/sep", src], check=True)
    voc = glob.glob(f"/tmp/sep/htdemucs/{os.path.basename(src).rsplit('.', 1)[0]}/vocals.wav")[0]
    y, sr = librosa.load(voc, sr=16000, mono=True)
    f0, _, _ = librosa.pyin(y, fmin=70, fmax=1000, sr=sr, frame_length=1024, hop_length=320)
    t = librosa.times_like(f0, sr=sr, hop_length=320); ok = ~np.isnan(f0); hi = ok & (f0 > lim)
    segs, a = [], None
    for i, h in enumerate(list(hi) + [False]):
        if h and a is None: a = i
        if not h and a is not None:
            b = min(i, len(t) - 1)
            if t[b] - t[a] >= 1.0: segs.append([round(float(t[a]), 1), round(float(t[b]), 1)])
            a = None
    v["voice"] = {"high_share": round(float(hi.sum() / max(1, ok.sum())), 2), "high": segs}
    print(v["file"], v["voice"], flush=True)
json.dump(r, open(f"{O}/report.json", "w"), indent=1)
