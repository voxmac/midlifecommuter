"""Runs the edit stage locally (no GPU) for a spec whose shots are all 'reuse' assets. Used to test the engine.
usage: python tools/run_local.py episodes/EP01.json"""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_kernel import build_source
os.environ.setdefault("STUDIO_LOCAL", "1")
os.environ.setdefault("STUDIO_ASSETS", os.path.join(ROOT, "assets"))
os.environ.setdefault("STUDIO_OUT", os.path.join(ROOT, "build", "local"))
spec = json.load(open(sys.argv[1], encoding="utf-8"))
src = build_source(spec).replace('"/kaggle/working/out"', repr(os.environ["STUDIO_OUT"]))
g = {"__name__": "__main__"}
exec(compile(src, "kernel.py", "exec"), g)
