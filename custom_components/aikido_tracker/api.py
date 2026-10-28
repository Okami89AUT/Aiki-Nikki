"""HTTP-Schnittstelle des Aikido-Trackers (aiohttp) – ohne Home-Assistant-Anteile.

`add_routes(app, api)` hängt die Aufrufe an eine aiohttp-Anwendung (Tests); die Home-Assistant-Anbindung benutzt
dieselbe Tabelle ROUTES. Beschreibung der Aufrufe: docs/SCHNITTSTELLE.md.
"""
from __future__ import annotations

import asyncio
import gzip
import hmac
import ipaddress
import json
import logging
import time
import unicodedata

from aiohttp import web

from .const import (
    API_VERSION,
    APP_NAME,
    BODY_TIMEOUT_SECONDS,
    LIMIT_FAIL_IP,
    LIMIT_FAIL_PERSON,
    LIMIT_REQUEST_IP,
    LIMIT_WRITE,
    MAX_BODY_BYTES,
    MAX_DRAIN_BYTES,
    MAX_TRACKED_KEYS,
    VERSION,
    WINDOW_FAIL,
    WINDOW_REQUEST,
    WINDOW_WRITE,
)
from .identity import InvalidCode, InvalidName, normalize_code, normalize_name, verify_code
from .limits import SlidingLog
from .store import InvalidData, NameTaken, NotFound, StorageError, StoreFull, TooLarge, check_data, loads_strict

_LOGGER = logging.getLogger(__name__)

PREFIX = "/api/aikido_tracker"
# (HTTP-Methode, Pfadende, Name der Methode in Api) – einzige Quelle für Tests und Home-Assistant-Anbindung
ROUTES = (
    ("GET", "ping", "ping"),
    ("POST", "register", "register"),
    ("POST", "login", "login"),
    ("POST", "pull", "pull"),
    ("POST", "push", "push"),
    ("POST", "change-code", "change_code"),
    ("POST", "delete", "delete"),
)

_MISSING = object()
_NO_CODE = "kein-gueltiger-code"  # Platzhalter, damit auch ungültige Eingaben genau einen Hash rechnen
_GZIP_FROM_BYTES = 16 * 1024


def add_routes(app: web.Application, api: "Api") -> None:
    for method, path, handler in ROUTES:
        app.router.add_route(method, f"{PREFIX}/{path}", getattr(api, handler))


# ---- Antworten -----------------------------------------------------------------------------------------------------
def _json_response(status: int, payload=None, *, headers=None, close: bool = False, body: bytes | None = None) -> web.Response:
    if body is None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    all_headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if headers:
        all_headers.update(headers)
    response = web.Response(status=status, body=body, headers=all_headers, content_type="application/json", charset="utf-8")
    if close:
        response.force_close()
    return response


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, extra=None, headers=None, close: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}
        self.headers = headers or {}
        self.close = close

    def response(self) -> web.Response:
        payload = {"ok": False, "code": self.code, "error": self.message, **self.extra}
        return _json_response(self.status, payload, headers=self.headers, close=self.close)


def _rate_error(retry: int, message: str) -> ApiError:
    return ApiError(429, "rate_limited", message, headers={"Retry-After": str(retry)}, extra={"retryAfter": retry})


def _bad_credentials() -> ApiError:
    return ApiError(401, "bad_credentials", "Name oder Zugangscode stimmt nicht.")


def _storage_error() -> ApiError:
    return ApiError(500, "storage_error", "Die Daten konnten nicht gelesen oder gespeichert werden.")


# ---- Eingaben ------------------------------------------------------------------------------------------------------
def _text(body: dict, key: str) -> str:
    value = body.get(key, _MISSING)
    if not isinstance(value, str):
        raise ApiError(400, "bad_request", f"Das Feld „{key}“ fehlt oder ist kein Text.")
    return value


def _count(body: dict, key: str) -> int:
    value = body.get(key, _MISSING)
    if type(value) is not int or value < 0:
        raise ApiError(400, "bad_request", f"Das Feld „{key}“ fehlt oder ist keine ganze Zahl ab 0.")
    return value


def _client_key(remote) -> str:
    """Absender-Adresse als Zähler-Schlüssel (IPv6: das /64-Netz, damit Adresswechsel innerhalb davon nichts bringen)."""
    if not remote or not isinstance(remote, str):
        return "unbekannt"
    try:
        address = ipaddress.ip_address(remote.split("%")[0])
    except ValueError:
        return "ungueltig"
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _same_secret(given: str, expected: str) -> bool:
    return hmac.compare_digest(
        unicodedata.normalize("NFC", given).encode("utf-8", "surrogatepass"),
        expected.encode("utf-8", "surrogatepass"),
    )


def _parse_json(raw: bytes):
    return loads_strict(raw.decode("utf-8"))


class Api:
    def __init__(self, store, invite_code: str | None = None, *, clock=time.time, verify=verify_code) -> None:
        self._store = store
        self._invite = unicodedata.normalize("NFC", invite_code) if isinstance(invite_code, str) and invite_code else None
        self._clock = clock
        self._verify = verify
        self._fail_ip = SlidingLog(LIMIT_FAIL_IP, WINDOW_FAIL, MAX_TRACKED_KEYS)
        self._fail_person = SlidingLog(LIMIT_FAIL_PERSON, WINDOW_FAIL, MAX_TRACKED_KEYS)
        self._writes = SlidingLog(LIMIT_WRITE, WINDOW_WRITE, MAX_TRACKED_KEYS)
        self._requests = SlidingLog(LIMIT_REQUEST_IP, WINDOW_REQUEST, MAX_TRACKED_KEYS)
        self._cpu = asyncio.Semaphore(4)  # höchstens 4 Hash-Berechnungen gleichzeitig (Arbeitsspeicher)

    # ---- öffentliche Aufrufe (Namen = dritte Spalte von ROUTES) ----
    async def ping(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._ping, counted=False)

    async def register(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._register)

    async def login(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._login)

    async def pull(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._pull)

    async def push(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._push)

    async def change_code(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._change_code)

    async def delete(self, request: web.Request) -> web.Response:
        return await self._guard(request, self._delete)

    # ---- Rahmen: Sperren, Fehlerbehandlung ----
    async def _guard(self, request: web.Request, func, *, counted: bool = True) -> web.Response:
        ip = _client_key(request.remote)
        try:
            if counted:
                now = self._clock()
                retry = self._requests.retry_after(ip, now)
                if retry:
                    raise _rate_error(retry, "Zu viele Anfragen von dieser Adresse. Bitte kurz warten.")
                self._requests.add(ip, now)
                retry = self._fail_ip.retry_after(ip, now)
                if retry:
                    raise _rate_error(retry, "Zu viele Fehlversuche von dieser Adresse. Bitte später erneut versuchen.")
            return await func(request, ip)
        except ApiError as err:
            return err.response()
        except Exception:  # noqa: BLE001 - nie eine rohe Fehlerseite ausliefern
            _LOGGER.exception("Unerwarteter Fehler bei %s", request.path)
            return ApiError(500, "server_error", "Unerwarteter Fehler im Server.").response()

    async def _cpu_bound(self, func, *args):
        async with self._cpu:
            return await asyncio.get_running_loop().run_in_executor(None, func, *args)

    # ---- Körper lesen ----
    async def _discard(self, request: web.Request, already: int) -> bool:
        """Rest einer abgelehnten Anfrage lesen und verwerfen (begrenzt), damit der Absender die Antwort noch empfängt."""
        budget = MAX_DRAIN_BYTES - already
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while budget > 0:
                    chunk = await request.content.read(65536)
                    if not chunk:
                        return True
                    budget -= len(chunk)
        except Exception:  # noqa: BLE001 - Verbindung weg, Zeit abgelaufen …
            pass
        return False

    async def _read_body(self, request: web.Request) -> bytes:
        declared = request.content_length
        too_large = "Die Anfrage ist zu groß."
        if declared is not None and declared > MAX_BODY_BYTES:
            finished = declared <= MAX_DRAIN_BYTES and await self._discard(request, 0)
            raise ApiError(413, "too_large", too_large, close=not finished)
        chunks: list[bytes] = []
        total = 0
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while True:
                    chunk = await request.content.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        finished = await self._discard(request, total)
                        raise ApiError(413, "too_large", too_large, close=not finished)
                    chunks.append(chunk)
        except TimeoutError:
            raise ApiError(408, "bad_request", "Die Anfrage kam nicht vollständig an.", close=True) from None
        return b"".join(chunks)

    async def _read_json(self, request: web.Request) -> dict:
        raw = await self._read_body(request)
        try:
            if len(raw) > 32768:
                body = await asyncio.get_running_loop().run_in_executor(None, _parse_json, raw)
            else:
                body = _parse_json(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "bad_request", "Die Anfrage ist kein gültiges JSON.") from None
        except (RecursionError, ValueError):
            raise ApiError(422, "invalid_data", "Die Daten enthalten ungültige Werte (Zahlen, Verschachtelung).") from None
        if not isinstance(body, dict):
            raise ApiError(400, "bad_request", "Die Anfrage muss ein JSON-Objekt sein.")
        return body

    # ---- Anmeldung ----
    def _reserve_attempt(self, ip: str, pid: str | None, now: float):
        """Prüft die Sperren und verbucht den Versuch in einem Zug (ohne `await` dazwischen).

        Der Versuch wird VOR dem Rechnen verbucht: so können auch gleichzeitige Anfragen das Limit nicht überholen.
        Gibt die Marken zurück, mit denen ein gelungener Versuch wieder ausgebucht wird.
        """
        retry = self._fail_ip.retry_after(ip, now)
        if retry:
            raise _rate_error(retry, "Zu viele Fehlversuche von dieser Adresse. Bitte später erneut versuchen.")
        if pid is not None:
            retry = self._fail_person.retry_after(pid, now)
            if retry:
                raise _rate_error(retry, "Zu viele Fehlversuche für diese Person. Bitte später erneut versuchen.")
        slot_ip = self._fail_ip.add(ip, now)
        slot_person = self._fail_person.add(pid, now) if pid is not None else None
        return slot_ip, slot_person

    async def _authenticate(self, body: dict, ip: str):
        name_raw = _text(body, "name")
        code_raw = _text(body, "code")
        try:
            pid = normalize_name(name_raw)[0]
        except InvalidName:
            pid = None
        try:
            code = normalize_code(code_raw)
        except InvalidCode:
            code = None
        slot_ip, slot_person = self._reserve_attempt(ip, pid, self._clock())
        meta = self._store.find(pid) if pid is not None else None
        usable = meta is not None and not meta.unreadable and bool(meta.auth)
        auth = meta.auth if usable else self._store.dummy_auth
        ok = await self._cpu_bound(self._verify, code if code is not None else _NO_CODE, auth)
        if ok and usable and code is not None:
            self._fail_ip.discard(ip, slot_ip)
            if slot_person is not None:
                self._fail_person.discard(pid, slot_person)
            return meta
        _LOGGER.warning("Anmeldung fehlgeschlagen: Adresse %s, Person %s", ip, pid or "<ungültiger Name>")
        raise _bad_credentials()

    # ---- Aufrufe ----
    async def _ping(self, request: web.Request, ip: str) -> web.Response:
        return _json_response(
            200,
            {"ok": True, "app": APP_NAME, "api": API_VERSION, "version": VERSION, "registration": self._invite is not None},
        )

    async def _register(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        name_raw = _text(body, "name")
        code_raw = _text(body, "code")
        invite_raw = _text(body, "invite")
        if self._invite is None:
            raise ApiError(403, "registration_disabled", "Neue Personen können hier nicht angelegt werden.")
        slot, _ = self._reserve_attempt(ip, None, self._clock())
        if not _same_secret(invite_raw, self._invite):
            _LOGGER.warning("Falscher Einladungscode von Adresse %s", ip)
            raise ApiError(403, "bad_invite", "Der Einladungscode stimmt nicht.")
        self._fail_ip.discard(ip, slot)
        try:
            pid, display = normalize_name(name_raw)
        except InvalidName as err:
            raise ApiError(422, "invalid_name", f"Der Name ist nicht erlaubt. {err}") from None
        try:
            code = normalize_code(code_raw)
        except InvalidCode as err:
            raise ApiError(422, "invalid_code", f"Der Zugangscode ist nicht erlaubt. {err}") from None
        if self._store.find(pid) is not None:
            raise ApiError(409, "name_taken", "Dieser Name ist schon vergeben.")
        auth = await self._cpu_bound(self._store.make_auth, code)
        try:
            meta = await self._store.create(pid, display, auth)
        except NameTaken:
            raise ApiError(409, "name_taken", "Dieser Name ist schon vergeben.") from None
        except StoreFull:
            raise ApiError(409, "full", "Die Höchstzahl an Personen ist erreicht.") from None
        except StorageError as err:
            _LOGGER.error("Person konnte nicht angelegt werden: %s", err)
            raise _storage_error() from None
        _LOGGER.info("Person angelegt: %s", meta.id)
        return _json_response(201, {"ok": True, "person": {"id": meta.id, "name": meta.name}, "rev": meta.rev, "updatedAt": meta.updated_at})

    async def _login(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        meta = await self._authenticate(body, ip)
        return _json_response(200, {"ok": True, "person": {"id": meta.id, "name": meta.name}, "rev": meta.rev, "updatedAt": meta.updated_at})

    async def _pull(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        since = _count(body, "sinceRev") if "sinceRev" in body else None
        meta = await self._authenticate(body, ip)
        if since is not None and since == meta.rev:
            return _json_response(200, {"ok": True, "unchanged": True, "rev": meta.rev, "updatedAt": meta.updated_at})
        try:
            current, data = await self._store.read(meta.id)
        except NotFound:
            raise _bad_credentials() from None
        except StorageError as err:
            _LOGGER.error("Person %s: Lesen fehlgeschlagen: %s", meta.id, err)
            raise _storage_error() from None
        payload = {"ok": True, "person": {"id": current.id, "name": current.name}, "rev": current.rev, "updatedAt": current.updated_at, "data": data}
        accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "").lower()
        return await asyncio.get_running_loop().run_in_executor(None, self._build_data_response, payload, accepts_gzip)

    @staticmethod
    def _build_data_response(payload: dict, accepts_gzip: bool) -> web.Response:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Vary": "Accept-Encoding"}
        if accepts_gzip and len(body) > _GZIP_FROM_BYTES:
            body = gzip.compress(body, compresslevel=5)
            headers["Content-Encoding"] = "gzip"
        return _json_response(200, headers=headers, body=body)

    async def _push(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        base_rev = _count(body, "baseRev")
        if "data" not in body:
            raise ApiError(400, "bad_request", "Das Feld „data“ fehlt.")
        meta = await self._authenticate(body, ip)
        try:
            check_data(body["data"])
        except InvalidData as err:
            raise ApiError(422, "invalid_data", f"Die Daten haben nicht das erwartete Format. {err}") from None
        now = self._clock()
        retry = self._writes.retry_after(meta.id, now)
        if retry:
            raise _rate_error(retry, "Zu viele Uploads in kurzer Zeit. Bitte kurz warten.")
        self._writes.add(meta.id, now)
        try:
            result = await self._store.write(meta.id, base_rev, body["data"])
        except InvalidData as err:
            raise ApiError(422, "invalid_data", f"Die Daten haben nicht das erwartete Format. {err}") from None
        except TooLarge:
            raise ApiError(413, "too_large", "Die Daten sind zu groß.") from None
        except NotFound:
            raise _bad_credentials() from None
        except StorageError as err:
            _LOGGER.error("Person %s: Speichern fehlgeschlagen: %s", meta.id, err)
            raise _storage_error() from None
        if result.status == "conflict":
            raise ApiError(
                409,
                "conflict",
                "Auf dem Server liegt ein neuerer Stand. Bitte zuerst abholen und zusammenführen.",
                extra={"rev": result.rev, "updatedAt": result.updated_at},
            )
        payload = {"ok": True, "rev": result.rev, "updatedAt": result.updated_at}
        if result.status == "unchanged":
            payload["unchanged"] = True
        return _json_response(200, payload)

    async def _change_code(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        new_raw = _text(body, "newCode")
        meta = await self._authenticate(body, ip)
        try:
            new_code = normalize_code(new_raw)
        except InvalidCode as err:
            raise ApiError(422, "invalid_code", f"Der neue Zugangscode ist nicht erlaubt. {err}") from None
        auth = await self._cpu_bound(self._store.make_auth, new_code)
        try:
            await self._store.set_auth(meta.id, auth)
        except NotFound:
            raise _bad_credentials() from None
        except StorageError as err:
            _LOGGER.error("Person %s: Zugangscode konnte nicht geändert werden: %s", meta.id, err)
            raise _storage_error() from None
        _LOGGER.info("Zugangscode geändert: %s", meta.id)
        return _json_response(200, {"ok": True})

    async def _delete(self, request: web.Request, ip: str) -> web.Response:
        body = await self._read_json(request)
        if body.get("confirm") is not True:
            raise ApiError(400, "bad_request", "Zum Löschen muss „confirm“ genau true sein.")
        meta = await self._authenticate(body, ip)
        try:
            await self._store.delete(meta.id)
        except NotFound:
            raise _bad_credentials() from None
        except StorageError as err:
            _LOGGER.error("Person %s: Löschen fehlgeschlagen: %s", meta.id, err)
            raise _storage_error() from None
        _LOGGER.info("Person gelöscht: %s", meta.id)
        return _json_response(200, {"ok": True})
