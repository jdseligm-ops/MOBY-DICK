#!/usr/bin/env python3
"""Read the published hackathon files (docs/DATASET.md) back into the per-example structure used by layoutb.py and
stage2_rows.py (the same keys as digitize.digitize() returns). The baseline then trains from the published
waveforms only, which is a kit requirement: the checker retrains from the Zenodo data folder.

Example e of a `<group>_NNN.h5` file becomes a dict with
  win_start, win_trig, seg_pmt, seg_win, seg_start, seg_len, seg_off, samples
and, if a labels file is given, the truth PEs (pe_pmt, pe_win, pe_t, pe_label) with pe_gain = 1. Only REAL PEs are
published; dark PEs are not listed, so truth-based hit labels need pe_label > 0 only.
"""
import h5py
import numpy as np


class WaveformFile:
    def __init__(self, path, labels_path=None):
        self.path, self.labels_path = path, labels_path
        self.f = h5py.File(path, "r")
        self.win_off = self.f["examples/win_off"][()]
        self.seg_off_ex = self.f["examples/seg_off"][()]
        self.win_start = self.f["windows/start_sample"][()]
        self.win_trig = self.f["windows/trigger_sample"][()]
        g = self.f["segments"]
        self.seg_pmt, self.seg_win = g["pmt"][()], g["window_in_example"][()]
        self.seg_start, self.seg_len, self.sample_off = g["start_sample"][()], g["length"][()], g["sample_off"][()]
        self.samples = self.f["samples"]                      # gzip; read slices on demand
        self.n = len(self.win_off) - 1
        self.L = h5py.File(labels_path, "r") if labels_path else None
        if self.L is not None:
            self.truth = {k: self.L[f"truth/{k}"][()] for k in self.L["truth"]}
            self.pe_off = self.L["real_pe/off"][()]

    def reopen(self):
        """Re-open the HDF5 handles (after a fork); the index arrays already in memory are kept (shared copy-on-write)."""
        self.f = h5py.File(self.path, "r")
        self.samples = self.f["samples"]
        if self.L is not None:
            self.L = h5py.File(self.labels_path, "r")

    def close(self):
        self.f.close()
        if self.L is not None:
            self.L.close()

    def __len__(self):
        return self.n

    def example(self, e, with_truth=False):
        w0, w1 = self.win_off[e], self.win_off[e + 1]
        s0, s1 = self.seg_off_ex[e], self.seg_off_ex[e + 1]
        a0, a1 = self.sample_off[s0], self.sample_off[s1]
        lens = self.seg_len[s0:s1].astype(np.int64)
        res = {"win_start": self.win_start[w0:w1].astype(np.int64), "win_trig": self.win_trig[w0:w1],
               "seg_pmt": self.seg_pmt[s0:s1], "seg_win": self.seg_win[s0:s1], "seg_start": self.seg_start[s0:s1],
               "seg_len": self.seg_len[s0:s1], "seg_off": np.concatenate(([0], np.cumsum(lens))).astype(np.int64),
               "samples": self.samples[a0:a1]}
        if with_truth and self.L is not None:
            p0, p1 = self.pe_off[e], self.pe_off[e + 1]
            res["pe_pmt"] = self.L["real_pe/pmt"][p0:p1]
            res["pe_win"] = self.L["real_pe/win"][p0:p1].astype(np.int16)
            res["pe_t"] = self.L["real_pe/t"][p0:p1]
            res["pe_label"] = self.L["real_pe/label"][p0:p1]
            res["pe_gain"] = np.ones(p1 - p0, np.float32)
        return res
