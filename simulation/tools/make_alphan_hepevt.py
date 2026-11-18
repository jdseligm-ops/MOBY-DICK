#!/usr/bin/env python3
"""Pre-sample 13C(alpha,n)16O final states from 210Po alphas in the LAB scintillator, as a HEPEVT ascii file for
ratpac's HEPEvt vertex generator (macros/alphan_hepevt.mac).  OBD17kt_geo variant, 2026-11-13.

Physics recipe (KamLAND PRL 100, 221803 (2008), arXiv:0801.4589; Zhao et al., Chin. Phys. C 38 (2014),
arXiv:1312.6347, Sec. 3; Sakai thesis Eqs. 6.8-6.12):
  1. final state: 16O ground state, or the excited states 6.049 MeV (0+, decays by e+e- internal pair, E0) and
     6.130 MeV (3-, decays by a 6.130 MeV gamma).  The excited-state share of the neutron yield is 8.5 %
     (Zhao Table 1: 4.90e-9 of 5.75e-8 n/alpha).  The split between the two excited states is a PROXY: KamLAND's
     detected counts (Table I: e+e- 15.2, gamma 3.5 events) -> 81 % / 19 %.
  2. alpha energy at the reaction, E_a in [E_threshold(state), 5.304 MeV], drawn from the thick-target weight
     sigma(E_a) / S(E_a).  PROXY (no evaluated cross-section table is used): sigma ~ exp(-2 pi eta) / E_cm (Gamow
     factor with a constant astrophysical S-factor; Harissopulos et al. PRC 72, 062801 resonances are NOT modelled),
     and the alpha stopping power S ~ E^-0.6 (power law through ASTAR polystyrene values, ~1300 and ~720
     MeV cm2/g at 2 and 5.3 MeV; a LAB-specific table would replace it).
  3. two-body relativistic kinematics alpha + 13C(rest) -> n + 16O(*), with an ISOTROPIC centre-of-mass angle
     (PROXY; measured Legendre angular distributions, e.g. Walton 1957, are not used) and an isotropic alpha
     direction.
  4. particles written per event: neutron, 16O recoil (heavily quenched), the alpha's pre-reaction energy loss
     (5.304 - E_a) as a short alpha track from the same point (the light the alpha made before reacting), and the
     de-excitation: 6.130 MeV gamma, or an e+e- pair sharing 6.049 - 1.022 MeV uniformly with independent isotropic
     directions (PROXY for the E0 pair correlation).
  The neutron is then transported by Geant4 (proton recoils are Birks-quenched by the scintillation model, 12C(n,n')
  4.4 MeV gammas arise naturally) and captures -> the delayed signal.

Output: <out>.hepevt (ascii, momenta in GeV) and <out>.truth.csv (one row per event, same order as ratpac evid:
state, E_alpha at reaction, neutron KE, gamma/pair energy).  Deterministic for a given --seed (numpy default_rng),
so the chunk seed fully determines the file; the job records its sha256.
usage: make_alphan_hepevt.py --seed S --n N -o OUTBASE
"""
import argparse
import hashlib
import math

import numpy as np

U = 931.49410242          # MeV
ME = 0.51099895
M_N = 939.56542052
M_A = 4.00260325413 * U - 2 * ME          # nuclear masses from atomic masses (AME2020)
M_C13 = 13.00335483507 * U - 6 * ME
M_O16 = 15.99491461957 * U - 8 * ME
E_PO210 = 5.304           # MeV, 210Po alpha
STATES = [("gs", 0.0, 0.915), ("0+_6049", 6.049, 0.085 * 15.2 / 18.7), ("3-_6130", 6.130, 0.085 * 3.5 / 18.7)]
PDG = {"n": 2112, "O16": 9808016, "alpha": 9802004, "gamma": 22, "e-": 11, "e+": -11}   # ions: GLG4 98zzaaa codes
MASS = {"n": M_N, "O16": M_O16, "alpha": M_A, "gamma": 0.0, "e-": ME, "e+": ME}


def threshold(ex):
    """lab alpha kinetic energy threshold for 13C(a,n)16O*(ex)."""
    mf = M_N + M_O16 + ex
    s_thr = mf * mf
    ea = (s_thr - M_A ** 2 - M_C13 ** 2) / (2 * M_C13)
    return max(ea - M_A, 0.0)


def weight(ea):
    """thick-target proxy weight sigma(E)/S(E) (see module docstring)."""
    mu = 4.0026 * 13.0034 / (4.0026 + 13.0034)
    ecm_kev = ea * 1000 * M_C13 / (M_C13 + M_A)
    two_pi_eta = 31.29 * 2 * 6 * math.sqrt(mu / ecm_kev)
    return math.exp(-two_pi_eta) / ecm_kev * ea ** 0.6


def iso(rng, n=None):
    c = rng.uniform(-1, 1, n)
    ph = rng.uniform(0, 2 * math.pi, n)
    s = np.sqrt(1 - c * c)
    return np.stack([s * np.cos(ph), s * np.sin(ph), c], axis=-1)


def two_body(ta, ex, ua, cos_cm, phi_cm):
    """alpha (KE ta, unit dir ua) on 13C at rest -> n + 16O*(ex). returns lab momenta (MeV/c) of n and O."""
    ea = ta + M_A
    pa = math.sqrt(ea * ea - M_A * M_A)
    s = M_A ** 2 + M_C13 ** 2 + 2 * M_C13 * ea
    rs = math.sqrt(s)
    mo = M_O16 + ex
    pst = math.sqrt((s - (M_N + mo) ** 2) * (s - (M_N - mo) ** 2)) / (2 * rs)
    en_st = math.sqrt(pst * pst + M_N * M_N)
    beta = pa / (ea + M_C13)
    gam = 1 / math.sqrt(1 - beta * beta)
    sin_cm = math.sqrt(1 - cos_cm * cos_cm)
    p_par = gam * (pst * cos_cm + beta * en_st)            # along the alpha direction
    p_perp = pst * sin_cm
    # orthonormal basis around ua
    a = np.array([1.0, 0, 0]) if abs(ua[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(ua, a); e1 /= np.linalg.norm(e1)
    e2 = np.cross(ua, e1)
    pn = p_par * ua + p_perp * (math.cos(phi_cm) * e1 + math.sin(phi_cm) * e2)
    po = pa * ua - pn
    return pn, po


def ke(p, m):
    return math.sqrt(float(p @ p) + m * m) - m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("-o", "--out", required=True, help="output base name (writes .hepevt and .truth.csv)")
    a = ap.parse_args()
    rng = np.random.default_rng([20261113, a.seed])
    probs = np.array([p for _, _, p in STATES]); probs /= probs.sum()
    grids = {}
    for name, ex, _ in STATES:
        lo = threshold(ex) + 1e-4
        g = np.linspace(lo, E_PO210, 4000)
        w = np.array([weight(x) for x in g])
        cdf = np.cumsum(w); cdf /= cdf[-1]
        grids[name] = (g, cdf)
    lines, truth = [], ["evid,state,E_alpha_MeV,n_KE_MeV,O16_KE_MeV,alpha_pre_KE_MeV,deexc_MeV"]
    for ev in range(a.n):
        k = rng.choice(len(STATES), p=probs)
        name, ex, _ = STATES[k]
        g, cdf = grids[name]
        e_a = float(np.interp(rng.uniform(), cdf, g))
        ua = iso(rng)
        pn, po = two_body(e_a, ex, ua, rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi))
        parts = [("n", pn), ("O16", po)]
        t_pre = E_PO210 - e_a
        if t_pre > 1e-4:
            parts.append(("alpha", iso(rng) * math.sqrt(t_pre * (t_pre + 2 * M_A))))
        if name == "3-_6130":
            parts.append(("gamma", iso(rng) * 6.130))
        elif name == "0+_6049":
            tk = 6.049 - 2 * ME
            f = rng.uniform()
            for pname, t in (("e+", f * tk), ("e-", (1 - f) * tk)):
                parts.append((pname, iso(rng) * math.sqrt(t * (t + 2 * ME))))
        lines.append(f"{ev} {len(parts)}")
        for pname, p in parts:
            m = MASS[pname]
            e = math.sqrt(float(p @ p) + m * m)
            lines.append("1 {} 0 0 0 0 {:.9e} {:.9e} {:.9e} {:.9e} {:.9e}".format(
                PDG[pname], p[0] / 1e3, p[1] / 1e3, p[2] / 1e3, e / 1e3, m / 1e3))
        truth.append(f"{ev},{name},{e_a:.6f},{ke(pn, M_N):.6f},{ke(po, M_O16):.6f},{max(t_pre, 0):.6f},{ex:.3f}")
    with open(a.out + ".hepevt", "w") as f:
        f.write("# 13C(alpha,n)16O from 210Po, tools/make_alphan_hepevt.py seed {}\n".format(a.seed))
        f.write("\n".join(lines) + "\n")
    with open(a.out + ".truth.csv", "w") as f:
        f.write("\n".join(truth) + "\n")
    h = hashlib.sha256(open(a.out + ".hepevt", "rb").read()).hexdigest()
    print(f"{a.out}.hepevt events={a.n} sha256={h}")


if __name__ == "__main__":
    main()
