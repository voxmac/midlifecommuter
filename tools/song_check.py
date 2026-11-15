"""Checks every song version before anyone listens (CPU, GitHub runner):
 - lyrics: vocals separated + Korean/English speech recognition aligned to the lyrics -> lines that were not sung
 - voice: pitch held above a male chest voice (ACE-Step sometimes slides into a female voice on a high chorus)
usage: song_check.py songs/ID.json OUTDIR  -> adds v["lyrics_missing"], v["voice"] to OUTDIR/report.json"""
import json, os, subprocess, sys
import numpy as np, librosa
spec_path, O = sys.argv[1], sys.argv[2]
spec = json.load(open(spec_path)); r = json.load(open(f"{O}/report.json"))
lim = float(spec.get("voice_max_hz", 370)); male = spec.get("voice", "male") == "male"
for v in r["versions"]:
    mp3 = f"{O}/{v['file'][:-4]}.mp3"; D = f"/tmp/chk_v{v['version']}"
    tmp = f"/tmp/chk_spec_{v['version']}.json"; json.dump({**spec, "pick": v["version"]}, open(tmp, "w"), ensure_ascii=False)
    ok = subprocess.run([sys.executable, "tools/song_prep.py", tmp, D], env={**os.environ, "PREP_SRC": mp3}).returncode == 0
    if not ok: print("prep failed for", mp3); continue
    lines = json.load(open(f"{D}/timing.json"))["lines"]
    v["lyrics_missing"] = [l["line"] for l in lines if l.get("start") is None or (l.get("matched", 0) < 0.5 * max(1, l.get("words", 1)))]
    if male:
        y, sr = librosa.load(f"{D}/{spec['id']}_vocals.wav", sr=16000, mono=True)
        f0, _, _ = librosa.pyin(y, fmin=70, fmax=1000, sr=sr, frame_length=1024, hop_length=320)
        t = librosa.times_like(f0, sr=sr, hop_length=320); vv = ~np.isnan(f0); hi = vv & (f0 > lim); segs, a = [], None
        for i, h in enumerate(list(hi) + [False]):
            if h and a is None: a = i
            if not h and a is not None:
                b = min(i, len(t) - 1)
                if t[b] - t[a] >= 1.0: segs.append([round(float(t[a]), 1), round(float(t[b]), 1)])
                a = None
        v["voice"] = {"high_share": round(float(hi.sum() / max(1, vv.sum())), 2), "high": segs}
    print(v["file"], v.get("lyrics_missing"), v.get("voice"), flush=True)
json.dump(r, open(f"{O}/report.json", "w"), indent=1, ensure_ascii=False)
