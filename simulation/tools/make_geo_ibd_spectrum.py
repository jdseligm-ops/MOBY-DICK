#!/usr/bin/env python3
"""Build ratpac-two IBD spectrum tables for 238U-chain and 232Th-chain geoneutrinos (OBD17kt_geo variant).

Source spectra: S. Enomoto, antineutrino spectra of the full 238U and 232Th decay chains, generated with DONGURI
v1.0.1 from the Table of Isotopes 1996 (all branches > 0.01 %, Fermi function; normalised per decay of the
chain-head nucleus; 1 keV bins, bin centres 0.5-4500.5 keV, units keV and 1/keV).
  https://www.awa.tohoku.ac.jp/~sanshiro/research/geoneutrino/spectrum/
  Cite: S. Enomoto, PhD thesis (Tohoku 2005); S. Enomoto et al., EPSL 258, 147 (2007).
No licence or terms of use are stated for these files, so they are NOT redistributed: this tool fetches them (or
reads a local cache), verifies the pinned sha256, and writes the derived ratpac table, which is .gitignored and
regenerated on demand. The table's sha256 is recorded in the run's code manifest like every other ratdb file.

ratpac semantics (src/gen/src/IBDgen.cc, tag 4.4.0): with "apply_xs": 1, spec_flux is the antineutrino FLUX and
the generator applies its own first-order Vogel-Beacom dsigma/dcos(theta) by rejection sampling, exactly as for the
reactor "default" table. ("apply_xs": 0 would mean spec_flux is already flux x sigma, and then the angle is drawn
from dE1/dcos only, which is not the physical angular distribution, so we do not use it.) emin/emax bound the
uniform energy proposal; spec_e/spec_flux are linearly interpolated. Normalisation is irrelevant (rejection).

Output: <out>/IBD_GEO.ratdb with indices geo_U238 and geo_Th232. Run with --check to print sanity numbers:
the fraction of each chain's antineutrinos above the IBD threshold and the IBD-weighted Th/U signal ratio for a
Th/U mass ratio of 3.9, to compare with R_s = 0.27 (Borexino PRD 101, 012009 (2020), Eq. 18).
usage: make_geo_ibd_spectrum.py [--cache DIR] [--out ratdb/OBD17kt] [--check]
"""
import argparse
import hashlib
import math
import os
import sys
import urllib.request

BASE_URL = "https://www.awa.tohoku.ac.jp/~sanshiro/research/geoneutrino/spectrum/"
FILES = {  # index -> (remote file name, pinned sha256, cache aliases)
    "geo_U238": ("AntineutrinoSpectrum_238U.knt",
                 "e31894af4a8a89454da783d8a05c69f65d0683e9a5e63c2c9c1d4e89c3741f5a", ("238U.knt",)),
    "geo_Th232": ("AntineutrinoSpectrum_232Th.knt",
                  "e28088a857c42a09147b6e2561872dc222b1b42edbada8e6d9d2135ab20cd38a", ("232Th.knt",)),
}
ME, MP, MN = 0.51099895, 938.27208816, 939.56542052
DELTA = MN - MP
E_THR = ((MN + ME) ** 2 - MP ** 2) / (2 * MP)      # IBD threshold, 1.806 MeV
EMIN = 1.810                                       # MeV: first point safely above threshold (ratpac default uses 1.85)
STEP_KEV = 5                                       # resample the 1 keV source to 5 keV in the table (ratpac interpolates)


def fetch(name, sha, aliases, cache):
    cands = [os.path.join(cache, n) for n in (name, *aliases)] if cache else []
    for c in cands:
        if os.path.exists(c):
            data = open(c, "rb").read()
            break
    else:
        req = urllib.request.Request(BASE_URL + name, headers={"User-Agent": "spectrum-fetch/1.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        if cache:
            os.makedirs(cache, exist_ok=True)
            open(os.path.join(cache, name), "wb").write(data)
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        sys.exit(f"sha256 mismatch for {name}: {got} != pinned {sha}")
    e, w = [], []
    for line in data.decode().splitlines():
        if line.strip() and not line.startswith("#"):
            a, b = line.split()[:2]
            e.append(float(a) / 1000.0)      # keV -> MeV
            w.append(float(b) * 1000.0)      # 1/keV -> 1/MeV
    return e, w


def sigma0(enu):
    """zeroth-order IBD total cross section shape (Vogel & Beacom 1999): sigma ~ E_e p_e, E_e = E_nu - Delta."""
    ee = enu - DELTA
    return ee * math.sqrt(ee * ee - ME * ME) if ee > ME else 0.0


def table(index, e, w):
    pts = [(x, y) for x, y in zip(e, w) if x >= EMIN]
    last = max(i for i, (x, y) in enumerate(pts) if y > 0)
    emax = pts[last][0] + 0.001
    first = min(pts, key=lambda p: abs(p[0] - EMIN))[1]          # source value at the lower edge
    se, sf = [EMIN], [first]
    x = (math.floor(EMIN * 1000 / STEP_KEV) + 1) * STEP_KEV / 1000  # first grid point strictly above EMIN
    half = STEP_KEV / 2000.0
    while x <= emax:
        # average the 1 keV source bins whose centres fall in [x - STEP/2, x + STEP/2)
        vals = [y for (ex, y) in pts if x - half <= ex < x + half]
        se.append(round(x, 4)); sf.append(sum(vals) / len(vals) if vals else 0.0)
        x = round(x + STEP_KEV / 1000, 6)
    se.append(round(emax + STEP_KEV / 1000, 4)); sf.append(0.0)
    return {"name": "IBD", "index": index, "run_range": [0, 0], "apply_xs": 1, "emin": EMIN, "emax": se[-1],
            "spec_e": se, "spec_flux": [float(f"{v:.6g}") for v in sf]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/obd_geonu_spectra"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ratdb", "OBD17kt"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    tabs, stats = [], {}
    for idx, (name, sha, al) in FILES.items():
        e, w = fetch(name, sha, al, a.cache)
        tabs.append(table(idx, e, w))
        de = e[1] - e[0]
        tot = sum(w) * de
        above = sum(y for x, y in zip(e, w) if x > E_THR) * de
        ibd = sum(y * sigma0(x) for x, y in zip(e, w) if x > E_THR) * de   # per decay, arbitrary units
        stats[idx] = (tot, above, ibd, tabs[-1]["emax"])
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "IBD_GEO.ratdb")
    with open(path, "w") as f:
        f.write("// GENERATED by tools/make_geo_ibd_spectrum.py from S. Enomoto's geoneutrino spectra (pinned sha256).\n"
                "// Not for redistribution (no licence stated by the source): regenerate, do not commit.\n"
                f"// apply_xs = 1: spec_flux is the antineutrino flux per chain-head decay (1/MeV), resampled to {STEP_KEV} keV.\n\n")
        for t in tabs:
            f.write("{\n")
            for k, v in t.items():
                f.write(f"\"{k}\": {v if not isinstance(v, str) else chr(34) + v + chr(34)},\n".replace("'", '"'))
            f.write("}\n\n")
    print(path, hashlib.sha256(open(path, "rb").read()).hexdigest())
    if a.check:
        for idx, (tot, above, ibd, emax) in stats.items():
            print(f"{idx}: {tot:.3f} antineutrinos/decay, {above:.3f} above {E_THR:.3f} MeV "
                  f"({100 * above / tot:.2f} %), table emax {emax:.3f} MeV")
        # decays per unit mass per unit time ~ lambda / A; Th/U mass ratio 3.9 (chondritic, Borexino Eq. 18)
        lam_u, lam_th = math.log(2) / 4.468e9, math.log(2) / 1.405e10
        decay_ratio = 3.9 * (lam_th / 232.038) / (lam_u / 238.051)
        rs = decay_ratio * stats["geo_Th232"][2] / stats["geo_U238"][2]
        print(f"Th/U decay-rate ratio at mass ratio 3.9: {decay_ratio:.3f}; IBD-weighted R_s = S(Th)/S(U) = {rs:.3f} "
              "(Borexino PRD 101, 012009 Eq. 18: 0.27, includes the same zeroth-order sigma shape to within ~1 %)")


if __name__ == "__main__":
    main()
