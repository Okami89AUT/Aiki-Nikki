#!/usr/bin/env python3
"""Praxistest des Bausteins gegen ein ECHTES Home Assistant (headless, eigene Konfigurationsordner unter .work/live).

Der Baustein wird so installiert, wie HACS es tut: nur der Ordner custom_components/aikido_tracker wird kopiert
(samt App, ohne Datei in www). Der Test startet Home Assistant selbst, prüft die Schnittstelle über echtes HTTP
(mit HAs eigener Middleware), startet einmal neu (Daten müssen erhalten bleiben), prüft die Protokolle auf Geheimnisse
und startet zwei weitere Instanzen: eine mit Datenordner im Ordner des Bausteins (muss ablehnen) und eine mit page_file.
Nur "live-sichere" Prüfungen: keine gefälschte Uhr, die Fehlversuch-Grenzen (10 je Adresse) werden nicht erreicht.

Voraussetzung: eine Python-Umgebung mit homeassistant, home-assistant-frontend und aiohttp; Pfad zu `hass` in AIKIDO_HASS
(oder im PATH). Aufruf:  AIKIDO_HASS=/pfad/zu/venv/bin/hass python3 tests/test_live.py      (AIKIDO_WORK = Arbeitsordner)
"""
import asyncio
import gzip  # noqa: F401
import json
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import sys
import time

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import CONST, Resp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = pathlib.Path(os.environ.get("AIKIDO_SRC") or ROOT / "custom_components" / "aikido_tracker")
WORK = pathlib.Path(os.environ.get("AIKIDO_WORK") or ROOT / ".work" / "live")
HASS = os.environ.get("AIKIDO_HASS") or shutil.which("hass")
BASE = "http://127.0.0.1:18123"
INVITE = "einladung-7"
CODE = "geheim-123"

N = 0
FEHLER = 0

CONFIG = """\
# Minimale Testkonfiguration (ohne default_config) für den Test des Bausteins gegen echtes Home Assistant
homeassistant:
  name: Testhaus
  time_zone: Europe/Vienna
  latitude: 48.2
  longitude: 16.3
  elevation: 180
  unit_system: metric
http:
  server_host: 127.0.0.1
  server_port: 18123
logger:
  default: warning
  logs:
    custom_components.aikido_tracker: debug
aikido_tracker:
  invite_code: !secret aikido_invite_code
  max_persons: 20
  history_days: 14
{extra}"""


def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def check(name, ist, soll):
    global N, FEHLER
    N += 1
    if canon(ist) != canon(soll):
        FEHLER += 1
        print(f"  FALSCH {name}\n    ist  = {canon(ist)[:500]}\n    soll = {canon(soll)[:500]}")


def make_config(name, extra=""):
    """Frischer Konfigurationsordner mit dem Baustein, installiert wie durch HACS (nur custom_components/aikido_tracker)."""
    cfg = WORK / name
    shutil.rmtree(cfg, ignore_errors=True)
    (cfg / "custom_components").mkdir(parents=True)
    shutil.copytree(PKG, cfg / "custom_components" / "aikido_tracker", ignore=shutil.ignore_patterns("__pycache__"))
    (cfg / "secrets.yaml").write_text(f"aikido_invite_code: {INVITE}\n", encoding="utf-8")
    (cfg / "configuration.yaml").write_text(CONFIG.format(extra=extra), encoding="utf-8")
    return cfg


class HA:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.out = WORK / f"{cfg.name}.out"

    def start(self):
        WORK.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen([HASS, "-c", str(self.cfg), "--skip-pip"], stdout=open(self.out, "ab"), stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        return self.proc.returncode if self.proc else None

    def log(self):
        f = self.cfg / "home-assistant.log"
        return f.read_text(errors="replace") if f.exists() else ""

    async def wait_log(self, text, seconds=90):
        t0 = time.time()
        while time.time() - t0 < seconds:
            if text in self.log():
                return True
            await asyncio.sleep(0.5)
        return False


async def call(s, path, body=None, *, method="POST", raw=None, headers=None):
    kw = {"headers": dict(headers or {})}
    if raw is not None:
        kw["data"] = raw
        kw["headers"].setdefault("Content-Type", "application/json")
    elif body is not None:
        kw["json"] = body
    async with s.request(method, f"{BASE}/api/aikido_tracker/{path}", **kw) as r:
        return Resp(r.status, r.headers, await r.read())


async def wait_ready(s, seconds=90):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            r = await call(s, "ping", method="GET")
            if r.status == 200:
                return time.time() - t0
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(1)
    return None


async def wait_http(s, seconds=90):
    """Wartet, bis Home Assistant überhaupt HTTP spricht (egal welche Antwort)."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            async with s.get(f"{BASE}/") as r:
                await r.read()
                return True
        except aiohttp.ClientError:
            await asyncio.sleep(1)
    return False


async def get(s, path, **kw):
    async with s.get(f"{BASE}{path}", **kw) as r:
        return r.status, r.headers, await r.read()


def fehler(r):
    return [r.status, (r.json or {}).get("ok"), (r.json or {}).get("code")]


async def teil1(s):
    r = await call(s, "ping", method="GET")
    check("H1 ping über Home Assistant: 200, ok, registration true", [r.status, r.json.get("ok"), r.json.get("registration"), r.json.get("version")], [200, True, True, CONST.VERSION])
    check("H1 unsere Kopfzeilen bleiben erhalten (no-store, nosniff, JSON)", [r.headers.get("Cache-Control"), r.headers.get("X-Content-Type-Options"), r.headers.get("Content-Type", "").split(";")[0]], ["no-store", "nosniff", "application/json"])
    r = await call(s, "ping", method="GET", headers={"Authorization": "Bearer unsinn"})
    check("H1 ein ungültiges Home-Assistant-Token stört den Aufruf nicht (keine HA-Anmeldung nötig)", r.status, 200)

    r = await call(s, "register", {"name": "Sebastián", "code": CODE, "invite": INVITE})
    check("H2 Person anlegen: 201, Kennung sebastian", [r.status, r.json.get("person"), r.json.get("rev")], [201, {"id": "sebastian", "name": "Sebastián"}, 0])
    r = await call(s, "register", {"name": "SEBASTIAN", "code": CODE, "invite": INVITE})
    check("H2 gleicher Name -> 409 name_taken", fehler(r), [409, False, "name_taken"])
    r = await call(s, "register", {"name": "Anna", "code": CODE, "invite": "falsch"})
    check("H2 falscher Einladungscode -> 403 bad_invite", fehler(r), [403, False, "bad_invite"])

    daten = {"app": "aikido-kyu-tracker", "schemaVersion": 2, "log": [{"id": "a1", "date": "2026-10-01", "note": "Übung 日本語 \"zitiert\" <b>", "n": 1.5}], "examTarget": {"kyu": 5}}
    r = await call(s, "push", {"name": "sebastian", "code": CODE, "baseRev": 0, "data": daten})
    check("H3 Hochladen: rev 1", [r.status, r.json.get("rev")], [200, 1])
    r = await call(s, "pull", {"name": "Sebastián", "code": CODE})
    check("H3 Abholen liefert dieselben Daten", [r.status, r.json.get("rev"), r.json.get("data") == daten], [200, 1, True])
    r = await call(s, "pull", {"name": "Sebastián", "code": CODE, "sinceRev": 1})
    check("H3 sinceRev gleich -> unchanged", [r.json.get("unchanged"), "data" in r.json], [True, False])
    r = await call(s, "push", {"name": "sebastian", "code": CODE, "baseRev": 0, "data": {**daten, "examTarget": {"kyu": 4}}})
    check("H3 veraltete baseRev -> 409 conflict", [fehler(r), r.json.get("rev")], [[409, False, "conflict"], 1])
    r = await call(s, "push", {"name": "sebastian", "code": CODE, "baseRev": 1, "data": {**daten, "examTarget": {"kyu": 4}}})
    check("H3 richtige baseRev -> rev 2", [r.status, r.json.get("rev")], [200, 2])
    rs = await asyncio.gather(*[call(s, "push", {"name": "sebastian", "code": CODE, "baseRev": 2, "data": {"von": i}}) for i in range(8)])
    check("H3 8 gleichzeitige Uploads über echtes HTTP: genau einer gewinnt", sorted(r.status for r in rs), [200] + [409] * 7)

    r = await call(s, "login", {"name": "Sebastian", "code": "falsch-999"})
    check("H4 falscher Code -> 401", fehler(r), [401, False, "bad_credentials"])
    r = await call(s, "login", method="GET")
    check("H4 GET statt POST -> 405", r.status, 405)
    r = await call(s, "gibtsnicht", {})
    check("H4 unbekannter Pfad -> 404", r.status, 404)
    r = await call(s, "login", raw=b"{")
    check("H4 kaputtes JSON -> 400 bad_request", fehler(r), [400, False, "bad_request"])
    r = await call(s, "login", {"name": "Sebastian", "code": CODE}, headers={"Origin": "https://boese.example"})
    check("H4 keine CORS-Freigabe für fremde Herkunft", [r.status, r.headers.get("Access-Control-Allow-Origin")], [200, None])
    r = await call(s, "login", {"name": "Sebastian", "code": CODE}, headers={"X-Forwarded-For": "203.0.113.9"})
    check("H4 Anfrage mit X-Forwarded-For ohne eingerichteten Proxy: Home Assistant lehnt sie ab (400)", r.status, 400)

    r = await call(s, "push", raw=b'{"name":"sebastian","code":"geheim-123","baseRev":3,"data":{"x":"' + b"a" * (CONST.MAX_BODY_BYTES + 10) + b'"}}')
    check("H5 Anfrage über der Körpergrenze -> 413 too_large", fehler(r), [413, False, "too_large"])
    check("H5 danach ist der Server weiter erreichbar", (await call(s, "ping", method="GET")).status, 200)
    gross = {"log": [{"id": f"id-{i}", "note": "Übung " * 30, "n": i} for i in range(15000)]}
    cur = (await call(s, "pull", {"name": "sebastian", "code": CODE})).json["rev"]
    t0 = time.time()
    r = await call(s, "push", {"name": "sebastian", "code": CODE, "baseRev": cur, "data": gross})
    back = await call(s, "pull", {"name": "sebastian", "code": CODE}, headers={"Accept-Encoding": "gzip"})
    check("H5 großer Stand (ca. 4 MB) über Home Assistant: speichern, abholen, komprimiert, unter 15 s", [r.status, back.json["data"] == gross, back.headers.get("Content-Encoding"), time.time() - t0 < 15], [200, True, "gzip", True])
    return gross


async def seite_gebuendelt(s, cfg):
    """H10: die mitgelieferte App wird unter /aikido-tracker ausgeliefert (Installation wie durch HACS: keine Datei in www)."""
    app = cfg / "custom_components" / "aikido_tracker" / "app" / "aikido-kyu-tracker.html"
    original = app.read_bytes()
    check("H10 wie durch HACS installiert: die App kommt aus dem Baustein-Ordner, in www liegt keine App", [original == (PKG / "app" / "aikido-kyu-tracker.html").read_bytes(), sorted(p.name for p in (cfg / "www").iterdir())], [True, ["probe.html"]])
    st, h, b = await get(s, "/local/probe.html")
    check("H10 Befund: Home Assistant liefert www-Dateien unter /local mit langem Zwischenspeicher aus (der Grund für /aikido-tracker)", [st, "max-age=" in (h.get("Cache-Control") or "")], [200, True])
    try:
        st, h, b = await get(s, "/aikido-tracker")
        check("H10 /aikido-tracker: 200, HTML, no-cache, nosniff, ETag, Inhalt = App im Baustein", [st, h.get("Content-Type"), h.get("Cache-Control"), h.get("X-Content-Type-Options"), bool(h.get("ETag")), b == original], [200, "text/html; charset=utf-8", "no-cache", "nosniff", True, True])
        check("H10 keine CORS-Freigabe für die Seite", h.get("Access-Control-Allow-Origin"), None)
        etag = h["ETag"]
        st, h, b = await get(s, "/aikido-tracker", headers={"If-None-Match": etag})
        check("H10 unverändert: Nachfrage mit ETag -> 304", st, 304)
        app.write_bytes(original + b"\n<!-- neue Fassung -->\n")
        st, h, b = await get(s, "/aikido-tracker", headers={"If-None-Match": etag})
        check("H10 Datei ersetzt (wie nach einem HACS-Update): sofort die neue Fassung (200, neuer ETag)", [st, b.endswith(b"neue Fassung -->\n"), h.get("ETag") != etag], [200, True, True])
        st, h, b = await get(s, "/aikido-tracker/")
        check("H10 auch mit Schrägstrich erreichbar", st, 200)
    finally:
        app.write_bytes(original)


async def teil2(s, gross, cfg):
    data_dir = cfg / "aikido_tracker"
    r = await call(s, "login", {"name": "sebastian", "code": CODE})
    check("H6 nach Neustart von Home Assistant: Anmelden klappt", [r.status, r.json.get("rev") is not None], [200, True])
    back = await call(s, "pull", {"name": "sebastian", "code": CODE})
    check("H6 nach Neustart: alle Daten sind da", back.json["data"] == gross, True)
    r = await call(s, "register", {"name": "Sebastian", "code": CODE, "invite": INVITE})
    check("H6 nach Neustart: Name weiterhin belegt", fehler(r), [409, False, "name_taken"])
    r = await call(s, "change-code", {"name": "sebastian", "code": CODE, "newCode": "neuer-code-42"})
    check("H7 Zugangscode ändern", [r.status, (await call(s, "login", {"name": "sebastian", "code": "neuer-code-42"})).status], [200, 200])
    r = await call(s, "register", {"name": "Anna", "code": CODE, "invite": INVITE})
    check("H7 zweite Person anlegen", r.status, 201)
    r = await call(s, "delete", {"name": "anna", "code": CODE, "confirm": True})
    check("H7 Person löschen", [r.status, (await call(s, "login", {"name": "anna", "code": CODE})).status], [200, 401])

    persons = data_dir / "persons"
    modes = {p.name: stat.S_IMODE(p.stat().st_mode) for p in persons.glob("*.json")}
    check("H8 Dateirechte: Personen-Dateien 600, Ordner 700", [modes, stat.S_IMODE(persons.stat().st_mode), stat.S_IMODE(data_dir.stat().st_mode)], [{"sebastian.json": 0o600}, 0o700, 0o700])
    check("H8 Datei enthält keinen Zugangscode im Klartext", [c in (persons / "sebastian.json").read_text() for c in (CODE, "neuer-code-42")], [False, False])
    hist = sorted(p.name for p in (data_dir / "history").iterdir())
    check("H8 Sicherungen: Ordner der Person und der gelöschten Person", [h.startswith("_deleted-anna-") or h == "sebastian" for h in hist], [True] * len(hist))
    check("H8 Daten liegen außerhalb des Bausteins: im Ordner des Bausteins entsteht nichts außer den Dateien des Pakets", sorted(p.name for p in (cfg / "custom_components" / "aikido_tracker").iterdir() if p.name != "__pycache__"), sorted(p.name for p in PKG.iterdir() if p.name != "__pycache__"))
    await seite_gebuendelt(s, cfg)


async def lauf_a():
    """Hauptlauf: Standard-Installation, Schnittstelle, Neustart, Seite, Protokolle."""
    cfg = make_config("a")
    (cfg / "www").mkdir()
    (cfg / "www" / "probe.html").write_text("<p>probe</p>", encoding="utf-8")
    ha = HA(cfg)
    ha.start()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            t = await wait_ready(s)
            check("H0 Home Assistant startet und die Schnittstelle ist erreichbar", t is not None, True)
            if t is None:
                return
            print(f"  Info: bereit nach {t:.1f} s")
            gross = await teil1(s)
        code = ha.stop()
        check("H6 Home Assistant beendet sich sauber (Exitcode 0)", code, 0)
        ha.start()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            t = await wait_ready(s)
            check("H6 Home Assistant startet nach dem Neustart wieder", t is not None, True)
            if t is not None:
                await teil2(s, gross, cfg)
    finally:
        ha.stop()
    log = ha.log()
    out = ha.out.read_text(errors="replace")
    check("H9 Protokolle (Datei und Konsole) enthalten weder Zugangs- noch Einladungscodes", [s in log + out for s in (CODE, "neuer-code-42", INVITE, "falsch-999")], [False] * 4)
    mine = [l for l in log.splitlines() if "aikido_tracker" in l]
    check("H9 keine Fehler/Tracebacks des Bausteins im Protokoll", [l for l in mine if " ERROR " in l or "Traceback" in l], [])
    check("H9 Protokoll enthält Meldungen des Bausteins (Start, Anmeldefehler)", [any("bereit" in l for l in mine), any("fehlgeschlagen" in l for l in mine)], [True, True])
    check("H9 Startmeldung nennt die App im Ordner des Bausteins", any("App-Seite aus" in l and "custom_components/aikido_tracker/app/aikido-kyu-tracker.html" in l for l in mine), True)


async def lauf_b():
    """Datenordner im Ordner des Bausteins: HACS würde ihn bei einem Update löschen -> der Baustein muss ablehnen."""
    cfg = make_config("b", "  data_dir: custom_components/aikido_tracker/daten\n")
    ha = HA(cfg)
    ha.start()
    try:
        gemeldet = await ha.wait_log("liegt im Ordner des Bausteins")
        check("H11 Datenordner im Baustein-Ordner: der Baustein meldet den Grund im Protokoll", gemeldet, True)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            await wait_http(s)
            r = await call(s, "ping", method="GET")
            st, h, b = await get(s, "/aikido-tracker")
        check("H11 und richtet nichts ein: weder Schnittstelle noch Seite (404)", [r.status, st], [404, 404])
        check("H11 im Ordner des Bausteins wurde kein Datenordner angelegt", (cfg / "custom_components" / "aikido_tracker" / "daten").exists(), False)
        log = ha.log()
        check("H11 Meldung enthält weder Zugangs- noch Einladungscode", [INVITE in log, CODE in log], [False, False])
    finally:
        code = ha.stop()
    check("H11 Home Assistant selbst läuft weiter und beendet sich sauber (Exitcode 0)", code, 0)


async def lauf_c():
    """page_file übersteuert die mitgelieferte App."""
    cfg = make_config("c", "  page_file: www/eigene-seite.html\n")
    (cfg / "www").mkdir()
    eigene = cfg / "www" / "eigene-seite.html"
    inhalt = "<!doctype html><meta charset=utf-8><title>Eigene Seite</title>Übung".encode("utf-8")
    eigene.write_bytes(inhalt)
    ha = HA(cfg)
    ha.start()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            t = await wait_ready(s)
            check("H12 Home Assistant mit page_file startet", t is not None, True)
            if t is None:
                return
            st, h, b = await get(s, "/aikido-tracker")
            check("H12 page_file: die eigene Datei wird ausgeliefert (nicht die mitgelieferte App)", [st, b == inhalt, h.get("Cache-Control")], [200, True, "no-cache"])
            eigene.unlink()
            st, h, b = await get(s, "/aikido-tracker")
            check("H12 page_file zeigt auf eine fehlende Datei: 404 mit Hinweis auf page_file (kein stilles Ausweichen auf die App im Baustein)", [st, b"page_file" in b, h.get("Cache-Control")], [404, True, "no-store"])
            eigene.write_bytes(inhalt)
            st, h, b = await get(s, "/aikido-tracker")
            check("H12 Datei wieder da: sofort wieder 200", [st, b == inhalt], [200, True])
    finally:
        ha.stop()
    check("H12 Startmeldung nennt die eingestellte Datei", any("App-Seite aus" in l and "www/eigene-seite.html" in l for l in ha.log().splitlines()), True)


async def main():
    if not HASS or not os.path.exists(HASS):
        print("Home Assistant nicht gefunden: Pfad zu `hass` in AIKIDO_HASS angeben (oder in den PATH legen).")
        return 2
    await lauf_a()
    await lauf_b()
    await lauf_c()
    print(f"\nPraxistest gegen echtes Home Assistant: {N - FEHLER} von {N} Prüfungen bestanden{f' — {FEHLER} FEHLGESCHLAGEN' if FEHLER else ' — alles grün'}")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
