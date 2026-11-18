# Physics audit of the OBD17kt_geo simulation (2026-11-13, read-only)

Requested by the user before more cluster work. The analysis scripts are kept locally by the authors (not in this repository).

- **Verified:** read from the ratdb files, the ratpac 4.4.0 source, and the 200-event dev samples.
- **Inferred:** a photon-transport toy using the configured optics, checked against the sample (re-emitted share 0.86 vs 0.83; median delay 34.8 vs 37.4 ns at 10–14 m).
- **Literature:** values marked "from memory" were not re-checked against papers.

**Verdict: nothing is BLOCKING.**
- Geometry, the group velocity in the LS (n_g 1.60–1.63, i.e. 5.3–5.45 ns/m), the light-yield chain, the neutron physics and the α/t pulse shapes are correct.
- A vertex time-likelihood on truth timing reaches ~15 cm (optimistic), so the ~1 m from the simple fit is a limit of that fitter.
- The existing output is usable as a *self-consistent model detector*. It is not a realistic OBD optical model.

## Findings

| # | Item | Severity | Detail | Fix |
|---|---|---|---|---|
| 1 | LAB re-emission probability | **MAJOR** | 0.7508, flat over 100–1000 nm (`OPTICS_OBD.ratdb:40,99`; `make_obd_ratdb.py:146-149`; stock is 0.540, also flat). It applies to any photon LAB absorbs (`GLG4Scint.cc:360-388`), and LAB absorption is 4–7.5 m at 360–390 nm. As a result, 82 % of detected PE are re-emitted, mostly metres from the vertex. Median delay over straight-line time of flight: re-emitted photons 48 ns, all photons 38.6 ns. The re-emitted light also inflates the PE yield (~40 % of PE). | Make it wavelength-dependent: 0.751 below ~340 nm, 0 above. Toy: light ×0.57 at 12 m; median delay 35 → 22 ns. |
| 2 | PPO absorption tail and missing OBD-LS absorption data | MAJOR (uncertain) | Stock SNO+ PPO absorption with re-emission probability 0.898 out to 430 nm. Only ~10 % of primary light survives 12 m without absorption. Sakai 2021 Figs 5.19/5.20 (OBD-LS transmittance) are not digitised. | Add the LS to GAP 2. Optionally make PPO absorption non-radiative above ~380–390 nm. Toy: light ×0.35 and median delay ~14 ns at 12 m. |
| 3 | PPO `ABSLENGTH_SCALING` | MINOR | [1.0, 0.833] gives an effective 2.08 g/L. ratpac divides by the scaling (`Materials.cc:557`), so 3 g/L needs 1.2. The DETECTOR_MODEL §3 text repeats the error. | Set it to 1.2. Toy: light −4 %, delay +1.7 ns. |
| 5 | PE yield | Note | With item 1 fixed, the same settings give ~200–220 PE/MeV with air shields and ~400 with gel. | User choice. |
| 7 | Photocathode | MINOR | ratpac r3600 has an effective diameter of ~484 mm against φ460 (OHN24). Coverage ~39 % vs 35.4 %. | Optional |
| 9–11 | K-290, acrylic, glass shield optics | MINOR | Stock substitutes; no Rayleigh scattering in K-290; the shield skin is ground (polish 0.9). | Digitise ONO25 Fig 5.4 / 7.1 (optional). |
| 13 | Neutron end point in `extract_events.py:160-166,201-203` | **MAJOR (truth labels only)** | It takes the last point of the *primary* neutron track. For (α,n) the primary ends at the first inelastic scatter. 20/599 (α,n) events have a "capture" at 0.3–9 ns with n_target = 3, and all their PE are flagged delayed. IBD samples are unaffected. | Follow the neutron's descendants to the α+t, d or γ capture vertex. Re-extraction is enough while the ntuples exist. |
| 14 | TTS convention | MINOR | 7.7 ns (OHN24 Table 4.2) was read as FWHM (σ 3.27 ns). If it is σ, timing is 2.4× worse. | Confirm with the user. |
| OK | Geometry (OHN24 Table 5.1); no shield overlaps (min PMT spacing 727.9 mm vs 720 mm shields); buffer and acrylic do not scintillate; light-yield chain consistent (10,000/MeV, QE 23 % at 390 nm); ⁶Li captures 96 %, τ 4.94 µs, displacement ~43 mm; ⁶Li and ²¹⁰Po light have the same α-type time profile | | | |

**Minimal re-simulation if the optics are fixed:**
1. `make_obd_ratdb.py`: wavelength-dependent LAB re-emission (optionally also PPO above ~390 nm), and PPO scaling 1.2.
2. Regenerate `OPTICS_OBD.ratdb`.
3. Re-run tests T1/T5.
4. Choose the light yield or shield option.
5. Re-simulate every sample, then rebuild everything downstream.

## Addendum 2026-11-14: non-physical bright neutron captures (Geant4 NeutronHP), about 5e-4 of events

Found while checking the task's pulse cap: the largest examples are not pile-up. They are two-window IBD/(α,n) events whose CAPTURE window holds 7,000–14,000 real PE, against ~260 for a normal ⁶Li capture.

Inspection (job 15435142, `projects/OBD17kt_ml/tools/inspect_events.py`) of the 7 cases in v3c val (out of 13,000 IBD/(α,n)):
- geoU s4100188/133, s4100488/46, s4100491/7; geoTh s4200138/8; reactor s4300058/111; alphan s5100138/323, s5100146/328.
- Total scintillator edep: 26–32 MeV (one at 14.8 and one at 16.2). The expected values are 6.4 (geo), ~8–12 (reactor) and 12.3 ((α,n)). So 8–20 MeV is deposited at capture time that energy conservation does not allow: n + ⁶Li → α + t has Q = 4.78 MeV and no γ.
- In all 7, the neutron track ends via `neutronInelastic`, the NeutronHP channel that handles ⁶Li(n,t)α, so this is also the normal ending. The delayed light comes within ~500 ns of the capture and is mostly heavy-ion ionisation (`ionIoni`). That points to a wrong final state sampled by Geant4 NeutronHP for this reaction, a known class of energy-non-conservation issues in G4ParticleHP final-state handling.
- The rate is about 5e-4 per neutron capture on ⁶Li, the same for signal and (α,n).

Status: reported to the user (keep and document, or drop with a kinematic/energy-conservation cut). See PICKUP.
