#!/usr/bin/env python3
"""Derive the OBD 17 kt optics and PMT tables from ratpac-two's stock tables (tag 4.4.0).

OBD17kt_geo variant (2026-11-13; copied from projects/OBD17kt): adds the 1.0 wt% 6Li scintillator optics entry
(obd_ls_li6_1p0, same optics as obd_ls_li6) and particle-dependent scintillation pulse shapes and Birks constants
(SNO+ LAB+PPO measurements) so alpha/triton light from n+6Li capture has its measured slower time profile.

Writes into the experiment directory (default ratdb/OBD17kt/):
  OPTICS_OBD.ratdb  optics for obd_ls_li6, obd_k290, obd_acrylic
  PMT_OBD.ratdb     PMT / PMTTRANSIT / PMTCHARGE for model "obd_r3600"

Every change from the stock tables is listed in CHANGES below. Each entry gives its source;
"assumption" means no OBD-specific number exists yet (see docs/OBD17kt_DETECTOR_MODEL.md, GAPs).
Usage:  make_obd_ratdb.py --base <ratpac-two>/ratdb [--out ratdb/OBD17kt]
"""
import argparse
import json
import math
import os
import re

# Refractive indices at 380 nm, measured at 2 C (ONO25 p.70-71)
N380 = {"obd_ls_li6": 1.523, "obd_k290": 1.496, "obd_acrylic": 1.511}
LS_LIGHT_YIELD = 10000.0   # photons/MeV, the value ONO25 p.106 assumed for the OBD Geant4 light-collection study
PPO_G_PER_L = 3.0          # JPCS21 p.5, OHN24 p.31
QE_390 = 0.23              # OHN24 Table 4.2 (KamLAND 20-inch PMT)
TTS_FWHM_NS = 7.7          # OHN24 Table 4.2; read as FWHM (Hamamatsu convention) -> sigma = FWHM / 2.3548
DARK_RATE_HZ = 40000.0     # OHN24 Table 4.2 (applied at analysis time, not in Geant4; see extract tool)

# --- particle-dependent scintillation (OBD17kt_geo) -----------------------------------------------------------
# ratpac selects the GLG4Scint table by particle MASS (src/physics/src/PhysicsList.cc, GLG4Scint.cc
# GenericPostPostStepDoIt): m < 0.9 m_p -> default ("") [e-, e+, gamma secondaries];
# 0.9 m_p <= m < 0.999 m_n -> "proton"; 0.999 m_n <= m < 0.9 m_alpha -> "neutron" [in practice DEUTERONS and
# TRITONS, e.g. the triton from n+6Li]; m >= 0.9 m_alpha -> "alpha" [alphas and heavier ions].
# Decay-time waveforms: x = -tau (ns), y = light fraction of that component (ratpac integrates
# A*(1-exp(-t/tau)) with a common rise time, i.e. the SNO+ fit form). Order is irrelevant (InsertValues sorts).
# SNO+ Collaboration, JINST 16 P05009 (2021), arXiv:2011.12924, Table 5, Method 2 (LAB + 2 g/L PPO):
WAVE_BETA = ([4.88, 15.4, 66.0, 400.0], [0.665, 0.218, 0.083, 0.035])
WAVE_ALPHA = ([4.79, 18.4, 92.0, 900.0], [0.427, 0.313, 0.157, 0.102])
RISE_NS = 0.72             # Caravaca et al., EPJC 77, 811 (2017), LAB + 2 g/L PPO (measured for e-like light)
# Birks constants kB in mm/MeV (ratpac SCINTMOD key 1). e-: stock 0.0798 (SNO+ EPJC 85 (2025) 17, arXiv:2405.19700).
# alpha: 66-76 um/MeV (von Krosigk et al., EPJC 76, 109 (2016), quoted in JINST 16 P05009 Sec. 4.1.1) -> midpoint.
# proton: 94-98 um/MeV (von Krosigk et al., EPJC 73, 2390 (2013), same quote) -> midpoint.
BIRKS = {"": 0.0798, "alpha": 0.071, "proton": 0.096, "neutron": 0.096}
LI6_1P0_INDEX = "obd_ls_li6_1p0"

CHANGES = []


def load_tables(path):
    """Minimal RATDB reader: comments stripped, missing commas between fields tolerated."""
    t = open(path).read()
    t = re.sub(r"//[^\n]*", "", t)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    out, depth, start = [], 0, None
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                s = t[start:i + 1]
                s = re.sub(r'([\]\d"el.])\s*\n(\s*")', r"\1,\n\2", s)
                s = re.sub(r",\s*,", ",", s)
                s = re.sub(r",\s*([\]}])", r"\1", s)
                s = re.sub(r"(\d)\.(\s*[,\]])", r"\1.0\2", s)
                out.append(json.loads(s))
    return out


def get(tables, name, index):
    for tb in tables:
        if tb.get("name") == name and tb.get("index") == index:
            return json.loads(json.dumps(tb))
    raise KeyError(f"{name}[{index}] not found")


def interp(x, xs, ys):
    pts = sorted(zip(xs, ys))
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if a <= x <= c:
            return b if c == a else b + (d - b) * (x - a) / (c - a)
    raise ValueError(f"{x} outside table range")


def scale_rindex(tb, target):
    base = interp(380.0, tb["RINDEX_value1"], tb["RINDEX_value2"])
    f = target / base
    tb["RINDEX_value2"] = [round(v * f, 6) for v in tb["RINDEX_value2"]]
    return base, f


def dump(tables, path, header):
    with open(path, "w") as f:
        f.write(header)
        for tb in tables:
            f.write("{\n")
            keys = ["name", "index", "run_range"] + [k for k in tb if k not in ("name", "index", "run_range")]
            for k in keys:
                f.write(f"\"{k}\": {json.dumps(tb[k])},\n")
            f.write("}\n\n")


def set_pulse_shapes(ls):
    """Per-particle waveform, rise time and Birks constant for the LS optics entry (in place)."""
    shapes = {"": WAVE_BETA, "alpha": WAVE_ALPHA, "proton": WAVE_ALPHA, "neutron": WAVE_ALPHA}
    props = [p for p in ls["PROPERTY_LIST"] if not re.match(r"(SCINTWAVEFORM|SCINT_RISE_TIME|SCINTMOD)", p)]
    for part, (taus, amps) in shapes.items():
        ls[f"SCINT_RISE_TIME{part}"] = RISE_NS
        ls[f"SCINTWAVEFORM{part}_value1"] = [-t for t in taus]
        ls[f"SCINTWAVEFORM{part}_value2"] = list(amps)
        ls[f"SCINTMOD{part}_value1"] = [1.0]
        ls[f"SCINTMOD{part}_value2"] = [BIRKS[part]]
        props += [f"SCINT_RISE_TIME{part}", f"SCINTWAVEFORM{part}", f"SCINTMOD{part}"]
    ls["PROPERTY_LIST"] = props
    CHANGES.append("obd_ls_li6: e-/gamma pulse shape tau = 4.88/15.4/66/400 ns, A = 0.665/0.218/0.083/0.035 "
                   "(SNO+ JINST 16 P05009 Table 5, Method 2; stock was 3 components 13.5/23/98.5 ns)")
    CHANGES.append("obd_ls_li6: alpha pulse shape tau = 4.79/18.4/92/900 ns, A = 0.427/0.313/0.157/0.102 (same source)")
    CHANGES.append("obd_ls_li6: proton and 'neutron' (= deuteron/triton by ratpac's mass selection) tables use the "
                   "ALPHA shape (assumption: no LAB measurement for p/d/t; heavy, high-dE/dx particles)")
    CHANGES.append(f"obd_ls_li6: rise time {RISE_NS} ns for all particles (Caravaca et al., EPJC 77, 811 (2017); stock 0.8)")
    CHANGES.append("obd_ls_li6: Birks kB (mm/MeV) e- 0.0798 (stock, arXiv:2405.19700), alpha 0.071 (midpoint 66-76 um/MeV, "
                   "EPJC 76, 109), proton 0.096 (midpoint 94-98 um/MeV, EPJC 73, 2390), deuteron/triton 0.096 "
                   "(assumption: proton value; no triton measurement found)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="ratpac-two ratdb directory (stock tables)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "ratdb", "OBD17kt"))
    a = ap.parse_args()
    B = lambda f: load_tables(os.path.join(a.base, f))
    optics, labppo = B("OPTICS.ratdb"), B("OPTICS_LABPPO.ratdb")
    pmt, transit, charge, pc = B("PMT.ratdb"), B("PMTTRANSIT.ratdb"), B("PMTCHARGE.ratdb"), B("OPTICS_Photocathode.ratdb")

    # --- liquid scintillator: LAB + 3 g/L PPO + 0.1 wt% 6Li --------------------------------------------
    ls = get(labppo, "OPTICS", "scintillator_lab_ppo0p6")
    ls["index"] = "obd_ls_li6"
    ls["LIGHT_YIELD"] = LS_LIGHT_YIELD
    CHANGES.append(f"obd_ls_li6: base scintillator_lab_ppo0p6; LIGHT_YIELD 6694 -> {LS_LIGHT_YIELD:.0f} /MeV "
                   "(ONO25 p.106 assumption; Li loading may lower this, assumption)")
    ls["ABSLENGTH_SCALING"] = [1.0, round(PPO_G_PER_L / 2.5, 6)]
    CHANGES.append("obd_ls_li6: PPO absorption scaled to 3 g/L (stock data are for 2.5 g/L): ABSLENGTH_SCALING[1] = 3/2.5 = 1.2. "
                   "ratpac DIVIDES absorption lengths by the scaling (Materials.cc:557; stock 0.6 g/L entry uses 0.6/2.5 = 0.24). "
                   "Fixed 2026-11-13 after the physics audit; it was 2.5/3, i.e. an effective 2.08 g/L")
    p_lab_ppo = -0.4430 * math.exp(-0.77 * PPO_G_PER_L) + 0.8801   # stock-file fit, JINST 16 P05009
    p0 = round(p_lab_ppo * 0.898, 4)
    # LAB-component re-emission only where LAB itself absorbs (UV below ~340 nm, the intrinsic LAB absorption edge),
    # because that energy can be transferred to PPO. Above it, absorption by the LAB component is by impurities and
    # is non-radiative. Physics audit 2026-11-13: a flat 0.751 at all wavelengths made 82 % of detected light
    # re-emitted far from the vertex. The 340 nm edge is an assumption; no OBD-LS measurement has been digitised yet (GAP 2).
    ls["REEMISSION_PROB0_option"] = "wavelength"
    ls["REEMISSION_PROB0_value1"] = [100.0, 339.0, 341.0, 1000.0]
    ls["REEMISSION_PROB0_value2"] = [p0, p0, 0.0, 0.0]
    CHANGES.append(f"obd_ls_li6: REEMISSION_PROB0 0.540 -> {p0} below 340 nm, 0 above (stock-file transfer-efficiency fit at 3 g/L x 0.898; "
                   "wavelength-dependent since the 2026-11-13 physics audit)")
    base, f = scale_rindex(ls, N380["obd_ls_li6"])
    CHANGES.append(f"obd_ls_li6: RINDEX x{f:.5f} (stock {base:.4f} -> {N380['obd_ls_li6']} at 380 nm, ONO25 p.70)")
    set_pulse_shapes(ls)
    ls1 = json.loads(json.dumps(ls))
    ls1["index"] = LI6_1P0_INDEX
    CHANGES.append(f"{LI6_1P0_INDEX}: identical optics to obd_ls_li6 (light yield held constant with 6Li loading: "
                   "project assumption 2026-11-13; real high-loading LS likely loses light)")

    # --- buffer oil Hicall K-290 ------------------------------------------------------------------------
    k290 = get(optics, "OPTICS", "mineral_oil")
    k290["index"] = "obd_k290"
    for k in [k for k in k290 if k.startswith("NEUTRON_")]:
        del k290[k]
    k290["PROPERTY_LIST"] = [p for p in k290["PROPERTY_LIST"] if not p.startswith("NEUTRON_")]
    base, f = scale_rindex(k290, N380["obd_k290"])
    CHANGES.append(f"obd_k290: base mineral_oil optics; RINDEX x{f:.5f} ({base:.4f} -> 1.496 at 380 nm, ONO25 p.70); "
                   "ABSLENGTH = stock mineral_oil (K-290 transmittance not digitised yet: GAP 2)")

    # --- acrylic vessel ---------------------------------------------------------------------------------
    acr = get(optics, "OPTICS", "acrylic_uvt_good")
    acr["index"] = "obd_acrylic"
    base, f = scale_rindex(acr, N380["obd_acrylic"])
    CHANGES.append(f"obd_acrylic: base acrylic_uvt_good; RINDEX x{f:.5f} ({base:.4f} -> 1.511 at 380 nm, ONO25 p.71); "
                   "ABSLENGTH stock (GAP 2)")

    # --- PMT: KamLAND-type 20-inch Venetian-blind = Hamamatsu R3600 shape ---------------------------------
    m = get(pmt, "PMT", "r3600")
    m["index"] = "obd_r3600"
    pct = get(pc, "OPTICS", "photocathode_R3600")
    qe_stock = interp(390.0, pct["EFFICIENCY_value1"], pct["EFFICIENCY_value2"])
    m["efficiency_correction"] = round(QE_390 / qe_stock, 5)
    m["noise_rate"] = DARK_RATE_HZ
    CHANGES.append(f"obd_r3600: stock r3600 bulb/photocathode; efficiency_correction {m['efficiency_correction']} "
                   f"(stock QE {qe_stock:.4f} at 390 nm -> 0.23, OHN24 Table 4.2); noise_rate 40 kHz (OHN24)")
    sigma = TTS_FWHM_NS / (2 * math.sqrt(2 * math.log(2)))
    t = [round(-25.0 + 0.1 * i, 2) for i in range(501)]
    tr = {"name": "PMTTRANSIT", "index": "obd_r3600", "run_range": [0, 0], "cable_delay": 0.0,
          "time": t, "time_prob": [round(math.exp(-0.5 * (x / sigma) ** 2), 8) for x in t]}
    CHANGES.append(f"obd_r3600 transit: Gaussian sigma {sigma:.3f} ns (TTS 7.7 ns read as FWHM; stock r3600 sigma 1.27 ns). "
                   "Mean transit (90 ns) is a constant offset and omitted")
    ch = get(charge, "PMTCHARGE", "r3600")
    ch["index"] = "obd_r3600"
    CHANGES.append("obd_r3600 charge: stock r3600 single-PE spectrum (P/V 1.5 in OHN24 not modelled separately)")

    os.makedirs(a.out, exist_ok=True)
    hdr = ("// Generated by tools/make_obd_ratdb.py from ratpac-two 4.4.0 stock tables - do not edit by hand.\n"
           + "".join(f"// - {c}\n" for c in CHANGES) + "\n")
    dump([ls, ls1, k290, acr], os.path.join(a.out, "OPTICS_OBD.ratdb"), hdr)
    dump([m, tr, ch], os.path.join(a.out, "PMT_OBD.ratdb"), hdr)
    print("\n".join(CHANGES))


if __name__ == "__main__":
    main()
