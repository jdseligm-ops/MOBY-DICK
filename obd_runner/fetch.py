"""Download and verify the OBD 17 kt dataset from Zenodo (record 24322961, DOI 10.5281/zenodo.24322961).

Standard library only. The logic follows the task's fetch_data.py: every file is checked against the size and md5 in
data_manifest.json; downloads go to a temporary name inside the data folder and are moved into place only after
verification; an existing identical file is kept, a different one is refused. Held-out test LABELS are never
downloaded. NOTE: the record is reserved but becomes downloadable only after it is published on Zenodo.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "data_manifest.json"
API = "https://zenodo.org/api/records/{record}/files/{name}/content"
GROUPS = ("geometry", "val", "train", "test")      # test = waveforms only


class Refused(RuntimeError):
    pass


def md5_of(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, entry: dict) -> None:
    if not path.is_file():
        raise Refused(f"{path} is missing")
    if path.stat().st_size != entry["size"]:
        raise Refused(f"{path}: {path.stat().st_size} bytes, the manifest says {entry['size']}")
    if md5_of(path) != entry["md5"]:
        raise Refused(f"{path}: md5 differs from the manifest")


def wanted(entries: list[dict], groups: set[str]) -> list[dict]:
    out = []
    for e in entries:
        n = e["name"]
        if n == "pmt_geometry.h5":
            g = "geometry"
        else:
            g = n.split("_")[0]
            if g == "test" and n.endswith(".labels.h5"):
                continue                                  # held-out test labels: never fetched
        if g in groups:
            out.append(e)
    return out


def download(record: str, name: str, target: Path) -> None:
    url = API.format(record=record, name=urllib.parse.quote(name))
    req = urllib.request.Request(url, headers={"User-Agent": "moby-dick-run/1"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r, target.open("wb") as sink:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 22):
                sink.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {name}: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
            print()
    except urllib.error.HTTPError as err:
        if err.code in (403, 404):
            raise Refused(f"Zenodo answered {err.code} for {name}: the record 10.5281/zenodo.{record} is probably not "
                          "published yet. Use --source_dir with files you already have.") from None
        raise


def fetch(output_dir: str, groups: set[str], source_dir: str | None = None) -> int:
    man = json.loads(MANIFEST.read_text())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    todo = wanted(man["files"], groups)
    print(f"{len(todo)} file(s), {sum(e['size'] for e in todo) / 1e9:.2f} GB -> {out}")
    try:
        for e in todo:
            dst = out / e["name"]
            if dst.exists():
                try:
                    verify(dst, e)
                except Refused:
                    raise Refused(f"{dst} exists with different content; left unchanged") from None
                print(f"kept {dst} (already verified)")
                continue
            part = out / (e["name"] + ".partial")
            if source_dir:
                shutil.copyfile(Path(source_dir) / e["name"], part)
            else:
                download(man["zenodo_record_id"], e["name"], part)
            try:
                verify(part, e)
            except Refused:
                part.unlink(missing_ok=True)               # never leave an unverified file behind
                raise
            os.replace(part, dst)
            print(f"wrote {dst} (md5 ok)")
    except (Refused, OSError) as err:
        print(f"fetch refused: {err}", file=sys.stderr)
        return 2
    print(f"data ready in {out}")
    return 0
