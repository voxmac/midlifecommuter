"""Builds a self-contained Kaggle script kernel for one episode spec.
usage: python tools/build_kernel.py episodes/EP02.json <kaggle_username> [--shots-dataset]
writes build/<ep>/kernel.py + kernel-metadata.json"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ["sfx.py", "voice.py", "gen.py", "edit.py", "qc.py", "main.py"]

def build_source(spec):
    src = [f"SPEC = json.loads({json.dumps(spec)!r})\n"]
    mods = {"song": ["song.py"], "lab": ["wangp.py"], "qccal": ["qc.py"]}.get(spec.get("type"), MODULES)
    if spec.get("format") == "mv": mods = MODULES[:-1] + ["wangp.py", "main.py"]   # lip-sync shots run WanGP
    for m in mods:
        src.append(open(os.path.join(ROOT, "studio", m), encoding="utf-8").read())
    return "import json\n" + "\n".join(src)

def main():
    spec_path, user = sys.argv[1], sys.argv[2]
    with_shots = "--shots-dataset" in sys.argv
    spec = json.load(open(spec_path, encoding="utf-8"))
    ep = spec["id"]
    d = os.path.join(ROOT, "build", ep); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "kernel.py"), "w", encoding="utf-8").write(build_source(spec))
    meta = {
        "id": f"{user}/puddlepals-{ep.lower()}",
        "title": f"puddlepals-{ep.lower()}",
        "code_file": "kernel.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_internet": True,
        "enable_gpu": True,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [f"{user}/puddlepals-assets"] + ([f"{user}/puddlepals-shots"] if with_shots else []),
        "competition_sources": [], "kernel_sources": [], "model_sources": [],
    }
    json.dump(meta, open(os.path.join(d, "kernel-metadata.json"), "w"), indent=1)
    print(d)

if __name__ == "__main__":
    main()
