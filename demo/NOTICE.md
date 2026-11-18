# Demo sample: licence and origin

These files are a subset of the dataset "OBD 17 kt geoneutrino IBD selection and vertex reconstruction", Zenodo DOI 10.5281/zenodo.24322961. They are licensed under **Creative Commons Attribution 4.0 International (CC-BY-4.0)**, https://creativecommons.org/licenses/by/4.0/. If you use them, cite the Zenodo record. The repository's GPL-3.0 licence covers the code, not these data files.

| File | What | md5 |
|---|---|---|
| `demo_000.h5` | The first 200 examples of the published validation file `val_000.h5` (md5 `b4087fd65a8e38a5b1360fff1377c40c`). That file is stored in random order, so these examples are a random sample. Same layout as the published file. | `5ee4c5d94f10356e282a50239ca8c387` |
| `demo_000.labels.h5` | The same 200 rows of `val_000.labels.h5` (md5 `cad0513b6c09d6198b62ef19c58d34b6`) | `097e8422c5426b1e15bc53c9788dd4c2` |
| `pmt_geometry.h5` | Identical to the published `pmt_geometry.h5` | `19e3216ca53ea47ca20b1824fe0415c3` |

The sample was cut with `python -m obd_runner.cut_sample --wave val_000.h5 --labels val_000.labels.h5 --n 200 --out demo/demo_000`.

`python run.py demo` runs the model on this sample to show that it works. **The demo claims no score.** 200 examples cannot resolve the task metrics, and the S/B = 1 selection in particular needs the full validation file.
