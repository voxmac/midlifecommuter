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
    # automatic check: lines the singer skipped, and an ending cut off by the song length
    warn = [l["line"] for l in r["lines"] if l.get("words") and l["matched"] / l["words"] < 0.5]
    dur = r.get("seconds") or r.get("duration")
    if warn: print("\n**⚠ Possibly not sung / unclear:** " + " · ".join(warn))
    if dur and r["lines"] and r["lines"][-1]["end"] > dur - 1.5:
        print(f"\n**⚠ The last line ends at {r['lines'][-1]['end']} s of {dur} s: it may be cut off.** Ask Claude to extend the ending.")
    if not warn and not (dur and r["lines"] and r["lines"][-1]["end"] > dur - 1.5): print("\n✅ Automatic check: every line is sung and the ending is complete.")
    sys.exit()
print(f"## {r['episode']} — {r.get('title', '')}: {len(r['versions'])} versions to listen to\n")
for v in r["versions"]:
    vc = v.get("voice")
    tag = "" if not vc else (" — ✅ one voice throughout" if not vc["high"] else
          " — ⚠ high / possibly female voice at " + ", ".join(f"{a:.0f}–{b:.0f} s" for a, b in vc["high"]))
    if "lyrics_missing" in v:
        tag += " — ✅ every line sung" if not v["lyrics_missing"] else " — ⚠ not heard: " + " / ".join(v["lyrics_missing"])
    print(f"- **v{v['version']}**: [{v['file'][:-4]}.mp3]({base}/{v['file'][:-4]}.mp3) (seed {v['seed']}){tag}")
print("\nReply with the version you like, e.g. `/approve 2`, or `/rerun` for new versions.")
