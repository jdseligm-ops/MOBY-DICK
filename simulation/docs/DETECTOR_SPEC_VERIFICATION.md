# OBD 17 kt simulation: detector specification verification

Independent check by the SIDERIUS instance, 2026-11-14 (HST), at the user's request ("it is imperative our detector is as correct as possible and variations be explained"). The main session's summary numbers were not taken on trust. Every "source" value below was re-read in the source text.

**How it was checked.**
- **Source text.** The theses and papers in the authors' reference-PDF folder (not redistributed) were converted with `pdftotext -layout`, and each value was located with a page-aware search: `siderius_instance_tools/spec_verify/pgrep.py`.
- **Page numbers** are **PDF pages**. For the theses the printed page is also given where it differs (OHN24 printed = PDF − 10).
- **"Our value"** is what the **production data** used (dataset v3b/v3d/v3e, `detector_json` attribute in the published HDF5: *"OBD17kt v1 geometry, GEL-filled glass shields, LY 10000/MeV, 1.0 wt% ⁶Li LAB+PPO 3 g/L; OPTICS sha256 84128bc2… (LAB re-emission < 340 nm only; PPO scaling 1.2)"*). It was read from `projects/OBD17kt_geo/ratdb/OBD17kt/*.ratdb` and `.geo`. Measured quantities come from the published v3d validation labels (true photoelectrons).

**Source keys** (full citations in `projects/OBD17kt_geo/references/README.md`):
- **OHN24**: T. Ohno, Tohoku M.S. thesis 2024, the 17 kt design.
- **ONO25**: T. Ono, Tohoku M.S. thesis, 1.5 kt structural and optical design.
- **SAK21**: T. Sakai, Tohoku M.S. thesis 2021.
- **ASNE26**: Araki et al., arXiv:2606.20780.
- **JPCS21**: Sakai et al., J. Phys. Conf. Ser. 2156, 012144.

**Status legend.**
- **MATCH**: our value equals the source.
- **VARIATION**: a deliberate difference, with the reason (author or user decision, or a different but defensible source).
- **GAP**: no OBD source; filled by an assumption.
- **CONFLICT**: OBD sources disagree, so the user or the OBD group must choose.
- **MISTAKE**: wrong; to fix.

## Summary of items needing action

| # | Item | Status | Why it matters | Proposed action |
|---|---|---|---|---|
| A | **Which 20″ PMT** (rows P2–P6) | **CONFLICT → user / OBD group** | OHN24 Table 4.2 (our model) describes the old KamLAND 20″ Venetian-blind tube (QE 23 %, TTS 7.7 ns). ONO25 p.50 says the OBD inner detector will use **the 20″ PMT planned for KamLAND2**, a high-QE tube. Hyper-K sources describe the 20″ box-and-line tube (R12860) as improving peak QE from 22 % to 30 % and TTS from 6.73 to 2.59 ns FWHM over the Venetian-blind type (from a search result; to confirm from a primary source). A Tohoku KamLAND2 thesis credits the high-QE PMT with ×1.9 light collection. That changes light yield, vertex resolution and PSD, and it is the baseline for any coverage study. | Ask the OBD group which tube is baseline. Run the coverage study with both PMT models, or with the KamLAND2 one if confirmed. |
| B | **LS optical absorption / re-emission** (row O3) | **GAP with a large measured effect → user** | Stock SNO+ PPO/LAB data, not OBD-LS (SAK21 Figs 5.19/5.20 transmittance not digitised; physics audit MAJOR #2). Measured on the published data with **true photon times and true vertices**: ~40 % of prompt PE arrive > 30 ns after the onset for **both** positrons and proton recoils, so p/e PSD tops out at **~25 % proton-recoil rejection at 95 % signal efficiency**. The emission profiles alone would give a tail fraction of 0.10 vs 0.19. It also sets the photon-arrival smearing for the vertex fit. | Digitise SAK21 Figs 5.19/5.20 (and ONO25 ch. 5 for K-290/acrylic); refit absorption and re-emission; re-simulate. Make it the first item of the coverage study (an optics-only variant). **Quick look done (2026-11-14, main session; `references/digitized/SAK21_fig5.20_T7m_quick.csv`)**, by-eye reading of SAK21 Fig 5.20 (PDF p.50; 7 m transmittance of undoped OBD-LS extrapolated from 9 cm, large error bars). Model vs measured T(7 m) is 0.09 vs ~0.40 at 390 nm, 0.28 vs ~0.57 at 400 nm, 0.53 vs ~0.78 at 430 nm, so the real LS is **2–4× more transparent at 380–450 nm**. That holds even at the lower edge of the error bars at 390–420 nm. Weighted by the emission spectrum, about 2.6× more primary light reaches 12 m unattenuated (0.148 vs 0.057). Most light is still absorbed and re-emitted within 12 m (~85 % vs ~94 %), so the real-detector PSD and timing should be somewhat better than simulated, not dramatically. The re-emission probability (0.898, consistent with the PPO quantum yield) is not the issue; the absorption lengths are. |
| C | **Detector-model doc out of date** (`projects/OBD17kt_geo/docs/OBD17kt_DETECTOR_MODEL.md` §3, §6) | **MISTAKE (documentation only)** | It still says air-filled shields, flat LAB re-emission 0.751 and PPO scaling 2.5/3. Production used gel shields, re-emission < 340 nm only, and scaling 1.2. The simulation is right; the doc is not. | Main session to update §3/§6 to the production configuration (with the `detector_json` string). |
| D | **Shield interior: gel** (row P8) | **GAP (user decision 2026-11-13)** | No OBD source says air, gel or vacuum. Gel roughly doubles collected light vs air (371 → 691 PE/MeV in the v1 test). | Confirm with the OBD group; state it in every dataset description (already in `detector_json`). |
| E | **TTS convention** (row P5) | **GAP (user-settled as FWHM)** | OHN24 p.43 gives "7.7 ns" without FWHM/σ. Read as σ, the timing would be 2.4× worse. | Keep FWHM (consistent with the R3600-type datasheet of 5.5 ns); ask the OBD group to state it in the next design note. |

No other MISTAKE was found. Every geometry number matches OHN24 Table 5.1.

## 1. Geometry and materials

| # | Spec | Our value (production) | Source value [key, page] | Status | Explanation |
|---|---|---|---|---|---|
| G1 | LS volume | cylinder r 12.000 m, h 44.000 m (19,900 m³) | r 12 m, h 44 m [OHN24 Table 5.1, PDF p.54 / printed p.44] | MATCH | |
| G2 | Acrylic vessel | r 12.000/12.050 m, h 44.0/44.1 m (5 cm wall), ρ 1.18, C₅H₈O₂ | inner 12 m / outer 12.05 m; 44 / 44.1 m; ρ 1.18; C₅H₈O₂ [OHN24 T5.1, p.54] | MATCH | ONO25's structural study (1.5 kt) gives 7 cm unsupported or 1 cm with 8 steel pillars Ø 0.2 m [ONO25 p.104]; no 17 kt structural result exists, so OHN24 is used |
| G3 | Steel tank | r 15.000/15.016 m, h 50.000/50.032 m, `stainless_steel` | inner 15 m / outer 15.016 m; 50 / 50.032 m; ρ 7.938, steel 99 % + C 1 % [OHN24 T5.1, p.54] | MATCH | Composition: ratpac stock stainless steel instead of 99 % Fe-alloy + 1 % C; no effect on optics |
| G4 | Buffer thickness | 3.0 m radial, 2.95 m axial | 3 m, "optimised to balance accidental backgrounds and light collection" (1.5 kt) [ASNE26 p.8] | MATCH | Follows from G2/G3 |
| G5 | Buffer material | `obd_k290`: ρ 0.88817, C 85.6 % / H 14.4 % | Hicall **K-290** chosen on transmittance, index and density [ONO25 p.2, p.67]; ρ **888.17 kg/m³ at 4 km depth** [ONO25 p.75, p.90]. OHN24 T5.1 lists "C₂₅H₅₂, ρ 0.76" [p.54] | VARIATION (sources disagree; newer measured value used) | ONO25 measured K-290 at deep-sea conditions; OHN24's 0.76 is a generic paraffin. Optical effect small; mass ratio matters for buoyancy, not physics here |
| G6 | LS density | 0.89248 g/cm³ → 17.8 kt | **892.48 ± 0.62 kg/m³ at 4 km** and 870.80 at 2 °C / 1 atm [ONO25 p.75, p.90]; OHN24 T5.1 lists 0.87 (LAB) [p.54] | VARIATION (in-situ measured value) | 17.8 kt instead of 17.3 kt at 0.87. Target protons scale by +2.5 %; the IBD rates are taken from ASNE26 Table III, so they are unaffected |
| G7 | LS composition | LAB + PPO 3 g/L + **⁶Li 1.0 wt %** (pure ⁶Li, no counter-ion) | LAB + 3 g/L PPO [JPCS21 p.5; OHN24 T5.1 p.54]; "dopant not fixed; ⁶Li or Gd discussed for directionality" [ASNE26 p.9] | VARIATION (user decision 2026-11-13) | ⁶Li at 1.0 wt % is the task's choice. No LAB scintillator at that loading has been demonstrated (PROSPECT 0.082 wt %; DETECTOR_MODEL §7.2) |
| G8 | Light yield under ⁶Li loading | 10,000 photons/MeV (undoped value) | — | GAP | Loading usually lowers yield (PROSPECT ≈ 8,000/MeV); kept at the undoped value (user-agreed) |
| G9 | Tank inner surface | black liner, reflectivity 0 | black sheet, reflectivity 0 % [ONO25 p.104] | MATCH | |
| G10 | Outside the tank | ratpac `salt_water` | seawater ρ 1025 kg/m³ (load model) [ONO25 p.90] | MATCH (in substance) | |
| G11 | Outer detector | not modelled | **3,850** 13″ PMTs with shields (KM3NeT-style) [OHN24 p.44 / printed 34] | VARIATION (scope) | A muon veto, irrelevant to IBD reconstruction in the inner detector |
| G12 | Support pillars, ports, compensation hose | not modelled | 8 pillars Ø 0.2 m in one 1.5 kt option [ONO25 p.104]; light-collection change between options is not significant [ONO25 p.106] | VARIATION (scope) | Small shadowing |

## 2. Photosensors

| # | Spec | Our value | Source value [key, page] | Status | Explanation |
|---|---|---|---|---|---|
| P1 | Number of inner PMTs | 12,505 × 20″ | **12,505** [OHN24 p.42 / printed 32; p.53]; "about 12,000" [ONO25 p.50] | MATCH | |
| P2 | PMT type | ratpac `r3600` shape (KamLAND-type 20″ Venetian blind) | OHN24 Table 4.2 [p.43]: KamLAND 20″, Venetian blind, 13 stages. **ONO25 p.50: "the 20-inch PMT planned for use in KamLAND2"** | **CONFLICT** (item A) | See summary A. The R3600-02 datasheet itself gives 11 stages, P/V 1.7, TTS 5.5 ns (projects/OBD17kt_ml/docs/DIGITIZER.md) |
| P3 | Effective photocathode / coverage | ratpac r3600 effective Ø ≈ 484 mm → **≈ 39 %**. Doc quotes 35.4 % for Ø 460 | Ø **460 mm** effective [OHN24 T4.2 p.43]; photocathode Ø ≈ 50 cm [SAK21 p.51]; PMT hemisphere outer radius 25.04 cm [OHN24 T5.1 p.54]; 1.5 kt coverage ≈ 40 % with ~3,000 PMTs [SAK21 p.25] | VARIATION (minor, modelling) | The ratpac bulb is ~5 % larger in diameter than Ø 460. Coverage in the sim is ~39 %, not 35.4 % (physics audit #7). Either is within the OBD range (35–40 %); state 39 % as the simulated value |
| P4 | Quantum efficiency | ratpac R3600 curve scaled to **23 % at 390 nm** | **23 % at λ = 390 nm** [OHN24 T4.2 p.43] | MATCH (value); GAP (curve shape) | Spectral shape from ratpac stock |
| P5 | Transit-time spread | Gaussian σ 3.27 ns (7.7 ns read as FWHM) | "**7.7 ns**", convention not stated [OHN24 T4.2 p.43] | GAP (item E) | |
| P6 | Dark rate | 40 kHz per PMT, uniform | **40 kHz** [OHN24 T4.2 p.43] | MATCH | |
| P7 | Transit time, P/V, single-PE shape | transit time is a constant offset (irrelevant); SPE σ/μ 0.50; pulse FWHM 17.6 ns (lognormal fit to R3600 18.8 ns) | 90 ns; P/V 1.5 [OHN24 T4.2 p.43] | MATCH / literature | SPE shape from Okajima et al. PoS(PhotoDet2015)015 (DIGITIZER.md); OBD gives none |
| P8 | Pressure shield | borosilicate sphere, inner r 350 mm, outer r 360 mm, 10 mm; **gel-filled front dome** | glass sphere, inner radius 35 cm, outer 36 cm, ρ 2.4 [OHN24 T5.1 p.54]. (1.5 kt design: ID 67 / OD 70 cm, Okamoto glass [ONO25 p.91]) | MATCH (size); GAP (interior, item D) | |
| P9 | PMT layout | generated: 79 wall rings × 125 + 2 × 1,315 cap; min spacing 728 mm (> 720 mm shield) | no coordinates published | GAP | Shields cover 87 % of the wall area |

## 3. Optics and light yield

| # | Spec | Our value | Source value [key, page] | Status | Explanation |
|---|---|---|---|---|---|
| O1 | Scintillation yield | 10,000 photons/MeV | "about 10,000 photons/MeV" [ONO25 p.106] | MATCH | |
| O2 | Refractive index at 380 nm | LS 1.523, K-290 1.496, acrylic 1.511 (stock curves scaled) | 1.523 / 1.496 / 1.511 (LS and K-290 measured at 2 °C) [ONO25 p.71] | MATCH | |
| O3 | LS absorption and re-emission spectra | stock SNO+ LAB + PPO (PPO scaled to 3 g/L: ABSLENGTH_SCALING 1.2). LAB re-emission 0.7508 below 340 nm, 0 above. PPO re-emission 0.898 to 430 nm | OBD-LS transmittance measured [SAK21 Figs 5.19/5.20] but **not digitised** | **GAP (item B)** | Measured consequence: ~40 % of prompt PE > 30 ns late for e⁺ and p alike; PSD capped at ~25 % p-recoil rejection at 95 % (true times) |
| O4 | K-290 and acrylic absorption | stock `mineral_oil` / `acrylic_uvt_good` | measured spectra in ONO25 ch. 5 figures (K-290 transmittance, acrylic attenuation) | GAP | Digitise with O3 |
| O5 | Light collected (prompt) | **measured on the published data: median 395 PE/MeV** (all geo-ν prompts, visible E = T_e⁺ + 1.022 MeV); **337 PE/MeV** for r < 8 m, \|z\| < 18 m. ⁶Li capture flash: median **230 PE** | target **450 p.e./MeV** "comparable to KamLAND" [ASNE26 p.8; ONO25 p.87]. ONO25 Geant4: ≈ **500 p.e./MeV** from a ~5 % photon detection rate × 10,000/MeV [ONO25 p.106, Fig. 7.20 p.106] | VARIATION (explained) | ONO25's number is for the **1.5 kt** geometry (6 m vessel radius, so half our path length) with its own optics. Our 17 kt has twice the path, stock optics (O3) and QE 23 % (P2). With the KamLAND2 high-QE PMT (item A) it would plausibly exceed 450 |
| O6 | Temperature effect on yield | not applied | +8.6 % light at 4 °C vs 20 °C after PMT correction [ASNE26 p.6] | VARIATION (conservative) | Would add ~9 % light |
| O7 | Particle time profiles and quenching | e⁻: SNO+ LAB+PPO; α (and, by ratpac's mass rule, t/d): α profile; p: α profile; kB e⁻ 0.0798, α 0.071, p/d/t 0.096 mm/MeV | none in OBD sources | GAP (literature-sourced) | ratpac-two 4.4.0 picks the table by mass (`PhysicsList.cc:184-187`), so tritons use the α-like profile. ⁶Li capture and ²¹⁰Po then have identical pulse shapes. The p = α profile and triton kB are assumptions (DETECTOR_MODEL §7.3) |
| O8 | Known Geant4 defect | ~5 × 10⁻⁴ of ⁶Li captures get a spurious ~20 MeV γ (G4ParticleHP final state) | — | Documented (kept by user decision) | In the task card |

## 4. Backgrounds and rates

| # | Spec | Our value | Source value [key, page] | Status | Explanation |
|---|---|---|---|---|---|
| B1 | Acrylic U / Th / K | 1.0e-11 g/g each | 1.0e-11 each (JUNO values) [OHN24 Table 5.4, PDF p.60] | MATCH | |
| B2 | LS U / Th / K | KamLAND early phase: 3.5e-18 / 5.2e-17 / 2.7e-16 (K = early-phase upper limit) | 5.0e-18 / 1.3e-17 / 1.0e-18 ("KamLAND"; post-purification U/Th; **K has no source**) [OHN24 T5.4 p.60] | VARIATION (user decision 2026-11-13) | The OBD sensitivity studies say they assume early-phase KamLAND (DETECTOR_MODEL §7.5). The thesis K value is unsourced |
| B3 | PMT glass, shield glass, steel, buffer, seawater ⁴⁰K | geometry and optics simulated; **not simulated as background sources** | PMT 1.5e-7 / 2.4e-7 / 1.0e-8; shield 1.0e-8 each [OHN24 T5.4 p.60]; singles rates in LS: acrylic 43.52 Hz, LS 5.36e-3 Hz, PMT 6.03 Hz, shield 1.22 Hz [OHN24 Table 5.5 p.60] | VARIATION (scope; documented in the task card) | PMT + shield singles (7.25 Hz) are 1/6 of the acrylic rate in the thesis estimate; they mostly deposit near the wall |
| B4 | ²¹⁰Po in LS | 70 Bq | I_source = **5.9 Bq per 1.5 kt OBD** (KamLAND scaled) [SAK21 p.56]; × 17.8/1.5 = 70 Bq | MATCH (derived) | KamLAND early-phase ²¹⁰Pb would give ~1 kBq (15× more); DETECTOR_MODEL §7.5 open question |
| B5 | ¹³C(α,n) rate | 127 /yr **produced** (70 Bq × 5.75e-8 n/α) | 55.47 /yr full volume [OHN24 Table 5.6, p.63] (ASNE26 Table III quotes the same per DATASET.md; its table is not in the extracted text, so not re-read), obtained by **scaling Sakai's 1.5 kt simulation** [OHN24 p.56] | VARIATION (different quantity) | OHN24's number counts events **passing its coincidence selection** (undoped-LS delayed windows); ours is the production rate before selection. The two are not directly comparable |
| B6 | ¹³C(α,n) prompt branches | n–p recoils, ¹²C(n,n′) 4.43 MeV γ, ¹⁶O* 6.049 (e⁺e⁻) / 6.130 (γ) | the same four prompt channels [OHN24 p.56, Eqs. 5.1–5.4] | MATCH | Cross-section proxies documented (DETECTOR_MODEL §7.6) |
| B7 | Cosmogenic ⁸He/⁹Li | not simulated | 19 and 180 /yr produced (1.5 kt, FLUKA); a 5 s full-detector veto after each muon reduces them to ~0 [OHN24 p.57] | MATCH (in substance) | Justifies leaving them out |
| B8 | Signal and reactor rates | geo-U 100.09, geo-Th 24.98, reactor 67.84 /yr | same [OHN24 Table 5.6 p.63] (ASNE26 Table III per DATASET.md, not re-read) | MATCH | |
| B9 | Dark-noise model | 40 kHz/PMT, uniform in time | 40 kHz [OHN24 T4.2 p.43] | MATCH | No afterpulses or flashers (task-card limitation) |

## 5. Comparison with other large liquid-scintillator detectors

Collected by a web-research subagent from the downloaded papers, with page tags (pN = PDF page). I spot-checked five values in the source text: JUNO 75.2 % coverage [J21], JUNO 1785 PE/MeV [J25], Borexino ≈ 500 p.e./MeV [B09], Daya Bay 162/163 p.e./MeV [D12], KamLAND 12 cm/√E [K08]. All five were confirmed.

| Detector | Photosensors | Coverage | QE / PDE | Light yield | Energy resolution | Vertex resolution | Target |
|---|---|---|---|---|---|---|---|
| **OBD 17 kt, our model** | 12,505 × 20″ R3600-type (Venetian blind) in glass shields (gel) | ≈ 39 % simulated (35.4 % for Ø 460) | 23 % at 390 nm | **395 PE/MeV** measured (337 central); ⁶Li capture 230 PE | – | ML 0.59 m median 3-D (geo-ν prompts, 1–2.6 MeV); classical fit 0.85 m | 17.8 kt LAB + PPO 3 g/L + ⁶Li 1 wt % |
| **OBD 1.5 kt design** | ~3,000 × 20″ (KamLAND2-type per ONO25 p.50) | ≈ 40 % [SAK21 p.25] | – | target 450 [ASNE26 p.8]; ≈ 500 simulated [ONO25 p.106] | – | – | 1.5 kt LAB + PPO 3 g/L |
| **KamLAND** | 1,325 × 17″ + 554 × 20″ = 1,879 [K03 p2; K13 p3] | 22 % (17″ only), 34 % total [K03 p2; K05 p2] | ≈ 20 % at 340–400 nm [KS04 p3] | ≈ 300 p.e./MeV, centre, 17″ only (2002) [K03 p2; KS04 p8] | 6.4 %/√E [K13 p3] | ≈ 12 cm/√E [K08 p2; K13 p3] | 1 kt; dodecane 80 % + PC 20 % + PPO 1.36 g/L [K08 p1] |
| **Borexino** | 2,212 × 8″ ETL 9351; 1,800 with concentrators [B09 p5; B14 p4] | 29.8 % effective [BC03 p6] | 26.5 % at 420 nm typical [B09 Tab.1] | ≈ 500 p.e./MeV [B09 p13; B14 p14] | ≈ 5 % at 1 MeV [B09 p6] | 9 cm (x,y) at ~1 MeV [B14 p14] | 278 t PC + PPO 1.5 g/L [B14 p4] |
| **JUNO CD** | 17,612 × 20″ (5,000 HPK dynode + 12,612 NNVT MCP) + 25,600 × 3″ [J21 p27–28, p40] | 75.2 % (20″) + 2.7 % (3″) [J21 p28] | 20″ average PDE 29.1 % [J21 p40] | **1785 PE/MeV measured** at the centre [J25 p8] | 3.4 % for 1.022 MeV at the centre, measured [J25 p8] | simulation only [J21 p53] | 20 kt LAB + PPO 2.5 g/L + bis-MSB 3 mg/L [J21 p27] |
| **Daya Bay AD** | 192 × 8″ R5912 [D12 p5] | ≈ 12 % effective with reflectors [D16 p17] | > 25 % at 420 nm (requirement) [D16 Tab.7] | 162–163 p.e./MeV (⁶⁰Co) [D12 p12] | (7.5/√E + 0.9) % [D12 p15] | ≈ 25 cm (⁶⁰Co; proceedings) [D14 p1] | 20 t Gd-LAB per AD [D12 p4] |
| **SNO+** | 9,362 × 8″ R1408 with concentrators [S21 p10, p25] | ≈ 54 % effective [S21 p25] | detection efficiency ≈ 15 % overall [R17 p16] | ≈ 210 hits/MeV (LAB+PPO), 320 with bis-MSB (hits, not p.e.) [S25a p3; S25b] | ≈ 6.5 %/√E [S25a p3] | 12 cm per axis at 2.5 MeV [S25a p3] | 780 t LAB + PPO 2.2 g/L [S25a p3] |

**What the comparison says about our detector.**
- Our 395 PE/MeV sits between KamLAND (~300) and Borexino (~500), below the OBD 450 target, and far below JUNO (1785). JUNO reaches that with 75 % coverage, PDE ~29 % and a 20.6 m attenuation length at 430 nm [J25].
- Our ~0.6 m vertex median is not directly comparable: it is a median 3-D error at 1–2.6 MeV in a 24 m × 44 m volume. KamLAND's ~12 cm/√E is a per-axis σ in a 13 m balloon. Even so, it says the optics model (item B) and photon statistics, not only coverage, set our floor.

**Survey references.**
- K03 hep-ex/0212021; K05 hep-ex/0406035; K08 arXiv:0801.4589; K13 arXiv:1303.4667; KS04 physics/0404071; KA14 arXiv:1409.4515
- B09 arXiv:0806.2400 (NIM A 600, 568); B14 arXiv:1308.0443; BC03 physics/0310076
- J21 arXiv:2104.02565 (PPNP 123, 103927); J22P arXiv:2205.08629; J21S arXiv:2102.11538; J24 arXiv:2405.17860; J25 arXiv:2511.14590
- D12 arXiv:1202.6181; D16 arXiv:1508.03943 (NIM A 811, 133); D14 arXiv:1402.7277
- S21 arXiv:2104.11687 (JINST 16 P08059); S25a arXiv:2505.04469; S25b arXiv:2511.11856; SNO00 nucl-ex/9910016; R17 arXiv:1710.03334
- PMT model context (item A): Hyper-K/Hamamatsu box-and-line 20″ (R12860): QE 22 → 30 %, TTS 6.73 → 2.59 ns FWHM vs the Venetian-blind type (search result; confirm from a primary source before quoting in the group doc). KamLAND2 upgrade plan with high-QE PMT (×1.9 light), mirrors (×2) and LAB-LS (×1.4): Tohoku thesis https://www.awa.tohoku.ac.jp/Thesis/ThesisFile/yoshida_yuki_m.pdf.

**Values the survey could not source:**
- KamLAND p.e./MeV with all PMTs;
- bare coverage for Borexino and Daya Bay;
- the SNO+ R1408 peak QE;
- a measured JUNO vertex resolution.

Disagreements between sources are listed in the survey: for example J24 credits KamLAND with 250 PE/MeV while the primary papers say ~300, and SNO+ reports hits rather than p.e.
