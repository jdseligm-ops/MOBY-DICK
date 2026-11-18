# OBD 17 kt: ratpac-two detector model and per-event output

> **CURRENT PRODUCTION CONFIGURATION (updated 2026-11-14; supersedes the older statements in §3 and §6, which are kept for history)**
> - **Shields: optical GEL inside** (`OBD_GLASS_SHIELD_GEL`). User decision after the 2026-11-13 physics audit; §6's "air-filled" decision is superseded.
> - **LS optics (fixed in the audit):**
>   - LAB→PPO re-emission only below 340 nm (REEMISSION_PROB0 = 0.7508 at λ < 340 nm, 0 above), not the flat 0.751 of §3;
>   - PPO absorption scaling 1.2, not 2.5/3;
>   - OPTICS sha 84128bc2.
> - **LY 10,000 photons/MeV**, giving a measured **395 PE/MeV** (337 PE/MeV central) and a ⁶Li capture median of 230 p.e. (published dataset, true p.e.).
> - The dataset's `detector_json` attribute records this configuration.
> - **Simulated photocathode coverage ≈ 39 %** (ratpac r3600 bulb, effective Ø ≈ 484 mm) vs 35.4 % for OHN24's Ø 460.
> - **Known gaps and conflicts:** `DETECTOR_SPEC_VERIFICATION.md`.
>   - item A: the PMT model (OHN24 KamLAND 20″ vs ONO25's KamLAND2 high-QE tube);
>   - item B: the stock LS absorption/re-emission, with SAK21 Figs 5.19/5.20 not digitised. It limits PSD to ~25 % proton-recoil rejection at 95 % e⁺ efficiency.
> - Sources: `DETECTOR_SPEC_VERIFICATION.md` (reference list; the PDFs are not redistributed).

Built 2026-11-12. Files live in `projects/OBD17kt/`. ratpac-two is the 4.4.0 container, and the stock tables were read from the same tag.

**Status.** The model has not run yet. It needs the ratpac container (`jobs/install_ratpac.sbatch`) and then `jobs/obd_smoke.sbatch`. Until the smoke test passes, treat every number below as design input, not validated output.

## 1. Files

| File | What | How made |
|---|---|---|
| `ratdb/OBD17kt/OBD17kt.geo` | Volumes: world (seawater), SS tank, black liner, K-290 buffer, acrylic vessel, LS, PMT array | hand-written |
| `ratdb/OBD17kt/MATERIALS_OBD.ratdb` | ⁶Li element; `obd_ls_li6`, `obd_k290`, `obd_acrylic` | hand-written |
| `ratdb/OBD17kt/OPTICS_OBD.ratdb` | Optics for the three materials | `tools/make_obd_ratdb.py --base <ratpac-two>/ratdb` |
| `ratdb/OBD17kt/PMT_OBD.ratdb` | PMT model `obd_r3600`, plus its transit-time and charge tables | same script |
| `ratdb/OBD17kt/ENCAPSULATION_OBD.ratdb` | Glass pressure shield, `OBD_GLASS_SHIELD` | hand-written |
| `ratdb/OBD17kt/PMTINFO_OBD17kt.ratdb` | 12,505 PMT positions and directions | `tools/make_pmt_layout.py -o …` |
| `macros/ibd_obd17kt.mac` | IBD generator, uniform in LS, isotropic ν; outntuple options | template (`__NEVENTS__`, `__SPECTRUM__`) |
| `jobs/run_chunk.sh` | One chunk: rat → archive RNG states → extraction → SHA256SUMS | |
| `jobs/obd_smoke.sbatch` | 10 events: geometry builds, extraction works, s/event and memory | |
| `jobs/sim_ibd_array.sbatch` | Production array, one seed per task | |
| `tools/extract_events.py` | ntuple → `*.events.npz` (truth + photon hits), described in §4 | |

## 2. Geometry

Lengths are in mm. Sources:
- OHN24 = T. Ohno, Tohoku M.S. thesis 2024, Table 5.1 p.44 and §4.2.
- ONO25 = T. Ono, Tohoku M.S. thesis.

| Volume | Dimensions | Material | Source |
|---|---|---|---|
| SS tank | r 15,016 / 15,000; h 50,032 / 50,000 | stainless_steel | OHN24 T5.1 |
| Black liner | 1 mm inside the tank | acrylic_black (absorbing) | ONO25 p.104: tank surface reflectivity 0 |
| Buffer | fills tank to the acrylic | `obd_k290`, ρ = 0.888 | ONO25 p.67, p.75 |
| Acrylic vessel | r 12,050 / 12,000; h 44,100 / 44,000 (5 cm wall) | `obd_acrylic`, ρ = 1.18 | OHN24 T5.1 |
| LS | r 12,000, h 44,000 → 19,900 m³ ≈ 17.8 kt | `obd_ls_li6`, ρ = 0.8925 | OHN24, ONO25 p.75 |
| PMTs | 12,505 × 20″ in glass spheres (r 350/360 mm) on the tank wall | Hamamatsu R3600 shape | OHN24 p.32–33, T5.1 |

**Not modelled:**
- the 3850 outer-detector PMTs (outside the tank, muon veto)
- acrylic support pillars, fill ports, pressure-compensation hose, cables

None of these matter for IBD position reconstruction in the ID, apart from small shadowing by the pillars.

**PMT layout.** The thesis gives no coordinates (GAP 1), so `make_pmt_layout.py` builds one:
- **Wall:** 79 staggered rings × 125 = 9,875 PMTs. Arc pitch is 735 mm and row spacing 632 mm.
- **Caps:** 1,315 on each, on a hexagonal lattice with 728 mm pitch.
- **Total:** exactly 12,505.
- **Spacing check:** the smallest centre-to-centre distance is 728 mm, more than the 720 mm shield diameter, so no shields overlap (the script asserts this).
- **Coverage:** shields cover 87% of the mounting surface, which forces near-hexagonal packing. Photocathode coverage (φ460) is 35.4%.
- **Placement:** PMT centres sit at r = 14,630 mm and |z| = 24,630 mm, and face inward.

## 3. Physics and optics choices

Every change from the stock ratpac tables is also written into the generated file headers.

| Item | Value used | Basis |
|---|---|---|
| LS composition | LAB (ratpac C15–C19 mix) + PPO 3 g/L (0.336 wt%) + **⁶Li 0.10 wt%** | JPCS21, OHN24; ⁶Li is the user's choice |
| ⁶Li form | pure ⁶Li isotope, no counter-ion | assumption (see below) |
| Light yield | 10,000 photons/MeV, Birks kB 0.0798 mm/MeV (ratpac LAB) | ONO25 p.106 used 10,000/MeV for OBD |
| LS optics | ratpac `scintillator_lab_ppo0p6`, rescaled to 3 g/L PPO: PPO absorption × 2.5/3, LAB→PPO re-emission 0.751 (ratpac's own fit at 3 g/L). **SUPERSEDED**: production uses re-emission only below 340 nm and PPO scaling 1.2 (see the banner) | ratpac stock + documented scaling |
| Refractive index at 380 nm | LS 1.523, K-290 1.496, acrylic 1.511; stock curves are scaled to these | ONO25 p.70–71 (measured at 2 °C) |
| K-290 / acrylic absorption | stock `mineral_oil` / `acrylic_uvt_good` | GAP 2 |
| PMT | R3600 bulb (KamLAND-type 20″ Venetian blind); QE scaled from 20.85% to 23% at 390 nm | OHN24 Table 4.2 |
| TTS | Gaussian, σ = 3.27 ns (7.7 ns read as FWHM) | OHN24 Table 4.2 |
| Dark rate | 40 kHz per PMT, **added at feature-building time**, not in Geant4 | OHN24 Table 4.2 |
| Shield | borosilicate glass, 10 mm thick, **air inside** (no optical gel). **SUPERSEDED**: production uses optical gel (see the banner) | OHN24 T5.1 thickness; the inside is an assumption |
| Neutron physics | ratpac `Shielding` list: NeutronHP < 20 MeV, thermal scattering below 4 eV (free-gas for LS hydrogen) | ratpac default |

**Expected neutron behaviour.** These are thermal hand estimates; the smoke test will measure them.

| Quantity | Estimate |
|---|---|
| Σ(⁶Li) | 0.084 cm⁻¹ |
| Σ(H) | 0.021 cm⁻¹ |
| Captures on ⁶Li | ≈ 80% |
| Captures on H | ≈ 20% |
| Capture time τ | ≈ 43 µs |

In Geant4, ⁶Li(n,t)α is a `neutronInelastic` end point, not `nCapture`. The extraction therefore takes the neutron's last trajectory point, whatever process ended it, and labels the target from the products: α + t means ⁶Li, d means H.

### Assumptions to confirm or replace (GAPs)

1. **PMT layout and shield interior.** Real coordinates are needed, and whether the shields hold air, vacuum or gel. Gel would raise light collection.
2. **K-290 and acrylic absorption spectra.** They are in ONO25 ch. 5 figures and need digitising.
3. **⁶Li loading chemistry.** A ⁶LiCl-type loading (as in PROSPECT) adds Cl (σ ≈ 33 b): roughly 3% of captures would go on Cl, with high-energy γs. Loading also usually lowers light yield (PROSPECT ≈ 8,000/MeV).
4. **Light yield of the doped LS.** ONO25's reference result is ≈ 500 p.e./MeV, with a target of 450. The smoke test reports p.e. per MeV so we can calibrate.
5. **Site geoneutrino spectrum.** The plan trains on the ratpac reactor spectrum (1.85–8.15 MeV ν). A Hawaii geo-ν spectrum table from geoneutrinos.org (OHN24 site 23.63°N, 155.83°W) is needed for evaluation.

## 4. Per-event output (`*.events.npz`, one file per chunk)

| Requested | Field(s) |
|---|---|
| IBD vertex | `vtx_x, vtx_y, vtx_z, vtx_t`, plus `nu_dir_*`, `ep_ke`, `n_ke` |
| Positron position and time | start `ep_x0…ep_t0` (= vertex); **annihilation point** `ep_x1, ep_y1, ep_z1, ep_t1`, `ep_end_proc` |
| Neutron position and time | capture point `n_x1, n_y1, n_z1, n_t1`; `n_end_proc`, `n_target` (1 ⁶Li, 2 H, 3 other) |
| Optical photon hits per PMT, as a time series | flat `pe_pmt`, `pe_t_true` (arrival), `pe_t` (with TTS), `pe_proc`, `pe_delayed`, sliced by `pe_off`. PMT geometry is in `pmt_x…pmt_w` |
| Random seed | `seed` (rat `-s` of the chunk) + `evid`; exact per-event engine states in `ibd_s<seed>.rndm_states.tar` |
| Extra | `edep`, `edep_quenched`, `npe_prompt`, `npe_delayed`, `overlap` (capture < 1 µs) |

**Seed scheme.** ratpac seeds the RNG once per process, so the seed is per chunk: seed = BASE_SEED × 100000 + array task.

To replay one event exactly, use that event's saved `run0evtN.rndm` state with `/random/resetEngineFrom` and run `/run/beamOn 1`. The smoke test checks that ratpac actually writes these state files.

**Truth caveat.** `pe_delayed` splits the photons using simulation truth (photon creation time ≥ capture time). Features for real-data-like training should instead split by hit-time clustering. The two only disagree in the roughly 2% of events where the capture happens within 1 µs.

**Untested code.** The extraction script has not been run against a real ratpac file yet, since none exists. The smoke job is its first test.

## 5. Validation and decisions (2026-11-12)

| Test | Job | Result |
|---|---|---|
| Container | 15397926 / 15398506 | `ratpac/ratpac-two@sha256:c85936d5…`; SIF sha256 `3b6cc869…` (pinned in `env/pins.sh`). Contents: rat 4.4.0, Geant4 11.4.1, ROOT 6.36.12, Python 3.10.12, numpy 1.21.5 |
| Smoke: 10 events × 2, same seed | 15398507 | geometry OK (12,505 shielded PMTs); identical `content_sha256` `01e77d75…`; RNG state archives identical. The only Geant4 warnings are mat219 (single-value timing tables in ratpac's stock LAB/PPO data) |
| Cross-CPU, same seed | 15403168–71 | identical hash on Ivy Bridge, Haswell, Cascade Lake, Ice Lake and AMD Genoa, so production may use any node |
| Speed / memory | – | 4.6 s/event on Ivy Bridge; ≈2.5–3 s/event on Cascade Lake, Ice Lake and Genoa; ~25 s setup per process; peak RSS ≈1.4 GB |
| Size | – | raw ntuple ≈570 KB/event; `.npz` ≈15 KB/event |

**Light model.** Prompt PE/MeV was estimated as N_PE / (T_e+ + 1.022 MeV):

| Shield interior | Job | Prompt PE/MeV | PE per ⁶Li capture |
|---|---|---|---|
| Air | 15398507 | 371 ± 20 | ≈270 |
| Optical gel (front dome) | 15403196 | 691 ± 34 | ≈470 |

For reference, ONO25's thesis simulation gave ≈500 PE/MeV (target 450).

**Decision (user, 2026-11-12; SUPERSEDED on 2026-11-13 by gel shields, see the banner):** the pilot and production use **air-filled shields and LY = 10,000/MeV**, about 370 PE/MeV, a conservative detector. The gel variant (`SHIELD=OBD_GLASS_SHIELD_GEL`) stays available for later studies.

**Photon process mix (air, 10 events):**
- 81% of detected PE are re-emitted photons
- 18% are primary scintillation
- 0.4% are Cherenkov

**Pilot:** array 15404858, 500 × 200 events, seeds 100000–100499. It runs from the frozen code snapshot at `runs/OBD17kt/pilot_b1/code` (code-manifest prefix `f15673c4…` in the job receipt). Raw ROOT and `.npz` both come back to `the authors' local results/OBD17kt/pilot_b1/`.

## 6. Two detector versions, compared with identical BDT pipelines (user request, 2026-11-12)

| | Version 1 ("v1", conservative) | Version 2 ("v2", higher information) |
|---|---|---|
| Shield interior | air (`OBD_GLASS_SHIELD`) | optical gel, front dome (`OBD_GLASS_SHIELD_GEL`) |
| LS light yield | 10,000 photons/MeV | 7,240 photons/MeV (Li loading lowers yield; tuned to reach ≈500 PE/MeV) |
| Prompt PE/MeV (10-event test) | 371 ± 6 | **514 ± 6** (job 15405121) |
| PE per ⁶Li capture | ≈270 | ≈345 |
| Pilot run set | `pilot_b1`, seeds 100000–100499 (array 15404858) | `pilot_gel7240_b2`, seeds 200000–200499 (array 15405731, run from a separate project copy) |

**How the versions are kept apart:**
- The variant is chosen by env (`SHIELD`, `LY`), written into `run.mac`, and recorded in every `provenance.json`.
- Each run set holds exactly one variant, and seeds never overlap between run sets.

**Code-change check:** job 15405122 ran v1 through the new LY-capable code and reproduced `content_sha256` `01e77d75…`. The new knob is therefore physics-neutral at its default.

## 7. Geoneutrino hackathon variant `OBD17kt_geo` (2026-11-13)

**Origin:** copied from `projects/OBD17kt` (v1: air shields, LY 10,000/MeV) on 2026-11-13. v1 production code is untouched. Approved scope (user, 2026-11-13): 1.0 wt% ⁶Li only; detector v1; U/Th geoneutrino signal; backgrounds = accidentals from internal U/Th/K, ¹³C(α,n)¹⁶O, reactor IBD (shortcut check), dark-noise triggers; alpha/triton pulse shape modelled. Everything below was prepared and statically checked locally; nothing has been run in ratpac yet (see 7.8).

### 7.1 Files changed or added (relative to v1)

| File | Change |
|---|---|
| `ratdb/OBD17kt/MATERIALS_OBD.ratdb` | + `obd_ls_li6_1p0` (LAB 0.9866386, PPO 0.0033614, ⁶Li 0.0100 by mass; ρ 0.89248) |
| `tools/make_obd_ratdb.py` → `OPTICS_OBD.ratdb` | per-particle pulse shapes + Birks constants; + optics entry `obd_ls_li6_1p0` (identical to `obd_ls_li6`). PMT tables byte-identical to v1 apart from the header |
| `tools/make_geo_ibd_spectrum.py` → `ratdb/OBD17kt/IBD_GEO.ratdb` | U-chain and Th-chain IBD spectrum tables (generated, **gitignored**) |
| `tools/make_alphan_hepevt.py` | ¹³C(α,n)¹⁶O final-state sampler → HEPEVT file per chunk |
| `macros/ibd_geo.mac` | IBD with `__SPECTRUM__` = `geo_U238` / `geo_Th232` / `default` (reactor) and `__LS_MATERIAL__` |
| `macros/singles_decay0.mac` | Decay0 isotope `__ISOTOPE__` uniform in volumes matching regex `__VOLUME__` |
| `macros/singles_po210.mac` | 5.304 MeV α gun uniform in the LS |
| `macros/alphan_hepevt.mac` | HEPEvt reader + fill in the LS |
| `tools/extract_events.py` | `--mode generic` for non-IBD samples; all events also store primaries (`prim_pdg`, `prim_ke`, `prim_off`) |
| `jobs/run_chunk.sh`, `jobs/sim_ibd_array.sbatch` | `MACRO`, `LS_MATERIAL`, `ISOTOPE`, `VOLUME` parameters; runs under `runs/OBD17kt_geo/`; all new parameters, the HEPEVT sha256 and the IBD_GEO table sha256 go into `provenance.json` |
| `jobs/geo_tests.sbatch` | first-run checks T1–T6 (7.8) |
| `.gitignore` | `ratdb/OBD17kt/IBD_GEO.ratdb` |

The other jobs (`obd_smoke`, `repro_check`, `variant_test`, `install_ratpac`) are v1 copies and still point at `projects/OBD17kt`.

### 7.2 1.0 wt% ⁶Li scintillator

- Composition as above; the scintillator volume is switched by `/rat/db/set GEO[scintillator] material "obd_ls_li6_1p0"` in every geo macro (the geo file itself is unchanged).
- **Assumptions:** light yield held at 10,000 photons/MeV (user-agreed); density unchanged; no counter-ion/surfactant modelled. No LAB-based scintillator at 1 wt% ⁶Li has been demonstrated in the literature found; the highest liquid loading found is a microemulsion with 1 wt% *natural* Li (Bergeron et al., NIM A 953, 163126 (2020)), and PROSPECT ran at 0.082 wt% ⁶Li (JINST 14 P03026).
- **Expected capture physics [derived]:** thermal-capture competition with σ(⁶Li) 940 b, σ(H) 0.3326 b, σ(C) 3.5 mb gives 97.5 % ⁶Li captures and τ ≈ 5.3 µs (plus thermalisation time). The same formula gives 79.4 % and 43.0 µs at 0.1 wt%, matching the v1 pilot (79.3 %, 43.1 µs) and PROSPECT-50 (42.8 µs at 0.1 %).
- **Consequence for the data:** about 17 % of captures happen within 1 µs of the prompt event (1 − e^(−1/5.3)), so prompt and delayed light overlap far more often than at 0.1 wt% (2.3 %). The v1 feature window (−300…+900 ns around the 10th PE) and the `overlap` flag (capture < 1000 ns) need revisiting in the ML design.

### 7.3 Scintillation pulse shapes and quenching

ratpac picks the scintillation table by **particle mass** (`PhysicsList.cc`, `GLG4Scint::GenericPostPostStepDoIt`): m < 0.9 m_p → default (e±, γ secondaries); up to 0.999 m_n → `proton`; up to 0.9 m_α → `neutron` (**in practice deuterons and tritons**); heavier → `alpha` (α and ions). Waveforms are decay-time lists (x = −τ in ns, y = light fraction), integrated with a common rise time; ordering is irrelevant (ratpac sorts on insertion).

| Table | τ (ns) | Light fractions | Rise | Birks kB (mm/MeV) | Source |
|---|---|---|---|---|---|
| default (e⁻/γ) | 4.88 / 15.4 / 66 / 400 | 0.665 / 0.218 / 0.083 / 0.035 | 0.72 ns | 0.0798 (stock) | SNO+ JINST 16 P05009 Table 5 (Method 2); rise: Caravaca et al. EPJC 77, 811; kB: SNO+ arXiv:2405.19700 |
| alpha | 4.79 / 18.4 / 92 / 900 | 0.427 / 0.313 / 0.157 / 0.102 | 0.72 ns | 0.071 | SNO+ Table 5; kB = midpoint of 66–76 µm/MeV (EPJC 76, 109) |
| proton | alpha shape | alpha | 0.72 ns | 0.096 | **assumption** (shape); kB = midpoint of 94–98 µm/MeV (EPJC 73, 2390) |
| neutron (= d, t) | alpha shape | alpha | 0.72 ns | 0.096 | **assumption** (shape and kB = proton value; no triton measurement found) |

- v1 used one 3-component shape (13.5/23/98.5 ns) for every particle, no `neutron` table (so tritons from n+⁶Li used the electron shape) and kB 0.0798 for all. The geo variant therefore changes the ⁶Li capture light (yield and timing) relative to v1: check in T1.
- No α rise time and no LAB-specific n+⁶Li visible energy were found. Reference points: 0.55 MeVee in PROSPECT's EJ-309/DIN LiLS (NIM A 922, 287); the KamLAND LS puts the 5.3 MeV ²¹⁰Po α at ~0.3 MeVee (PRC 92, 055808).

### 7.4 Geoneutrino spectra

- Source: S. Enomoto's full-chain antineutrino spectra (`AntineutrinoSpectrum_238U.knt`, `_232Th.knt`; DONGURI v1.0.1, ToI 1996; per chain-head decay, 1 keV bins), https://www.awa.tohoku.ac.jp/~sanshiro/research/geoneutrino/spectrum/. Pinned sha256: U `e31894af…41f5a`, Th `e28088a8…cd38a`. **No licence or terms stated → not committed or redistributed**; `tools/make_geo_ibd_spectrum.py` fetches/caches, verifies and regenerates the table. Generated table sha256 (5 keV resampling, emin 1.81 MeV): `2b3a7e1366db7ed6a3cbb881109197a9af8198a475c91034346f579dad107c33`.
- ratpac semantics (`IBDgen.cc`): `apply_xs: 1` → `spec_flux` is the flux and ratpac applies its own first-order Vogel–Beacom dσ/dcosθ (same as the reactor table). `apply_xs: 0` would draw the angle from dE₁/dcosθ only, which is unphysical, so it is not used.
- Sanity check (`--check`): 6.44 % of U-chain and 3.87 % of Th-chain antineutrinos are above the 1.806 MeV threshold; the U table extends to 4.39 MeV (²¹⁰Tl branch, 0.02 %), Th to 2.26 MeV. With a Th/U mass ratio of 3.9 the IBD-weighted ratio comes out R_s = S(Th)/S(U) = 0.263, versus 0.27 in Borexino PRD 101, 012009 (2020), Eq. 18.
- Physical mix: R_s = 0.27 (mass ratio 3.9; 0.26 mantle, 0.29 lithosphere, same source). The OBD 17 kt study expects U 100.09 and Th 24.98 events/yr at 12.1 TNU (arXiv:2606.20780 Table III; Th/U = 0.25). U and Th are run as separate samples so the mix stays a weighting choice.

### 7.5 Background samples and assumed contamination

| Sample | Macro / generator | Notes |
|---|---|---|
| Reactor IBD | `ibd_geo`, `SPEC=default` | stock ratpac reactor spectrum (not site-specific); irreducible event by event |
| Decay singles | `singles_decay0` (Decay0 `backg` + `regexfill`) | U chain: Pa234m, Pb214, Bi214; Th chain: Ac228, Pb212, Bi212, Tl208; K40. In the LS use BiPo214 / BiPo212 (correlated β then α, τ 237 µs / 0.43 µs) |
| ²¹⁰Po α | `singles_po210` | delayed-like in a ⁶Li detector (α light, α pulse shape, ~0.3–0.4 MeVee) |
| ¹³C(α,n)¹⁶O | `alphan_hepevt` + `make_alphan_hepevt.py` | see 7.6 |
| Dark-noise triggers | none in Geant4 | built at feature time from the 40 kHz/PMT model, as in v1 |

Contamination assumed by the OBD 17 kt thesis (Ohno, local `ono_takeru_m_r.txt`, Table 5.4, g/g) and its singles rates in the LS (Table 5.5):

| Component | ²³⁸U | ²³²Th | ⁴⁰K (as K) | Source in thesis | Rate in LS (Hz) |
|---|---|---|---|---|---|
| Acrylic vessel | 1.0e-11 | 1.0e-11 | 1.0e-11 | JUNO | 43.52 |
| Liquid scintillator | 5.0e-18 | 1.3e-17 | **1.0e-18 (no source given)** | KamLAND | 5.36e-3 |
| PMT glass | 1.5e-7 | 2.4e-7 | 1.0e-8 | KamLAND | 6.03 |
| PMT glass shield | 1.0e-8 | 1.0e-8 | 1.0e-8 | OBD low-background glass | 1.22 |

- **Flag:** the LS K value (1e-18) has no stated source; KamLAND after purification measured (7.3 ± 1.2)e-17 g/g (Gando et al. PRC 92, 055808 (2015)), early phase < 2.7e-16 (PRL 90, 021802). The LS U/Th values are KamLAND *after purification*; early-phase values were U 3.5e-18, Th 5.2e-17.
- The measured low-background shield glass (Sakai et al. JPCS 2156, 012144 (2021), Table 1, Pt-coated) is U 1.4e-8, Th < 5e-9, K 3.4e-9 g/g. JUNO materials (JHEP 11 (2021) 102, Table 1): acrylic 1 ppt each; SS 1/3/0.2 ppb; PMT glass 200–400 ppb U/Th. The steel tank is not in the thesis table.
- **²¹⁰Po in the LS [derived]:** KamLAND early-phase ²¹⁰Pb, 58.4 µBq/kg, gives about 1.04 kBq in the 17.8 kt LS. Sakai's 1.5 kt value (5.9 Bq) scaled to 17.8 kt gives about 70 Bq. These differ by 15×, and the (α,n) rate scales with them: 5.75e-8 n/α gives ~1,900/yr or ~130/yr, against 55.5/yr in the OBD 17 kt table (arXiv:2606.20780 Table III).
- **The OBD background table assumes an undoped LS** (delayed window 1.8–2.6 and 4.4–5.6 MeV for H and C captures, thesis Eq. 5.6). With ⁶Li the delayed signal moves to ≲1 MeVee, where ²¹⁰Po, BiPo α and low-energy γ singles live. Its accidental numbers (14.29/yr full volume, 12.61/yr in the geoneutrino region) therefore do not carry over.
- Seawater ⁴⁰K (10.78 ± 0.21 Bq/kg, Ye et al. Nat. Astron. 7, 1497 (2023)) is outside the steel tank and 3 m of buffer and is not simulated.
- OBD 17 kt per-year table for reference (arXiv:2606.20780 Table III; Ohno Table 5.6): full volume reactor 67.84, accidental 14.29, (α,n) 55.47; geoneutrino region 23.08 / 12.61 / 40.27.

### 7.6 ¹³C(α,n)¹⁶O generator (`tools/make_alphan_hepevt.py`)

Recipe after KamLAND PRL 100, 221803 (2008) and Zhao et al. arXiv:1312.6347:
1. Final state: ground state 91.5 %, excited 8.5 % (Zhao Table 1).
2. α energy at the reaction from σ/S on [threshold, 5.304 MeV].
3. Relativistic two-body kinematics.
4. Write per event the neutron, the ¹⁶O recoil, the α's pre-reaction energy loss as a short α track, and the de-excitation (6.130 MeV γ, or an e⁺e⁻ pair from the 6.049 MeV 0⁺ state).

Geant4 then transports the neutron: proton recoils are quenched, ¹²C(n,n′) gives 4.4 MeV γ, and the capture provides the delayed signal. The vertex is uniform in the LS (`HEPEvt:fill`), and the file is deterministic in the chunk seed (`default_rng([20261113, seed])`). A truth CSV is written alongside it.

**Proxies (clearly not evaluated nuclear data):**
- **Cross section:** σ(E) = Gamow factor with constant S-factor, so the Harissopulos resonances are absent.
- **Stopping power:** S(E) ∝ E^−0.6 (power law through ASTAR polystyrene values).
- **Neutron angles:** isotropic CM angular distribution.
- **Excited-state split:** 81/19 between 6.049 and 6.130 MeV, from KamLAND detected counts.
- **e⁺e⁻ pair:** uniform energy split with independent isotropic directions.

Febbraro et al. (PRL 125, 062501 (2020)) report partial cross sections differing by up to 4× from evaluations, so the excited-state share is uncertain in any case.

**Local validation (20k events):**
- The maximum neutron energy is 7.29 MeV, against KamLAND's "up to 7.3 MeV".
- Excited states appear only for E_α above 5.01 MeV (6.049) and 5.12 MeV (6.130), as their thresholds require.
- The mean neutron kinetic energy is 5.45 MeV for the ground state and 0.14–0.18 MeV for excited states.
- Reruns with the same seed are byte-identical.

### 7.7 Job interface

- `sbatch --array=… --export=ALL,BASE_SEED=<unique>,NEV=…,TAG=…,MACRO=…,SPEC=…,ISOTOPE=…,VOLUME='…',LS_MATERIAL=… jobs/sim_ibd_array.sbatch`. `LS_MATERIAL` defaults to `obd_ls_li6_1p0`, `MACRO` to `ibd_geo`.
- BASE_SEED must stay unique across *all* run sets: v1 used 1 and 2, so geo run sets should start at ≥ 10. Seeds = BASE_SEED×100000 + task id.
- File names are `<sample>_s<seed>.*` (e.g. `ibd_geo_U238_s1100000`, `decay0_Bi214_s…`, `alphan_s…`). Extraction uses `--mode ibd` for `ibd_geo` and `--mode generic` otherwise.
- `IBD_GEO.ratdb` must be generated locally before pushing code to the cluster. It is part of the frozen snapshot and manifest, and its sha256 is also recorded in every `provenance.json`.

### 7.8 Cluster tests to run first (nothing here has been executed in ratpac)

One command after pushing: `sbatch jobs/geo_tests.sbatch` (sandbox partition, ~1–2 h, one chunk per test under `runs/OBD17kt_geo/<date>_geotest_<jobid>/`).

| Test | What it checks | Pass condition |
|---|---|---|
| T1 `ibd_geo`, `geo_U238` | `GEO[scintillator] material` override; `OPTICS[obd_ls_li6_1p0]` and the 4-component and `neutron` waveforms load; custom IBD index found in the experiment directory | `rat.log` shows obd_ls_li6_1p0 and no "Could not read property"; `n_target` ≈ 97 % Li6; mean capture time ≈ 5–8 µs; E_ν ≤ 4.4 MeV; prompt PE/MeV still ≈ 370 (the electron Birks constant is unchanged); delayed ⁶Li PE recorded |
| T2 `geo_Th232`, `default` | other IBD indices | E_ν ≤ 2.26 MeV (Th); reactor spectrum as v1 |
| T3 Decay0 + regexfill | `decay0:regexfill` syntax, `backg` mode, BiPo214, `^ss_tank$` daughter subtraction | events generated; vertices inside the named volume |
| T4 shields / PMT glass | regexfill over 12,505 placements; actual physical-volume names | log line "Adding volumes:" lists `…_front/rear_dome_encapsulation_phys`. If `_body_phys$` matches nothing, read the real PMT volume names from the log (`/control/manual` or a GDML dump) and adjust |
| T5 ²¹⁰Po gun | α through the `alpha` table | visible energy ≈ 0.3–0.5 MeVee |
| T6 (α,n) | `HEPEvt:fill` reads the file; ion codes 9808016 / 9802004 accepted; one HEPEVT event per G4 event | events = NEV; a neutron is present in every event; capture recorded |

**Results, job 15418018 (2026-11-13, sandbox, 20 min, all rc=0; runs/OBD17kt_geo/20261113_geotest_15418018):**

| Test | Result | Verdict |
|---|---|---|
| T1 geo U (20 ev) | 340 ± 9 PE/MeV; E_ν max 3.25 MeV; 20/20 ⁶Li captures, mean 4.9 µs; delayed 261 PE (0.72 MeVee); 4/20 overlap < 1 µs | pass |
| T2 geo Th / reactor (10 + 10) | Th E_ν max 2.21 MeV (≤ 2.26); reactor 387 ± 9 PE/MeV, 9 ⁶Li + 1 H | pass |
| T3 Decay0 + regexfill | Tl-208 and BiPo-214 in the LS: 20/20 triggered. K-40 in acrylic: 1/20 triggered, vertex r = 12.0015 m (inside the 12.000–12.050 m shell). Bi-214 in steel: 0/10 triggered | pass (generators work; low trigger rates are physical) |
| T4 shields / PMT glass | regexfill matched `inner_pmts_{front,rear}_dome_encapsulation_phys` and `inner_pmts_body_phys`; 0/10 triggered each | pass |
| T5 ²¹⁰Po | 197 PE = 0.54 MeVee at 363 PE/MeV | **borderline**: just above the 0.3–0.5 MeVee target |
| T6 (α,n) | 20/20 events, 18 ⁶Li + 2 other captures, prompt 517 PE | pass |

Notes:
- **Summary `"events"` undercounts generic samples.** The macro keeps untriggered events, and `extract_events.py` de-duplicates rows by `evid`, so all untriggered decays collapse into one row (K-40: "events: 1" for 20 decays). True counts are in rat.log (`CountProc: Total # of events N (M triggered events)`). When nothing triggers, the old code also kept one untriggered row as a fake event (the steel, shield and PMT-glass npz files). **Fixed locally on 2026-11-13; not yet pushed or re-run on the cluster:** `select_rows()` drops every `evid < 0` row (ratpac writes untriggered events with evid = subev = -1, `OutNtupleProc.cc:790-793`), and the summary gains `n_generated` and `n_triggered`. Synthetic-layout unit checks pass. IBD output where every event triggers is unchanged. **Correction (same day):** in outntuple, `evid` is the trigger sub-event id (`OutNtupleProc.cc:616`); the MC event is `mcid` (line 401). The first fix (pushed with the signal arrays 15418179-81, code hash 63e1a572…) therefore over-counts `n_generated`/`n_triggered` for IBD chunks whose prompt and delayed trigger separately (386 for 200 events in chunk seed 1200030). The extracted events themselves are correct (`events` = 200; the subev == 0 filter keeps one row per MC event). The mcid-keyed version is local only and gets pushed after those arrays finish, before any background production. For the signal run sets, use `events`, not `n_generated`.
- **"Could not read property SCINT_RISE_TIMEneutron" is harmless.** ratpac 4.4.0 `Materials.cc:496-503` lists only the default, alpha and proton rise-time names as constants, so the neutron one is tried as a vector and skipped. `GLG4Scint.cc:1050-1055` then falls back to `SCINT_RISE_TIME`, which is the same 0.72 ns. "SCINTILLATION_WLS of lab" is stock ratpac.
- **External backgrounds (steel, shields, PMT glass) trigger in < 10 % of decays,** so production needs about 10⁵–10⁶ decays per isotope and volume, or a pre-selection on energy deposited in the LS.

### 7.9 Open questions for the user

1. Which contamination set: the thesis values (KamLAND post-purification LS, unsourced LS K), or KamLAND early-phase (as the OBD sensitivity studies say they assume)? This matters most for LS ²¹⁰Po, which differs 15× between the two sources and sets both (α,n) and the ⁶Li-delayed-like accidentals.
2. ~~Overlap handling~~ **Decided (user, 2026-11-13):** the hackathon data gives one combined 4 ns hit stream per IBD; overlap (< 1 µs) is flagged in truth only. Teams reconstruct **both** the prompt vertex and the neutron capture point, scored together as one combined score. The ²¹⁰Po visible energy (0.54 MeVee, slightly above the 0.3–0.5 MeVee target) is **accepted and documented as an assumption** (SNO+ α Birks constant, no LAB + ⁶Li measurement to tune against).
3. Should the steel tank and buffer oil get contamination values? They are not in the thesis table; JUNO steel values exist.
