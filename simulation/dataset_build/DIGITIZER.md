# Digitiser model (`tools/digitize.py`, version 0.2, 2026-11-13)

The digitiser turns simulated photoelectrons (ratpac `*.events.npz`) into the zero-suppressed 4 ns PMT waveforms that a large liquid-scintillator detector's DAQ would record. Those waveforms are the Stage 1 input and the hackathon input.

Each parameter below is a `DigiConfig` field. **Decision** means the user made the call. **Sourced** means a citation backs it. **Assumption** means no OBD source exists and we chose the value.

## Parameters

| Field | Value | Status | Basis |
|---|---|---|---|
| `sample_ns` | 4 ns (250 MS/s) | Decision (2026-11-13), assumption | User: "conservative ADC data transfer". No OBD paper names a digitiser. Hanohano mentions "cables … to digitizer, and fiber optics thereafter" (0810.4975). DOANE (2606.20780) mentions "neighborhood digitizers feeding fiber optics". |
| `adc_bits` | 14 | Assumption | CAEN V1725 class (14 bit, 250 MS/s, 125 MHz bandwidth). |
| Input range | 0.5 Vpp, so 1 LSB = 30.5 µV | Assumption (ours) | Chosen so that a 0.25 PE threshold sits about 5σ above the noise. At 2 Vpp it would be about 3σ, giving thousands of noise crossings per window. Saturation is about 120 PE per channel. The nearest PMT sees about 15 PE from an 8 MeV event 2.6 m away [derived]. |
| `adc_per_pe` | 130 counts at the SPE peak | Derived and assumed | SPE peak about 4 mV at gain 1e7 into 50 Ω (from the fitted shape and Q = 1.602 pC). Short cables to local digitisers are assumed, as in the OBD concepts. In-situ values: Super-K about 2.8 mV, KamLAND about 2 mV. |
| Pulse shape | Lognormal pdf, `ln_mean_ns` 100.7, `ln_width` 0.0748, peak 20 ns after the photoelectron | Fit to sourced numbers | R3600 SPE rise / fall / FWHM = 10.6 / 13.2 / 18.8 ns (Okajima et al., PoS(PhotoDet2015)015, Table 2). The Hyper-K Design Report (arXiv:1805.04163, p.109) gives 10.6 ns rise and 18.5 ns FWHM. The fit gives 11.5 / 13.9 / 17.6 ns. A pure lognormal can't match a flat-topped pulse exactly. Negative polarity, stored sign-flipped. No overshoot (DC coupling assumed). |
| `spe_sigma` | 0.50 | Sourced | R3600 σ/μ is 53% (Okajima Table 3) and 50% (Hyper-K DR, p.109 and Table XVII). It replaces the v1 value of 0.30. |
| `noise_adc` | 6.5 counts (0.05 of the SPE peak) | Assumption, bracketed | CAEN V1725 open input: 3.4 LSB at 0.5 Vpp (0.025 SPE). JUNO in situ: about 0.4 mV (about 0.06–0.1 SPE; arXiv:2208.08264). KamLAND2 front-end target: < 0.1 mV for a 1/4 PE threshold (JINST 19 P03013). |
| `zs_threshold_adc` | 33 counts (0.25 PE) | Sourced convention | Super-K: 0.25 PE (−0.69 mV), arXiv:1307.0162. KamLAND2: 1/4 PE. Hamamatsu TTS and dark rates are quoted at 1/4 PE. KamLAND used 0.15 PE and Borexino 0.2, which serve as sensitivity variants. |
| `zs_pre`, `zs_post` | 2 / 4 samples | Assumption | Context kept around each above-threshold sample. |
| TTS | σ = 3.27 ns, applied in ratpac (`pe_t`) | Sourced (settled) | OBD table: 7.7 ns FWHM (Ono T., Table 4.2). The measured R3600 core σ is 2.1–2.2 ns, with an asymmetric distribution. |
| `dark_rate_hz` | 40 kHz per PMT | Sourced (settled) | OHN24. |
| `trig_window_ns`, `trig_nhit` | 100 ns, 120 PEs | Assumption | Dark noise alone gives about 50 ± 7 PEs per 100 ns over 12,505 PMTs. ⁶Li captures give a median of about 130 signal PEs in their best 100 ns (1st percentile about 93), plus dark noise. |
| Readout window | −200 / +1000 ns around the trigger (300 samples) | Assumption | The next trigger can fire only after the window ends. |
| `dark_margin_ns` | 2 µs around each cluster of light | Implementation | Dark noise is generated only near light, because dark noise alone cannot trigger. Late decays up to about 1 s after (α,n) events made full-gap generation impossible (out of memory on the cluster, job 15420264). |

**PMT model caveat.** The OBD thesis table (Ono Takeru, Table 4.2) describes the "KamLAND 20-inch PMT": 13 stages, P/V 1.5, TTS 7.7 ns FWHM, transit time 90 ns. The R3600-02 datasheet gives 11 stages, P/V 1.7, TTS 5.5 ns. Ono Takanobu (§4.2) says the OBD would use the tube "planned for KamLAND2". The R3600 values here are an approximation.

## What is not modelled

- Afterpulses, pre-pulses, late pulses and the low-charge SPE tail.
- Baseline overshoot and the anti-aliasing filter (the 125 MHz bandwidth adds about 2.8 ns in quadrature to the rise).
- Channel-to-channel gain variation and dead channels.
- Electronics crosstalk.
- Dark-noise correlations (flasher-like bursts).

## Versions

- **0.1:** provisional ratpac stock lognormal (10.5 ns, width 0.15), SPE σ 0.3, 20 counts per PE. Used only for the provisional Stage 1 run `stage1_prov_d1b`.
- **0.2:** the sourced R3600 values above.
