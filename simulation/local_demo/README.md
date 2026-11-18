# OBD 17 kt simulation: local one-event demo

This kit runs the same simulation as our cluster production on any Linux workstation, without root or apptainer. It draws:
- the detector geometry;
- one geo-neutrino inverse-beta-decay (IBD) event with its optical photons followed to the PMTs that detected them.

It's meant for checking the simulated detector against the OBD design. Every detector number and its source is in `../docs/DETECTOR_SPEC_VERIFICATION.md` (the reference PDFs are not redistributed).

## What runs

- **Simulation:** **ratpac-two 4.4.0**, the official container `docker://ratpac/ratpac-two:4.4.0@sha256:c85936d5…`, converted to `ratpac-two_4.4.0.sif` (sha256 `3b6cc869a0b17db116a5e2d751b7f6ac534714a5f25e5f00810ff3d6c4d3ecba`). This is the same image and hash as the production on the HPC cluster.
- **Detector:** `../ratdb/OBD17kt/`, the same files as production.
  - Geometry `OBD17kt.geo`: SS tank r 15 m × h 50 m, K-290 buffer oil, acrylic vessel r 12 m × h 44 m, 12,505 × 20″ PMTs in glass shields.
  - Optics, PMT and material tables: `OPTICS_OBD.ratdb`, `PMT_OBD.ratdb`, `MATERIALS_OBD.ratdb`, `ENCAPSULATION_OBD.ratdb`.
- **Macro:** `ibd_demo_1event.mac` = the production macro (`../macros/ibd_geo.mac`) with these settings:
  - 1 event, geo-U spectrum;
  - ⁶Li-loaded LS (`obd_ls_li6_1p0`, 1 wt %);
  - gel-filled shields;
  - LY 10,000 photons/MeV.

  **One difference from production:** optical-photon trajectories are kept, so they can be drawn.

## How to run

```bash
# 1. build the container image (2.9 GB) from the pinned digest:
#    apptainer pull ratpac-two_4.4.0.sif docker://ratpac/ratpac-two@sha256:c85936d537dba4adba050c9fe4dde45a44e57454579ac96756007a925ff4c626
# 2. run one event (unpacks the image to ~/software/containers/ratpac-two_4.4.0.rootfs on first use; needs unsquashfs + bwrap)
SIF=/path/to/ratpac-two_4.4.0.sif ./run_local.sh ibd_demo_1event.mac 20261114 out/ibd_demo.ntuple.root
# 3. dump the event (runs inside the container: PyROOT) and draw it (host: numpy + matplotlib)
R=~/software/containers/ratpac-two_4.4.0.rootfs
bwrap --bind $R / --dev /dev --proc /proc --tmpfs /tmp --bind $PWD/out $PWD/out --ro-bind $PWD $PWD --chdir $PWD/out \
      --unsetenv LD_LIBRARY_PATH --unsetenv PYTHONPATH /bin/bash -c \
      'for f in /.singularity.d/env/*.sh; do . $f; done; exec /ratpac-setup/env.sh python3 '"$PWD"'/dump_event.py ibd_demo.ntuple.root event_dump.npz'
python3 plot_event.py out/event_dump.npz out/figures
```

With apptainer installed, steps 2–3 are just `apptainer exec ratpac-two_4.4.0.sif /ratpac-setup/env.sh rat -s 20261114 -o out.root ibd_demo_1event.mac` (copy `../ratdb/OBD17kt` into the working directory first).

## Reference run (2026-11-14, this machine)

- **Run:** seed 20261114; 60 s wall; 1.6 GB RAM.
- **Output:** kept locally by the authors (not in this repository) (ntuple 24 MB, `event_dump.npz`, `figures/`).
- **The event:**
  - IBD vertex at (−6.97, 1.10, 6.55) m; neutron captured on ⁶Li ≈ 4 cm away, about 3 µs later.
  - **57,432 optical photons** tracked (scintillation + re-emission). 3,455 ended on a PMT; **919 photo-electrons** on **804 PMTs**.
  - Of the photons that produced a PE: 660 prompt (e⁺), 265 delayed (⁶Li(n,α)t). That is consistent with our production averages (≈395 PE/MeV prompt; ⁶Li capture median 230 PE).

## Figures

| File | Shows |
|---|---|
| `figures/geometry.png` | 3-D cut-away of the tank, acrylic vessel / LS target and all 12,505 PMTs, plus an r–z section with dimensions |
| `figures/event_3d.png` | The IBD: vertex (star), capture point (circle), the photons that produced a PE (red = prompt e⁺ light, blue = delayed ⁶Li-capture light) and hit PMTs (marker size ∝ #PE). Each drawn line is the photon's LAST trajectory segment: photons absorbed and re-emitted by the LS start a new track at the re-emission point, which is why some lines don't start at the vertex |
| `figures/event_pmt_map.png` | Unrolled PMT hit map (wall + both caps), coloured by first PE time: prompt (~0 ns) vs delayed capture flash (~3 µs) |

## Known limitations of the model (details in the verification doc)

- The LS absorption and re-emission use ratpac's stock LAB/PPO data. A quick digitisation of the measured OBD-LS transmittance (Sakai 2021, Fig 5.20) suggests the real LS is 2–4× more transparent at 380–450 nm.
- The PMT model is the KamLAND 20″ tube (Ohno 2024, Table 4.2). Ono 2025 mentions the KamLAND2 high-QE tube.
- The PMT coordinates are generated (`../tools/make_pmt_layout.py`); real coordinates are not public.
