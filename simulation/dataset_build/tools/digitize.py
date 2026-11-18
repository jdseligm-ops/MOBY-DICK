#!/usr/bin/env python3
"""Photoelectrons -> digitised PMT waveforms (4 ns / 250 MS/s), as a large LS detector's DAQ would record them.

Model (every number is a DigiConfig field; the provenance of each value is in docs/DIGITIZER.md):
  1. Dark noise: Poisson PEs at `dark_rate_hz` per PMT, uniform in time over the example's span (+ margins),
     uniform over all PMTs. Ratpac simulates no dark noise, so these are the only noise PEs (truth label 0).
  2. Every PE gets a gain g ~ Normal(1, spe_sigma), clipped at 0 (the SPE charge spread), and the same PMT
     pulse template. Noise PEs are treated exactly like signal PEs (same gain spread, same pulse, same clock).
  3. A global sampling clock: one random phase per example, so physics times are not aligned to the samples.
  4. Trigger: hit count. A trigger fires when `trig_nhit` PEs fall within `trig_window_ns`. The readout window is
     [t_trig - readout_pre_ns, t_trig + readout_post_ns). The next trigger can fire only after that window ends.
  5. Each window: every PMT is a 4 ns waveform = sum of its PEs' pulses x adc_per_pe + Gaussian baseline noise.
     Values are rounded to ADC counts and clipped to the ADC range. Pulses are stored positive (polarity flipped).
  6. Per-channel zero suppression: keep samples above `zs_threshold_adc`, plus zs_pre / zs_post samples around
     them. PMTs without PEs are not computed sample by sample. Instead, their baseline-noise threshold crossings
     are drawn from the Gaussian tail, so that rare electronic-noise segments also exist.
Times in the output are relative to the start of the first readout window. Window start times are integer
sample counts on the global clock, so the prompt-delayed Δt is known to 4 ns. No MC time origin survives.

API: digitize(pe_pmt, pe_t, pe_label, n_pmt, cfg, rng) -> dict or None (None = nothing triggered).
"""
from dataclasses import asdict, dataclass

import numpy as np

DIGITIZER_VERSION = "0.2"


@dataclass(frozen=True)
class DigiConfig:
    sample_ns: float = 4.0            # 250 MS/s (user decision 2026-11-13)
    adc_bits: int = 14
    adc_per_pe: float = 130.0         # ADC counts at the SPE peak: ~4 mV at gain 1e7, 14 bit / 0.5 Vpp  (docs/DIGITIZER.md)
    ln_mean_ns: float = 100.7         # lognormal pulse fitted to R3600 SPE rise/fall/FWHM 10.6/13.2/18.8 ns
    ln_width: float = 0.0748          #   (Okajima et al. PoS(PhotoDet2015)015 Table 2)
    peak_delay_ns: float = 20.0       # pulse peak this long after the PE time (start of pulse ~1% of peak at 0)
    pulse_len_ns: float = 64.0        # template length after the PE time
    spe_sigma: float = 0.50           # SPE charge sigma/mean: R3600 53% (Okajima Table 3), 50% (Hyper-K DR)
    noise_adc: float = 6.5            # baseline noise sigma = 0.05 SPE amplitude (assumption; CAEN/JUNO/KamLAND2 bracket)
    zs_threshold_adc: float = 33.0    # 0.25 PE (Super-K, KamLAND2, Hamamatsu convention) = ~5 sigma of noise
    zs_pre: int = 2                   # samples kept before / after each above-threshold sample
    zs_post: int = 4
    dark_rate_hz: float = 40e3        # per PMT (OHN24)
    trig_window_ns: float = 100.0
    trig_nhit: int = 120              # dark noise alone gives ~50 +- 7 PEs per 100 ns over 12,505 PMTs
    readout_pre_ns: float = 200.0
    readout_post_ns: float = 1000.0
    dark_margin_ns: float = 2000.0    # dark noise is generated this far before the first and after the last PE

    @property
    def n_samples(self):
        return int(round((self.readout_pre_ns + self.readout_post_ns) / self.sample_ns))

    def as_dict(self):
        return {"digitizer_version": DIGITIZER_VERSION, **asdict(self)}


def pulse_shape(dt_ns, cfg):
    """Unit-peak lognormal pulse versus time after the PE (0 for dt <= 0)."""
    dt = np.asarray(dt_ns, dtype=np.float64)
    out = np.zeros_like(dt)
    pos = (dt > 0) & (dt < cfg.pulse_len_ns)
    t_peak = cfg.ln_mean_ns * np.exp(-cfg.ln_width ** 2)          # mode of the lognormal pdf
    x = dt[pos] - cfg.peak_delay_ns + t_peak                       # shift so the peak sits peak_delay_ns after the PE
    good = x > 0
    v = np.zeros_like(x)
    v[good] = np.exp(-0.5 * (np.log(x[good] / cfg.ln_mean_ns) / cfg.ln_width) ** 2) / x[good]
    out[pos] = v
    peak = np.exp(-0.5 * (np.log(t_peak / cfg.ln_mean_ns) / cfg.ln_width) ** 2) / t_peak
    return out / peak


def crossing_delay_ns(cfg):
    """Time from a mean-gain PE to its pulse crossing the zero-suppression threshold (continuous time)."""
    t = np.arange(0.01, cfg.pulse_len_ns, 0.01)
    above = pulse_shape(t, cfg) * cfg.adc_per_pe > cfg.zs_threshold_adc
    return float(t[np.argmax(above)]) if above.any() else float("nan")


def find_triggers(t_sorted, cfg):
    """Trigger times: the time of the PE that brings the count in (t - trig_window_ns, t] to trig_nhit."""
    trig = []
    n = len(t_sorted)
    if n < cfg.trig_nhit:
        return trig
    lo = np.searchsorted(t_sorted, t_sorted - cfg.trig_window_ns, side="right")
    count = np.arange(n) - lo + 1
    i = 0
    while True:
        cand = np.flatnonzero(count[i:] >= cfg.trig_nhit)
        if len(cand) == 0:
            break
        j = i + cand[0]
        t_trig = t_sorted[j]
        trig.append(t_trig)
        i = np.searchsorted(t_sorted, t_trig + cfg.readout_post_ns, side="left")   # dead until the window ends
        if i >= n:
            break
    return trig


def _zero_suppress(A, cfg):
    """Boolean keep-mask: above threshold, dilated by zs_pre / zs_post samples."""
    m = A > cfg.zs_threshold_adc
    keep = m.copy()
    for k in range(1, cfg.zs_post + 1):
        keep[:, k:] |= m[:, :-k]
    for k in range(1, cfg.zs_pre + 1):
        keep[:, :-k] |= m[:, k:]
    return keep


def _runs(keep_row):
    """(start, length) of contiguous True runs."""
    d = np.diff(np.concatenate(([0], keep_row.view(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return starts, ends - starts


def digitize(pe_pmt, pe_t, pe_label, n_pmt, cfg, rng):
    S, NS = cfg.sample_ns, cfg.n_samples
    pe_pmt = np.asarray(pe_pmt, np.int64)
    pe_t = np.asarray(pe_t, np.float64)
    pe_label = np.asarray(pe_label, np.int8)
    if len(pe_t) == 0:
        return None
    # 1. dark noise around each cluster of light. Clusters are separated by gaps longer than two margins plus one
    #    readout window. Dark noise alone never triggers (~50 PEs per 100 ns vs trig_nhit), so the empty time between
    #    clusters cannot hold a window. Late radioactive decays (seen up to ~1 s after an (alpha,n) event) then cost
    #    one more cluster instead of filling the whole gap with dark noise.
    ts = np.sort(pe_t)
    gap = 2 * cfg.dark_margin_ns + cfg.readout_pre_ns + cfg.readout_post_ns
    br = np.flatnonzero(np.diff(ts) > gap)
    c_lo = np.concatenate(([ts[0]], ts[br + 1])) - cfg.dark_margin_ns
    c_hi = np.concatenate((ts[br], [ts[-1]])) + cfg.dark_margin_ns
    d_pmt, d_t = [], []
    for lo, hi in zip(c_lo, c_hi):
        n_dark = rng.poisson(cfg.dark_rate_hz * n_pmt * (hi - lo) * 1e-9)
        d_pmt.append(rng.integers(0, n_pmt, n_dark)); d_t.append(rng.uniform(lo, hi, n_dark))
    d_pmt, d_t = np.concatenate(d_pmt), np.concatenate(d_t)
    pmt = np.concatenate([pe_pmt, d_pmt])
    t = np.concatenate([pe_t, d_t])
    lab = np.concatenate([pe_label, np.zeros(len(d_t), np.int8)])
    # 2. gains, 3. clock phase
    gain = np.clip(rng.normal(1.0, cfg.spe_sigma, len(t)), 0.0, None)
    t = t + rng.uniform(0.0, S)
    order = np.argsort(t, kind="stable")
    pmt, t, lab, gain = pmt[order], t[order], lab[order], gain[order]
    # 4. trigger
    trig = find_triggers(t, cfg)
    if not trig:
        return None
    L = int(np.ceil(cfg.pulse_len_ns / S)) + 1
    vmax = 2 ** (cfg.adc_bits - 1) - 1
    p_tail = 0.5 * _erfc(cfg.zs_threshold_adc / (cfg.noise_adc * np.sqrt(2.0)))
    s_first = None
    out = {k: [] for k in ("seg_pmt", "seg_win", "seg_start", "seg_len", "samples")}
    win_start, win_trig = [], []
    pe_win = np.full(len(t), -1, np.int16)
    for w, tt in enumerate(trig):
        s0 = int(np.floor((tt - cfg.readout_pre_ns) / S))          # global sample index of the window start
        if s_first is None:
            s_first = s0
        win_start.append(s0 - s_first)
        win_trig.append(int(np.floor(tt / S)) - s0)
        sel = np.flatnonzero((t >= s0 * S - cfg.pulse_len_ns) & (t < (s0 + NS) * S))
        in_win = sel[(t[sel] >= s0 * S) & (t[sel] < (s0 + NS) * S)]
        pe_win[in_win] = w
        lit, row = np.unique(pmt[sel], return_inverse=True)
        A = np.zeros((len(lit), NS), np.float64)
        if len(sel):
            k_first = np.ceil(t[sel] / S).astype(np.int64)                  # first sample at/after the PE
            j = np.arange(L)
            k = k_first[:, None] + j[None, :]                               # global sample index
            val = gain[sel][:, None] * cfg.adc_per_pe * pulse_shape(k * S - t[sel][:, None], cfg)
            col = k - s0
            ok = (col >= 0) & (col < NS)
            np.add.at(A, (np.broadcast_to(row[:, None], col.shape)[ok], col[ok]), val[ok])
        A += rng.normal(0.0, cfg.noise_adc, A.shape)
        A = np.clip(np.rint(A), -vmax - 1, vmax).astype(np.int16)
        keep = _zero_suppress(A, cfg)
        for r in range(len(lit)):
            st, ln = _runs(keep[r])
            for a, b in zip(st, ln):
                out["seg_pmt"].append(lit[r]); out["seg_win"].append(w); out["seg_start"].append(a)
                out["seg_len"].append(b); out["samples"].append(A[r, a:a + b])
        # electronic-noise-only crossings on PMTs with no PE in this window
        n_spur = rng.poisson(max(n_pmt - len(lit), 0) * NS * p_tail)
        if n_spur:
            unlit = np.setdiff1d(np.arange(n_pmt), lit)
            for p in rng.choice(unlit, n_spur, replace=False):
                c = int(rng.integers(0, NS))
                a, b = max(c - cfg.zs_pre, 0), min(c + cfg.zs_post + 1, NS)
                seg = rng.normal(0.0, cfg.noise_adc, b - a)
                tail = cfg.zs_threshold_adc + rng.exponential(cfg.noise_adc ** 2 / cfg.zs_threshold_adc)
                seg[c - a] = tail
                out["seg_pmt"].append(p); out["seg_win"].append(w); out["seg_start"].append(a)
                out["seg_len"].append(b - a)
                out["samples"].append(np.clip(np.rint(seg), -vmax - 1, vmax).astype(np.int16))
    lens = np.asarray(out["seg_len"], np.int64)
    res = {
        "win_start": np.asarray(win_start, np.int64),            # samples since the first window start
        "win_trig": np.asarray(win_trig, np.int16),              # trigger sample inside each window
        "seg_pmt": np.asarray(out["seg_pmt"], np.uint16),
        "seg_win": np.asarray(out["seg_win"], np.uint8),
        "seg_start": np.asarray(out["seg_start"], np.int16),     # first stored sample inside the window
        "seg_len": lens.astype(np.uint16),
        "seg_off": np.concatenate(([0], np.cumsum(lens))).astype(np.int64),
        "samples": np.concatenate(out["samples"]) if out["samples"] else np.zeros(0, np.int16),
        # truth (never a model input): every PE, signal and dark, in the window frame
        "pe_pmt": pmt.astype(np.uint16),
        "pe_win": pe_win,
        "pe_t": (t - s_first * S).astype(np.float32),            # ns since the first window start
        "pe_label": lab,
        "pe_gain": gain.astype(np.float32),
    }
    return res


def _erfc(x):
    """Complementary error function without scipy (Abramowitz-Stegun 7.1.26, |err| < 1.5e-7)."""
    x = float(x)
    s = 1.0 if x >= 0 else -1.0
    x = abs(x)
    tt = 1.0 / (1.0 + 0.3275911 * x)
    y = tt * (0.254829592 + tt * (-0.284496736 + tt * (1.421413741 + tt * (-1.453152027 + tt * 1.061405429))))
    r = y * np.exp(-x * x)
    return r if s > 0 else 2.0 - r
