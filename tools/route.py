"""Which GPU runs a job: prints 'kaggle' or 'modal'.  usage: route.py SPEC.json
Kaggle (free, ~30 GPU h/week, T4, slower) takes songs, character designs and first renders of a Short.
Modal (credits, fast L40S) takes retakes (the earlier shots live on the Modal volume) and anything with "runner": "modal"."""
import json, os, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
if os.environ.get("FORCE_RUNNER") in ("kaggle", "modal"): print(os.environ["FORCE_RUNNER"]); sys.exit()
if s.get("runner") in ("kaggle", "modal"): print(s["runner"]); sys.exit()
if not os.environ.get("KAGGLE_KEY"): print("modal"); sys.exit()
if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "no_modal")) and not os.environ.get("FORCE_RUNNER"):
    print("kaggle"); sys.exit()   # budget: Modal only when asked for explicitly
if s.get("type") == "qccal": print("modal"); sys.exit()
if "shots" in s and s.get("retake"): print("modal"); sys.exit()
print("kaggle")
