"""Writes the review-issue text for a finished episode or full episode.
usage: python tools/review_body.py <report.json> <repo> <release_tag> > body.md"""
import json, sys
rep, repo, tag = json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2], sys.argv[3]
up = rep.get("upload", {})
base = f"https://github.com/{repo}/releases"
full = rep.get("type") == "compile"
if full:
    rows = "\n".join(f"| {c['chapter']} | {c['episode']} | {c.get('title', '')} |" for c in rep.get("chapters", []))
    table = f"| Chapter | Episode | Title |\n| --- | --- | --- |\n{rows}"
else:
    rows = "\n".join(f"| {k} | {v if isinstance(v, str) else ('still' if v.get('still') else 'new') + ' (key seed ' + str(v.get('key_seed')) + (', ' + str(v.get('minutes')) + ' min' if v.get('minutes') else '') + ')'} |"
                     for k, v in rep.get("shots", {}).items())
    table = f"| Shot | Source |\n| --- | --- |\n{rows}"
narr = ""
if rep.get("narration_error"):
    narr = f"\n**⚠ Narration failed, video has no voice:** `{rep['narration_error'][:200]}` — comment `/rerun` to try again (no GPU shots are redone).\n"
elif rep.get("narration"):
    narr = f"\n**Narration:** {len(rep['narration'])} lines" + (" (placeholder, no voice)" if rep.get("narration_placeholder") else "") + "\n"
if rep.get("pending"):
    narr += (f"\n**⏳ Not finished yet (time budget):** {', '.join(rep['pending'])} are still pictures for now. "
             "Comment `/rerun` to make them; every finished shot is kept.\n")
if rep.get("qc"):   # automatic visual check (qc.py): what it fixed, and anything it could not fix
    fixed = [k for k, v in rep["qc"].items() if v.get("key_tries", 1) > 1 and v.get("key_ok", True)]
    left = [(k, v.get("key_problems", []) + v.get("shot_problems", [])) for k, v in rep["qc"].items()
            if not v.get("key_ok", True) or not v.get("shot_ok", True)]
    narr += f"\n**Automatic check:** {len(rep['qc'])} scenes checked" + (f", redrawn: {', '.join(fixed)}" if fixed else "") + ".\n"
    for k, probs in left:
        narr += f"- ⚠ {k}: {'; '.join(probs) or 'flagged'} — comment `/retake {k}` to redo it\n"
kind = "Full episode (landscape, regular video)" if full else {"bedtime": "Bedtime story (regular video)", "mv": "Music video (16:9, regular video)"}.get(rep.get("format", "short"), "Short")
print(f"""## {rep['episode']} is ready for review ({rep.get('seconds')}s · {kind})

![thumbnail]({base}/download/{tag}/thumb.jpg)

![review sheet]({base}/download/{tag}/review.jpg)

**Video and thumbnail:** {base}/tag/{tag}
{narr}
**YouTube title:** {up.get('title', '')}

**Description:** {up.get('description', '')}

**Settings:** Audience = {"Made for Kids" if up.get("made_for_kids") else "Not made for kids (general)"} · Altered or synthetic content = No (animation) · Thumbnail = thumb.jpg

{table}

Reply with a comment:
- `/approve` to mark it approved (you then upload it to YouTube)
- `/retake B3 B5` to regenerate only those shots and re-edit
""")
