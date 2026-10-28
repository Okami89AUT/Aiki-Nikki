"""Gemeinsame Hilfen für die Tests des Server-Bausteins (ohne Home Assistant).

Das Paket `aikido_tracker` wird als leeres Paket-Gerüst eingehängt: store.py und api.py werden normal importiert,
__init__.py (die Home-Assistant-Anbindung) wird dabei NICHT ausgeführt.
"""
import asyncio
import json
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import types
import datetime as dt

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path(os.environ.get("AIKIDO_SRC", ROOT / "custom_components" / "aikido_tracker"))


def load_modules():
    if "aikido_tracker" not in sys.modules:
        pkg = types.ModuleType("aikido_tracker")
        pkg.__path__ = [str(SRC)]
        sys.modules["aikido_tracker"] = pkg
    import importlib
    const = importlib.import_module("aikido_tracker.const")
    store = importlib.import_module("aikido_tracker.store")
    api = importlib.import_module("aikido_tracker.api")
    page = importlib.import_module("aikido_tracker.page")
    return const, store, api, page


CONST, STORE, API, PAGE = load_modules()

INVITE = "einladung-7"
START = dt.datetime(2026, 10, 25, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp()


class FakeClock:
    """Steuerbare Uhr (Sekunden seit 1970, UTC)."""

    def __init__(self, start=START):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds

    def advance_days(self, days):
        self.t += 86400 * days

    def date(self):
        return dt.datetime.fromtimestamp(self.t, dt.timezone.utc).date()


@web.middleware
async def remote_override(request, handler):
    """Nur für Tests: die Absender-Adresse kommt aus dem Kopf X-Test-Remote (sonst immer 127.0.0.1)."""
    remote = request.headers.get("X-Test-Remote")
    if remote:
        request = request.clone(remote=remote)
    return await handler(request)


class Resp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body
        self.text = body.decode("utf-8", "replace")
        try:
            self.json = json.loads(self.text)
        except ValueError:
            self.json = None


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception as err:  # pragma: no cover
            self.lines.append(f"<Logfehler {err}>")


class Env:
    """Ein frischer Server mit eigenem Datenordner, Uhr und Testclient."""

    def __init__(self, *, invite=INVITE, history_days=14, max_persons=20, n=16, directory=None, clock=None, verify=None):
        self.invite = invite
        self.history_days = history_days
        self.max_persons = max_persons
        self.n = n
        self.directory = directory
        self.clock = clock or FakeClock()
        self.verify = verify
        self.keep = directory is not None
        self.logs = LogCapture()
        self.client = None

    async def _boot(self):
        self.store = STORE.PersonStore(self.dir, history_days=self.history_days, max_persons=self.max_persons, scrypt_n=self.n, clock=self.clock)
        await self.store.async_load()
        kwargs = {"invite_code": self.invite, "clock": self.clock}
        if self.verify:
            kwargs["verify"] = self.verify
        self.api = API.Api(self.store, **kwargs)
        self.app = web.Application(middlewares=[remote_override])
        API.add_routes(self.app, self.api)
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def __aenter__(self):
        self.dir = self.directory or tempfile.mkdtemp(prefix="aikido-test-")
        logging.getLogger("aikido_tracker").addHandler(self.logs)
        logging.getLogger("aikido_tracker").setLevel(logging.DEBUG)
        await self._boot()
        return self

    async def restart(self):
        """Server beenden und auf demselben Ordner neu starten (Sperrzähler im Arbeitsspeicher sind danach leer)."""
        await self.client.close()
        await self._boot()

    async def __aexit__(self, *exc):
        if self.client:
            await self.client.close()
        logging.getLogger("aikido_tracker").removeHandler(self.logs)
        if not self.keep:
            shutil.rmtree(self.dir, ignore_errors=True)

    # ---- Aufrufe ----
    async def call(self, path, body=None, *, method="POST", remote=None, raw=None, headers=None):
        h = dict(headers or {})
        if remote:
            h["X-Test-Remote"] = remote
        url = f"/api/aikido_tracker/{path}"
        if method == "GET":
            r = await self.client.get(url, headers=h)
        elif raw is not None:
            h.setdefault("Content-Type", "application/json")
            r = await self.client.request(method, url, data=raw, headers=h)
        else:
            r = await self.client.request(method, url, json=body, headers=h)
        data = await r.read()
        return Resp(r.status, r.headers, data)

    async def register(self, name, code, invite=None, **kw):
        return await self.call("register", {"name": name, "code": code, "invite": self.invite if invite is None else invite}, **kw)

    async def login(self, name, code, **kw):
        return await self.call("login", {"name": name, "code": code}, **kw)

    async def pull(self, name, code, since=None, **kw):
        body = {"name": name, "code": code}
        if since is not None:
            body["sinceRev"] = since
        return await self.call("pull", body, **kw)

    async def push(self, name, code, base_rev, data, **kw):
        return await self.call("push", {"name": name, "code": code, "baseRev": base_rev, "data": data}, **kw)

    # ---- Dateien ----
    def person_file(self, pid):
        return pathlib.Path(self.dir) / "persons" / f"{pid}.json"

    def history_dir(self, pid):
        return pathlib.Path(self.dir) / "history" / pid

    def all_files(self):
        return sorted(str(p.relative_to(self.dir)) for p in pathlib.Path(self.dir).rglob("*") if p.is_file())
