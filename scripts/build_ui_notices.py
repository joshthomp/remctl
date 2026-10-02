#!/usr/bin/env python3
"""Collect the locked UI production dependencies' notices for distribution."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(dependency_root: Path) -> None:
    lock = json.loads((ROOT / "ui/package-lock.json").read_text())
    parts = ["RemCTL desktop UI dependency notices\n\nGenerated from ui/package-lock.json.\n"]
    for relative, entry in sorted(lock["packages"].items()):
        if not relative or entry.get("dev"):
            continue
        package = dependency_root / relative
        if not package.is_dir():
            raise ValueError(f"Missing dependency: {package}; run npm ci first")
        metadata = json.loads((package / "package.json").read_text())
        if metadata["version"] != entry["version"]:
            raise ValueError(f"Dependency version differs from lockfile: {relative}")
        files = sorted(p for p in package.iterdir() if p.is_file()
                       and p.name.lower().startswith(("license", "licence", "copying", "notice")))
        if not files and metadata["name"] == "@cfworker/json-schema" and metadata["version"] == "4.1.1":
            # This npm release omits its MIT license; preserve the matching gitHead copy.
            files = [ROOT / "ui/licenses/cfworker-LICENSE.txt"]
        if not files:
            raise ValueError(f"No license notice found for {relative}")
        parts.append(f'\n=== {metadata["name"]} {metadata["version"]} ===\n')
        parts.extend(path.read_text() + "\n" for path in files)
    (ROOT / "ui/THIRD-PARTY-NOTICES.txt").write_text("\n".join(parts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-root", type=Path, default=ROOT / "ui")
    build(parser.parse_args().dependency_root)
