#!/usr/bin/env python3
"""Inside the ratpac container (PyROOT): dump one event of an outntuple (with optical-photon trajectories kept) to npz:
PMT positions/directions, every trajectory (pdg, step points, end volume, end process) and the detected PEs (PMT id, time).
usage: dump_event.py in.ntuple.root out.npz"""
import sys
import numpy as np
import ROOT

f = ROOT.TFile.Open(sys.argv[1]); t, meta = f.Get("output"), f.Get("meta")
meta.GetEntry(0)
P = {k: np.array(getattr(meta, k)) for k in ("pmtX", "pmtY", "pmtZ", "pmtU", "pmtV", "pmtW")}
names = {int(p.second): str(p.first) for p in meta.processCodeMap}          # code -> process name
vnames = {int(p.second): str(p.first) for p in meta.volumeCodeMap}           # code -> physical volume name
br = {b.GetName() for b in t.GetListOfBranches()}
t.GetEntry(0)
pdg = np.array(t.trackPDG)
off, X, Y, Z, T, VOL, PROC = [0], [], [], [], [], [], []
vol_names = None
for i in range(len(pdg)):
    xs, ys, zs = list(t.trackPosX[i]), list(t.trackPosY[i]), list(t.trackPosZ[i])
    X += xs; Y += ys; Z += zs; T += list(t.trackTime[i]); off.append(off[-1] + len(xs))
    VOL.append(vnames.get(int(t.trackVolume[i][-1]), "?") if len(t.trackVolume[i]) else "")
    PROC.append(int(t.trackProcess[i][-1]) if len(t.trackProcess[i]) else -1)
out = dict(pmt_x=P["pmtX"], pmt_y=P["pmtY"], pmt_z=P["pmtZ"], pmt_u=P["pmtU"], pmt_v=P["pmtV"], pmt_w=P["pmtW"],
           trk_pdg=pdg, trk_off=np.array(off), trk_x=np.array(X), trk_y=np.array(Y), trk_z=np.array(Z), trk_t=np.array(T),
           trk_end_volume=np.array(VOL), trk_end_proc=np.array(PROC), proc_names=np.array([f"{k}:{v}" for k, v in sorted(names.items())]),
           pe_pmt=np.array(t.mcPEPMTID), pe_t=np.array(t.mcPEHitTime), mc_pdg=np.array(t.mcpdgs), mc_ke=np.array(t.mckes),
           vtx=np.array([t.mcx, t.mcy, t.mcz]), scint_edep=float(t.scintEdep), n_entries=int(t.GetEntries()))
np.savez_compressed(sys.argv[2], **out)
ev, cnt = np.unique(out["trk_end_volume"], return_counts=True)
print("tracks", len(pdg), "optical", int((pdg == 0).sum()) + int((pdg == -22).sum()), "PEs", len(out["pe_pmt"]), "entries", out["n_entries"])
print("end volumes (top):", sorted(zip(cnt, ev), reverse=True)[:12])
print("pdg codes:", np.unique(pdg, return_counts=True))
