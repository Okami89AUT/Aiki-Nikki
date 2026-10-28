#!/usr/bin/env python3
"""Bauwerkzeug für den Aikido Tracker (Repository „Aiki-Nikki“; nur Standardbibliothek).

  python3 tools/build.py notes <v1.2.3>                       Text des Eintrags aus CHANGELOG.md (Beschreibung des GitHub-Releases)
  python3 tools/build.py check-tag <v1.2.3>                   prüft, dass der Tag zur Version im Manifest passt
  python3 tools/build.py sync-app <aikido-kyu-tracker.html>   übernimmt die neueste App in den Baustein
  python3 tools/build.py files                                listet die Dateien, die ins Repository gehören
  python3 tools/build.py zip --out <Ordner>                   baut aikido-tracker-<Version>.zip (ganzes Repository)
                                                              und aikido_tracker.zip (nur der Baustein) samt Prüfsummen

Mit --root <Ordner> arbeitet das Werkzeug auf einer anderen Kopie des Repositories (für die Tests).
Die ZIP-Dateien sind reproduzierbar: gleicher Inhalt ergibt dieselbe Datei (feste Zeitstempel, sortierte Namen).
Exitcode 0 = in Ordnung, 1 = Problem (Meldung auf stderr).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import zipfile

# Was nie ins Repository gehört (entspricht .gitignore)
SKIP_DIRS = {".git", "__pycache__", ".work", "out", "dist", "venv", ".venv", ".ruff_cache", ".pytest_cache"}
SKIP_SUFFIX = (".pyc", ".pyo", ".zip")
SKIP_NAMES = {".DS_Store"}

ZIP_TIME = (2026, 1, 1, 0, 0, 0)
ZIP_ATTR = 0o100644 << 16     # normale Datei, rw-r--r--

APP_NAME = "aikido-kyu-tracker.html"


def fail(message: str) -> int:
    print(f"Fehler: {message}", file=sys.stderr)
    return 1


def package_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "custom_components" / "aikido_tracker"


def manifest_version(root: pathlib.Path) -> str:
    return json.loads((package_dir(root) / "manifest.json").read_text(encoding="utf-8"))["version"]


def shipped_files(root: pathlib.Path) -> list[str]:
    """Alle Dateien (relativ, mit /), die ins Repository gehören – sortiert."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIX):
                continue
            found.append(pathlib.Path(dirpath, name).relative_to(root).as_posix())
    return sorted(found)


def changelog_section(root: pathlib.Path, version: str) -> str | None:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    for part in re.split(r"^(?=## \[)", text, flags=re.M):
        head = re.match(r"## \[(\d+\.\d+\.\d+)\] – \d{4}-\d{2}-\d{2}[ \t]*\n", part)
        if head and head.group(1) == version:
            return part[head.end():].strip()
    return None


def tag_version(tag: str) -> str | None:
    hit = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    return hit.group(1) if hit else None


def cmd_notes(root: pathlib.Path, tag: str) -> int:
    version = tag_version(tag)
    if version is None:
        return fail(f"Tag „{tag}“ hat nicht die Form v1.2.3")
    section = changelog_section(root, version)
    if not section:
        return fail(f"In CHANGELOG.md gibt es keinen Eintrag für Version {version}")
    print(section)
    return 0


def cmd_check_tag(root: pathlib.Path, tag: str) -> int:
    version = tag_version(tag)
    if version is None:
        return fail(f"Tag „{tag}“ hat nicht die Form v1.2.3")
    have = manifest_version(root)
    if version != have:
        return fail(f"Tag {tag} passt nicht zur Version {have} im Manifest (manifest.json und const.py anpassen oder anderen Tag setzen)")
    return 0


def cmd_sync_app(root: pathlib.Path, source: str) -> int:
    src = pathlib.Path(source)
    if not src.is_file():
        return fail(f"Datei nicht gefunden: {source}")
    data = src.read_bytes()
    if data[:15].lower() != b"<!doctype html>":
        return fail("Das ist keine HTML-Seite (sie muss mit <!DOCTYPE html> beginnen)")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return fail("Die Datei ist nicht UTF-8")
    hit = re.search(r'APP_VERSION = "(\d+\.\d+)"', text)
    if not hit:
        return fail('In der Datei steht keine APP_VERSION = "x.y"')
    if b"\r\n" in data:
        return fail("Die Datei hat Windows-Zeilenenden (CRLF); bitte mit LF speichern")
    target = package_dir(root) / "app" / APP_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    print(f"App {hit.group(1)} übernommen ({len(data)} Bytes) -> {target.relative_to(root).as_posix()}")
    return 0


def cmd_files(root: pathlib.Path) -> int:
    for name in shipped_files(root):
        print(name)
    return 0


def _write_zip(path: pathlib.Path, entries: list[tuple[str, bytes]]) -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_ATTR
            info.create_system = 3
            z.writestr(info, data, compresslevel=9)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_zip(root: pathlib.Path, out: str) -> int:
    version = manifest_version(root)
    out_dir = pathlib.Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_entries = [(name, (root / name).read_bytes()) for name in shipped_files(root)]
    pkg = package_dir(root)
    pkg_prefix = pkg.relative_to(root).as_posix() + "/"
    pkg_entries = [(name[len(pkg_prefix):], data) for name, data in repo_entries if name.startswith(pkg_prefix)]
    if not any(name == "manifest.json" for name, _ in pkg_entries):
        return fail("Im Baustein fehlt manifest.json")
    for target, entries in ((out_dir / f"aikido-tracker-{version}.zip", repo_entries), (out_dir / "aikido_tracker.zip", pkg_entries)):
        digest = _write_zip(target, entries)
        print(f"{digest}  {target.name}  ({target.stat().st_size} Bytes, {len(entries)} Dateien)")
    return 0


def main(argv: list[str] | None = None) -> int:
    default_root = pathlib.Path(__file__).resolve().parents[1]
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=str(default_root), help="Hauptordner des Repositories")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("notes", parents=[common]).add_argument("tag")
    sub.add_parser("check-tag", parents=[common]).add_argument("tag")
    sub.add_parser("sync-app", parents=[common]).add_argument("source")
    sub.add_parser("files", parents=[common])
    sub.add_parser("zip", parents=[common]).add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if args.command == "notes":
        return cmd_notes(root, args.tag)
    if args.command == "check-tag":
        return cmd_check_tag(root, args.tag)
    if args.command == "sync-app":
        return cmd_sync_app(root, args.source)
    if args.command == "files":
        return cmd_files(root)
    return cmd_zip(root, args.out)


if __name__ == "__main__":
    sys.exit(main())
