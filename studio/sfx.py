# ===================== sfx.py: synthesised sound library (no samples, all original) =====================
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve, resample

SR = 44100
_rng = np.random.default_rng(3)

def t_(d): return np.arange(int(SR * d)) / SR
def env(n, a=0.005, r=0.1):
    e = np.ones(n); na = max(1, int(a * SR)); e[:na] = np.linspace(0, 1, na)
    nr = min(n, int(r * SR)); e[-nr:] *= np.linspace(1, 0, nr) ** 2; return e
def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)
def sweep(f0, f1, d):
    t = t_(d); f = f0 * (f1 / f0) ** (t / d); return np.sin(2 * np.pi * np.cumsum(f) / SR)
NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)
def noise(d): return _rng.standard_normal(int(SR * d))

def plop():   d = 0.14; return sweep(1400, 380, d) * np.exp(-t_(d) * 28) * 0.8
def tiny_plip(): d = 0.08; return sweep(1800, 900, d) * np.exp(-t_(d) * 45) * 0.5
def boing():
    d = 0.32; t = t_(d); f = 280 * (2.6 ** (t / d)) * (1 + 0.06 * np.sin(2 * np.pi * 22 * t))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * 0.6
def pong():   d = 0.2; return sweep(1100, 700, d) * np.exp(-t_(d) * 20) * 0.45
def quack(f0=520, d=0.13, vol=0.5):
    t = t_(d); f = f0 * (1 - 0.25 * t / d); saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    v = bp(saw, 900, 2600) + 0.5 * bp(saw, 300, 700); return v / (np.abs(v).max() + 1e-9) * env(len(t), 0.004, 0.05) * vol
def giggle(n=4, f0=560):
    out = np.zeros(int(SR * (0.16 * n + 0.2)))
    for i in range(n):
        q = quack(f0 * (1 + 0.06 * (i % 2)), 0.1, 0.42); s = int(i * 0.16 * SR); out[s:s + len(q)] += q
    return out
def whoosh(d=0.5):
    n = noise(d); t = t_(d); x = np.zeros_like(n)
    for k in range(8):
        a, b = int(k * len(n) / 8), int((k + 1) * len(n) / 8); lo = 300 + 2400 * k / 8; x[a:b] = bp(n, lo, lo * 1.8)[a:b]
    return x * np.sin(np.pi * t / d) ** 2 * 0.35
def splash():
    d = 1.1; n = noise(d); t = t_(d)
    x = bp(n, 500, 6000) * np.exp(-t * 4.5) * 0.9 + np.sin(2 * np.pi * 70 * t) * np.exp(-t * 14) * 0.9
    for _ in range(14):
        i = int(_rng.uniform(0.15, 0.9) * SR); dd = pong() * _rng.uniform(0.2, 0.5); x[i:i + len(dd)] += dd[: len(x) - i]
    x[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR)); return x * 0.9
def slow_splash(): sp = splash(); return lp(resample(sp, int(len(sp) * 2.4)), 3500) * 1.15
def boom():
    return np.sin(2 * np.pi * np.cumsum(np.linspace(90, 36, int(SR * 1.4))) / SR) * np.exp(-t_(1.4) * 2.6) * 0.85
def riser(d=2.0): return bp(noise(d), 400, 3000) * np.linspace(0, 1, int(SR * d)) ** 2 * 0.22
def brrr(d=0.8):
    t = t_(d); n = bp(_rng.standard_normal(len(t)), 800, 5000)
    return n * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 18 * t))) * np.sin(np.pi * t / d) * 0.35
def bell(m=84, d=1.4, vol=0.3):
    f = NOTE(m); t = t_(d)
    x = sum(a * np.sin(2 * np.pi * f * k * t) * np.exp(-t * r) for k, a, r in [(1, 1, 3), (2.01, .4, 5), (3.02, .2, 7), (4.1, .1, 9)])
    return x * vol * env(len(t), 0.002, 0.3)
def chimes(up=True):
    notes = [72, 76, 79, 84, 88, 91] if up else [91, 88, 84, 79, 76, 72]
    out = np.zeros(int(SR * 2.2))
    for i, m in enumerate(notes):
        b = bell(m, 1.4, 0.16); s = int(i * 0.12 * SR); out[s:s + len(b)] += b
    return out
def popup(): d = 0.12; return sweep(500, 1400, d) * env(int(SR * d), 0.002, 0.05) * 0.35
def flap():
    d = 0.12; x = bp(noise(d), 300, 2200) * np.sin(np.pi * t_(d) / d) ** 2; return x / np.abs(x).max() * 0.35
def flaps(n=4):
    out = np.zeros(int(SR * (0.4 * n + 0.2)))
    for i in range(n):
        f = flap(); s = int(i * 0.4 * SR); out[s:s + len(f)] += f; s2 = s + int(0.07 * SR); out[s2:s2 + len(f)] += f * 0.7
    return out
def sad_trombone():
    out = np.zeros(int(SR * 2.0))
    for i, (m, d) in enumerate([(55, 0.32), (54, 0.32), (53, 0.32), (52, 0.9)]):
        tt = t_(d); f = NOTE(m) * (1 + (0.025 * np.sin(2 * np.pi * 6 * tt) if i == 3 else 0))
        saw = 2 * ((np.cumsum(f * np.ones_like(tt)) / SR) % 1) - 1
        x = lp(saw, 1400) * env(len(tt), 0.02, 0.12) * 0.28; s = int(i * 0.34 * SR); out[s:s + len(x)] += x
    return out
def drip_whistle(d=0.7): return sweep(2600, 1600, d) * np.linspace(0, 1, int(SR * d)) * 0.10
def sniff(vol=0.35):
    d = 0.25; return bp(noise(d), 1500, 5000) * np.sin(np.pi * t_(d) / d) ** 2 * vol
def sob(n=3):
    out = np.zeros(int(SR * (0.35 * n + 0.4)))
    for i in range(n):
        d = 0.25; tt = t_(d); f = 520 * (1 - 0.3 * tt / d) * (1 + 0.04 * np.sin(2 * np.pi * 9 * tt))
        x = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * bp(_rng.standard_normal(len(tt)), 1500, 5000)) * env(len(tt), 0.02, 0.1) * 0.3
        s = int(i * 0.35 * SR); out[s:s + len(x)] += x
    return out
def eep(): d = 0.12; return sweep(700, 1500, d) * env(int(SR * d), 0.003, 0.04) * 0.45
def clack():
    d = 0.16; tt = t_(d); x = bp(_rng.standard_normal(len(tt)), 300, 1800) * np.exp(-tt * 40)
    return (x / np.abs(x).max() + np.sin(2 * np.pi * 160 * tt) * np.exp(-tt * 25)) * 0.5
def pop():
    d = 0.12; tt = t_(d); return (sweep(300, 1200, d) * np.exp(-tt * 22) + bp(_rng.standard_normal(len(tt)), 2000, 6000) * np.exp(-tt * 60) * 0.4) * 0.6
def hehe(n=4, f0=880, vol=0.32):
    out = np.zeros(int(SR * (0.14 * n + 0.3)))
    for i in range(n):
        d = 0.1; tt = t_(d); f = f0 * (1 + 0.04 * (i % 2)) * (1 + 0.03 * np.sin(2 * np.pi * 18 * tt))
        x = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * bp(_rng.standard_normal(len(tt)), 2000, 6000)) * env(len(tt), 0.005, 0.05)
        s = int(i * 0.14 * SR); out[s:s + len(x)] += x * vol
    return out
def zip_(): d = 0.16; return sweep(500, 2600, d) * np.exp(-t_(d) * 6) * 0.5
def slurp(): d = 0.14; return sweep(2200, 600, d) * env(int(SR * d), 0.003, 0.05) * 0.4
def gulp():
    d = 0.22; t = t_(d); return np.sin(2 * np.pi * np.cumsum(220 * (0.45 ** (t / d))) / SR) * np.sin(np.pi * t / d) ** 2 * 0.8
def ribbit(f=170, vol=0.55):
    out = []
    for d, ff in [(0.09, f), (0.14, f * 0.92)]:
        t = t_(d); car = np.sign(np.sin(2 * np.pi * ff * t)) * (0.5 + 0.5 * np.sin(2 * np.pi * 38 * t))
        out.append(bp(car, 250, 2200) * env(len(t), 0.004, 0.04)); out.append(np.zeros(int(0.03 * SR)))
    x = np.concatenate(out); return x / (np.abs(x).max() + 1e-9) * vol
def croak_laugh(n=5):
    out = np.zeros(int(SR * (0.2 * n + 0.3)))
    for i in range(n):
        r = ribbit(190 + 15 * (i % 2), 0.42); s = int(i * 0.2 * SR); out[s:s + len(r)] += r
    return out
def tongue():
    out = np.zeros(int(SR * 0.9));
    for x, at in [(zip_(), 0), (slurp(), 0.2), (gulp() * 0.8, 0.55)]:
        s = int(at * SR); out[s:s + len(x)] += x
    return out
def chirp():
    out = np.zeros(int(SR * 0.4))
    for j in range(3):
        d = 0.07; x = sweep(3200, 4600, d) * env(int(SR * d), 0.003, 0.03) * 0.12; s = int(j * 0.11 * SR); out[s:s + len(x)] += x
    return out
def thunder():
    d = 1.8; t = t_(d); return lp(noise(d), 180) * np.exp(-t * 1.8) * (1 + np.sin(2 * np.pi * 3 * t) * 0.3) * 1.6
def rainbow():
    out = np.zeros(int(SR * 2.6))
    for i, m in enumerate([72, 74, 76, 79, 81, 84, 86, 88]):
        b = bell(m, 1.6, 0.14); s = int(i * 0.1 * SR); out[s:s + len(b)] += b
    sh = lp(noise(1.2), 6000) * np.linspace(0, 1, int(SR * 1.2)) * 0.05     # shimmer swell under the bells
    out[:len(sh)] += sh
    return out
def slide(): d = 1.2; return sweep(300, 1500, d) * env(int(SR * d), 0.05, 0.3) * 0.25

# ---- ASMR / food sounds (close, crisp, no music-like pitch) ----
def _grains(n_grains, d, lo, hi, decay, vol, seed=0):
    r = np.random.default_rng(seed); out = np.zeros(int(SR * d)); g = int(SR * 0.03)
    for _ in range(n_grains):
        i = int(r.uniform(0, d - 0.03) * SR); x = bp(r.standard_normal(g), lo, hi) * np.exp(-np.arange(g) / SR * decay)
        out[i:i + g] += x * r.uniform(0.4, 1.0)
    return out / (np.abs(out).max() + 1e-9) * vol
def crunch(n=1, vol=0.7):
    """a crisp bite: dense crackle burst; n bites 0.45 s apart"""
    out = np.zeros(int(SR * (0.45 * n + 0.4)))
    for k in range(n):
        x = _grains(60, 0.28, 1800, 9000, 90, vol, seed=k) + _grains(18, 0.28, 300, 1500, 60, vol * 0.5, seed=k + 9)
        x *= np.exp(-t_(0.28) * 5); s = int(k * 0.45 * SR); out[s:s + len(x)] += x
    return out
def munch(n=4, vol=0.45):
    """soft chewing: muffled squishy clicks"""
    out = np.zeros(int(SR * (0.32 * n + 0.3)))
    for k in range(n):
        x = lp(_grains(10, 0.22, 200, 2500, 40, 1.0, seed=30 + k), 1800) * np.sin(np.pi * t_(0.22) / 0.22); s = int(k * 0.32 * SR)
        out[s:s + len(x)] += x / (np.abs(x).max() + 1e-9) * vol
    return out
def chomp(vol=0.8):
    """one big bite: thump + crackle"""
    d = 0.4; tt = t_(d); th = np.sin(2 * np.pi * np.cumsum(140 * 0.5 ** (tt / d)) / SR) * np.exp(-tt * 18)
    return (th * 0.8 + crunch(1, 0.6)[: len(tt)]) * vol
def squish(vol=0.5):
    """jelly / marshmallow squeeze: wet low gurgle that bends down"""
    d = 0.45; tt = t_(d); f = 180 * (1 + 0.6 * np.sin(2 * np.pi * 7 * tt)) * (0.6 ** (tt / d))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * lp(noise(d), 900)
    return x * np.sin(np.pi * tt / d) ** 2 * vol
def jelly(d=0.9, vol=0.4):
    """wobble: pitch wobbling and slowing like jelly"""
    tt = t_(d); f = 260 + 90 * np.sin(2 * np.pi * (9 - 6 * tt / d) * tt) * np.exp(-tt * 2.5)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 3) * vol
def fizz(d=1.5, vol=0.25):
    """soda bubbles: many tiny high pops"""
    return _grains(int(90 * d), d, 4000, 12000, 300, vol, seed=77) * np.linspace(1, 0.3, int(SR * d))
def bubble_pop(vol=0.5):
    d = 0.1; return sweep(600, 2400, d) * np.exp(-t_(d) * 35) * vol
def sparkle(n=6, vol=0.15):
    """magic twinkle: random high bells"""
    out = np.zeros(int(SR * (0.08 * n + 1.0))); r = np.random.default_rng(5)
    for i in range(n):
        b = bell(int(r.choice([88, 91, 93, 96, 98, 100])), 0.8, vol); s = int(i * 0.08 * SR); out[s:s + len(b)] += b
    return out
def yum(f0=300, vol=0.35):
    """a contented 'mmm!' hum that rises"""
    d = 0.6; tt = t_(d); f = f0 * (1 + 0.25 * tt / d) * (1 + 0.02 * np.sin(2 * np.pi * 6 * tt))
    x = lp(np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.35 * np.sin(4 * np.pi * np.cumsum(f) / SR), 900)
    return x * env(len(tt), 0.05, 0.2) * vol
def crack(vol=0.7):
    """an egg / shell / ice crack"""
    d = 0.3; x = _grains(25, d, 2500, 10000, 160, 1.0, seed=11) * np.exp(-t_(d) * 9)
    return (x + np.sin(2 * np.pi * 900 * t_(d)) * np.exp(-t_(d) * 60) * 0.3) * vol
def pour(d=1.4, vol=0.3):
    """liquid pouring: band noise with gurgle"""
    tt = t_(d); x = bp(noise(d), 500, 3000) * (0.7 + 0.3 * np.sin(2 * np.pi * 11 * tt))
    return x * np.sin(np.pi * tt / d) ** 0.7 * vol
def lullaby_chime(): return chimes(False) * 0.5
def snore(n=2, vol=0.3):
    """a tiny sleepy snore and whistle"""
    out = np.zeros(int(SR * (1.6 * n + 0.5)))
    for k in range(n):
        x = lp(noise(0.7), 400) * np.sin(np.pi * t_(0.7) / 0.7) ** 2 * vol * 2
        w = sweep(1800, 1200, 0.5) * np.sin(np.pi * t_(0.5) / 0.5) * vol * 0.25
        s = int(k * 1.6 * SR); out[s:s + len(x)] += x; out[s + len(x) + 2000:s + len(x) + 2000 + len(w)] += w
    return out

SFX = {k: v for k, v in dict(globals()).items() if callable(v) and k in (
    "plop tiny_plip boing pong quack giggle whoosh splash slow_splash boom riser brrr bell chimes popup flap flaps "
    "sad_trombone drip_whistle sniff sob eep clack pop hehe zip_ slurp gulp ribbit croak_laugh tongue chirp thunder "
    "rainbow slide crunch munch chomp squish jelly fizz bubble_pop sparkle yum crack pour lullaby_chime snore").split()}

def pluck(f, d=0.9, vol=0.22):
    n = int(SR * d); p = int(SR / f); buf = _rng.uniform(-1, 1, p); out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]; buf[i % p] = 0.5 * (buf[i % p] + buf[(i + 1) % p]) * 0.996
    return out * vol * env(n, 0.002, 0.25)

def make_music(N, sections, rests, slow_mask, finale_t):
    """sections: [(start_s, 'major'|'minor')]; rests: [(a,b)] silent windows; slow_mask: array 0..1 to muffle."""
    t = np.arange(N) / SR; cache = {}
    def ks(m, d, v):
        k = (m, d, v)
        if k not in cache: cache[k] = pluck(NOTE(m), d, v)
        return cache[k]
    mus = np.zeros(N + SR * 3); bass = np.zeros_like(mus); pad = np.zeros_like(mus)
    def put(b, x, at): i = int(at * SR); b[i:i + len(x)] += x[: len(b) - i]
    PROG = {"major": [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]],
            "minor": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [52, 56, 59]],
            "lullaby": [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]],
            "playful": [[60, 64, 67], [62, 65, 69], [64, 67, 71], [55, 59, 62]]}
    MEL = {"major": [72, 74, 76, None, 79, 76, 74, None, 72, 74, 76, 79, 81, None, 79, None],
           "minor": [76, None, 72, None, 69, None, 71, 72, 69, None, None, None, 64, None, 68, None],
           "lullaby": [76, None, None, 74, 72, None, None, None, 69, None, 72, None, 71, None, None, None],
           "playful": [72, 72, 76, 72, 79, None, 77, 76, 74, 74, 77, 74, 79, None, None, None]}
    BPM = {"major": 112, "minor": 84, "lullaby": 66, "playful": 126}
    LVL = {"major": 0.13, "minor": 0.10, "lullaby": 0.07, "playful": 0.12}
    def mode_at(x):
        m = sections[0][1]
        for s, mm in sections:
            if x >= s: m = mm
        return m
    at = 0.0; b = 0
    while at < N / SR + 1:
        mode = mode_at(at); bpm = BPM[mode]; beat = 60 / bpm
        ch = PROG[mode][(b // 4) % 4]
        if not any(a - 0.1 < at < z for a, z in rests):
            lvl = LVL[mode]
            for j, m in enumerate(ch): put(mus, ks(m + 12, 0.9, lvl if b % 2 == 0 else lvl * 0.6), at + j * 0.016)
            if b % 2 == 0: put(bass, np.sin(2 * np.pi * NOTE(ch[0] - 24) * t_(beat * 1.8)) * env(int(SR * beat * 1.8), 0.01, 0.2) * 0.2, at)
            mel = MEL[mode][b % 16]
            if mel and at > 2.5: put(mus, ks(mel + 12 if at > finale_t else mel, 0.8, 0.11), at)
        if b % 4 == 0:
            tt = t_(beat * 4.2); x = sum(np.sin(2 * np.pi * NOTE(m) * tt * (1 + dt)) for m in ch for dt in (-0.003, 0.003))
            put(pad, x * np.sin(np.pi * tt / (beat * 4.2)) ** 1.5 * (0.018 if at < finale_t else 0.03), at)
        b += 1; at += beat
    music = lp(mus[:N], 6000) * 1.5 + bass[:N] + pad[:N]
    music = music * (1 - slow_mask) + lp(music, 500) * slow_mask * 0.8
    return music * np.clip(t / 0.3, 0, 1)

def master(L, R):
    N = len(L); rng = np.random.default_rng(5)
    ir_t = t_(1.3); ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t * 4.5); ir = lp(ir, 5000); ir /= np.abs(ir).sum() ** 0.5 * 6
    mix = np.stack([L, R], 1) + np.stack([fftconvolve(L, ir)[:N], fftconvolve(R, rng.permutation(ir))[:N]], 1) * 0.35
    return np.tanh(mix / (np.abs(mix).max() + 1e-9) * 1.6) / np.tanh(1.6) * 0.89
