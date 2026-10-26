"""Write and verify a relocation-safe inventory, including symlinks and modes."""
import argparse
import hashlib
import json
from pathlib import Path
import stat


def inventory(root):
    entries = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == "MANIFEST.json" or "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            target = path.readlink()
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"External symlink: {relative} -> {target}")
            entries[relative] = {"link": str(target)}
        elif path.is_file():
            entries[relative] = {
                "bytes": path.stat().st_size,
                "mode": stat.S_IMODE(path.stat().st_mode),
                "sha256": hashlib.file_digest(path.open("rb"), "sha256").hexdigest(),
            }
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    observed = inventory(args.root)
    manifest = args.root / "MANIFEST.json"
    if args.verify:
        expected = json.loads(manifest.read_text())
        if observed != expected:
            changed = sorted(k for k in observed.keys() | expected.keys()
                             if observed.get(k) != expected.get(k))
            raise ValueError(f"Inventory mismatch: {changed[:20]}")
        print(f"Verified {len(observed)} inventory entries")
    else:
        manifest.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
        print(f"Recorded {len(observed)} inventory entries")


if __name__ == "__main__":
    main()
