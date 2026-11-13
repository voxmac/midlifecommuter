"""Cuts a character out of a cast candidate (plain grey background) into a transparent PNG for assets/.
usage: python tools/make_cutout.py candidate.png assets/bibi_sad_cut.png
Uses rembg for the mask, then fills holes inside the body that rembg wrongly cleared (e.g. Tock's belly)
while keeping real gaps that show background (e.g. between Pip's legs)."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage
from rembg import remove, new_session

src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
rgba = np.array(remove(im, session=new_session("isnet-general-use")))
rgb = np.array(im).astype(np.float32)
al = rgba[..., 3].copy()

# background colour from the image border
border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
bgc = np.median(border, 0)
low = al < 128
lab, n = ndimage.label(np.pad(low, 1, constant_values=True))
outside = lab[0, 0]
lab = lab[1:-1, 1:-1]
for i in range(1, n + 1):
    if i == outside: continue
    hole = lab == i
    looks_like_bg = np.linalg.norm(rgb[hole].mean(0) - bgc) < 30          # a real see-through gap
    if not looks_like_bg: al[hole] = 255
al[ndimage.binary_erosion(al > 40, iterations=6) & (np.linalg.norm(rgb - bgc, axis=-1) > 30)] = 255
al[al < 12] = 0
out = Image.fromarray(np.dstack([np.array(im), al]).astype(np.uint8))   # original colours (rembg darkens cleared areas)
out = out.crop(out.getbbox())
out.save(dst)
print(dst, out.size)
