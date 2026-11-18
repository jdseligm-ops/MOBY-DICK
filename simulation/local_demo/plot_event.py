#!/usr/bin/env python3
"""Draw the OBD 17 kt detector and one simulated IBD from dump_event.py output (host python: numpy + matplotlib).
  geometry.png        3-D cut-away of the tank, buffer, acrylic vessel / LS target and the 12,505 inner PMTs + r-z section
  event_3d.png        the IBD: e+ vertex, neutron capture, optical photons that end on a PMT and produced a photo-electron
                      (prompt e+ light vs delayed 6Li-capture light), hit PMTs sized by #PE
  event_pmt_map.png   unrolled PMT hit map (wall phi-z + both caps), coloured by first hit time
usage: plot_event.py event_dump.npz outdir
Dimensions (mm) from ratdb/OBD17kt/OBD17kt.geo: SS tank r 15016 / half-h 25016; buffer (K-290) r 14999 / 24999;
acrylic vessel r 12050 / 22050; LS r 12000 / 22000; PMT array on the tank wall and caps.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

d = np.load(sys.argv[1]); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
M = 1e-3                                                      # mm -> m
px, py, pz = d["pmt_x"] * M, d["pmt_y"] * M, d["pmt_z"] * M
TANK, BUF, AV, LS = (15.016, 25.016), (14.999, 24.999), (12.05, 22.05), (12.0, 22.0)


def cyl(ax, r, h, color, alpha, n=60, half=True, lw=0.4):
    th = np.linspace(0 if not half else np.pi * 0.5, 2 * np.pi if not half else np.pi * 2.0 - 0.0, n)
    th = np.linspace(np.pi / 2, 2 * np.pi, n) if half else np.linspace(0, 2 * np.pi, n)
    for zz in (-h, h):
        ax.plot(r * np.cos(th), r * np.sin(th), zz, color=color, lw=lw, alpha=alpha)
    for a in th[::6]:
        ax.plot([r * np.cos(a)] * 2, [r * np.sin(a)] * 2, [-h, h], color=color, lw=lw * 0.7, alpha=alpha * 0.7)


def style(ax, title):
    ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]"); ax.set_zlabel("z [m]")
    ax.set_xlim(-16, 16); ax.set_ylim(-16, 16); ax.set_zlim(-26, 26)
    ax.set_box_aspect((32, 32, 52)); ax.set_title(title, fontsize=11)
    ax.view_init(elev=14, azim=-58)


# ---------------------------------------------------------------- geometry
fig = plt.figure(figsize=(13, 9))
ax = fig.add_subplot(1, 2, 1, projection="3d")
cut = ~((px > 0) & (py < 0))                                  # remove one quadrant so the inside is visible
ax.scatter(px[cut], py[cut], pz[cut], s=1.2, c="#3b6ea5", alpha=0.7, linewidths=0, label="12,505 × 20″ PMTs (glass shields)")
cyl(ax, TANK[0], TANK[1], "0.25", 0.6, half=True)
cyl(ax, AV[0], AV[1], "#d9822b", 0.9, half=True, lw=0.8)
ax.plot([], [], color="0.25", label="stainless-steel tank (r 15 m, h 50 m), K-290 buffer oil inside")
ax.plot([], [], color="#d9822b", label="acrylic vessel + ⁶Li-loaded LAB/PPO (r 12 m, h 44 m, ≈17.8 kt)")
style(ax, "OBD 17 kt detector model (ratpac-two 4.4.0)")
ax.legend(loc="upper left", fontsize=8, frameon=False)
ax2 = fig.add_subplot(1, 2, 2)
for (r, h), c, lab in ((TANK, "0.25", "SS tank / black liner"), (BUF, "0.6", "K-290 buffer oil"), (AV, "#d9822b", "acrylic vessel"), (LS, "#f2c14e", "Li-6 LS target")):
    ax2.add_patch(plt.Rectangle((-r, -h), 2 * r, 2 * h, fill=(c == "#f2c14e"), alpha=0.35 if c == "#f2c14e" else 1, ec=c, fc=c if c == "#f2c14e" else "none", lw=1.2, label=lab))
rho = np.hypot(px, py)
sel = np.abs(np.arctan2(py, px)) < 0.03                     # PMTs near the x-z plane
ax2.scatter(np.where(px[sel] >= 0, rho[sel], -rho[sel]), pz[sel], s=6, c="#3b6ea5", label="PMTs (slice near the x–z plane)")
capsel = (np.abs(pz) > 24) & (np.abs(py) < 0.4)
ax2.scatter(px[capsel], pz[capsel], s=6, c="#3b6ea5")
ax2.set_aspect("equal"); ax2.set_xlim(-17, 17); ax2.set_ylim(-27, 27)
ax2.set_xlabel("x [m]"); ax2.set_ylabel("z [m]"); ax2.set_title("r–z section", fontsize=11)
ax2.annotate("", xy=(12, -23.5), xytext=(-12, -23.5), arrowprops=dict(arrowstyle="<->", lw=0.8)); ax2.text(0, -23.2, "24 m", ha="center", fontsize=8)
ax2.annotate("", xy=(13.3, 22), xytext=(13.3, -22), arrowprops=dict(arrowstyle="<->", lw=0.8)); ax2.text(13.6, 0, "44 m", rotation=90, va="center", fontsize=8)
ax2.legend(loc="center", fontsize=8, frameon=True, framealpha=0.9)
fig.tight_layout(); fig.savefig(os.path.join(out, "geometry.png"), dpi=160); plt.close(fig)

# ---------------------------------------------------------------- the event
pdg, off = d["trk_pdg"], d["trk_off"]; X, Y, Z, T = d["trk_x"] * M, d["trk_y"] * M, d["trk_z"] * M, d["trk_t"]
endv = d["trk_end_volume"].astype(str)
opt = (pdg == 0) | (pdg == -22)
on_pmt = opt & np.char.startswith(endv, "inner_pmts")
ends = off[1:] - 1
P = np.column_stack([px, py, pz])
E = np.column_stack([X[ends], Y[ends], Z[ends]])
idx_on = np.flatnonzero(on_pmt)
near = np.array([np.argmin(((P - E[i]) ** 2).sum(1)) for i in idx_on]) if len(idx_on) else np.array([], int)
pe_pmt, pe_t = d["pe_pmt"].astype(int), d["pe_t"]
detected = np.zeros(len(pdg), bool)
for i, j in zip(idx_on, near):                                # a photon "made a PE": same PMT, hit time within 1 ns
    m = pe_pmt == j
    if m.any() and np.min(np.abs(pe_t[m] - T[ends[i]])) < 1.0:
        detected[i] = True
vtx = d["vtx"] * M
t_split = 500.0                                               # ns: prompt e+ light vs delayed capture light
fig = plt.figure(figsize=(11, 11))
ax = fig.add_subplot(projection="3d")
cyl(ax, AV[0], AV[1], "#d9822b", 0.35, half=False, lw=0.6)
cyl(ax, TANK[0], TANK[1], "0.4", 0.25, half=False, lw=0.5)
ax.scatter(px, py, pz, s=0.15, c="0.75", alpha=0.25, linewidths=0)
n_pr = n_de = 0
for i in np.flatnonzero(detected):
    s = slice(off[i], off[i + 1])
    late = T[off[i]] > t_split
    ax.plot(X[s], Y[s], Z[s], color="#2b6cb0" if late else "#e4572e", lw=0.35, alpha=0.55)
    n_de += late; n_pr += (not late)
hit, cnt = np.unique(pe_pmt, return_counts=True)
ax.scatter(px[hit], py[hit], pz[hit], s=4 + 6 * cnt, c="#111111", alpha=0.8, linewidths=0)
cap_i = [i for i in range(len(pdg)) if pdg[i] in (1000020040, 1000010030)]
cap = np.array([X[off[cap_i[0]]], Y[off[cap_i[0]]], Z[off[cap_i[0]]]]) if cap_i else vtx
ax.scatter(*vtx, s=120, marker="*", c="#e4572e", edgecolors="k", zorder=5)
ax.scatter(*cap, s=60, marker="o", c="#2b6cb0", edgecolors="k", zorder=5)
ax.plot([], [], color="#e4572e", label=f"prompt e⁺ photons that produced a PE ({n_pr})")
ax.plot([], [], color="#2b6cb0", label=f"delayed ⁶Li(n,α)t photons that produced a PE ({n_de})")
ax.scatter([], [], s=30, c="#111111", label=f"hit PMTs ({len(hit)}; marker ∝ #PE; {len(pe_pmt)} PE total)")
ax.scatter([], [], s=80, marker="*", c="#e4572e", edgecolors="k", label="IBD vertex")
ax.scatter([], [], s=40, marker="o", c="#2b6cb0", edgecolors="k", label="neutron capture on ⁶Li")
style(ax, f"One simulated geo-U IBD in OBD 17 kt (ratpac-two; {int(opt.sum()):,} optical photons tracked)")
ax.legend(loc="upper left", fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(out, "event_3d.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- unrolled PMT map
first = {}
for j, t in zip(pe_pmt, pe_t):
    first[j] = min(first.get(j, np.inf), t)
fig, axs = plt.subplots(1, 3, figsize=(16, 6), gridspec_kw={"width_ratios": [1, 2.6, 1]})
wall = np.abs(d["pmt_w"]) < 0.5
phi = np.angle(np.exp(1j * (np.arctan2(py, px) - np.arctan2(vtx[1], vtx[0]))))      # centred on the vertex azimuth
for a, sel_, title, xy in ((axs[0], (~wall) & (pz > 0), "top cap", (px, py)), (axs[1], wall, "wall (unrolled, centred on the vertex azimuth)", (phi * 14.63, pz)),
                           (axs[2], (~wall) & (pz < 0), "bottom cap", (px, py))):
    a.scatter(xy[0][sel_], xy[1][sel_], s=1.5, c="0.85", linewidths=0)
    hs = np.array([j for j in first if sel_[j]], int)
    if len(hs):
        sc = a.scatter(xy[0][hs], xy[1][hs], s=10, c=[first[j] for j in hs], cmap="plasma", vmin=0, vmax=max(pe_t.max(), 1), linewidths=0)
    a.set_aspect("equal"); a.set_title(title, fontsize=10); a.set_xlabel("m")
fig.colorbar(sc, ax=axs, shrink=0.8, label="first PE time [ns] (delayed flash = ⁶Li capture)")
fig.suptitle(f"PMT hits for the same event: {len(hit)} PMTs, {len(pe_pmt)} PE", fontsize=11)
fig.savefig(os.path.join(out, "event_pmt_map.png"), dpi=150, bbox_inches="tight"); plt.close(fig)
print({"optical_photons": int(opt.sum()), "photons_ending_on_pmts": int(on_pmt.sum()), "photons_matched_to_PE": int(detected.sum()),
       "PE": int(len(pe_pmt)), "hit_pmts": int(len(hit)), "prompt": n_pr, "delayed": n_de,
       "vertex_m": [round(float(v), 2) for v in vtx], "capture_m": [round(float(v), 2) for v in cap]})
