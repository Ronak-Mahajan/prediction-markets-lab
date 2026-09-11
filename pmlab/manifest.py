"""Per-blob sha256 manifest for the archive on the ``data`` branch.

    python -m pmlab.manifest archive                   # add new blobs
    python -m pmlab.manifest archive --check           # verify what is on disk
    python -m pmlab.manifest archive --prune --full    # full archive checked out

The manifest is incremental: blobs already listed are not re-hashed
unless ``--rehash`` is given, so the recorder's cost per run stays
constant as the archive grows. Every analysis result cites
``manifest_sha256``, the hash of the sorted (path, sha256) pairs, as the
identity of the archive it ran on.

**A partial checkout must never shrink the manifest.** The recorder and
the settle job check the data branch out as a partial clone with a sparse
cone, so almost none of the archive is on disk when the manifest is
updated: pruning by default would rewrite the manifest down to the one
blob that run happened to write. So listed-but-absent blobs are kept, and
``--prune`` (which needs the full archive on disk, together with
``--full`` for the matching check) is the only way to drop them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA = 1


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def blob_paths(root: Path) -> list[str]:
    data = root / "data"
    if not data.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix() for p in data.glob("*/*.json.gz"))


def manifest_identity(blobs: dict[str, dict]) -> str:
    h = hashlib.sha256()
    for path in sorted(blobs):
        h.update(f"{path}\t{blobs[path]['sha256']}\n".encode())
    return h.hexdigest()


def load_manifest(root: Path) -> dict:
    p = root / "manifest.json"
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {"schema": MANIFEST_SCHEMA, "blobs": {}}


def update_manifest(root: str | Path, rehash: bool = False,
                    prune: bool = False) -> dict:
    """Add every on-disk blob not yet listed. Drops listed blobs only when
    ``prune`` is set, which is valid only with the whole archive on disk."""
    root = Path(root)
    man = load_manifest(root)
    blobs: dict[str, dict] = dict(man.get("blobs", {})) if not rehash else {}
    on_disk = blob_paths(root)
    added = [p for p in on_disk if p not in blobs]
    removed = [p for p in blobs if p not in set(on_disk)] if prune else []
    for p in removed:
        blobs.pop(p, None)
    for rel in added:
        fp = root / rel
        blobs[rel] = {"sha256": sha256_file(fp), "bytes": fp.stat().st_size}
    man = {
        "schema": MANIFEST_SCHEMA,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_count": len(blobs),
        "first": min(blobs) if blobs else None,
        "last": max(blobs) if blobs else None,
        "total_bytes": sum(b["bytes"] for b in blobs.values()),
        "manifest_sha256": manifest_identity(blobs),
        "blobs": dict(sorted(blobs.items())),
    }
    with open(root / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, sort_keys=False)
        fh.write("\n")
    man["_added"], man["_removed"] = added, removed
    return man


def check_manifest(root: str | Path, full: bool = False) -> list[str]:
    """Problems found; empty means everything on disk matches the manifest.

    ``full`` additionally requires every listed blob to be present, which
    only holds when the whole archive is checked out (not in the recorder
    and settle jobs, which use a sparse cone).
    """
    root = Path(root)
    man = load_manifest(root)
    blobs = man.get("blobs", {})
    problems: list[str] = []
    on_disk = blob_paths(root)
    for rel in on_disk:
        if rel not in blobs:
            problems.append(f"unlisted: {rel}")
        elif sha256_file(root / rel) != blobs[rel]["sha256"]:
            problems.append(f"sha256 mismatch: {rel}")
    if full:
        for rel in blobs:
            if rel not in set(on_disk):
                problems.append(f"missing on disk: {rel}")
    if blobs and man.get("manifest_sha256") != manifest_identity(blobs):
        problems.append("manifest_sha256 does not match listed blobs")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", help="archive root containing data/ and manifest.json")
    ap.add_argument("--check", action="store_true", help="verify instead of update")
    ap.add_argument("--rehash", action="store_true", help="re-hash every blob")
    ap.add_argument("--prune", action="store_true",
                    help="drop listed blobs that are absent from disk "
                         "(only valid with the whole archive checked out)")
    ap.add_argument("--full", action="store_true",
                    help="--check also requires every listed blob to be present")
    a = ap.parse_args(argv)
    if a.check:
        problems = check_manifest(a.root, full=a.full)
        for p in problems:
            print(p)
        print(f"manifest check: {len(problems)} problem(s)")
        return 1 if problems else 0
    man = update_manifest(a.root, rehash=a.rehash, prune=a.prune)
    print(f"manifest: {man['snapshot_count']} snapshots, "
          f"+{len(man['_added'])} -{len(man['_removed'])}, "
          f"id {man['manifest_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
