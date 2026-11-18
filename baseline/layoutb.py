#!/usr/bin/env python3
"""Compile digitised waveforms into Stage-1 (hit cleaner) rows, "Layout B", aligned on each pulse.

One row per pulse onset (a sample where a PMT's waveform rises above the zero-suppression threshold):
  [ own waveform, samples k-PRE .. k+POST-1 | neighbour slot 1 | ... | slot 6 | ring-2 sum (same samples) | extras ]
with PRE = 8, POST = 24 (32 samples = 128 ns, aligned on the pulse; user decision 2026-11-13).
Neighbours: the 6 nearest PMTs (3D distance), in fixed slots ordered by direction in the PMT's tangent plane.
Slot 1 is nearest to the reference direction: +z on the wall, radially outward on the caps. Then the slots go
counter-clockwise, seen from inside the detector. A neighbour without stored samples contributes zeros.
Ring 2 (layout "B2", user decision 2026-11-13): the next 12 nearest PMTs (the hexagonal second ring), summed
sample by sample into one waveform, because 76 % of hits had no lit first-ring neighbour at geoneutrino energies.
Extras: onset time relative to the window's trigger (ns), onset rank on this PMT in the window (0 = first pulse),
is_wall, z/25 m, cos(phi), sin(phi), rho/15 m.
Truth label (never an input): 1 if real light (any non-dark PE) reaches at least half the zero-suppression
threshold at the onset sample or the next one, else 0 (dark noise or electronic noise). `real_frac` gives the
real share of the noise-free amplitude at the onset.
"""
import numpy as np

import digitize as dg

PRE, POST = 8, 24
NNB = 6
NRING2 = 12
N_BLOCKS = NNB + 2            # own + 6 neighbours + ring-2 sum
LAYOUT_VERSION = "B2"
N_EXTRA = 7
EXTRA_NAMES = ["t_onset_minus_trig_ns", "onset_rank", "is_wall", "z_over_25m", "cos_phi", "sin_phi", "rho_over_15m"]


def feature_names():
    names = []
    for s in range(N_BLOCKS):
        tag = "own" if s == 0 else ("ring2" if s == NNB + 1 else f"nb{s}")
        names += [f"{tag}_s{j - PRE:+d}" for j in range(PRE + POST)]
    return names + EXTRA_NAMES


def neighbour_table(px, py, pz, pu, pv, pw, k=NNB):
    """(n_pmt, k) first-ring ids ordered by direction (see module doc), wall flag, (n_pmt, NRING2) ring-2 ids."""
    from scipy.spatial import cKDTree
    P = np.column_stack([px, py, pz]).astype(np.float64)
    N = np.column_stack([pu, pv, pw]).astype(np.float64)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    _, idx = cKDTree(P).query(P, k=k + NRING2 + 1)
    nb = idx[:, 1:k + 1]
    ring2 = idx[:, k + 1:].astype(np.int32)
    wall = np.abs(N[:, 2]) < 0.5
    rho = np.hypot(P[:, 0], P[:, 1])
    ref = np.where(wall[:, None], np.array([0.0, 0.0, 1.0]),
                   np.column_stack([np.where(rho > 1, P[:, 0] / np.maximum(rho, 1), 1.0),
                                    np.where(rho > 1, P[:, 1] / np.maximum(rho, 1), 0.0), np.zeros(len(P))]))
    e1 = ref - (ref * N).sum(1, keepdims=True) * N
    e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
    e2 = np.cross(N, e1)
    d = P[nb] - P[:, None, :]
    ang = np.arctan2((d * e2[:, None, :]).sum(2), (d * e1[:, None, :]).sum(2))
    ang = np.mod(ang + np.pi / NNB, 2 * np.pi)            # slot 1 = within +-30 deg of the reference direction
    order = np.argsort(ang, axis=1, kind="stable")
    return np.take_along_axis(nb, order, axis=1).astype(np.int32), wall, ring2


def _pulse_sum(rows, t_local, gain, n_rows, cfg):
    """Noise-free waveform sum (n_rows, NS) of the given PEs (window-local times, ns)."""
    S, NS = cfg.sample_ns, cfg.n_samples
    L = int(np.ceil(cfg.pulse_len_ns / S)) + 1
    A = np.zeros((n_rows, NS))
    if len(rows) == 0:
        return A
    k = np.ceil(t_local / S).astype(np.int64)[:, None] + np.arange(L)[None, :]
    val = gain[:, None] * cfg.adc_per_pe * dg.pulse_shape(k * S - t_local[:, None], cfg)
    ok = (k >= 0) & (k < NS)
    np.add.at(A, (np.broadcast_to(rows[:, None], k.shape)[ok], k[ok]), val[ok])
    return A


def compile_rows(res, nbt, wall, geo_xyz, cfg, with_truth=True, ring2=None, meta=None):
    """Rows for every pulse onset in every window of one digitised example (ring2=None: layout B, no ring-2 block).
    Returns X (n, N_BLOCKS*32 + 7) float32, y (n,) int8 or None, real_frac (n,) float32 or None, win (n,) int8."""
    S, NS = cfg.sample_ns, cfg.n_samples
    n_pmt = len(nbt)
    px, py, pz = geo_xyz
    W = PRE + POST
    Xs, ys, fs, ws = [], [], [], []
    for w in range(len(res["win_start"])):
        m = np.flatnonzero(res["seg_win"] == w)
        if len(m) == 0:
            continue
        lit, row = np.unique(res["seg_pmt"][m], return_inverse=True)
        D = np.zeros((len(lit) + 1, NS + W), np.float32)            # +1 zero row for unlit; PRE/POST padding
        for seg, r in zip(m, row):
            a, o = int(res["seg_start"][seg]), int(res["seg_off"][seg])
            ln = int(res["seg_len"][seg])
            D[r, PRE + a:PRE + a + ln] = res["samples"][o:o + ln]
        above = D[:-1, PRE:PRE + NS] > cfg.zs_threshold_adc
        up = above & ~np.concatenate([np.zeros((len(lit), 1), bool), above[:, :-1]], axis=1)
        r_on, k_on = np.nonzero(up)
        if len(r_on) == 0:
            continue
        rank = np.zeros(len(r_on), np.int64)                        # onset rank on its PMT (np.nonzero is row-major)
        if len(r_on) > 1:
            same = np.concatenate([[False], r_on[1:] == r_on[:-1]])
            grp = np.cumsum(~same) - 1
            first = np.flatnonzero(~same)
            rank = np.arange(len(r_on)) - first[grp]
        pmt_row = np.full(n_pmt, len(lit), np.int64)                # unlit -> zero row
        pmt_row[lit] = np.arange(len(lit))
        rows7 = np.column_stack([r_on, pmt_row[nbt[lit[r_on]]]])    # (n_on, 7)
        cols = k_on[:, None] + np.arange(W)[None, :]                # padded coordinates: sample k-PRE .. k+POST-1
        wave = D[rows7[:, :, None], cols[:, None, :]].reshape(len(r_on), -1)
        if ring2 is not None:
            rows12 = pmt_row[ring2[lit[r_on]]]                                 # (n_on, 12)
            r2 = D[rows12[:, :, None], cols[:, None, :]].sum(axis=1)            # (n_on, 32) summed ring-2 waveform
            wave = np.hstack([wave, r2])
        p = lit[r_on]
        rho = np.hypot(px[p], py[p])
        phi = np.arctan2(py[p], px[p])
        extra = np.column_stack([(k_on - int(res["win_trig"][w])) * S, rank, wall[p].astype(float),
                                 pz[p] / 25000.0, np.cos(phi), np.sin(phi), rho / 15000.0])
        Xs.append(np.hstack([wave, extra]).astype(np.float32))
        ws.append(np.full(len(r_on), w, np.int8))
        if meta is not None:                    # caller-supplied dict: per-row PMT id and onset sample
            meta.setdefault("pmt", []).append(p.astype(np.int64)); meta.setdefault("k_on", []).append(k_on.astype(np.int64))
        if with_truth:
            sel = np.flatnonzero(np.isin(res["pe_pmt"], lit) & (res["pe_t"] >= res["win_start"][w] * S - cfg.pulse_len_ns)
                                 & (res["pe_t"] < (res["win_start"][w] + NS) * S))
            t_loc = res["pe_t"][sel].astype(np.float64) - res["win_start"][w] * S
            rr = pmt_row[res["pe_pmt"][sel].astype(np.int64)]
            real = res["pe_label"][sel] > 0
            A_real = _pulse_sum(rr[real], t_loc[real], res["pe_gain"][sel][real], len(lit), cfg)
            A_dark = _pulse_sum(rr[~real], t_loc[~real], res["pe_gain"][sel][~real], len(lit), cfg)
            k2 = np.minimum(k_on + 1, NS - 1)
            a_real = np.maximum(A_real[r_on, k_on], A_real[r_on, k2])
            a_dark = np.maximum(A_dark[r_on, k_on], A_dark[r_on, k2])
            ys.append((a_real >= 0.5 * cfg.zs_threshold_adc).astype(np.int8))
            fs.append((a_real / np.maximum(a_real + a_dark, 1e-9)).astype(np.float32))
            if meta is not None:                # dominant real source of the pulse: 1 (prompt/A) or 2 (delayed/B)
                l2 = real & (res["pe_label"][sel] == 2)
                A2 = _pulse_sum(rr[l2], t_loc[l2], res["pe_gain"][sel][l2], len(lit), cfg)
                a2 = np.maximum(A2[r_on, k_on], A2[r_on, k2])
                meta.setdefault("src", []).append(np.where(a2 > 0.5 * a_real, 2, 1).astype(np.int8))
    if not Xs:
        nb_ = N_BLOCKS if ring2 is not None else NNB + 1
        return np.zeros((0, nb_ * W + N_EXTRA), np.float32), None, None, np.zeros(0, np.int8)
    X = np.vstack(Xs)
    return X, (np.concatenate(ys) if with_truth else None), (np.concatenate(fs) if with_truth else None), np.concatenate(ws)
