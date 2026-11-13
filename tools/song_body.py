"""Review-issue text for song versions. usage: python tools/song_body.py <report.json> <repo> <tag>"""
import json, sys
r, repo, tag = json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2], sys.argv[3]
base = f"https://github.com/{repo}/releases/download/{tag}"
if r.get("type") == "songprep":
    print(f"## {r['episode']} v{r['pick']}: vocals separated and lyrics timed\n")
    print(f"Vocals: [{r['episode']}_vocals.mp3]({base}/{r['episode']}_vocals.mp3)\n")
    print("| section | line | start | end | matched |\n|---|---|---|---|---|")
    for l in r["lines"]:
        print(f"| {l['section']} | {l['line']} | {l['start']} | {l['end']} | {l['matched']}/{l['words']} |")
    sys.exit()
print(f"## {r['episode']} — {r.get('title', '')}: {len(r['versions'])} versions to listen to\n")
for v in r["versions"]:
    print(f"- **v{v['version']}**: [{v['file'][:-4]}.mp3]({base}/{v['file'][:-4]}.mp3) (seed {v['seed']})")
print("\nReply with the version you like, e.g. `/approve 2`, or `/rerun` for new versions.")
