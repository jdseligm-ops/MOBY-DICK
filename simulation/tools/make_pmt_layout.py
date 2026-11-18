#!/usr/bin/env python3
"""Generate the inner-detector PMT layout for the OBD 17 kt model as a ratpac-two PMTINFO table.

Design inputs (OHN24 = T. Ohno, Tohoku M.S. thesis 2024, Table 5.1 p.44 and §4.2 p.32-33):
  - 12,505 20-inch PMTs, each inside a spherical glass shield (inner r 350 mm, outer r 360 mm).
  - Mounted on the stainless-steel tank inner wall; tank inner r = 15 m, inner height = 50 m.
  The thesis gives no coordinates (GAP 1 in OBD_geometry_sourced.md), so this script builds one:
  - side wall: n_rows x n_phi staggered rings (hexagonal-like packing, rows offset by half a pitch);
  - top/bottom caps: identical hexagonal lattices clipped to a disc, trimmed to an exact count.
  12,505 shields of 72 cm diameter cover ~88% of the available surface, so the packing has to be
  near-hexagonal; the script asserts that no two shields overlap.

Output: PMTINFO ratdb (mm), PMT fronts facing inward (side wall: -r_hat; caps: -/+z).
"""
import argparse
import json
import math
import sys

import numpy as np

N_TOTAL = 12505
SHIELD_R = 360.0        # mm, glass shield outer radius (OHN24 Table 5.1)
LINER_R = 14999.0       # mm, inner radius of the buffer volume (1 mm black liner inside the 15 m tank)
LINER_HZ = 24999.0      # mm, half-height of the buffer volume
CLEAR = 9.0             # mm, gap between shield and liner
R_PMT = LINER_R - SHIELD_R - CLEAR      # 14630 mm, radius of side-wall PMT centres
Z_CAP = LINER_HZ - SHIELD_R - CLEAR     # 24630 mm, |z| of cap PMT centres
MIN_SEP = 2 * SHIELD_R + 2.0            # mm, required centre-to-centre distance (2 mm margin)


def side_wall(n_rows, n_phi):
    zs = np.linspace(-Z_CAP, Z_CAP, n_rows)
    pts = []
    for i, z in enumerate(zs):
        off = 0.5 if i % 2 else 0.0
        phi = 2 * math.pi * (np.arange(n_phi) + off) / n_phi
        pts.append(np.column_stack([R_PMT * np.cos(phi), R_PMT * np.sin(phi), np.full(n_phi, z)]))
    return np.vstack(pts)


def cap_lattice(pitch, rho_max, n_target):
    """Hexagonal lattice centred on the axis, clipped to rho <= rho_max, trimmed to n_target by
    dropping the outermost points (ties broken by azimuth so the trim is deterministic)."""
    k = int(rho_max / pitch) + 2
    ii, jj = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1))
    x = pitch * (ii + 0.5 * jj)
    y = pitch * (math.sqrt(3) / 2) * jj
    xy = np.column_stack([x.ravel(), y.ravel()])
    rho = np.hypot(xy[:, 0], xy[:, 1])
    keep = rho <= rho_max
    xy, rho = xy[keep], rho[keep]
    if len(xy) < n_target:
        return None
    order = np.lexsort((np.arctan2(xy[:, 1], xy[:, 0]), rho))
    return xy[order[:n_target]]


def min_pair_distance(p):
    from scipy.spatial import cKDTree
    d, _ = cKDTree(p).query(p, k=2)
    return d[:, 1].min()


def build(n_rows, n_phi, cap_pitch):
    wall = side_wall(n_rows, n_phi)
    n_cap = (N_TOTAL - len(wall)) // 2
    if len(wall) + 2 * n_cap != N_TOTAL or n_cap <= 0:
        return None
    # caps must stay MIN_SEP away from the top/bottom wall row (which sits at the same |z|)
    cap = cap_lattice(cap_pitch, R_PMT - MIN_SEP, n_cap)
    if cap is None:
        return None
    top = np.column_stack([cap, np.full(len(cap), Z_CAP)])
    bot = np.column_stack([cap, np.full(len(cap), -Z_CAP)])
    pos = np.vstack([wall, top, bot])
    region = np.array([0] * len(wall) + [1] * len(top) + [2] * len(bot))
    return pos, region


def search():
    """Pick the most uniform layout: maximise the smallest nearest-neighbour distance."""
    best = None
    for n_phi in range(115, 131):
        s_arc = 2 * R_PMT * math.sin(math.pi / n_phi)
        if s_arc < MIN_SEP:
            continue
        for n_rows in range(60, 90):
            dz = 2 * Z_CAP / (n_rows - 1)
            if math.hypot(s_arc / 2, dz) < MIN_SEP:
                continue
            n_wall = n_rows * n_phi
            if (N_TOTAL - n_wall) % 2:
                continue
            n_cap = (N_TOTAL - n_wall) // 2
            rho_max = R_PMT - MIN_SEP
            # largest hex pitch that still fits n_cap points in the disc (scan downward)
            for pitch in np.arange(900.0, MIN_SEP - 1e-9, -2.0):
                if cap_lattice(pitch, rho_max, n_cap) is not None:
                    break
            else:
                continue
            wall_nn = min(s_arc, math.hypot(s_arc / 2, dz))
            score = min(wall_nn, pitch)
            if best is None or score > best[0]:
                best = (score, n_rows, n_phi, pitch)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True, help="output PMTINFO .ratdb path")
    ap.add_argument("--summary", help="optional JSON summary path")
    a = ap.parse_args()

    score, n_rows, n_phi, pitch = search()
    pos, region = build(n_rows, n_phi, pitch)
    assert len(pos) == N_TOTAL, len(pos)
    dmin = min_pair_distance(pos)
    assert dmin >= MIN_SEP, f"shield overlap: min centre distance {dmin:.1f} mm < {MIN_SEP} mm"
    rho = np.hypot(pos[:, 0], pos[:, 1])
    assert rho.max() <= LINER_R - SHIELD_R and np.abs(pos[:, 2]).max() <= LINER_HZ - SHIELD_R

    # PMT axis (direction the photocathode faces): side wall -> axis, caps -> detector midplane
    d = np.zeros_like(pos)
    w = region == 0
    d[w, 0], d[w, 1] = -pos[w, 0] / rho[w], -pos[w, 1] / rho[w]
    d[region == 1, 2] = -1.0
    d[region == 2, 2] = 1.0

    cov_shield = N_TOTAL * math.pi * SHIELD_R**2
    surf = 2 * math.pi * R_PMT * 2 * Z_CAP + 2 * math.pi * R_PMT**2
    summary = {
        "n_total": int(N_TOTAL), "n_wall": int(w.sum()), "n_top": int((region == 1).sum()),
        "n_bottom": int((region == 2).sum()), "wall_rows": n_rows, "wall_per_row": n_phi,
        "wall_arc_pitch_mm": round(2 * R_PMT * math.sin(math.pi / n_phi), 1),
        "wall_row_spacing_mm": round(2 * Z_CAP / (n_rows - 1), 1), "cap_hex_pitch_mm": round(float(pitch), 1),
        "min_centre_distance_mm": round(float(dmin), 1), "r_pmt_mm": R_PMT, "z_cap_mm": Z_CAP,
        "shield_area_over_mount_surface": round(cov_shield / surf, 3),
        "photocathode_coverage_phi460_at_r_pmt": round(N_TOTAL * math.pi * 230.0**2 / surf, 3),
    }

    def arr(v, fmt="{:.1f}"):
        return "[" + ", ".join(fmt.format(x) for x in v) + "]"

    with open(a.out, "w") as f:
        f.write("// Generated by tools/make_pmt_layout.py - do not edit by hand.\n")
        f.write("// " + json.dumps(summary) + "\n")
        f.write("{\n\"name\": \"PMTINFO_OBD17kt\",\n\"run_range\": [0, 0],\n")
        for k, col in (("x", 0), ("y", 1), ("z", 2)):
            f.write(f"\"{k}\": {arr(pos[:, col])},\n")
        for k, col in (("dir_x", 0), ("dir_y", 1), ("dir_z", 2)):
            f.write(f"\"dir_{k[-1]}\": {arr(d[:, col], '{:.6f}')},\n")
        f.write(f"\"type\": {arr([1] * N_TOTAL, '{:d}')},\n")
        f.write("}\n")
    if a.summary:
        with open(a.summary, "w") as f:
            json.dump(summary, f, indent=1)
    json.dump(summary, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
