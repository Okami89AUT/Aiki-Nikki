#!/usr/bin/env python3
"""Prüft das Repository als Ganzes: Aufbau für HACS, Manifest, hacs.json, Versionen, Symbol, App, Workflows, Doku, Bauwerkzeug.

Die Regeln stammen aus der HACS-Dokumentation und dem HACS-Quelltext (validate/*.py, utils/validate.py) und aus den
Regeln von hassfest (Manifest-Schlüssel sortiert: domain, name, dann alphabetisch). Ohne Home Assistant lauffähig;
für die Workflow-Dateien wird PyYAML gebraucht (pip install pyyaml).
Aufruf:  python3 tests/test_package.py        (AIKIDO_REPO=<Ordner> prüft eine andere Kopie, z. B. für die Gegenprobe)
Ausgabe wie bei den anderen Tests: "  FALSCH <Name>" je Fehler, Zusammenfassung am Ende, Exitcode 1 bei Fehlern.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import traceback
import zipfile

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(os.environ.get("AIKIDO_REPO") or pathlib.Path(__file__).resolve().parents[1])
PKG = ROOT / "custom_components" / "aikido_tracker"
BUILD = ROOT / "tools" / "build.py"

N = 0
FEHLER = 0


def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def check(name, ist, soll):
    global N, FEHLER
    N += 1
    if canon(ist) != canon(soll):
        FEHLER += 1
        print(f"  FALSCH {name}\n    ist  = {canon(ist)[:600]}\n    soll = {canon(soll)[:600]}")


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def load_json(p):
    return json.loads(read(p))


# Was nie ins Repository gehört (entspricht .gitignore) – unabhängig vom Bauwerkzeug nachgebaut
_SKIP_DIRS = {".git", "__pycache__", ".work", "out", "dist", "venv", ".venv", ".ruff_cache", ".pytest_cache"}
_SKIP_SUFFIX = (".pyc", ".pyo", ".zip")
_SKIP_NAMES = {".DS_Store"}


def shipped():
    """Alle Dateien (relativ, mit /), die ins Repository gehören."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for f in sorted(filenames):
            if f in _SKIP_NAMES or f.endswith(_SKIP_SUFFIX):
                continue
            out.append(pathlib.Path(dirpath, f).relative_to(ROOT).as_posix())
    return sorted(out)


def clean_listing(p):
    return sorted(e.name for e in pathlib.Path(p).iterdir() if e.name not in _SKIP_DIRS)


def run_tool(*args, root=None):
    """Bauwerkzeug aufrufen; liefert (Exitcode, stdout, stderr)."""
    cmd = [sys.executable, "-I", "-B", str(BUILD), *args, "--root", str(root or ROOT)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def png_size(p):
    b = pathlib.Path(p).read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", b[16:24])


# =====================================================================================================================
# K1: Aufbau des Repositories (so, wie HACS ihn erwartet)
# =====================================================================================================================
def gruppe_aufbau():
    check("K1 custom_components enthält genau einen Ordner: aikido_tracker", clean_listing(ROOT / "custom_components"), ["aikido_tracker"])
    check("K1 Inhalt des Bausteins: genau die erwarteten Dateien und Ordner", clean_listing(PKG),
          ["__init__.py", "api.py", "app", "brand", "const.py", "identity.py", "limits.py", "manifest.json", "page.py", "store.py"])
    check("K1 app/ enthält genau die App", clean_listing(PKG / "app"), ["aikido-kyu-tracker.html"])
    check("K1 brand/ enthält genau Symbol und Symbol in doppelter Größe", clean_listing(PKG / "brand"), ["icon.png", "icon@2x.png"])
    check("K1 Hauptordner des Repositories: genau die erwarteten Einträge", clean_listing(ROOT),
          [".github", ".gitignore", "CHANGELOG.md", "README.md", "custom_components", "docs", "hacs.json", "tests", "tools"])
    check("K1 Workflows vorhanden", clean_listing(ROOT / ".github" / "workflows"), ["release.yml", "validate.yml"])
    check("K1 docs/: erwartete Dokumente", clean_listing(ROOT / "docs"), ["BAULOG.md", "INSTALLATION.md", "SCHNITTSTELLE.md", "VEROEFFENTLICHEN.md"])
    check("K1 tools/: Bauwerkzeug", clean_listing(ROOT / "tools"), ["build.py"])
    gi = read(ROOT / ".gitignore").split()
    check("K1 .gitignore schließt Zwischenstände aus", [x in gi for x in ("__pycache__/", ".work/", "*.pyc", "*.zip", "out/", "dist/")], [True] * 6)
    kaputt = []
    for f in sorted(PKG.glob("*.py")):
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec", dont_inherit=True)
        except SyntaxError as err:
            kaputt.append(f"{f.name}: {err.msg[:80]}")
    check("K1 alle Python-Dateien des Bausteins übersetzen fehlerfrei", kaputt, [])


# =====================================================================================================================
# K2/K3: manifest.json und hacs.json
# =====================================================================================================================
_URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)$")


def repo_slug():
    m = load_json(PKG / "manifest.json")
    hit = _URL.match(str(m.get("documentation", "")))
    return f"{hit.group(1)}/{hit.group(2)}" if hit else None


def gruppe_manifest():
    m = load_json(PKG / "manifest.json")
    keys = list(m)
    check("K2 Schlüssel sortiert: domain, name, dann alphabetisch (hassfest)", [keys[:2], keys[2:] == sorted(keys[2:])], [["domain", "name"], True])
    check("K2 HACS-Pflichtschlüssel vorhanden", [k in m for k in ("codeowners", "documentation", "domain", "issue_tracker", "name", "version")], [True] * 6)
    check("K2 Schlüsseltypen", [isinstance(m.get("codeowners"), list), isinstance(m.get("domain"), str), isinstance(m.get("name"), str), isinstance(m.get("version"), str)], [True] * 4)
    check("K2 Domain = Ordnername = aikido_tracker", [m.get("domain"), PKG.name], ["aikido_tracker", "aikido_tracker"])
    check("K2 Name", m.get("name"), "Aikido Tracker")
    check("K2 Version hat die Form x.y.z", bool(re.fullmatch(r"\d+\.\d+\.\d+", str(m.get("version")))), True)
    const_version = re.search(r'^VERSION = "([^"]+)"', read(PKG / "const.py"), re.M)
    check("K2 Version im Manifest = VERSION in const.py (Schnittstelle meldet sie bei ping)", [m.get("version"), const_version and const_version.group(1)], [m.get("version"), m.get("version")])
    slug = repo_slug()
    check("K2 documentation: https://github.com/<Besitzer>/<Repository>", bool(slug), True)
    check("K2 issue_tracker = documentation + /issues", m.get("issue_tracker"), f"{m.get('documentation')}/issues")
    check("K2 codeowners: @Besitzer des Repositories", m.get("codeowners"), ["@" + (slug or "?/?").split("/")[0]])
    check("K2 abhängig nur von http, ohne zusätzliche Python-Pakete (nichts wird bei der Installation nachgeladen)", [m.get("dependencies"), m.get("requirements")], [["http"], []])
    check("K2 Einrichtung per configuration.yaml: kein config_flow-Eintrag", "config_flow" in m, False)
    check("K2 Typ und Art", [m.get("integration_type"), m.get("iot_class")], ["service", "local_push"])
    check("K2 loggers", m.get("loggers"), ["custom_components.aikido_tracker"])

    h = load_json(ROOT / "hacs.json")
    erlaubt = {"content_in_root", "country", "filename", "hacs", "hide_default_branch", "homeassistant", "persistent_directory", "render_readme", "zip_release", "name"}
    check("K3 hacs.json: nur bekannte Schlüssel (HACS lehnt unbekannte ab)", sorted(set(h) - erlaubt), [])
    check("K3 hacs.json: name ist Pflicht und gleich dem Namen im Manifest", [h.get("name"), h.get("name") == m.get("name")], [m.get("name"), True])
    check("K3 hacs.json: kein zip_release ohne filename", bool(h.get("zip_release")) and not h.get("filename"), False)
    check("K3 hacs.json: kein content_in_root (der Baustein liegt in custom_components)", h.get("content_in_root", False), False)
    check("K3 hacs.json: keine Mindestversion von Home Assistant, die ungetestet blockieren könnte", "homeassistant" in h, False)


# =====================================================================================================================
# K4: Versionen und Änderungsprotokolle stimmen überein
# =====================================================================================================================
def gruppe_versionen():
    m = load_json(PKG / "manifest.json")
    ver = m["version"]
    log = read(ROOT / "CHANGELOG.md")
    heads = re.findall(r"^## \[(\d+\.\d+\.\d+)\] – (\d{4}-\d{2}-\d{2})\s*$", log, re.M)
    check("K4 CHANGELOG: oberster Eintrag = Version im Manifest", heads[0][0] if heads else None, ver)
    tup = [tuple(int(x) for x in v.split(".")) for v, _ in heads]
    check("K4 CHANGELOG: Versionen absteigend und ohne Doppelte", tup == sorted(set(tup), reverse=True), True)
    daten = []
    for _, d in heads:
        try:
            daten.append(dt.date.fromisoformat(d))
        except ValueError:
            daten.append(None)
    check("K4 CHANGELOG: gültige Daten, nicht aufsteigend", None not in daten and daten == sorted(daten, reverse=True), True)
    app = read(PKG / "app" / "aikido-kyu-tracker.html")
    appver = re.search(r'APP_VERSION = "([^"]+)"', app)
    top = re.split(r"^## \[", log, flags=re.M)[1] if heads else ""
    check("K4 oberster CHANGELOG-Eintrag nennt die mitgelieferte App-Version", bool(appver) and f"App v{appver.group(1)}" in top, True)
    baulog = read(ROOT / "docs" / "BAULOG.md")
    first = re.search(r"^## .*?Version (\d+\.\d+\.\d+)", baulog, re.M)
    check("K4 BAULOG: oberster Eintrag = aktuelle Version", first and first.group(1), ver)
    api = read(ROOT / "docs" / "SCHNITTSTELLE.md")
    check("K4 SCHNITTSTELLE: Beispielantwort von ping nennt die aktuelle Version", f'"version": "{ver}"' in api, True)


# =====================================================================================================================
# K5/K6: Symbol und App
# =====================================================================================================================
def gruppe_symbol_app():
    check("K5 Symbol icon.png: PNG, 256 x 256", png_size(PKG / "brand" / "icon.png"), (256, 256))
    check("K5 Symbol icon@2x.png: PNG, 512 x 512", png_size(PKG / "brand" / "icon@2x.png"), (512, 512))
    check("K5 Symbole klein genug (je unter 200 KB)", [(PKG / "brand" / n).stat().st_size < 200_000 for n in ("icon.png", "icon@2x.png")], [True, True])
    app = (PKG / "app" / "aikido-kyu-tracker.html").read_bytes()
    text = app.decode("utf-8", "replace")
    check("K6 App: HTML-Seite, UTF-8, mit Titel und APP_VERSION", [app[:15].lower(), "<title>" in text, bool(re.search(r'APP_VERSION = "\d+\.\d+"', text)), "�" in text], [b"<!doctype html>", True, True, False])
    check("K6 App: Größe plausibel (100 KB bis 2 MB)", 100_000 < len(app) < 2_000_000, True)
    check("K6 App: Zeilenenden LF (kein CRLF, sonst ändert sich der Inhalt bei jedem Hochladen)", b"\r\n" in app, False)


# =====================================================================================================================
# K7: nichts im Repository, was nicht hinein gehört
# =====================================================================================================================
def gruppe_inhalt():
    dateien = shipped()
    check("K7 keine Zwischendateien (pycache, pyc, tmp, log, zip, env, secrets)", [f for f in dateien if re.search(r"(__pycache__|\.pyc$|\.tmp$|\.log$|\.zip$|(^|/)\.env$|(^|/)secrets\.ya?ml$|\.DS_Store)", f)], [])
    check("K7 keine Datei über 1 MB", [f for f in dateien if (ROOT / f).stat().st_size > 1_000_000], [])
    # Geheimnisse und Spuren der Entwicklungsumgebung (Muster zerlegt, damit diese Datei sich nicht selbst findet)
    muster = [r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"gho_[A-Za-z0-9]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
              r"sk-ant-[A-Za-z0-9_-]{20,}", r"AKIA[0-9A-Z]{16}",
              "/tmp/" + "claude", "scratch" + "pad", "hlf" + "krems", "schoen" + "baeck", "schön" + "bäck"]
    treffer = []
    for f in dateien:
        if f.endswith(".png"):
            continue
        t = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        for mu in muster:
            if re.search(mu, t, re.I if not mu.startswith(("ghp_", "github_", "gho_", "sk-", "AKIA", "-----")) else 0):
                treffer.append(f"{f}: {mu[:18]}")
    check("K7 keine Zugangsdaten, keine Pfade der Entwicklungsumgebung, keine privaten Namen/Adressen", treffer, [])
    produktiv = [f for f in dateien if not f.startswith("tests/")]
    check("K7 Test-Einladungscode steht nur in tests/", [f for f in produktiv if "einladung-7" in (ROOT / f).read_text(encoding="utf-8", errors="replace")], [])


# =====================================================================================================================
# K8: GitHub-Workflows
# =====================================================================================================================
def _on(wf):
    return wf.get("on", wf.get(True)) or {}


def gruppe_workflows():
    if yaml is None:
        check("K8 PyYAML ist installiert (pip install pyyaml)", False, True)
        return
    val = yaml.safe_load(read(ROOT / ".github" / "workflows" / "validate.yml"))
    rel = yaml.safe_load(read(ROOT / ".github" / "workflows" / "release.yml"))
    on = _on(val)
    check("K8 validate: läuft bei push, pull_request, täglich und von Hand", [k in on for k in ("push", "pull_request", "schedule", "workflow_dispatch")], [True] * 4)
    steps = [s for j in val["jobs"].values() for s in j.get("steps", [])]
    uses = {s.get("uses", "").split("@")[0]: s for s in steps if s.get("uses")}
    check("K8 validate: HACS-Prüfung als Integration", [bool(uses.get("hacs/action")), (uses.get("hacs/action") or {}).get("with", {}).get("category")], [True, "integration"])
    check("K8 validate: hassfest und Tests laufen mit", [bool(uses.get("home-assistant/actions/hassfest")), any("tests/test_server.py" in str(s.get("run", "")) for s in steps), any("tests/test_package.py" in str(s.get("run", "")) for s in steps)], [True] * 3)
    check("K8 validate: HACS-Prüfung ignoriert nur 'license' (noch keine Lizenz festgelegt)", (uses.get("hacs/action") or {}).get("with", {}).get("ignore"), "license")
    ron = _on(rel)
    check("K8 release: startet nur bei Tags v*", [list(ron), (ron.get("push") or {}).get("tags")], [["push"], ["v*"]])
    check("K8 release: darf Releases schreiben (contents: write)", (rel.get("permissions") or {}).get("contents"), "write")
    rsteps = [s for j in rel["jobs"].values() for s in j.get("steps", [])]
    rruns = "\n".join(str(s.get("run", "")) for s in rsteps)
    check("K8 release: Tag und Manifest-Version vergleichen, Tests, Release-Text, ZIP, gh release create", [x in rruns for x in ("check-tag", "tests/test_server.py", "tests/test_package.py", "build.py notes", "build.py zip", "gh release create")], [True] * 6)
    alle_runs = [str(s.get("run", "")) for wf in (val, rel) for j in wf["jobs"].values() for s in j.get("steps", [])]
    check("K8 keine fremden Eingaben direkt im Shell-Text (${{ github.event/head_ref … }}: Einschleus-Gefahr)", [r for r in alle_runs if re.search(r"\$\{\{\s*github\.(event|head_ref)", r)], [])
    check("K8 kein pull_request_target", ["pull_request_target" in _on(wf) for wf in (val, rel)], [False, False])
    ohne_ref = [s["uses"] for wf in (val, rel) for j in wf["jobs"].values() for s in j.get("steps", []) if s.get("uses") and "@" not in s["uses"]]
    check("K8 jede verwendete Aktion nennt eine Version/einen Zweig (@…)", ohne_ref, [])
    fehlen = []
    for r in alle_runs:
        for pfad in re.findall(r"\b((?:tests|tools)/[A-Za-z0-9_./-]+\.py)\b", r):
            if not (ROOT / pfad).is_file():
                fehlen.append(pfad)
    check("K8 alle in den Workflows genannten Dateien existieren", fehlen, [])


# =====================================================================================================================
# K9: Dokumentation
# =====================================================================================================================
def gruppe_doku():
    slug = repo_slug() or "?/?"
    owner, repo = slug.split("/")
    readme = read(ROOT / "README.md")
    check("K9 README nennt die Repository-Adresse", f"https://github.com/{slug}" in readme, True)
    check("K9 README: Ein-Klick-Link (My Home Assistant) für dieses Repository", f"https://my.home-assistant.io/redirect/hacs_repository/?owner={owner}&repository={repo}&category=integration" in readme, True)
    for abschnitt in ("## Installation", "## Einrichtung", "## Aktualisieren", "## Sicherheit", "## Lizenz"):
        check(f"K9 README enthält den Abschnitt '{abschnitt}'", abschnitt in readme, True)
    check("K9 README erklärt den HACS-Weg und die Adresse der App", [x in readme for x in ("Benutzerdefinierte Repositories", "invite_code", "/aikido-tracker")], [True] * 3)
    check("K9 README: kein Verweis auf das frühere Kopieren der App nach www", "/config/www" in readme, False)
    kaputt = []
    for datei in [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]:
        for ziel in re.findall(r"\]\(([^)\s]+)\)", read(datei)):
            if re.match(r"^(https?:|mailto:|#)", ziel):
                continue
            pfad = (datei.parent / ziel.split("#")[0]).resolve()
            if not pfad.exists():
                kaputt.append(f"{datei.name} -> {ziel}")
    check("K9 alle relativen Verweise in README und docs führen zu vorhandenen Dateien", kaputt, [])
    install = read(ROOT / "docs" / "INSTALLATION.md")
    check("K9 INSTALLATION: HACS zuerst, page_file nur als Ausnahme erwähnt", [install.find("HACS") != -1, install.find("HACS") < install.find("Manuell"), "page_file" in install], [True, True, True])
    veroeff = read(ROOT / "docs" / "VEROEFFENTLICHEN.md")
    check("K9 VEROEFFENTLICHEN: nennt Repository, öffentlich, Beschreibung, Themen, Release und ein Tag-Beispiel (vX.Y.Z)", [x in veroeff for x in (repo, "öffentlich", "Beschreibung", "Themen", "Release")] + [bool(re.search(r"\bv\d+\.\d+\.\d+\b", veroeff))], [True] * 6)


# =====================================================================================================================
# K10: Bauwerkzeug (notes, check-tag, files, zip, sync-app)
# =====================================================================================================================
def gruppe_werkzeug():
    ver = load_json(PKG / "manifest.json")["version"]
    rc, out, err = run_tool("notes", f"v{ver}")
    check("K10 notes: Text des obersten Eintrags (Exitcode 0, nennt die App-Version, ohne die Überschrift der nächsten Version)", [rc, "App v" in out, out.count("## [")], [0, True, 0])
    check("K10 notes: unbekannte Version -> Exitcode 1", run_tool("notes", "v9.9.9")[0], 1)
    check("K10 check-tag: passender Tag -> 0", run_tool("check-tag", f"v{ver}")[0], 0)
    check("K10 check-tag: falscher Tag -> 1", run_tool("check-tag", "v0.0.1")[0], 1)
    check("K10 check-tag: Tag ohne v -> 1", run_tool("check-tag", ver)[0], 1)
    rc, out, err = run_tool("files")
    check("K10 files: Liste = unabhängig ermittelte Liste", [rc, out.split("\n")[:-1] if out.endswith("\n") else out.split("\n")], [0, shipped()])

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="aikido-k10-"))
    try:
        o1, o2 = tmp / "eins", tmp / "zwei"
        rc1, out1, err1 = run_tool("zip", "--out", str(o1))
        rc2, out2, err2 = run_tool("zip", "--out", str(o2))
        check("K10 zip: beide Läufe erfolgreich", [rc1, rc2], [0, 0])
        repo_zip = o1 / f"aikido-tracker-{ver}.zip"
        paket_zip = o1 / "aikido_tracker.zip"
        check("K10 zip: erwartete Dateien", sorted(p.name for p in o1.iterdir()) if o1.exists() else [], sorted([repo_zip.name, paket_zip.name]))
        if repo_zip.exists() and paket_zip.exists():
            with zipfile.ZipFile(repo_zip) as z:
                check("K10 zip (Repository): Inhalt = Dateiliste des Repositories", sorted(z.namelist()), shipped())
                check("K10 zip (Repository): feste Zeitstempel und Rechte (gleicher Inhalt = gleiche Datei)", sorted({(i.date_time, i.external_attr >> 16) for i in z.infolist()}), [((2026, 1, 1, 0, 0, 0), 0o100644)])
            with zipfile.ZipFile(paket_zip) as z:
                im_paket = sorted(p.relative_to(PKG).as_posix() for p in PKG.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
                check("K10 zip (Baustein): Inhalt = Ordner des Bausteins, manifest.json ganz oben", [sorted(z.namelist()), "manifest.json" in z.namelist()], [im_paket, True])
            h1 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in o1.iterdir()}
            h2 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in o2.iterdir()}
            check("K10 zip: zweimal gebaut = Byte für Byte gleich", h1 == h2, True)
            check("K10 zip: Prüfsummen stehen in der Ausgabe", all(h in out1 for h in h1.values()), True)

        # sync-app auf einer KOPIE des Repositories
        kopie = tmp / "kopie"
        for f in shipped():
            ziel = kopie / f
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, ziel)
        app = kopie / "custom_components" / "aikido_tracker" / "app" / "aikido-kyu-tracker.html"
        alt = app.read_bytes()
        neu = tmp / "neue-app.html"
        neu.write_bytes(re.sub(rb'APP_VERSION = "[^"]+"', b'APP_VERSION = "9.9"', alt))
        rc, out, err = run_tool("sync-app", str(neu), root=kopie)
        check("K10 sync-app: kopiert die App und nennt ihre Version", [rc, app.read_bytes() == neu.read_bytes(), "9.9" in out], [0, True, True])
        kaputt1 = tmp / "kein-html.html"
        kaputt1.write_bytes(b'<p>kein Doctype</p>\n<script>APP_VERSION = "1.0"</script>\n')
        rc, out, err = run_tool("sync-app", str(kaputt1), root=kopie)
        check("K10 sync-app: Datei ohne <!DOCTYPE html> wird abgelehnt (obwohl APP_VERSION drinsteht), Ziel bleibt unverändert", [rc, app.read_bytes() == neu.read_bytes()], [1, True])
        kaputt2 = tmp / "ohne-version.html"
        kaputt2.write_bytes(b"<!DOCTYPE html><title>x</title>")
        rc, out, err = run_tool("sync-app", str(kaputt2), root=kopie)
        check("K10 sync-app: HTML ohne APP_VERSION wird abgelehnt", [rc, app.read_bytes() == neu.read_bytes()], [1, True])
        rc, out, err = run_tool("sync-app", str(tmp / "gibt-es-nicht.html"), root=kopie)
        check("K10 sync-app: fehlende Datei -> 1", rc, 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================================================================
def main():
    gruppen = [gruppe_aufbau, gruppe_manifest, gruppe_versionen, gruppe_symbol_app, gruppe_inhalt, gruppe_workflows, gruppe_doku, gruppe_werkzeug]
    wahl = [a.lower() for a in sys.argv[1:]]
    global N, FEHLER
    for g in gruppen:
        if wahl and not any(w in g.__name__ for w in wahl):
            continue
        try:
            g()
        except Exception as err:
            N += 1
            FEHLER += 1
            print(f"  FALSCH {g.__name__}: abgebrochen – {type(err).__name__}: {err}")
            traceback.print_exc(limit=3)
    print(f"\nRepository-Prüfung: {N - FEHLER} von {N} Prüfungen bestanden{f' — {FEHLER} FEHLGESCHLAGEN' if FEHLER else ' — alles grün'}   (Quelle: {ROOT})")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(main())
