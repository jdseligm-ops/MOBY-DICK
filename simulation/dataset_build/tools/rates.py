#!/usr/bin/env python3
"""Expected yearly rates for the hackathon dataset weights (user decisions 2026-11-13; provenance in docs/RATES.md).

Signal: OBD 17 kt study, arXiv:2606.20780 Table III, 12.1 TNU: geo U 100.09/yr, geo Th 24.98/yr.
Reactor IBD: 67.84/yr full volume (same table); reported separately, never part of the background in the score.
(alpha,n): Po-210 activity A_Po x 5.75e-8 n per alpha (13C in LAB; docs/OBD17kt_DETECTOR_MODEL.md section 7.5)
           x 3.156e7 s/yr. A_Po = 70 Bq (Sakai et al. 1.5 kt value 5.9 Bq scaled to 17.8 kt; user decision).
Singles (accidental ingredients): rate_i = activity_i (Bq) x f_trig,i. f_trig,i = the fraction of simulated decays
           that our digitiser + trigger accept; it is measured on the production samples (build_dataset.py).
Activities, secular equilibrium (specific activities: U-238 12,445 Bq/g, Th-232 4,057 Bq/g, natural K 31.6 Bq/g):
  LS 17.8 kt (19,900 m^3 x 0.8925 t/m^3): KamLAND early phase U 3.5e-18, Th 5.2e-17 g/g (approved scope).
     K: only an upper limit exists for the early phase (< 2.7e-16 g/g). The limit is used here, which is conservative.
     ASSUMPTION, to confirm.
  Acrylic vessel ~250 t (r 12.00-12.05 m, h 44.0-44.1 m, 1.18 t/m^3): 1e-11 g/g each of U, Th, K
     (OBD thesis Table 5.4, from JUNO).
  Chain members simulated and their branching: U chain -> Pa234m, Pb214, Bi214 (as BiPo214 in the LS, Bi214 in the
     acrylic); Th chain -> Ac228, Pb212, Bi212 (BiPo212 64.06 %), Tl208 (35.94 % of Bi212 decays).
  Not simulated (documented limitation): PMT glass, glass shields, steel tank, buffer oil, seawater K-40, and the
     other U/Th-chain gamma emitters in the acrylic.
"""
import math

YEAR_S = 3.156e7
SPEC_ACT = {"U": 12445.0, "Th": 4057.0, "K": 31.6}       # Bq per g of element (U-238 / Th-232 / natural K)
M_LS_G = 19900.0 * 0.8925e6
M_ACRYLIC_G = math.pi * (12.05 ** 2 * 44.1 - 12.0 ** 2 * 44.0) * 1.18e6
CONTAM = {"ls": {"U": 3.5e-18, "Th": 5.2e-17, "K": 2.7e-16}, "acrylic": {"U": 1e-11, "Th": 1e-11, "K": 1e-11}}
PO210_BQ = 70.0
ALPHA_N_PER_ALPHA = 5.75e-8
SIGNAL_PER_YEAR = {"geoU": 100.09, "geoTh": 24.98}
REACTOR_PER_YEAR = 67.84

# sample tag -> (volume, element, branching of this chain member)
SINGLES = {
    "pa234m_ls": ("ls", "U", 1.0), "pb214_ls": ("ls", "U", 1.0), "bipo214_ls": ("ls", "U", 1.0),
    "ac228_ls": ("ls", "Th", 1.0), "pb212_ls": ("ls", "Th", 1.0), "bipo212_ls": ("ls", "Th", 0.6406), "tl208_ls": ("ls", "Th", 0.3594),
    "k40_ls": ("ls", "K", 1.0),
    "k40_acrylic": ("acrylic", "K", 1.0), "bi214_acrylic": ("acrylic", "U", 1.0), "tl208_acrylic": ("acrylic", "Th", 0.3594),
}


def activity_bq(sample):
    """Decay rate (Bq) of a simulated singles sample in its volume."""
    if sample == "po210_ls":
        return PO210_BQ
    vol, el, br = SINGLES[sample]
    mass = M_LS_G if vol == "ls" else M_ACRYLIC_G
    return mass * CONTAM[vol][el] * SPEC_ACT[el] * br


def alpha_n_per_year():
    return PO210_BQ * ALPHA_N_PER_ALPHA * YEAR_S


def table():
    rows = {s: activity_bq(s) for s in list(SINGLES) + ["po210_ls"]}
    return {"activity_bq": rows, "alpha_n_per_year": alpha_n_per_year(), "signal_per_year": SIGNAL_PER_YEAR,
            "reactor_per_year": REACTOR_PER_YEAR, "m_ls_t": M_LS_G / 1e6, "m_acrylic_t": M_ACRYLIC_G / 1e6}


if __name__ == "__main__":
    import json
    print(json.dumps(table(), indent=1))
