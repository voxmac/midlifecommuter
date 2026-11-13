# ===================== modal_job.py: run one job (song / cast) on a Modal GPU =====================
# modal run tools/modal_job.py --spec songs/MC01.json --out out/MC01
# The same studio/*.py code the Kaggle pipeline uses runs here unchanged: this container mimics Kaggle's paths
# (/kaggle/input/assets, /kaggle/working/out). Tools and model weights live in a Modal Volume, so only the
# first run pays for installing ACE-Step / ComfyUI and downloading weights. Billing: per second, $30/month free credits.
import json, os, pathlib, subprocess, sys, time
import modal

RATE = {"T4": 0.59, "L4": 0.80, "A10G": 1.10, "L40S": 1.95, "A100-40GB": 2.10, "A100-80GB": 2.50, "H100": 3.95}  # $/h, approx

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("git", "ffmpeg", "build-essential", "libgl1", "libglib2.0-0")
         .pip_install("torch==2.7.1", "torchvision==0.22.1", "torchaudio==2.7.1", "numpy<2.3", "pillow", "scipy",
                      "huggingface_hub", "imageio-ffmpeg", "soundfile", "requests", "uv")
         # tools are baked into the image (built once, cached by Modal); only model weights live in the Volume
         .run_commands(
             "git clone -q --depth 1 https://github.com/ace-step/ACE-Step-1.5 /opt/ace",
             "cd /opt/ace && uv sync -q",
             "sed -i 's/self.dtype = torch.float16/self.dtype = torch.float32/' /opt/ace/acestep/core/generation/handler/init_service_orchestrator.py",
             "git clone -q --depth 1 https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI",
             "git clone -q --depth 1 https://github.com/city96/ComfyUI-GGUF /opt/ComfyUI/custom_nodes/ComfyUI-GGUF",
             "git clone -q --depth 1 https://github.com/cubiq/ComfyUI_IPAdapter_plus /opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus"))
GPU = os.environ.get("MODAL_GPU", "T4")   # Modal fixes the GPU at decoration time: the workflow sets it from the spec
image = image.env({"MODAL_GPU": GPU})     # so the container re-imports this file with the same GPU
app = modal.App("midlife-commuter", image=image)
vol = modal.Volume.from_name("midlife-commuter-cache", create_if_missing=True)


@app.function(gpu=GPU, volumes={"/cache": vol}, timeout=4 * 3600, memory=32768)
def run(spec, source, files):
    import shutil
    t0 = time.time()
    # the studio code expects /tmp/ace and /tmp/ComfyUI: point them at the image, and their weight folders at the Volume
    for link, target in (("/tmp/ace", "/opt/ace"), ("/tmp/ComfyUI", "/opt/ComfyUI")):
        if not os.path.lexists(link): os.symlink(target, link)
    for local, cached in (("/opt/ace/checkpoints", "/cache/ace-checkpoints"), ("/opt/ComfyUI/models", "/cache/comfy-models")):
        os.makedirs(cached, exist_ok=True)
        if os.path.isdir(local) and not os.path.islink(local):
            for f in os.listdir(local):                                   # keep the folders ComfyUI ships with
                if not os.path.exists(f"{cached}/{f}"): shutil.move(f"{local}/{f}", f"{cached}/{f}")
            shutil.rmtree(local)
        if not os.path.lexists(local): os.symlink(cached, local)
    for old in ("/cache/ace", "/cache/ComfyUI"): shutil.rmtree(old, ignore_errors=True)   # leftovers of the first layout
    os.makedirs("/cache/hf", exist_ok=True)
    os.makedirs("/kaggle/input/assets", exist_ok=True); os.makedirs("/kaggle/working/out", exist_ok=True)
    for name, data in files.items(): open(f"/kaggle/input/assets/{name}", "wb").write(data)
    open("/root/kernel.py", "w").write(source)
    gpu = subprocess.run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", shell=True,
                         capture_output=True, text=True).stdout.strip()
    print("GPU", gpu, flush=True)
    env = {**os.environ, "STUDIO_OUT": "/kaggle/working/out", "HF_HOME": "/cache/hf", "PYTHONUNBUFFERED": "1"}
    p = subprocess.Popen([sys.executable, "/root/kernel.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    log = []
    for line in p.stdout:
        print(line, end="", flush=True); log.append(line)
    p.wait(); vol.commit()
    E = f"/kaggle/working/out/{spec['id']}"
    res = {f: open(f"{E}/{f}", "rb").read() for f in (os.listdir(E) if os.path.isdir(E) else []) if os.path.isfile(f"{E}/{f}")}
    mins = (time.time() - t0) / 60
    res["run.log"] = "".join(log[-4000:]).encode()
    res["modal.json"] = json.dumps({"id": spec["id"], "gpu": gpu, "exit": p.returncode, "minutes": round(mins, 1),
                                    "usd_approx": round(mins / 60 * RATE.get(GPU, 2.0), 2)}, indent=1).encode()
    return res


@app.local_entrypoint()
def main(spec: str, out: str):
    root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    from build_kernel import build_source
    sp = json.load(open(spec, encoding="utf-8"))
    assert sp.get("gpu", "T4") == GPU, "set MODAL_GPU to the spec's gpu"
    files = {p.name: p.read_bytes() for p in (root / "assets").iterdir()
             if p.is_file() and not p.name.startswith(".") and p.stat().st_size < 50 * 2**20}
    res = run.remote(sp, build_source(sp), files)
    os.makedirs(out, exist_ok=True)
    for f, data in res.items(): open(f"{out}/{f}", "wb").write(data)
    print(res["modal.json"].decode())
    if json.loads(res["modal.json"])["exit"] != 0: sys.exit(1)
