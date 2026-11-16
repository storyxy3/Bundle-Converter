"""Copy prepared Gakumas content and replace a native bundle by manifest key.

Only packaging: no runtime adapters or changes to original content.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("destination", type=Path)
parser.add_argument("--bundle", type=Path, action="append", required=True)
args = parser.parse_args()
if args.source.resolve() == args.destination.resolve():
    parser.error("destination must differ from the original content directory")
manifest = json.loads((args.source / "manifest.json").read_text())
replacements = {p.name.removesuffix(".unity3d"): p for p in args.bundle}
entries = {e["name"]: e for e in manifest["bundles"]}
if replacements.keys() - entries.keys():
    parser.error("replacement bundle has no matching manifest key")
if any(not p.is_file() for p in replacements.values()):
    parser.error("replacement bundle is missing")
args.destination.mkdir(parents=True, exist_ok=True)
for entry in manifest["bundles"]:
    source = replacements.get(entry["name"], args.source / entry["file"])
    target = args.destination / entry["file"]
    if source.resolve() == target.resolve():
        raise ValueError("refusing to overwrite an input bundle")
    shutil.copyfile(source, target)
    if entry["name"] in replacements:
        entry["source"] = str(source.resolve())
        entry["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        entry.pop("original_sha256", None)
        entry.pop("replaced_shaders", None)
(args.destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Staged {len(entries)} bundles; replaced {len(replacements)}")
