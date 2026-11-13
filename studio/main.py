# ===================== main.py: one episode, end to end =====================
# SPEC is injected above this file by tools/build_kernel.py. Locally: STUDIO_LOCAL=1 python tools/run_local.py episodes/EP01.json
import os, glob, json, shutil, time

def asset(name):
    """Files from the puddlepals-assets dataset (Kaggle) or ./assets (local)."""
    roots = [os.environ.get("STUDIO_ASSETS", ""), "/kaggle/input"]
    for r in roots:
        if not r: continue
        hits = [p for p in glob.glob(f"{r}/**/*", recursive=True) if os.path.basename(p).lower().startswith(name.lower())]
        if hits: return sorted(hits)[0]
    return None

def font_file(spec):
    """Caption/title font: an asset by name, else downloaded once (e.g. a Korean Google font for MIDLIFE COMMUTER)."""
    name = spec.get("font", "LuckiestGuy"); p = asset(name)
    if p: return p
    import urllib.request
    dst = f"/tmp/{name}.ttf"
    if not os.path.exists(dst): urllib.request.urlretrieve(spec["font_url"], dst)
    return dst

def previous_shot(ep, sid):
    hits = glob.glob(f"{os.environ.get('STUDIO_SHOTS', '/kaggle/input')}/**/{ep}_{sid}.mp4", recursive=True)
    return hits[0] if hits else None

def produce(spec):
    ep = spec["id"]; t0 = time.time()
    landscape = spec.get("aspect", "16:9" if spec.get("format") == "bedtime" else "9:16") == "16:9"
    set_orientation(landscape)
    out_root = os.environ.get("STUDIO_OUT", "/kaggle/working/out")
    E = os.path.join(out_root, ep); os.makedirs(f"{E}/shots", exist_ok=True); os.makedirs(f"{E}/keys", exist_ok=True)
    report = {"episode": ep, "format": spec.get("format", "short"), "shots": {}}
    retake = set(spec.get("retake", []))
    shot_files, todo = {}, []
    for s in spec["shots"]:
        dst = f"{E}/shots/{s['id']}.mp4"
        if s.get("reuse"):
            shutil.copy(asset(s["reuse"]), dst); shot_files[s["id"]] = dst; report["shots"][s["id"]] = "reused " + s["reuse"]
        elif s.get("still_image"):      # a ready picture from assets as a still shot (no GPU)
            still_clip(asset(s["still_image"]), dst, s.get("dur", 5.0)); shot_files[s["id"]] = dst
            report["shots"][s["id"]] = "still " + s["still_image"]
        elif s.get("same_as"):          # music video: another cut of a shot made in this episode
            continue
        elif s["id"] not in retake and previous_shot(ep, s["id"]):
            shutil.copy(previous_shot(ep, s["id"]), dst); shot_files[s["id"]] = dst; report["shots"][s["id"]] = "kept from last run"
        else:
            todo.append(s); shot_files[s["id"]] = dst
    # narration first (CPU, a few minutes): a failure here must not cost the GPU work, so it only drops the voice
    lines = [{"key": s["id"], "text": s["say"], "speed": s.get("say_speed", spec.get("say_speed", 0.92))}
             for s in spec["shots"] if s.get("say") and not spec.get("song")]
    vo = {}
    if lines:
        try:
            log("narration:", len(lines), "lines"); vo = narrate(lines, f"{E}/edit/voice")
        except Exception as ex:
            log("NARRATION FAILED, continuing without voice:", ex); report["narration_error"] = str(ex)[:300]
    if todo:
        if not os.environ.get("STUDIO_LOCAL"):
            setup()
            ensure("image")
            if any(s.get("props") for s in todo):
                report["props"] = make_props(spec, todo, f"{E}/props")
            for s in todo:
                key = f"{E}/keys/{s['id']}.png"
                seed = make_keyframe(s, key, s.get("key_seed"))
                report["shots"][s["id"]] = {"key_seed": seed}
                log("keyframe", s["id"], seed)
            for s in [x for x in todo if x.get("still")]:
                still_clip(f"{E}/keys/{s['id']}.png", shot_files[s["id"]], s.get("dur", 5.0))
                report["shots"][s["id"]]["still"] = True
            moving = [x for x in todo if not x.get("still") and not x.get("lipsync")]
            sing = [x for x in todo if x.get("lipsync")]
            stop_server()
            # time budget (Kaggle stops a session at 12 h): lip-sync is reserved first, Wan shots that do not fit
            # become stills of their keyframe for now and are made on the next run ("kept from last run" keeps the rest)
            budget = spec.get("budget_min", 640) * 60
            reserve = (len(sing) * 50 + (20 if sing else 0) + 25) * 60
            if moving:
                ensure("video")
                for s in moving:
                    if time.time() - t0 + reserve + spec.get("wan_min", 40) * 60 > budget:
                        os.makedirs(f"{E}/pending", exist_ok=True); shot_files[s["id"]] = f"{E}/pending/{s['id']}.mp4"
                        still_clip(f"{E}/keys/{s['id']}.png", shot_files[s["id"]], 5.0)   # not in shots/ → redone next run
                        report["shots"][s["id"]]["pending"] = True; report.setdefault("pending", []).append(s["id"])
                        log("over budget, pending:", s["id"]); continue
                    prompt = s["motion"] + ", the characters keep exactly the same faces and designs as in the first frame, pixar style 3d animation, smooth natural motion, cinematic"
                    seed, sec = gen_shot(f"{E}/keys/{s['id']}.png", prompt, shot_files[s["id"]], s.get("video_seed"), frames=s.get("frames", 81))
                    report["shots"][s["id"]].update({"video_seed": seed, "minutes": round(sec / 60, 1)})
                    log("shot", s["id"], f"{sec/60:.1f} min")
                stop_server()
            if sing:
                shutil.rmtree(f"{CUI}/models", ignore_errors=True)   # disk for WanGP's weights
                song = spec["song"]; voc = f"{E}/edit/vocals.wav"; os.makedirs(f"{E}/edit", exist_ok=True)
                sh(f'"{ffmpeg_bin()}" -loglevel error -y -i "{asset(song["vocals"])}" "{voc}"')
                items = [{"id": x["id"], "image": f"{E}/keys/{x['id']}.png", "from": x["lipsync"]["from"], "to": x["lipsync"]["to"],
                          "prompt": x["lipsync"].get("prompt", "")} for x in sing]
                ls = lipsync_shots(items, spec["lipsync_preset"], voc, f"{E}/sing")
                for x in sing:
                    r = ls.get(x["id"], {}); f = f"{E}/sing/{x['id']}.mp4"
                    if r.get("ok") and os.path.exists(f): shutil.copy(f, shot_files[x["id"]])
                    else:
                        os.makedirs(f"{E}/pending", exist_ok=True); shot_files[x["id"]] = f"{E}/pending/{x['id']}.mp4"
                        still_clip(f"{E}/keys/{x['id']}.png", shot_files[x["id"]], 5.0); report.setdefault("pending", []).append(x["id"])
                    report["shots"][x["id"]].update({"lipsync": r.get("ok", False), "minutes": r.get("minutes"), "errors": r.get("errors")})
        else:
            raise RuntimeError("local run needs every shot as reuse or kept: " + ", ".join(s["id"] for s in todo))

    for s in spec["shots"]:
        if s.get("same_as"): shot_files[s["id"]] = shot_files[s["same_as"]]
    ff = ffmpeg_bin(); work = f"{E}/edit"; os.makedirs(work, exist_ok=True)
    tz = spec.get("teaser")
    if tz:   # cold open: a 1-1.5 s flash of the climax before the story starts ("how did this happen?")
        src = next(x for x in spec["shots"] if x["id"] == tz["shot"])
        a = tz.get("at", 2.0)
        spec = {**spec, "shots": [{"id": "TZ", "cut": [a, a + tz.get("dur", 1.3)], "camera": {"move": "push", "amount": 0.08},
                                   "sfx": [{"fx": "whoosh", "at": 0.0, "args": {"d": 0.4}, "vol": 0.6}] + tz.get("sfx", [])}]
                                 + spec["shots"]}
        shot_files["TZ"] = shot_files[tz["shot"]]
        if spec.get("music"): spec["music"] = [{**spec["music"][0], "from": "TZ"}] + spec["music"][1:]
    log("edit: assemble")
    tl, total, body = assemble(spec, shot_files, work, ff)
    voice_tl = []
    if vo:
        for s in spec["shots"]:
            if s["id"] in vo:
                v = vo[s["id"]]; st = tl[s["id"]]["start"] + s.get("say_at", 0.25)
                voice_tl.append({"start": st, "dur": v["dur"], "wav": v["wav"],
                                 "words": [[w, st + a, st + b] for w, a, b in v["words"]]})
        report["narration"] = {s: round(v["dur"], 2) for s, v in vo.items()}
        if any(v.get("placeholder") for v in vo.values()): report["narration_placeholder"] = True
    if spec.get("song"):     # music video: karaoke captions from the lyric timing (absolute song time)
        voice_tl = [{"start": ln[0][1], "dur": ln[-1][2] - ln[0][1], "wav": None, "words": ln} for ln in spec["lyrics_tl"]]
    log("edit: graphics")
    chap = f"{work}/chapter_video.mp4" if spec.get("series") else None
    motion = overlay(spec, tl, total, body, f"{work}/video.mp4", font_file(spec), ff, voice_tl, chap)
    log("edit: sound")
    soundtrack(spec, tl, total, motion, f"{work}/audio.wav", voice_tl)
    final = f"{E}/{ep}_{spec.get('slug', 'episode')}.mp4"
    finalize(f"{work}/video.mp4", f"{work}/audio.wav", final, ff)
    if spec.get("format") == "bedtime" and not landscape:   # old 9:16 bedtime specs: still deliver a regular 16:9 video
        vert = f"{work}/vertical.mp4"; os.replace(final, vert)
        fc = ("[0:v]split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=24:2,"
              "eq=brightness=-0.10:saturation=1.1[bg];[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,format=yuv420p[v]")
        sh(f'"{ff}" -y -loglevel error -i "{vert}" -filter_complex "{fc}" -map "[v]" -map 0:a -c:v libx264 -crf 18 '
           f'-preset veryfast -r 30 -c:a copy -movflags +faststart "{final}"')
        os.remove(vert)
    if chap:
        soundtrack(spec, tl, total, motion, f"{work}/chapter_audio.wav", voice_tl, chapter=True)
        finalize(chap, f"{work}/chapter_audio.wav", f"{E}/{ep}_chapter.mp4", ff)
    ser = spec.get("series", {})
    col = RAINBOW7[min(6, max(0, ser.get("chapter", 1) - 1))] if ser else None
    if spec.get("format", "short") == "bedtime" or landscape:     # regular video: landscape cover
        thumbnail(spec, tl, body, f"{E}/thumb.jpg", font_file(spec), ff, col, f"{E}/keys")
    else:                                             # Shorts: vertical cover + a wide one for the full episode
        thumbnail_vertical(spec, tl, body, f"{E}/thumb.jpg", font_file(spec), ff, col, f"{E}/keys")
        thumbnail(spec, tl, body, f"{E}/thumb_wide.jpg", font_file(spec), ff, col, f"{E}/keys")
    review_sheet(final, f"{E}/review.jpg", ff)
    shutil.rmtree(f"{work}/seg", ignore_errors=True)
    for f in (body, f"{work}/video.mp4", chap or ""):
        if f and os.path.exists(f): os.remove(f)
    report.update({"timeline": tl, "seconds": round(total, 2), "final": os.path.basename(final),
                   "upload": spec.get("upload", {}), "minutes_total": round((time.time() - t0) / 60, 1)})
    json.dump(report, open(f"{E}/report.json", "w"), indent=1, ensure_ascii=False)
    log("DONE", final, f"{total:.1f}s", f"{report['minutes_total']} min")
    return final

def produce_cast(spec):
    """One-time job: expression / angle candidates for each character, for a person to pick from."""
    out = os.path.join(os.environ.get("STUDIO_OUT", "/kaggle/working/out"), spec["id"])
    setup()
    if spec.get("design") or spec.get("plates"):   # new characters / backgrounds from text
        ensure("image"); made = design_candidates(spec, out)
    elif spec.get("engine") == "qwen_edit":
        ensure("edit"); made = cast_candidates_edit(spec, out)
    else:
        ensure("image"); made = cast_candidates(spec, out)
    cast_sheets(made, out)
    for f in glob.glob(f"{out}/*_init.png"): os.remove(f)
    json.dump({"episode": spec["id"], "type": "design" if spec.get("design") or spec.get("plates") else "cast",
               "picks": list(spec.get("design", {})), "downloads": list(spec.get("plates", {})), "candidates": {k: len(v) for k, v in made.items()}},
              open(f"{out}/report.json", "w"), indent=1)
    stop_server(); log("DONE cast", sum(len(v) for v in made.values()), "candidates")

if __name__ == "__main__" and "SPEC" in globals():
    produce_cast(SPEC) if SPEC.get("type") == "cast" else produce(SPEC)
