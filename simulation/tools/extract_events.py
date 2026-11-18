#!/usr/bin/env python3
"""Turn one ratpac-two outntuple chunk into a compact per-event truth + photon-hit file for ML.

OBD17kt_geo variant (2026-11-13, copied from projects/OBD17kt): adds --mode generic for non-IBD samples (decay
singles, 210Po alphas, 13C(alpha,n)). In generic mode an event needs no positron: missing positron/neutron truth
is NaN (n_target 0 = no neutron), pe_delayed splits at the neutron end time when a primary neutron exists and is
all-False otherwise, and every event also stores its primary particles (prim_pdg, prim_ke, prim_off).
IBD mode output is unchanged except for the added prim_* arrays.

Input : <chunk>.ntuple.root written with include_tracking / include_mcparticles / include_mchits = 1
        and optical-photon trajectories discarded (macros/ibd_obd17kt.mac).
Output: <chunk>.events.npz (numpy + PyROOT from the ratpac container only). Contents:

 per event (length N):
   seed, evid                    RNG seed of the rat process (-s) and the event index inside it.
                                 (seed, evid) + container sha + macro reproduces the event; an exact
                                 per-event engine state is also archived as rndm_states.tar by the job.
   vtx_{x,y,z,t}                 IBD vertex (primary vertex), mm / ns
   nu_dir_{x,y,z}, ep_ke, n_ke   from the primaries (positron/neutron kinetic energy, MeV)
   ep_{x0,y0,z0,t0}              positron start (== vertex)
   ep_{x1,y1,z1,t1}, ep_end_proc positron end point (annihilation, "annihil") and process code
   n_{x1,y1,z1,t1}, n_end_proc   neutron capture point and time from the capture products (triton+alpha / deuteron; else the
                                 latest neutron track end). n_end_proc is the primary neutron's last process (6Li(n,t)a shows up as "neutronInelastic"
                                 in Geant4, H/C capture as "nCapture") and process code
   n_target                      1 = 6Li (alpha+triton seen), 2 = H (deuteron), 3 = other/unknown
   edep, edep_quenched           total and Birks-quenched energy deposited in the scintillator (MeV)
   npe_prompt, npe_delayed       photoelectron counts
   overlap                       1 if the neutron end time < 1000 ns (prompt and delayed light mix)
 per photoelectron (flat arrays, event i owns pe_*[pe_off[i]:pe_off[i+1]]):
   pe_pmt (int32)                PMT id (index into pmt_x/y/z)
   pe_t_true (float32)           photon arrival time at the photocathode (ns, global)
   pe_t (float32)                front-end time = arrival + PMT transit-time spread (what a DAQ sees)
   pe_proc (int8)                ratpac mc_pe_type: 0 dark noise, 1 Cherenkov, 2 scintillation, 3 re-emission, 4 unknown
   pe_delayed (bool)             photon emitted at/after the neutron end time (truth split)
 detector: pmt_x, pmt_y, pmt_z, pmt_u, pmt_v, pmt_w; process_names (code -> Geant4 process name)
Dark noise is NOT simulated in Geant4. Add it at feature-building time (40 kHz/PMT, OHN24) with its own seed.
"""
import argparse
import json
import sys

import numpy as np
import ROOT  # PyROOT from the pinned ratpac container: no packages from outside the image

ROOT.gROOT.SetBatch(True)


def conv(x):
    """PyROOT value -> python/numpy: scalars, std::vector<T> -> ndarray, vector<vector<T>> -> list of ndarray."""
    if isinstance(x, (int, float, bool)):
        return x
    n = x.size()
    if n and hasattr(x[0], "size"):
        return [np.array(list(y)) for y in x]
    return np.array(list(x)) if n else np.array([])


def read_tree(tree, branches):
    tree.SetBranchStatus("*", 0)
    for b in branches:
        tree.SetBranchStatus(b, 1)
    cols = {b: [] for b in branches}
    for _ in tree:
        for b in branches:
            cols[b].append(conv(getattr(tree, b)))
    return cols


def proc_map(meta):
    """{code: Geant4 process name} from the meta tree's std::map<std::string,int> processCodeMap."""
    names = {b.GetName() for b in meta.GetListOfBranches()}
    if "processCodeMap" not in names:
        return {}
    meta.GetEntry(0)
    return {int(kv.second): str(kv.first) for kv in meta.processCodeMap}


def select_rows(evid, subev=None, mcid=None):
    """Rows to extract (one per triggered MC event) plus (n_generated, n_triggered).

    In ratpac 4.4.0 outntuple, `evid` is the id of a triggered sub-event (EV), not of the simulated event
    (OutNtupleProc.cc:616). The simulated event is `mcid` (line 401). splitevdaq writes one row per triggered
    sub-event with MC truth repeated, so an IBD whose prompt and delayed trigger separately has two rows with
    different evid and the same mcid. We keep the subev == 0 row of each MC event.
    With include_untriggered_events, each untriggered MC event is one row with evid = subev = -1 (lines 790-793).
    Those rows are never extracted, because they carry no detector data, but they count as generated events.
    Background rates are normalised per generated decay. The count is exact only when the macro keeps
    untriggered events. Without an mcid branch, (evid, subev) is the fallback key.
    """
    evid = np.asarray(evid)
    trig = evid >= 0
    if subev is not None:
        sub = np.asarray(subev)
        first_sub = trig & (sub == 0)
    else:
        first_sub = trig
    key = np.asarray(mcid) if mcid is not None else evid
    cand = np.flatnonzero(first_sub)
    _, first = np.unique(key[cand], return_index=True)
    rows = np.sort(cand[first]).astype(int)
    n_triggered = len(rows)
    n_generated = n_triggered + int((~trig).sum())
    return rows, n_generated, n_triggered


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ntuple")
    ap.add_argument("--seed", type=int, required=True, help="the -s seed rat was run with")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--mode", choices=("ibd", "generic"), default="ibd")
    a = ap.parse_args()
    nan = float("nan")

    f = ROOT.TFile.Open(a.ntuple)
    out, meta = f.Get("output"), f.Get("meta")
    pnames = proc_map(meta)
    mcols = read_tree(meta, ["pmtX", "pmtY", "pmtZ", "pmtU", "pmtV", "pmtW"])
    m = {k: v[0] for k, v in mcols.items()}

    want = ["evid", "mcx", "mcy", "mcz", "mct", "mcpdgs", "mcxs", "mcys", "mczs", "mcus", "mcvs", "mcws",
            "mckes", "mcts", "scintEdep", "scintEdepQuenched", "trackPDG", "trackPosX", "trackPosY",
            "trackPosZ", "trackTime", "trackProcess", "mcPEPMTID", "mcPEHitTime", "mcPEFrontEndTime",
            "mcPEProcess", "mcPECreationTime"]
    have = {b.GetName() for b in out.GetListOfBranches()}
    missing = [b for b in want if b not in have]
    if missing:
        sys.exit(f"missing branches {missing}: check the macro's outntuple options")
    for b in ("subev", "mcid"):
        if b in have:
            want.append(b)
    T = read_tree(out, want)
    T["evid"] = np.asarray(T["evid"])

    rows, n_generated, n_triggered = select_rows(T["evid"], T.get("subev"), T.get("mcid"))

    cols = {k: [] for k in ["evid", "vtx_x", "vtx_y", "vtx_z", "vtx_t", "nu_dir_x", "nu_dir_y", "nu_dir_z",
                            "ep_ke", "n_ke", "ep_x0", "ep_y0", "ep_z0", "ep_t0", "ep_x1", "ep_y1", "ep_z1",
                            "ep_t1", "ep_end_proc", "n_x1", "n_y1", "n_z1", "n_t1", "n_end_proc", "n_target",
                            "edep", "edep_quenched", "npe_prompt", "npe_delayed", "overlap"]}
    pe = {k: [] for k in ("pe_pmt", "pe_t_true", "pe_t", "pe_proc", "pe_delayed")}
    off = [0]
    prim_pdg, prim_ke, prim_off = [], [], [0]
    for r in rows:
        v = np.array([T["mcx"][r], T["mcy"][r], T["mcz"][r]])
        pdg = np.asarray(T["trackPDG"][r])
        X, Y, Z, TT = T["trackPosX"][r], T["trackPosY"][r], T["trackPosZ"][r], T["trackTime"][r]
        P = T["trackProcess"][r]

        def primary(code):
            idx = np.flatnonzero(pdg == code)
            if not len(idx):
                return None
            d = [np.linalg.norm(np.array([X[i][0], Y[i][0], Z[i][0]]) - v) for i in idx]
            return idx[int(np.argmin(d))]

        ie, inn = primary(-11), primary(2112)
        if a.mode == "ibd" and (ie is None or inn is None):
            print(f"evid {T['evid'][r]}: primary positron/neutron track missing, skipped", file=sys.stderr)
            continue
        if inn is not None:
            # Capture point from the capture PRODUCTS, not from the end of the primary neutron track. Geant4 ends the
            # primary at its first inelastic scatter (e.g. 12C(n,n')), which mislabelled ~3 % of (alpha,n) events
            # (physics audit 2026-11-13). The tracks carry no parent ids, so:
            #   6Li: a triton starting where an alpha starts (n + 6Li -> alpha + t). The (alpha,n) primary alpha has no triton.
            #   H:   a deuteron start (n + p -> d + gamma).
            #   else: the end of the latest-ending neutron track (capture on another nucleus, or escape).
            starts = np.array([[X[i][0], Y[i][0], Z[i][0]] for i in range(len(pdg))])
            t0s = np.array([TT[i][0] for i in range(len(pdg))])
            tri, alp, deu = (np.flatnonzero(pdg == c) for c in (1000010030, 1000020040, 1000010020))
            cap_i, target = None, 3
            for it in tri[np.argsort(t0s[tri])]:
                if len(alp) and np.min(np.linalg.norm(starts[alp] - starts[it], axis=1)) < 1e-3:
                    cap_i, target = it, 1
                    break
            if cap_i is None and len(deu):
                cap_i, target = deu[int(np.argmin(t0s[deu]))], 2
            if cap_i is not None:
                n_end, t_cap = starts[cap_i].copy(), float(t0s[cap_i])
            else:
                neu = np.flatnonzero(pdg == 2112)
                last = neu[int(np.argmax([TT[i][-1] for i in neu]))]
                n_end, t_cap = np.array([X[last][-1], Y[last][-1], Z[last][-1]]), float(TT[last][-1])
        else:
            n_end, t_cap, target = np.array([nan, nan, nan]), nan, 0

        mp = np.asarray(T["mcpdgs"][r])
        ke = np.asarray(T["mckes"][r])
        prim_pdg.append(mp.astype(np.int64)); prim_ke.append(ke.astype(np.float64)); prim_off.append(prim_off[-1] + len(mp))
        ie_p = int(np.argmax(mp == -11)) if (mp == -11).any() else None
        in_p = int(np.argmax(mp == 2112)) if (mp == 2112).any() else None
        cols["evid"].append(T["evid"][r])
        for k, val in zip(("vtx_x", "vtx_y", "vtx_z", "vtx_t"), (*v, T["mct"][r])):
            cols[k].append(val)
        if ie_p is not None and in_p is not None:
            pnu = (np.array([T["mcus"][r][ie_p], T["mcvs"][r][ie_p], T["mcws"][r][ie_p]]) * np.sqrt(ke[ie_p] ** 2 + 2 * ke[ie_p] * 0.511)
                   + np.array([T["mcus"][r][in_p], T["mcvs"][r][in_p], T["mcws"][r][in_p]]) * np.sqrt(ke[in_p] ** 2 + 2 * ke[in_p] * 939.565))
            pnu /= np.linalg.norm(pnu)   # momentum conservation: p_nu = p_e+ + p_n (proton at rest)
        else:
            pnu = np.array([nan, nan, nan])
        for k, val in zip(("nu_dir_x", "nu_dir_y", "nu_dir_z"), pnu):
            cols[k].append(val)
        cols["ep_ke"].append(ke[ie_p] if ie_p is not None else nan)
        cols["n_ke"].append(ke[in_p] if in_p is not None else nan)
        if ie is not None:
            e0 = (X[ie][0], Y[ie][0], Z[ie][0], TT[ie][0]); e1 = (X[ie][-1], Y[ie][-1], Z[ie][-1], TT[ie][-1]); ep_proc = P[ie][-1]
        else:
            e0 = e1 = (nan, nan, nan, nan); ep_proc = -1
        for k, val in zip(("ep_x0", "ep_y0", "ep_z0", "ep_t0"), e0):
            cols[k].append(val)
        for k, val in zip(("ep_x1", "ep_y1", "ep_z1", "ep_t1"), e1):
            cols[k].append(val)
        cols["ep_end_proc"].append(ep_proc)
        for k, val in zip(("n_x1", "n_y1", "n_z1", "n_t1"), (*n_end, t_cap)):
            cols[k].append(val)
        cols["n_end_proc"].append(P[inn][-1] if inn is not None else -1); cols["n_target"].append(target)
        cols["edep"].append(T["scintEdep"][r]); cols["edep_quenched"].append(T["scintEdepQuenched"][r])

        ctime = np.asarray(T["mcPECreationTime"][r])
        delayed = ctime >= t_cap if inn is not None else np.zeros(len(ctime), dtype=bool)
        pe["pe_pmt"].append(np.asarray(T["mcPEPMTID"][r], dtype=np.int32))
        pe["pe_t_true"].append(np.asarray(T["mcPEHitTime"][r], dtype=np.float32))
        pe["pe_t"].append(np.asarray(T["mcPEFrontEndTime"][r], dtype=np.float32))
        pe["pe_proc"].append(np.asarray(T["mcPEProcess"][r], dtype=np.int8))
        pe["pe_delayed"].append(delayed)
        cols["npe_prompt"].append(int((~delayed).sum())); cols["npe_delayed"].append(int(delayed.sum()))
        cols["overlap"].append(int(inn is not None and t_cap < 1000.0))
        off.append(off[-1] + len(delayed))

    n = len(cols["evid"])
    res = {k: np.asarray(v) for k, v in cols.items()}
    res["seed"] = np.full(n, a.seed, dtype=np.int64)
    for k, v in pe.items():
        res[k] = np.concatenate(v) if v else np.array([])
    res["pe_off"] = np.asarray(off, dtype=np.int64)
    res["prim_pdg"] = np.concatenate(prim_pdg) if prim_pdg else np.array([], dtype=np.int64)
    res["prim_ke"] = np.concatenate(prim_ke) if prim_ke else np.array([])
    res["prim_off"] = np.asarray(prim_off, dtype=np.int64)
    res["mode"] = np.array(a.mode)
    res.update({"pmt_x": m["pmtX"], "pmt_y": m["pmtY"], "pmt_z": m["pmtZ"],
                "pmt_u": m["pmtU"], "pmt_v": m["pmtV"], "pmt_w": m["pmtW"],
                "process_names": np.array(json.dumps(pnames))})
    np.savez_compressed(a.out, **res)
    # content hash over every array in fixed key order: identical physics output <=> identical hash
    import hashlib
    h = hashlib.sha256()
    for k in sorted(res):
        arr = np.ascontiguousarray(res[k])
        h.update(k.encode()); h.update(str(arr.dtype).encode()); h.update(str(arr.shape).encode()); h.update(arr.tobytes())
    content_sha = h.hexdigest()

    def nm(c):
        return pnames.get(int(c), str(int(c)))
    summ = {"content_sha256": content_sha, "events": n, "n_generated": n_generated, "n_triggered": n_triggered, "seed": a.seed, "mean_npe_prompt": float(np.mean(res["npe_prompt"])) if n else 0,
            "mean_npe_delayed": float(np.mean(res["npe_delayed"])) if n else 0,
            "n_target_counts": {t: int((res["n_target"] == i).sum()) for i, t in ((0, "none"), (1, "Li6"), (2, "H"), (3, "other"))}, "mode": a.mode,
            "n_end_procs": sorted({nm(c) for c in res["n_end_proc"] if c >= 0}), "ep_end_procs": sorted({nm(c) for c in res["ep_end_proc"] if c >= 0}),
            "mean_capture_time_ns": float(np.nanmean(res["n_t1"])) if n and np.isfinite(res["n_t1"]).any() else None,
            "mean_ep_disp_mm": float(np.nanmean(np.hypot(np.hypot(res["ep_x1"] - res["vtx_x"], res["ep_y1"] - res["vtx_y"]), res["ep_z1"] - res["vtx_z"]))) if n and np.isfinite(res["ep_x1"]).any() else None,
            "mean_n_disp_mm": float(np.nanmean(np.hypot(np.hypot(res["n_x1"] - res["vtx_x"], res["n_y1"] - res["vtx_y"]), res["n_z1"] - res["vtx_z"]))) if n and np.isfinite(res["n_x1"]).any() else None,
            "max_vtx_r_mm": float(np.max(np.hypot(res["vtx_x"], res["vtx_y"]))) if n else 0,
            "max_abs_vtx_z_mm": float(np.max(np.abs(res["vtx_z"]))) if n else 0}
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
