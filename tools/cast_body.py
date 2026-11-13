"""Review-issue text for a cast job. usage: python tools/cast_body.py <out_dir> <repo> <tag> > body.md"""
import glob, os, sys
out, repo, tag = sys.argv[1:4]
base = f"https://github.com/{repo}/releases/download/{tag}"
sheets = sorted(glob.glob(os.path.join(out, "sheet_*.jpg")))
import json
rep = json.load(open(os.path.join(out, "report.json"))) if os.path.exists(os.path.join(out, "report.json")) else {}
if rep.get("type") == "design":   # new character designs (+ backgrounds to download)
    print(f"## {os.path.basename(out)}: new designs\n")
    for s in sheets:
        key = os.path.basename(s)[6:-4]
        print(f"### {key}\n![{key}]({base}/{os.path.basename(s)})\n")
    if rep.get("picks"):
        ex = " ".join(f"{k}=0" for k in rep["picks"])
        print(f"Pick the master design with one comment, e.g. `/pick {ex}`. It becomes the transparent cutout "
              f"`assets/<name>_cut.png` that every later expression, pose and scene starts from.\n")
    for k in rep.get("downloads", []):
        files = sorted(glob.glob(os.path.join(out, f"{k}_*.png")))
        print(f"**{k}** (download only, no /pick): " + " · ".join(f"[{os.path.basename(f)[:-4]}]({base}/{os.path.basename(f)})" for f in files) + "\n")
    sys.exit()
print(f"## {os.path.basename(out)}: expression and angle candidates\n")
print("Each row is one expression (only the face was repainted; the body is the approved master); the label under each picture is what you type (e.g. `bibi_sad=1`).\n")
for s in sheets:
    char = os.path.basename(s)[6:-4]
    print(f"### {char}\n![{char}]({base}/{os.path.basename(s)})\n")
print("""Reply with one comment listing your picks, for example:

`/pick pip_sad=1 pip_laugh=0 momo_surprised=2 tock_side=3 bibi_sad=0`

Skip any you don't like; they can be regenerated later. Each pick becomes a transparent cutout in `assets/`
(e.g. `assets/bibi_sad_cut.png`) that episode scripts can use with `"expr": "sad"`.""")
