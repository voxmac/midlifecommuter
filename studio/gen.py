# ===================== gen.py: Kaggle GPU setup, ComfyUI API, keyframe compositing, Wan shots =====================
import os, re, sys, json, time, glob, shutil, subprocess, urllib.request, urllib.error, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WORK = "/kaggle/working"
OUT = f"{WORK}/out"
CUI = "/tmp/ComfyUI"

def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)

def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and r.returncode != 0:
        print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise RuntimeError(f"failed: {cmd}")
    return r.stdout

def find_input(word):
    hits = [p for p in glob.glob("/kaggle/input/**/*", recursive=True) if word.lower() in os.path.basename(p).lower()]
    return sorted(hits)[0] if hits else None

def setup():
    import torch, torchvision
    assert torch.cuda.is_available(), "no GPU: set accelerator NvidiaTeslaT4"
    os.makedirs(OUT, exist_ok=True)
    log("torch", torch.__version__)
    if not os.path.exists(f"{CUI}/main.py"):
        sh(f"git clone --depth 1 https://github.com/comfyanonymous/ComfyUI {CUI}")
    for repo in ["city96/ComfyUI-GGUF", "cubiq/ComfyUI_IPAdapter_plus"]:
        d = f"{CUI}/custom_nodes/{repo.split('/')[1]}"
        if not os.path.exists(d): sh(f"git clone --depth 1 https://github.com/{repo} {d}")
    if os.environ.get("STUDIO_DEPS_READY"):   # Modal: ComfyUI and its requirements are baked into the image
        return
    open("/tmp/constraints.txt", "w").write(f"torch=={torch.__version__}\ntorchvision=={torchvision.__version__}\n")
    TORCH_LINE = re.compile(r"^\s*(torch|torchvision|torchaudio)\s*([<>=!~;].*)?$", re.I)
    for req in [f"{CUI}/requirements.txt"] + glob.glob(f"{CUI}/custom_nodes/*/requirements.txt"):
        lines = [l for l in open(req).read().splitlines() if l.strip() and not TORCH_LINE.match(l)]
        open("/tmp/req.txt", "w").write("\n".join(lines))
        sh(f"{sys.executable} -m pip install -q -c /tmp/constraints.txt -r /tmp/req.txt")
    sh(f"{sys.executable} -m pip install -q -c /tmp/constraints.txt gguf imageio-ffmpeg huggingface_hub")

QUANT = "Q4_K_M"
MODELS = {
    "image": [
        ("stabilityai/stable-diffusion-xl-base-1.0", "sd_xl_base_1.0.safetensors", "checkpoints", None),
        ("h94/IP-Adapter", "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors", "ipadapter", None),
        ("h94/IP-Adapter", "models/image_encoder/model.safetensors", "clip_vision", "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"),
    ],
    "video": [
        ("QuantStack/Wan2.2-I2V-A14B-GGUF", f"HighNoise/Wan2.2-I2V-A14B-HighNoise-{QUANT}.gguf", "unet", None),
        ("QuantStack/Wan2.2-I2V-A14B-GGUF", f"LowNoise/Wan2.2-I2V-A14B-LowNoise-{QUANT}.gguf", "unet", None),
        ("lightx2v/Wan2.2-Distill-Loras", r"re:wan2\.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step.*\.safetensors", "loras", "wan22_i2v_lightning_high.safetensors"),
        ("lightx2v/Wan2.2-Distill-Loras", r"re:wan2\.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step.*\.safetensors", "loras", "wan22_i2v_lightning_low.safetensors"),
        ("Comfy-Org/Wan_2.1_ComfyUI_repackaged", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders", None),
        ("Comfy-Org/Wan_2.1_ComfyUI_repackaged", "split_files/vae/wan_2.1_vae.safetensors", "vae", None),
    ],
    # Qwen-Image-Edit 2509 (Apache-2.0): instruction edits that keep the character ("make him cry, keep the rest")
    "edit": [
        ("QuantStack/Qwen-Image-Edit-2509-GGUF", r"re:(?i)edit-2509.*Q4_K_M\.gguf$", "unet", "qwen_edit_2509.gguf"),
        ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", "text_encoders", None),
        ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/vae/qwen_image_vae.safetensors", "vae", None),
        ("lightx2v/Qwen-Image-Lightning", r"re:(?i)edit-2509.*lightning.*4steps.*\.safetensors$", "loras", "qwen_edit_lightning.safetensors"),
    ],
}

def fetch(repo, name, sub, rename):
    from huggingface_hub import hf_hub_download, list_repo_files
    if name.startswith("re:"):
        pat = re.compile(name[3:]); hits = sorted(f for f in list_repo_files(repo) if pat.search(f.split("/")[-1]))
        if not hits: raise RuntimeError(f"{repo}: no file matches {name}")
        name = hits[-1]
    dest_dir = f"{CUI}/models/{sub}"; os.makedirs(dest_dir, exist_ok=True)
    dest = f"{dest_dir}/{rename or name.split('/')[-1]}"
    if os.path.exists(dest): return False
    log("download", repo, name)
    shutil.move(hf_hub_download(repo, name, local_dir="/tmp/hf_dl"), dest); return True

PORT = 8188; URL = f"http://127.0.0.1:{PORT}"; SERVER = None
def server_alive():
    try: urllib.request.urlopen(URL + "/system_stats", timeout=3); return True
    except Exception: return False
def start_server():
    global SERVER
    stop_server()
    lg = open(f"{OUT}/comfyui.log", "a")
    SERVER = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", str(PORT), "--fp32-vae",
                               "--disable-auto-launch"], cwd=CUI, stdout=lg, stderr=subprocess.STDOUT,
                              env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"})
    for _ in range(300):
        if server_alive(): log("ComfyUI ready"); return
        if SERVER.poll() is not None: break
        time.sleep(1)
    print(open(f"{OUT}/comfyui.log").read()[-4000:]); raise RuntimeError("ComfyUI did not start")
def stop_server():
    global SERVER
    if SERVER and SERVER.poll() is None:
        SERVER.terminate()
        try: SERVER.wait(30)
        except subprocess.TimeoutExpired: SERVER.kill(); SERVER.wait()
    SERVER = None
def ensure(kind):
    new = False
    for m in MODELS[kind]: new = fetch(*m) or new
    if new or not server_alive(): start_server()

def _get(path): return json.load(urllib.request.urlopen(URL + path, timeout=60))
def _post(path, data):
    req = urllib.request.Request(URL + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e: raise RuntimeError("ComfyUI rejected graph:\n" + e.read().decode()[:3000])
_INFO = {}
def fill_defaults(graph):
    """ComfyUI nodes gain required inputs between versions; fill any we didn't set with the node's own default."""
    for node in graph.values():
        cls = node["class_type"]
        if cls not in _INFO:
            try: _INFO[cls] = _get(f"/object_info/{cls}").get(cls, {})
            except Exception: _INFO[cls] = {}
        for k, spec in _INFO[cls].get("input", {}).get("required", {}).items():
            if k in node["inputs"] or not isinstance(spec, (list, tuple)) or not spec: continue
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if "default" in opts: node["inputs"][k] = opts["default"]
            elif isinstance(spec[0], list) and spec[0]: node["inputs"][k] = spec[0][0]
            elif spec[0] == "COMBO" and opts.get("options"): node["inputs"][k] = opts["options"][0]
            else: continue
            log(f"  {cls}.{k} not set -> default {node['inputs'][k]!r}")

def run(graph, timeout=5400):
    fill_defaults(graph)
    pid = _post("/prompt", {"prompt": graph, "client_id": "studio"})["prompt_id"]; t0 = time.time()
    while time.time() - t0 < timeout:
        if SERVER is not None and SERVER.poll() is not None:
            print(open(f"{OUT}/comfyui.log").read()[-3000:]); raise RuntimeError("ComfyUI died (out of memory?)")
        h = _get(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error": raise RuntimeError("generation error: " + json.dumps(st.get("messages", [])[-2:])[:2000])
            files = [os.path.join(CUI, "output", im.get("subfolder", ""), im["filename"])
                     for o in h[pid]["outputs"].values() for im in o.get("images", [])]
            return files, time.time() - t0
        time.sleep(2)
    raise RuntimeError("timeout")
def to_input(path):
    os.makedirs(f"{CUI}/input", exist_ok=True)
    name = f"{int(time.time()*1000)}_{os.path.splitext(os.path.basename(path))[0]}.png"
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); im = Image.alpha_composite(bg, im)
    im.convert("RGB").save(f"{CUI}/input/{name}"); return name

STYLE_3D = ("3d render, pixar style animated movie character, soft subsurface scattering, detailed soft texture, "
            "big glossy expressive eyes, cinematic soft key light with warm rim light, shallow depth of field, high detail, 8k")
NEG_3D = ("2d, flat, illustration, lineart, outline, sketch, anime, photo of a real animal, realistic animal, creepy, uncanny, "
          "scary, extra limbs, deformed, blurry, lowres, text, watermark, logo, black outline, thick lines, cel shading, flat colors")
PANELS_NEG = "collage, split screen, multiple panels, triptych, comic panels, grid of images, frame border, pagoda, temple, japanese architecture, chinese architecture"
PLATE_NEG = "animal, duck, bird, frog, turtle, cloud creature, character, creature, person, people, text, watermark, 2d, flat, illustration, lowres, blurry, " + PANELS_NEG
PLATE_STYLE = "cinematic 3d animated movie background, pixar style environment, no characters, shallow depth of field"
BIBLE = {
    "pip": "cute baby duckling, round head and egg-shaped body, fluffy cream ivory down feathers, little feather tuft on top of the head, orange beak and webbed feet, big glossy black eyes",
    "momo": "chubby baby frog, wide low dumpling-shaped body, soft glossy pastel pink skin, cream belly, two huge round glossy black eyes on top of the head",
    "tock": "baby turtle standing on short legs, big round head with very large glossy brown eyes, light green skin, domed green shell with hexagon pattern, pale yellow belly plates",
    "bibi": "baby cloud creature, fluffy cotton candy cloud body with soft round bumps, pale pink, small shiny black eyes, rosy cheeks, tiny smile, floating",
    # MIDLIFE COMMUTER (second channel): M, the commuting dad
    "m": "middle-aged Korean office worker man in his late 40s, short black hair graying at the temples, round thin-framed glasses, "
         "kind tired eyes, slight smile lines, grey wool coat over a white shirt and navy tie, employee ID badge on a lanyard, "
         "dark trousers, brown shoes, holding a worn brown leather briefcase",
    # M's people: family, office, friend (same 3D animated look)
    "wife": "Korean woman in her mid 40s, M's wife, warm kind face, shoulder-length wavy dark brown hair, beige cardigan over a white blouse, blue jeans",
    "son": "Korean boy about 12 years old, M's son, short black hair, navy hoodie, jeans, sneakers, school backpack",
    "daughter": "Korean girl about 8 years old, M's daughter, black hair in two pigtails with yellow ribbons, pink dress, white sneakers",
    "junior": "young Korean office worker in his early 30s, M's junior colleague, neat short hair, white shirt with rolled sleeves, ID badge lanyard, laptop under his arm",
    "boss": "Korean manager in his late 50s, M's boss, balding with grey hair at the sides, thick eyebrows, dark navy suit and red tie, stern but comic",
    "friend": "Korean man in his late 40s, M's old school friend, chubby and cheerful, short hair, padded olive jacket over a hoodie, baseball cap",
    "grandma": "Korean grandmother in her mid 70s, M's mother, short permed grey hair, gentle wrinkled smiling face, floral blouse and a purple padded vest",
    "grandpa": "Korean grandfather in his late 70s, M's father, thin white hair, kind wrinkled face, beige jacket over a sweater, walking cane",
}

def gen_image(prompt, neg=NEG_3D, w=None, h=None, seed=None, init=None, denoise=1.0, steps=30, cfg=6.0, prefix="img",
              ref=None, ref_weight=0.6, mask=None):
    """SDXL txt2img / img2img. ref = an image the result should resemble (IP-Adapter, prompt keeps priority)."""
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    w, h = w or W, h or H
    g = {"ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
         "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["ckpt", 1]}},
         "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["ckpt", 1]}}}
    model = ["ckpt", 0]
    if ref:
        g["refimg"] = {"class_type": "LoadImage", "inputs": {"image": to_input(ref)}}
        g["ipl"] = {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": ["ckpt", 0], "preset": "PLUS (high strength)"}}
        g["ipa"] = {"class_type": "IPAdapter", "inputs": {"model": ["ipl", 0], "ipadapter": ["ipl", 1], "image": ["refimg", 0],
                    "weight": ref_weight, "start_at": 0.0, "end_at": 1.0, "weight_type": "prompt is more important"}}
        model = ["ipa", 0]
    if init:
        g["init"] = {"class_type": "LoadImage", "inputs": {"image": to_input(init)}}
        g["scale"] = {"class_type": "ImageScale", "inputs": {"image": ["init", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}}
        g["enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["scale", 0], "vae": ["ckpt", 2]}}; latent = ["enc", 0]
        if mask:   # repaint only the white part of the mask (e.g. the face), keep the rest
            g["mimg"] = {"class_type": "LoadImage", "inputs": {"image": to_input(mask)}}
            g["mscale"] = {"class_type": "ImageScale", "inputs": {"image": ["mimg", 0], "upscale_method": "bilinear", "width": w, "height": h, "crop": "center"}}
            g["mask"] = {"class_type": "ImageToMask", "inputs": {"image": ["mscale", 0], "channel": "red"}}
            g["nm"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["enc", 0], "mask": ["mask", 0]}}; latent = ["nm", 0]
    else:
        g["empty"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}; latent = ["empty", 0]
    g["ks"] = {"class_type": "KSampler", "inputs": {"model": model, "seed": seed, "steps": steps, "cfg": cfg,
               "sampler_name": "dpmpp_2m", "scheduler": "karras", "positive": ["pos", 0], "negative": ["neg", 0],
               "latent_image": latent, "denoise": denoise}}
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["ckpt", 2]}}
    g["save"] = {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": prefix}}
    files, sec = run(g); return files[0], seed

WAN_NEG = "blurry, low quality, distorted, deformed, extra limbs, bad anatomy, flickering, jitter, text, watermark, ugly, static image"
def gen_shot(image, prompt, out_mp4, seed=None, width=None, height=None, frames=81, fps=16):
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    width, height = width or (832 if W > H else 480), height or (480 if W > H else 832)
    g = {
        "hi": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": f"Wan2.2-I2V-A14B-HighNoise-{QUANT}.gguf"}},
        "lo": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": f"Wan2.2-I2V-A14B-LowNoise-{QUANT}.gguf"}},
        "hil": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["hi", 0], "lora_name": "wan22_i2v_lightning_high.safetensors", "strength_model": 1.0}},
        "lol": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["lo", 0], "lora_name": "wan22_i2v_lightning_low.safetensors", "strength_model": 1.0}},
        "his": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["hil", 0], "shift": 5.0}},
        "los": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["lol", 0], "shift": 5.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": WAN_NEG, "clip": ["clip", 0]}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "img": {"class_type": "LoadImage", "inputs": {"image": to_input(image)}},
        "i2v": {"class_type": "WanImageToVideo", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
                "width": width, "height": height, "length": frames, "batch_size": 1, "start_image": ["img", 0]}},
        "k1": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["his", 0], "add_noise": "enable", "noise_seed": seed,
               "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["i2v", 0],
               "negative": ["i2v", 1], "latent_image": ["i2v", 2], "start_at_step": 0, "end_at_step": 2,
               "return_with_leftover_noise": "enable"}},
        "k2": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["los", 0], "add_noise": "disable", "noise_seed": seed,
               "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["i2v", 0],
               "negative": ["i2v", 1], "latent_image": ["k1", 0], "start_at_step": 2, "end_at_step": 10000,
               "return_with_leftover_noise": "disable"}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["k2", 0], "vae": ["vae", 0]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": f"D_{seed}/f"}},
    }
    files, sec = run(g)
    seq = f"/tmp/seq_{seed}"; os.makedirs(seq, exist_ok=True)
    for i, f in enumerate(sorted(files)): shutil.copy(f, f"{seq}/{i:04d}.png")
    sh(f'"{ffmpeg_bin()}" -y -loglevel error -framerate {fps} -i "{seq}/%04d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p "{out_mp4}"')
    shutil.rmtree(seq, ignore_errors=True)
    return seed, sec

def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p: return p
    import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()

# ---------- keyframes: plate + approved character cutouts, then a light harmonising pass ----------
W, H = 768, 1344          # portrait (Shorts); set_orientation() switches to 1344x768 for 16:9 episodes
def set_orientation(landscape):
    global W, H
    W, H = (1344, 768) if landscape else (768, 1344)
    set_video_size(landscape)
PROP_FILES = {}     # prop key -> cutout png made for this episode (make_props)
def cutout(char, expr=None, flip=False):
    """Approved cutout <char>_<expr>_cut.png (falls back to the neutral <char>_cut.png); 'prop:<key>' = an episode prop."""
    if char.startswith("prop:"):
        p = PROP_FILES.get(char[5:]) or find_input(f"prop_{char[5:]}_cut")
        if not p: raise RuntimeError(f"prop '{char[5:]}' was not made")
    else:
        p = (find_input(f"{char}_{expr}_cut") if expr else None) or find_input(f"{char}_cut")
    rgba = Image.open(p).convert("RGBA"); rgba = rgba.crop(rgba.getbbox())
    return rgba.transpose(Image.FLIP_LEFT_RIGHT) if flip else rgba

def _place(bg, ch, h_ratio, cx, foot_y, shadow):
    s = (H * h_ratio) / ch.height
    if ch.width * s > W * 0.9: s = W * 0.9 / ch.width
    ch = ch.resize((max(1, int(ch.width * s)), max(1, int(ch.height * s))), Image.LANCZOS)
    x, y = int(W * cx - ch.width / 2), int(H * foot_y - ch.height)
    if shadow > 0:
        sm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sm).ellipse([x + ch.width * 0.12, H * foot_y - ch.height * 0.035,
                                    x + ch.width * 0.88, H * foot_y + ch.height * 0.035], fill=int(255 * shadow))
        bg = Image.composite(Image.new("RGB", (W, H), (25, 25, 35)), bg, sm.filter(ImageFilter.GaussianBlur(14)))
    a = np.array(ch.split()[-1]).astype(np.float32) / 255
    blur = np.array(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255
    edge = np.clip((a - blur) * 3, 0, 1)[..., None]
    rgb = np.array(ch.convert("RGB")).astype(np.float32)
    region = np.array(bg.filter(ImageFilter.GaussianBlur(20)).crop((x, y, x + ch.width, y + ch.height))).astype(np.float32)
    rgb = rgb * (1 - edge * 0.35) + region * edge * 0.35       # light wrap: the scene's colour on the rim
    ch2 = Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).convert("RGBA"); ch2.putalpha(ch.split()[-1])
    bg.paste(ch2, (x, y), ch2)
    return bg

def composite(plate, members):
    """members: list of dicts {char, expr?, flip?, place{h,cx,foot,shadow}} drawn back (smaller foot) to front."""
    bg = Image.open(plate).convert("RGB").resize((W, H))
    for m in sorted(members, key=lambda m: m["place"]["foot"]):
        bg = _place(bg, cutout(m["char"], m.get("expr"), m.get("flip", False)), m["place"]["h"], m["place"]["cx"],
                    m["place"]["foot"], m["place"]["shadow"])
    return bg

def shot_members(shot):
    """A shot has one 'char' (+expr/flip/place) or a 'cast' list of such entries, plus optional 'props'
    [{prop, place, flip?}] that are composited like characters (no 'char' at all = an empty scene)."""
    base = {"h": 0.5, "cx": 0.5, "foot": 0.86, "shadow": 0.4}
    items = list(shot.get("cast") or ([{"char": shot["char"], "expr": shot.get("expr"), "flip": shot.get("flip", False),
                                        "place": shot.get("place", {})}] if shot.get("char") else []))
    items += [{"char": "prop:" + p["prop"], "flip": p.get("flip", False), "place": p.get("place", {})} for p in shot.get("props", [])]
    return [{**m, "place": {**base, **m.get("place", {})}} for m in items]

PROP_STYLE = ("single object, centered, whole object fully in frame, isolated on a plain light grey studio background, "
              "3d render, pixar style animated movie prop, glossy, soft studio light, high detail")
PROP_NEG = ("character, animal, creature, face, eyes, person, hands, text, watermark, logo, several objects, cropped, cut off, "
            "2d, flat, illustration, lowres, blurry, dark background, shadow on wall")
def make_props(spec, shots, out_dir):
    """Generate each prop the given shots use (SDXL on grey) and cut it out (rembg). Seeded by name: retakes match."""
    import zlib
    used = {p["prop"] for s in shots for p in s.get("props", [])}
    os.makedirs(out_dir, exist_ok=True)
    for key in sorted(used):
        dst = f"{out_dir}/prop_{key}_cut.png"
        if not os.path.exists(dst):
            seed = spec.get("prop_seeds", {}).get(key, zlib.crc32(key.encode()) & 0x7fffffff)
            f, _ = gen_image(f"{spec['props'][key]}, {PROP_STYLE}", neg=PROP_NEG, w=1024, h=1024, seed=seed, prefix=f"PR_{key}")
            shutil.copy(f, dst.replace("_cut.png", "_raw.png")); make_cutout(f, dst)
            log("prop", key, seed)
        PROP_FILES[key] = dst
    return sorted(used)

def still_clip(png, out_mp4, dur=5.0):
    """A still keyframe as a clip (the edit adds the camera move): storybook / bedtime shots, ~1 GPU min instead of 20."""
    sh(f'"{ffmpeg_bin()}" -y -loglevel error -loop 1 -framerate 30 -t {dur + 0.1:.2f} -i "{png}" '
       f'-vf "scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p" -c:v libx264 -crf 14 -pix_fmt yuv420p -preset veryfast "{out_mp4}"')

PLATE_OPEN = "the centre and foreground of the frame left open and uncluttered for the characters"
EXTRAS_STYLE = ("a few stylized 3d animated cartoon people in the background, soft focus, small in the frame, "
                "same pixar-like style, nobody in the centre")
def make_keyframe(shot, out_png, seed=None):
    members = [m for m in shot_members(shot) if m["char"].startswith("prop:") or find_input(f"{m['char']}_cut")]
    if len(members) < len(shot_members(shot)): log("skipped cast without a cutout yet:", [m["char"] for m in shot_members(shot) if m not in members])
    if shot.get("extras"):   # passers-by, commuters, elderly people... drawn into the background plate
        neg = "text, watermark, 2d, flat, illustration, lowres, blurry, photo, photorealistic, person in the centre, object in the centre, " + PANELS_NEG
        pf, pseed = gen_image(f"{shot['plate']}, {shot['extras']}, {EXTRAS_STYLE}, {PLATE_STYLE.replace('no characters, ', '')}",
                              neg=neg, seed=seed, prefix=f"P_{shot['id']}")
    else:
        pf, pseed = gen_image(f"{shot['plate']}, {PLATE_OPEN}, {PLATE_STYLE}", neg=PLATE_NEG + ", object in the centre",
                              seed=seed, prefix=f"P_{shot['id']}")
    comp = composite(pf, members)
    raw = out_png.replace(".png", "_raw.png"); comp.save(raw)
    who = "; ".join(BIBLE.get(m["char"], m["char"][5:].replace("_", " ")) for m in members)
    hf, _ = gen_image(f"{who}, {shot['plate']}, soft light with warm rim light, {STYLE_3D}",
                      init=raw, denoise=0.25, seed=pseed, prefix=f"H_{shot['id']}")
    shutil.copy(hf, out_png)
    return pseed

def gen_edit(image, instruction, seed=None, prefix="E", steps=4, cfg=1.0, megapixels=1.0):
    """Qwen-Image-Edit 2509 + 4-step Lightning LoRA: edit one image by an instruction."""
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    g = {
        "unet": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen_edit_2509.gguf"}},
        "lora": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["unet", 0], "lora_name": "qwen_edit_lightning.safetensors", "strength_model": 1.0}},
        "ms": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["lora", 0], "shift": 3.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "img": {"class_type": "LoadImage", "inputs": {"image": to_input(image)}},
        "scale": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["img", 0], "upscale_method": "lanczos", "megapixels": megapixels}},
        "pos": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["clip", 0], "prompt": instruction, "vae": ["vae", 0], "image1": ["scale", 0]}},
        "neg": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["clip", 0], "prompt": "", "vae": ["vae", 0], "image1": ["scale", 0]}},
        "enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["scale", 0], "vae": ["vae", 0]}},
        "ks": {"class_type": "KSampler", "inputs": {"model": ["ms", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler",
               "scheduler": "simple", "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["enc", 0], "denoise": 1.0}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": prefix}},
    }
    files, sec = run(g)
    im = np.array(Image.open(files[0]).convert("L"))
    if im.mean() < 8 or im.std() < 3:
        raise RuntimeError("Qwen edit returned a blank/black image (fp16 problem on this GPU?)")
    return files[0], seed, sec

# ---------- cast: expression candidates for each character (one-time, reviewed by a person) ----------
# Only the face is repainted (masked img2img, strong denoise); the body stays exactly the approved master.
EXPRESSIONS = {
    "sad": "crying sadly, big tears streaming down, sad droopy eyebrows, downturned trembling mouth",
    "laugh": "laughing out loud with joy, eyes closed as happy upturned arcs, wide open smiling mouth",
    "surprised": "very surprised, eyes wide open with tiny pupils, raised eyebrows, small round open mouth",
    "scared": "a little scared, worried eyebrows, wobbly frown, eyes looking sideways",
}
# face box per character, as fractions of the cutout's bounding box (x0, y0, x1, y1)
FACE_BOX = {"pip": (0.12, 0.0, 0.88, 0.42), "momo": (0.05, 0.0, 0.95, 0.75),
            "tock": (0.12, 0.0, 0.88, 0.45), "bibi": (0.15, 0.22, 0.85, 0.78)}
CAST_BG = (138, 143, 153)
NAMES = {"pip": "duckling", "momo": "pink frog", "tock": "baby turtle", "bibi": "little pink cloud", "m": "middle-aged office worker man",
         "wife": "woman", "son": "boy", "daughter": "little girl", "junior": "young office worker", "boss": "older manager", "friend": "chubby man",
         "grandma": "grandmother", "grandpa": "grandfather"}
EDITS = {
    "sad": "Change only the facial expression: the {n} is crying sadly with big tears rolling down and a downturned mouth.",
    "laugh": "Change only the facial expression: the {n} is laughing out loud with joy, eyes squeezed shut into happy curves, mouth wide open.",
    "surprised": "Change only the facial expression: the {n} looks very surprised, eyes wide open, mouth in a small round O.",
    "scared": "Change only the facial expression: the {n} looks a little scared and worried, eyebrows raised, wobbly frown.",
    "side": "Turn the {n} to a three-quarter view facing right, happy expression, same pose otherwise.",
    "cheer": "Make the {n} jump happily in the air with a big joyful smile.",
    # CAST4: action poses for travel, bedtime and snack episodes
    "run": "Make the {n} run happily to the right in a lively mid-stride running pose, excited smile.",
    "sit": "Make the {n} sit down calmly on the ground, relaxed and content, gentle smile.",
    "wave": "Make the {n} wave hello with one wing / hand / little arm raised high, cheerful open smile.",
    "point": "Make the {n} point up excitedly at something above, looking up with wide sparkling eyes and an open mouth.",
    "sleep": "Make the {n} fast asleep, curled up cosily, eyes peacefully closed, tiny content smile.",
    "eat": "Make the {n} take a big happy bite of food, cheeks puffed out, eyes closed in delight.",
    # MIDLIFE COMMUTER: M's scenes (commute, office, home)
    "walk": "Make the {n} walk briskly to the right on his way to work, mid-stride, briefcase in his hand, tired but determined face.",
    "sigh": "Make the {n} look worn out and resigned: shoulders slumped, head tilted slightly down, eyes half closed, mouth in a small flat line, no tears, briefcase hanging low.",
    "smile": "Change only the facial expression: the {n} smiles warmly and gently, soft happy eyes, a little moved.",
    "lookup": "Make the {n} raise his chin and gaze up toward the sky with a calm, warm, hopeful smile, relaxed eyebrows, no fear, no sweat, peaceful and moved.",
    "seated": "Make the {n} sit down with the briefcase on his lap and both hands resting on it, as if on a bench, tired gentle face.",
    "back": "Show the {n} from behind, walking away from the camera, briefcase in his right hand, same clothes.",
    "wallet": "Make the {n} look down sadly at an open wallet held in both hands, the briefcase standing at his feet.",
}
KEEP = " Keep exactly the same character design, colours, proportions and glossy 3D animated style. Plain light grey background."

def cast_candidates_edit(spec, out_dir):
    os.makedirs(out_dir, exist_ok=True); made = {}
    for char in spec.get("chars", list(BIBLE)):
        base = cutout(char)
        canvas = Image.new("RGB", (1024, 1024), CAST_BG)
        s = 760 / max(base.width, base.height); b = base.resize((int(base.width * s), int(base.height * s)), Image.LANCZOS)
        canvas.paste(b, ((1024 - b.width) // 2, 1024 - 90 - b.height), b)
        init = f"{out_dir}/{char}_init.png"; canvas.save(init)
        for expr in spec.get("exprs", list(EDITS)):
            for k in range(spec.get("per_item", 2)):
                f, sd, sec = gen_edit(init, EDITS[expr].format(n=NAMES[char]) + KEEP, prefix=f"E_{char}_{expr}")
                dst = f"{out_dir}/{char}_{expr}_{k}.png"; shutil.copy(f, dst); made.setdefault(f"{char}_{expr}", []).append(dst)
                log("edit", char, expr, k, sd, f"{sec:.0f}s")
    return made

def cast_candidates(spec, out_dir):
    os.makedirs(out_dir, exist_ok=True); made = {}
    for char in spec.get("chars", list(BIBLE)):
        base = cutout(char)
        canvas = Image.new("RGB", (1024, 1024), CAST_BG)
        s = 760 / max(base.width, base.height); b = base.resize((int(base.width * s), int(base.height * s)), Image.LANCZOS)
        ox, oy = (1024 - b.width) // 2, 1024 - 90 - b.height
        canvas.paste(b, (ox, oy), b)
        init = f"{out_dir}/{char}_init.png"; canvas.save(init)
        fx0, fy0, fx1, fy1 = FACE_BOX[char]
        m = Image.new("L", (1024, 1024), 0)
        ImageDraw.Draw(m).ellipse([ox + b.width * fx0, oy + b.height * fy0, ox + b.width * fx1, oy + b.height * fy1], fill=255)
        from PIL import ImageChops
        m = ImageChops.multiply(m, _alpha_canvas(b, ox, oy)).filter(ImageFilter.GaussianBlur(10))   # face ∩ body, soft edge
        mask = f"{out_dir}/{char}_mask.png"; m.convert("RGB").save(mask)
        for expr in spec.get("exprs", list(EXPRESSIONS)):
            k = 0
            for d in spec.get("denoise", [0.75, 0.88]):
                for _ in range(spec.get("per_denoise", 2)):
                    f, sd = gen_image(f"{BIBLE[char]}, {EXPRESSIONS[expr]}, expressive cartoon face, plain light grey studio background, {STYLE_3D}",
                                      w=1024, h=1024, init=init, mask=mask, denoise=d, prefix=f"C_{char}_{expr}")
                    dst = f"{out_dir}/{char}_{expr}_{k}.png"; shutil.copy(f, dst); made.setdefault(f"{char}_{expr}", []).append(dst)
                    log("cast", char, expr, k, d, sd); k += 1
    return made

# ---------- design: brand-new characters and backgrounds from text (one-time, a person picks) ----------
# spec "design": {"m": {"prompt": "...", "count": 8}}  -> m_0.png ... ; `/pick m=3` makes assets/m_cut.png (the master)
# spec "plates": {"bannerbg": {"prompt": "...", "count": 4, "w": 1344, "h": 768}} -> backgrounds to download (no /pick)
HUMAN_NEG = ", photo, photorealistic, real person, uncanny valley, creepy, distorted face, extra fingers, cropped feet, cut off head"
def design_candidates(spec, out_dir):
    os.makedirs(out_dir, exist_ok=True); made = {}
    for key, d in spec.get("design", {}).items():
        for k in range(d.get("count", 8)):
            f, sd = gen_image(f"{d['prompt']}, full body standing pose, whole body in frame from head to shoes, centered, "
                              f"plain light grey studio background, {STYLE_3D}", neg=NEG_3D + HUMAN_NEG,
                              w=d.get("w", 832), h=d.get("h", 1216), prefix=f"D_{key}")
            dst = f"{out_dir}/{key}_{k}.png"; shutil.copy(f, dst); made.setdefault(key, []).append(dst); log("design", key, k, sd)
    sty = {k: d["stylize"] for k, d in spec.get("design", {}).items() if d.get("stylize")}
    if sty:   # SDXL tends to draw people photo-real: Qwen-Image-Edit turns each candidate into the 3D animated look
        stop_server(); ensure("edit")
        for key, instr in sty.items():
            for dst in made[key]:
                f, sd, sec = gen_edit(dst, instr, prefix=f"S_{key}")
                shutil.copy(f, dst); log("stylize", key, os.path.basename(dst), f"{sec:.0f}s")
        stop_server(); ensure("image")
    for key, d in spec.get("plates", {}).items():
        for k in range(d.get("count", 4)):
            f, sd = gen_image(f"{d['prompt']}, {PLATE_STYLE}", neg=PLATE_NEG, w=d.get("w", 1344), h=d.get("h", 768), prefix=f"B_{key}")
            dst = f"{out_dir}/{key}_{k}.png"; shutil.copy(f, dst); made.setdefault(key, []).append(dst); log("plate", key, k, sd)
    return made

def _alpha_canvas(b, ox, oy):
    a = Image.new("L", (1024, 1024), 0); a.paste(b.split()[-1].point(lambda v: 255 if v > 20 else 0), (ox, oy)); return a

def cast_sheets(made, out_dir):
    from PIL import ImageFont
    by_char = {}
    for key, files in made.items(): by_char.setdefault(key.split("_")[0], []).append((key, files))
    for char, rows in by_char.items():
        tw = 256; cols = max(len(f) for _, f in rows)
        sheet = Image.new("RGB", (tw * cols, (tw + 30) * len(rows)), "white"); d = ImageDraw.Draw(sheet)
        for r, (key, files) in enumerate(rows):
            for c, f in enumerate(files):
                sheet.paste(Image.open(f).resize((tw, tw)), (c * tw, r * (tw + 30)))
                d.text((c * tw + 6, r * (tw + 30) + tw + 6), f"{key}={c}", fill="black")
        sheet.save(f"{out_dir}/sheet_{char}.jpg", quality=88)
