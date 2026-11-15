"""Song prep on the GitHub runner (CPU, no Kaggle queue): chosen version → vocals + lyric line timings.
usage: python tools/song_prep.py songs/SONG1.json <outdir>   (needs demucs, faster-whisper, torch, ffmpeg)"""
import ast, json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec, E = json.load(open(sys.argv[1])), sys.argv[2]; os.makedirs(E, exist_ok=True); t0 = time.time()
src_code = open(os.path.join(ROOT, "studio/song.py")).read()
PREP = next(n.value.value for n in ast.parse(src_code).body if isinstance(n, ast.Assign) and n.targets[0].id == "PREP")
open("/tmp/song_prep_run.py", "w").write(PREP); json.dump(spec, open("/tmp/song_spec.json", "w"))
src = os.environ.get("PREP_SRC") or os.path.join(ROOT, "assets", f"{spec['id']}_v{spec['pick']}.mp3")
subprocess.run([sys.executable, "/tmp/song_prep_run.py", "/tmp/song_spec.json", src, E], check=True)
subprocess.run(f'cp "{src}" {E}/ && ffmpeg -loglevel error -y -i {E}/{spec["id"]}_vocals.wav -b:a 160k {E}/{spec["id"]}_vocals.mp3', shell=True, check=True)
tm = json.load(open(f"{E}/timing.json"))
secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip() or 0)
json.dump({"episode": spec["id"], "type": "songprep", "title": spec.get("title"), "pick": spec["pick"], "lines": tm["lines"], "seconds": round(secs, 2),
           "minutes_total": round((time.time() - t0) / 60, 1)}, open(f"{E}/report.json", "w"), indent=1)
print(E)
