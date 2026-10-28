#!/usr/bin/env python3
"""Gegenprobe: baut absichtlich Fehler ein und prüft, ob die Tests jeden bemerken.

Drei Arten (jede Mutation arbeitet auf einer KOPIE, das Original bleibt unberührt; "erkannt" = der Test meldet Fehler):
  M   Fehler im Baustein      -> tests/test_server.py (je Mutation alle Gruppen oder nur die genannten)
  ML  Fehler in __init__.py   -> tests/test_live.py (echtes Home Assistant, nacheinander, je ca. 35 s; mit AIKIDO_NO_LIVE=1 überspringen)
  MP  Fehler im Repository    -> tests/test_package.py (Manifest, hacs.json, Symbol, Workflows, Doku, Werkzeug ...)
Aufruf:  python3 tests/mutationen.py [Teil des Namens ...]      Ergebnis: <Arbeitsordner>/mut/ergebnis.txt
Arbeitsordner: AIKIDO_WORK (Vorgabe .work im Repository); AIKIDO_SRC = anderer Quellordner des Bausteins;
AIKIDO_HASS = Pfad zu `hass` (nur für ML).
"""
import concurrent.futures
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import time
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path(os.environ.get("AIKIDO_SRC") or ROOT / "custom_components" / "aikido_tracker")
WORK = pathlib.Path(os.environ.get("AIKIDO_WORK") or ROOT / ".work")
OUT = WORK / "mut"
PY = sys.executable
TEST = str(ROOT / "tests" / "test_server.py")
TEST_PKG = str(ROOT / "tests" / "test_package.py")
TEST_LIVE = str(ROOT / "tests" / "test_live.py")

# (Name, Datei, [(alt, neu), ...])  – "alt" muss genau einmal vorkommen
M = [
    # ---- identity.py ----
    ("name-strip-weg", "identity.py", [('for c in text).strip()', 'for c in text)')]),
    ("name-leerzeichen-nicht-zusammengefasst", "identity.py", [('while "  " in text:', 'while False:')]),
    ("name-laenge-40-zu-streng", "identity.py", [('if not 1 <= len(text) <= MAX_NAME_LEN:', 'if not 1 <= len(text) < MAX_NAME_LEN:')]),
    ("name-unerlaubte-zeichen-erlaubt", "identity.py", [('            raise InvalidName("Der Name enthält unerlaubte Zeichen.")', '            continue')]),
    ("name-ohne-buchstabe-erlaubt", "identity.py", [('if not has_letter_or_digit:', 'if False:')]),
    ("kennung-ohne-umschrift", "identity.py", [('.translate(_ID_MAP)', '')]),
    ("kennung-akzente-bleiben", "identity.py", [('unicodedata.category(c)[0] != "M")', 'unicodedata.category(c)[0] != "Z")')]),
    ("kennung-nicht-gekuerzt", "identity.py", [('[:MAX_NAME_LEN].strip("-")', '.strip("-")')]),
    ("kennung-hash-zu-kurz", "identity.py", [('hexdigest()[:12]', 'hexdigest()[:8]')]),
    ("code-mindestlaenge", "identity.py", [('if not MIN_CODE_LEN <= len(code) <= MAX_CODE_LEN:', 'if not MIN_CODE_LEN < len(code) <= MAX_CODE_LEN:')]),
    ("code-hoechstlaenge", "identity.py", [('if not MIN_CODE_LEN <= len(code) <= MAX_CODE_LEN:', 'if not MIN_CODE_LEN <= len(code) < MAX_CODE_LEN:')]),
    ("code-nur-leerzeichen-erlaubt", "identity.py", [('if not code.strip():', 'if False:')]),
    ("code-steuerzeichen-erlaubt", "identity.py", [('if any(unicodedata.category(c)[0] == "C" for c in code):', 'if False:')]),
    ("hash-festes-salz", "identity.py", [('salt = secrets.token_bytes(16)', 'salt = bytes(16)')]),
    ("verify-verfahren-ignoriert", "identity.py", [(' or auth.get("alg") != "scrypt":', ':')]),
    ("verify-immer-wahr", "identity.py", [('return hmac.compare_digest(_scrypt(code, salt, n, r, p), expected)', 'return True')]),
    # ---- store.py ----
    ("store-unveraendert-erkennung-weg", "store.py", [('if prepared.digest == meta.digest:', 'if False:')]),
    ("store-konflikt-erkennung-weg", "store.py", [('if base_rev != meta.rev:', 'if False:')]),
    ("store-rev-springt-um-zwei", "store.py", [('rev=meta.rev + 1,', 'rev=meta.rev + 2,')]),
    ("store-sicherung-schon-bei-rev-0", "store.py", [('if old.rev >= 1 and not os.path.exists(snapshot):', 'if old.rev >= 0 and not os.path.exists(snapshot):')]),
    ("store-sicherung-wird-ueberschrieben", "store.py", [('if old.rev >= 1 and not os.path.exists(snapshot):', 'if old.rev >= 1:')]),
    ("store-aufraeumen-grenze-person", "store.py", [('dt.date.fromisoformat(match.group(1)) <= cutoff', 'dt.date.fromisoformat(match.group(1)) < cutoff')]),
    ("store-aufraeumen-grenze-geloeschte", "store.py", [('.date() <= cutoff:', '.date() < cutoff:')]),
    ("store-history-null-ignoriert", "store.py", [('if self._history_days > 0:\n            snapshot =', 'if True:\n            snapshot =')]),
    ("store-temporaerdatei-bleibt-liegen", "store.py", [('            os.unlink(tmp)', '            pass')]),
    ("store-unlesbare-werden-ignoriert", "store.py", [('metas[pid] = Meta(id=pid, name=pid, unreadable=True)', 'pass')]),
    ("store-temporaerdateien-beim-start-bleiben", "store.py", [('if entry.name.endswith(".tmp"):', 'if False:')]),
    ("store-voll-vor-vergeben", "store.py", [('        if pid in self._metas:\n            raise NameTaken(pid)\n        if len(self._metas) >= self._max_persons:\n            raise StoreFull(str(self._max_persons))',
                                             '        if len(self._metas) >= self._max_persons:\n            raise StoreFull(str(self._max_persons))\n        if pid in self._metas:\n            raise NameTaken(pid)')]),
    ("store-name-wird-zu-spaet-reserviert", "store.py", [('        self._metas[pid] = meta  # Name sofort reservieren (gleichzeitige Anmeldungen desselben Namens)', '        pass'),
                                                         ('                await self._run(self._create_sync, meta, now)', '                await self._run(self._create_sync, meta, now)\n                self._metas[pid] = meta')]),
    ("store-loeschen-ohne-letzten-stand", "store.py", [('_atomic_write(os.path.join(target, "final.json.gz"), _snapshot_bytes(doc))', 'pass')]),
    ("store-loeschen-laesst-datei-liegen", "store.py", [('        os.unlink(path)\n        _fsync_dir(self._persons_dir)', '        pass\n        _fsync_dir(self._persons_dir)')]),
    ("store-neuer-code-nicht-im-speicher", "store.py", [('            await self._run(self._set_auth_sync, pid, auth)\n            meta.auth = auth', '            await self._run(self._set_auth_sync, pid, auth)')]),
    ("store-neuer-code-nicht-auf-platte", "store.py", [('        _atomic_write(path, _doc_bytes(meta, canonical(doc["data"]).encode("utf-8")))', '        pass')]),
    ("store-schluesselmuster-nur-anfang", "store.py", [('_KEY_RE.fullmatch(key)', '_KEY_RE.match(key)')]),
    ("store-31-schluessel-erlaubt", "store.py", [('if len(data) > MAX_DATA_KEYS:', 'if len(data) > MAX_DATA_KEYS + 1:')]),
    ("store-groessengrenze-zu-streng", "store.py", [('if len(raw) > MAX_DATA_BYTES:', 'if len(raw) >= MAX_DATA_BYTES:')]),
    ("store-groessengrenze-zu-locker", "store.py", [('if len(raw) > MAX_DATA_BYTES:', 'if len(raw) > MAX_DATA_BYTES + 1:')]),
    ("store-nan-ganz-erlaubt", "store.py", [('return json.loads(text, parse_constant=_no_constant, parse_float=_parse_float)', 'return json.loads(text)'),
                                            ('separators=(",", ":"), allow_nan=False)', 'separators=(",", ":"), allow_nan=True)')]),
    ("store-ordnerrechte-offen", "store.py", [('        os.chmod(path, 0o700)', '        os.chmod(path, 0o755)')]),
    ("store-schreiben-ohne-sperre", "store.py", [('        async with self._lock_for(pid):\n            meta = self._usable(pid)\n            if prepared.digest == meta.digest:', '        if True:\n            meta = self._usable(pid)\n            if prepared.digest == meta.digest:')]),
    # ---- api.py / limits.py / const.py ----
    ("api-einladungscode-immer-richtig", "api.py", [('if not _same_secret(invite_raw, self._invite):', 'if False:')]),
    ("api-sperre-adresse-11", "const.py", [('LIMIT_FAIL_IP = 10 ', 'LIMIT_FAIL_IP = 11 ')]),
    ("api-sperre-person-31", "const.py", [('LIMIT_FAIL_PERSON = 30 ', 'LIMIT_FAIL_PERSON = 31 ')]),
    ("api-schreibgrenze-31", "const.py", [('LIMIT_WRITE = 30 ', 'LIMIT_WRITE = 31 ')]),
    ("api-anfragegrenze-121", "const.py", [('LIMIT_REQUEST_IP = 120 ', 'LIMIT_REQUEST_IP = 121 ')]),
    ("api-erfolg-wird-nicht-ausgebucht", "limits.py", [('        queue = self._events.get(key)\n        if queue is None:\n            return\n        try:\n            queue.remove(stamp)', '        return\n        queue = self._events.get(key)\n        if queue is None:\n            return\n        try:\n            queue.remove(stamp)')]),
    ("api-gleichzeitige-versuche-nicht-gesperrt", "api.py", [('        retry = self._fail_ip.retry_after(ip, now)\n        if retry:\n            raise _rate_error(retry, "Zu viele Fehlversuche von dieser Adresse. Bitte später erneut versuchen.")\n        if pid is not None:', '        if pid is not None:')]),
    ("api-unbekannter-name-rechnet-keinen-hash", "api.py", [('ok = await self._cpu_bound(self._verify, code if code is not None else _NO_CODE, auth)', 'ok = usable and await self._cpu_bound(self._verify, code if code is not None else _NO_CODE, auth)')]),
    ("api-keine-kompression", "api.py", [('if accepts_gzip and len(body) > _GZIP_FROM_BYTES:', 'if False:')]),
    ("api-nosniff-weg", "api.py", [('all_headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}', 'all_headers = {"Cache-Control": "no-store"}')]),
    ("api-no-store-weg", "api.py", [('all_headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}', 'all_headers = {"X-Content-Type-Options": "nosniff"}')]),
    ("api-loeschen-ohne-genaue-bestaetigung", "api.py", [('if body.get("confirm") is not True:', 'if not body.get("confirm"):')]),
    ("api-koerpergrenze-ohne-inhaltslaenge-weg", "api.py", [('                    if total > MAX_BODY_BYTES:', '                    if False:')]),
    ("api-koerpergrenze-mit-inhaltslaenge-weg", "api.py", [('if declared is not None and declared > MAX_BODY_BYTES:', 'if False:')]),
    ("api-kaputtes-json-als-422", "api.py", [('raise ApiError(400, "bad_request", "Die Anfrage ist kein gültiges JSON.") from None', 'raise ApiError(422, "invalid_data", "Die Anfrage ist kein gültiges JSON.") from None')]),
    ("api-ipv6-nicht-zusammengefasst", "api.py", [('return str(ipaddress.ip_network(f"{address}/64", strict=False))', 'return str(address)')]),
    ("api-ping-wird-gesperrt", "api.py", [('return await self._guard(request, self._ping, counted=False)', 'return await self._guard(request, self._ping, counted=True)')]),
    ("limits-wartezeit-falsch", "limits.py", [('blocking = queue[len(queue) - self.limit]', 'blocking = queue[-1]')]),
    ("limits-keine-obergrenze", "limits.py", [('if key not in self._events and len(self._events) >= self.max_keys:', 'if False:')]),
    # ---- page.py ----
    ("seite-langer-zwischenspeicher", "page.py", [('"Cache-Control": "no-cache",', '"Cache-Control": "public, max-age=2678400",')]),
    # ---- page.py / store.py: mitgelieferte App, page_file, Schutz des Datenordners (nur die Gruppen W und S laufen) ----
    ("seite-page-file-wird-ignoriert", "page.py", [("    if configured:\n        return os.path.join(config_dir, configured)", "    if False:\n        return os.path.join(config_dir, configured)")], "W S"),
    ("seite-leeres-page-file-gilt", "page.py", [("    if configured:\n        return os.path.join(config_dir, configured)", "    if configured is not None:\n        return os.path.join(config_dir, configured)")], "W S"),
    ("seite-falscher-dateiname", "page.py", [('BUNDLED_FILE = "aikido-kyu-tracker.html"', 'BUNDLED_FILE = "aikido-tracker.html"')], "W S"),
    ("seite-falscher-ordner", "page.py", [('BUNDLED_DIR = "app"', 'BUNDLED_DIR = "www"')], "W S"),
    ("seite-404-text-alt", "page.py", [("(in HACS: Neu herunterladen) oder prüfe die Einstellung page_file.", "in den Ordner www legen.")], "W S"),
    ("pfad-praefix-ohne-trenner", "store.py", [("child.startswith(base.rstrip(os.sep) + os.sep)", "child.startswith(base)")], "W S"),
    ("pfad-ohne-verknuepfungen", "store.py", [("    child = os.path.realpath(path)\n    base = os.path.realpath(parent)", "    child = os.path.abspath(path)\n    base = os.path.abspath(parent)")], "W S"),
    ("pfad-gleicher-ordner-zaehlt-nicht", "store.py", [("    return child == base or child.startswith(", "    return child.startswith(")], "W S"),
    ("pfad-nur-gleicher-ordner", "store.py", [(" or child.startswith(base.rstrip(os.sep) + os.sep)", "")], "W S"),
]

# ---- ML: Fehler in __init__.py, nur mit echtem Home Assistant zu bemerken ----
ML = [
    ("init-schutz-datenordner-weg", "__init__.py", [("    if is_inside(data_dir, package_dir):", "    if False:")]),
    ("init-page-file-wird-ignoriert", "__init__.py", [("resolve_page_path(hass.config.config_dir, conf.get(CONF_PAGE_FILE), package_dir)", "resolve_page_path(hass.config.config_dir, None, package_dir)")]),
    ("init-falscher-baustein-ordner", "__init__.py", [("    package_dir = os.path.dirname(os.path.abspath(__file__))", "    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")]),
    ("init-seite-nicht-registriert", "__init__.py", [("    hass.http.register_view(_make_page_view(lambda: page_file))", "    pass")]),
]


def _png(path, size):
    """Kleinste gültige PNG-Datei (einfarbig) in der Größe size x size."""
    raw = b"".join(b"\x00" + b"\x1b\x2a\x41\xff" * size for _ in range(size))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _edit(rel, old, new):
    def fn(repo):
        f = repo / rel
        text = f.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise ValueError(f"Ersetzungstext kommt {text.count(old)}x vor in {rel}: {old[:50]!r}")
        f.write_text(text.replace(old, new), encoding="utf-8")
    return fn


def _delete(rel):
    return lambda repo: (repo / rel).unlink()


def _add(rel, content):
    def fn(repo):
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return fn


def _append(rel, text):
    def fn(repo):
        f = repo / rel
        f.write_text(f.read_text(encoding="utf-8") + text, encoding="utf-8")
    return fn


PK = "custom_components/aikido_tracker/"
# ---- MP: Fehler im Repository (Aufruf: Name, Änderung an einer Kopie) ----
MP = [
    ("paket-manifest-unsortiert", lambda repo: _manifest_unsortiert(repo), "K2"),
    ("paket-manifest-ohne-documentation", _edit(PK + "manifest.json", '  "documentation": "https://github.com/Okami89AUT/Aiki-Nikki",\n', ""), "K2"),
    ("paket-manifest-ohne-issue-tracker", _edit(PK + "manifest.json", '  "issue_tracker": "https://github.com/Okami89AUT/Aiki-Nikki/issues",\n', ""), "K2"),
    ("paket-manifest-codeowner-falsch", _edit(PK + "manifest.json", '"@Okami89AUT"', '"@jemand-anders"'), "K2"),
    ("paket-manifest-mit-config-flow", _edit(PK + "manifest.json", '  "dependencies"', '  "config_flow": true,\n  "dependencies"'), "K2"),
    ("paket-version-const-abweichend", _edit(PK + "const.py", 'VERSION = "1.1.0"', 'VERSION = "1.1.1"'), "K2"),
    ("paket-zwei-integrationen", _add("custom_components/zweite/__init__.py", ""), "K1"),
    ("paket-fremde-datei-im-baustein", _add(PK + "notizen.txt", "x"), "K1"),
    ("paket-hacs-json-unbekannter-schluessel", _edit("hacs.json", '"name": "Aikido Tracker"', '"name": "Aikido Tracker",\n  "foo": 1'), "K3"),
    ("paket-hacs-json-mindestversion", _edit("hacs.json", '"name": "Aikido Tracker"', '"name": "Aikido Tracker",\n  "homeassistant": "2026.3.0"'), "K3"),
    ("paket-hacs-json-anderer-name", _edit("hacs.json", '"name": "Aikido Tracker"', '"name": "Aikido"'), "K3"),
    ("paket-hacs-json-fehlt", _delete("hacs.json"), "K1"),
    ("paket-symbol-falsche-groesse", lambda repo: _png(repo / PK / "brand" / "icon.png", 255), "K5"),
    ("paket-symbol-fehlt", _delete(PK + "brand/icon.png"), "K1"),
    ("paket-app-fehlt", _delete(PK + "app/aikido-kyu-tracker.html"), "K1"),
    ("paket-app-ohne-version", _edit(PK + "app/aikido-kyu-tracker.html", 'APP_VERSION = "2.1"', 'APP_VERSIONX = "2.1"'), "K6"),
    ("paket-app-mit-windows-zeilenenden", lambda repo: (repo / PK / "app" / "aikido-kyu-tracker.html").write_bytes((repo / PK / "app" / "aikido-kyu-tracker.html").read_bytes().replace(b"\n", b"\r\n")), "K6"),
    ("paket-changelog-ohne-app-version", _edit("CHANGELOG.md", "(App v2.1).\n\n### Neu", "(App v9.9).\n\n### Neu"), "K4"),
    ("paket-changelog-falsche-version", _edit("CHANGELOG.md", "## [1.1.0] – 2026-10-27", "## [1.2.0] – 2026-10-27"), "K4"),
    ("paket-baulog-alte-version", _edit("docs/BAULOG.md", "## ✅ Version 1.1.0 (27.10.2026)", "## ✅ Version 1.0.5 (27.10.2026)"), "K4"),
    ("paket-schnittstelle-alte-version", _edit("docs/SCHNITTSTELLE.md", '"version": "1.1.0"', '"version": "1.0.0"'), "K4"),
    ("paket-workflow-release-ohne-schreibrecht", _edit(".github/workflows/release.yml", "  contents: write", "  contents: read"), "K8"),
    ("paket-workflow-release-ohne-tagpruefung", _edit(".github/workflows/release.yml", 'run: python tools/build.py check-tag "$GITHUB_REF_NAME"', 'run: echo ohne Pruefung'), "K8"),
    ("paket-workflow-ohne-hacs-pruefung", _edit(".github/workflows/validate.yml", "uses: hacs/action@main", "uses: actions/checkout@v4"), "K8"),
    ("paket-workflow-aktion-ohne-version", _edit(".github/workflows/validate.yml", "uses: home-assistant/actions/hassfest@master", "uses: home-assistant/actions/hassfest"), "K8"),
    ("paket-workflow-einschleusung", _edit(".github/workflows/validate.yml", "run: pip install aiohttp pyyaml", 'run: echo "${{ github.event.head_commit.message }}"'), "K8"),
    ("paket-workflow-pull-request-target", _edit(".github/workflows/validate.yml", "  pull_request:\n", "  pull_request_target:\n"), "K8"),
    ("paket-workflow-fehlende-datei", _edit(".github/workflows/validate.yml", "python tests/test_package.py", "python tests/test_paket.py"), "K8"),
    ("paket-readme-ohne-repo-adresse", _edit("README.md", "https://github.com/Okami89AUT/Aiki-Nikki`", "https://github.com/jemand/anderes`"), "K9"),
    ("paket-readme-kaputter-verweis", _edit("README.md", "[docs/INSTALLATION.md](docs/INSTALLATION.md).", "[docs/INSTALLATION.md](docs/gibts-nicht.md)."), "K9"),
    ("paket-readme-altes-www-kopieren", _edit("README.md", "## Einrichtung\n", "## Einrichtung\n\nDatei nach /config/www legen.\n"), "K9"),
    ("paket-veroeffentlichen-falscher-repo-name", _edit("docs/VEROEFFENTLICHEN.md", "`Okami89AUT/Aiki-Nikki` ist angelegt", "`Okami89AUT/anderes` ist angelegt"), "K9"),
    ("paket-zugangsdaten-im-repo", _append("docs/INSTALLATION.md", "\nToken: ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8\n"), "K7"),
    ("paket-private-adresse-im-repo", _append("docs/INSTALLATION.md", "\nKontakt: daniel." + "schoen" + "baeck" + "@hlf" + "krems.ac.at\n"), "K7"),
    ("paket-pfad-der-entwicklung-im-repo", _append("docs/INSTALLATION.md", "\nAblage: /tmp/" + "claude-0/x\n"), "K7"),
    ("paket-test-einladungscode-im-repo", _append("docs/INSTALLATION.md", "\nEinladung: einladung-7\n"), "K7"),
    ("paket-env-datei", _add(".env", "X=1\n"), "K7"),
    ("paket-werkzeug-zip-zeitstempel", _edit("tools/build.py", "ZIP_TIME = (2026, 1, 1, 0, 0, 0)", "ZIP_TIME = (2026, 1, 2, 0, 0, 0)"), "K10"),
    ("paket-werkzeug-tag-wird-nicht-verglichen", _edit("tools/build.py", "    if version != have:", "    if False:"), "K10"),
    ("paket-werkzeug-notes-leer", _edit("tools/build.py", "            return part[head.end():].strip()", '            return ""'), "K10"),
    ("paket-werkzeug-sync-ohne-html-pruefung", _edit("tools/build.py", '    if data[:15].lower() != b"<!doctype html>":', "    if False:"), "K10"),
    ("paket-werkzeug-sync-ohne-versionspruefung", _edit("tools/build.py", "    if not hit:\n        return fail('In der Datei steht keine APP_VERSION = \"x.y\"')", "    if False:\n        pass"), "K10"),
    ("paket-werkzeug-baustein-zip-mit-pfadpraefix", _edit("tools/build.py", 'pkg_entries = [(name[len(pkg_prefix):], data) for name, data in repo_entries if name.startswith(pkg_prefix)]', 'pkg_entries = [(name, data) for name, data in repo_entries if name.startswith(pkg_prefix)]'), "K10"),
]


def _manifest_unsortiert(repo):
    import json
    f = repo / PK / "manifest.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    v = m.pop("version")
    items = list(m.items())
    items.insert(2, ("version", v))
    f.write_text(json.dumps(dict(items), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")





def _verdict(p, label_ok="erkannt"):
    out = p.stdout + p.stderr
    failed = [l.strip() for l in out.splitlines() if l.strip().startswith("FALSCH")]
    status = label_ok if p.returncode != 0 else "ÜBERLEBT"
    detail = (failed[0][:110] if failed else out.strip().splitlines()[-1][:110]) if status == label_ok else ""
    return status, detail


def run(item):
    """Fehler im Baustein -> tests/test_server.py (alle Gruppen oder nur die genannten)."""
    name, filename, edits, *rest = item
    groups = rest[0].split() if rest else []
    work = OUT / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work / "aikido_tracker", ignore=shutil.ignore_patterns("__pycache__"))
    target = work / "aikido_tracker" / filename
    text = target.read_text(encoding="utf-8")
    for old, new in edits:
        if text.count(old) != 1:
            return name, "FEHLER", f"Ersetzungstext kommt {text.count(old)}x vor: {old[:60]!r}", 0.0
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    t0 = time.time()
    env = dict(os.environ, AIKIDO_SRC=str(work / "aikido_tracker"), PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([PY, "-I", TEST, *groups], env=env, capture_output=True, text=True, timeout=240)
        status, detail = _verdict(p)
    except subprocess.TimeoutExpired:
        status, detail = "erkannt", "Zeitüberschreitung (hängt) – gilt als erkannt"
    shutil.rmtree(work, ignore_errors=True)
    return name, status, detail, time.time() - t0


def run_pkg(item):
    """Fehler im Repository -> tests/test_package.py auf einer Kopie des ganzen Repositories."""
    name, change, expected = item
    work = OUT / name
    shutil.rmtree(work, ignore_errors=True)
    repo = work / "repo"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", ".work", "out", "dist", "venv", ".venv", ".ruff_cache", "*.pyc", "*.zip", ".DS_Store"))
    try:
        change(repo)
    except Exception as err:  # Mutation selbst kaputt
        return name, "FEHLER", f"Änderung nicht anwendbar: {err}", 0.0
    t0 = time.time()
    env = dict(os.environ, AIKIDO_REPO=str(repo), PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([PY, "-I", "-B", TEST_PKG], env=env, capture_output=True, text=True, timeout=240)
        status, detail = _verdict(p)
        if status == "erkannt":
            ziele = [l.strip() for l in (p.stdout + p.stderr).splitlines() if l.strip().startswith(f"FALSCH {expected} ")]
            if not ziele:
                status, detail = "UNGEZIELT", f"schlägt an, aber nicht bei {expected}: {detail}"
            else:
                detail = ziele[0][:110]
    except subprocess.TimeoutExpired:
        status, detail = "erkannt", "Zeitüberschreitung (hängt) – gilt als erkannt"
    shutil.rmtree(work, ignore_errors=True)
    return name, status, detail, time.time() - t0


def run_live(item):
    """Fehler in __init__.py -> tests/test_live.py (echtes Home Assistant; nur nacheinander, der Port ist fest)."""
    name, filename, edits = item
    work = OUT / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work / "aikido_tracker", ignore=shutil.ignore_patterns("__pycache__"))
    target = work / "aikido_tracker" / filename
    text = target.read_text(encoding="utf-8")
    for old, new in edits:
        if text.count(old) != 1:
            return name, "FEHLER", f"Ersetzungstext kommt {text.count(old)}x vor: {old[:60]!r}", 0.0
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    t0 = time.time()
    env = dict(os.environ, AIKIDO_SRC=str(work / "aikido_tracker"), AIKIDO_WORK=str(work / "live"), PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([PY, "-I", TEST_LIVE], env=env, capture_output=True, text=True, timeout=420)
        status, detail = _verdict(p)
    except subprocess.TimeoutExpired:
        status, detail = "erkannt", "Zeitüberschreitung (hängt) – gilt als erkannt"
    shutil.rmtree(work, ignore_errors=True)
    return name, status, detail, time.time() - t0


def main():
    filt = sys.argv[1:]

    def sel(name):
        return not filt or any(f in name for f in filt)

    OUT.mkdir(parents=True, exist_ok=True)
    results = []

    def show(res):
        results.append(res)
        print(f"{res[1]:9} {res[0]:48} {res[3]:5.1f}s  {res[2]}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for res in ex.map(run, [m for m in M if sel(m[0])]):
            show(res)
        for res in ex.map(run_pkg, [m for m in MP if sel(m[0])]):
            show(res)
    if not os.environ.get("AIKIDO_NO_LIVE"):
        for item in [m for m in ML if sel(m[0])]:
            show(run_live(item))
    survived = [r for r in results if r[1] in ("ÜBERLEBT", "UNGEZIELT")]
    broken = [r for r in results if r[1] == "FEHLER"]
    line = f"\nGegenprobe: {sum(1 for r in results if r[1] == 'erkannt')} von {len(results)} eingebauten Fehlern erkannt; {len(survived)} überlebt, {len(broken)} Mutation ungültig"
    print(line)
    (OUT / "ergebnis.txt").write_text("\n".join(f"{r[1]:9} {r[0]}  {r[2]}" for r in results) + line + "\n", encoding="utf-8")
    return 1 if survived or broken else 0


if __name__ == "__main__":
    sys.exit(main())
