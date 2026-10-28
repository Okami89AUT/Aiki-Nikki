"""Speicher der Personen: eine JSON-Datei je Person, Tagessicherungen, atomares Schreiben.

Reine Python-Datei (nur Standardbibliothek), ohne Home-Assistant-Anteile -> eigenständig testbar.
Alle Datei-Zugriffe laufen im Thread-Pool (nie im Event-Loop); je Person sorgt eine Sperre für Reihenfolge.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import gzip
import hashlib
import json
import logging
import math
import os
import re
import shutil
import tempfile
import time
from typing import NamedTuple

from .const import DATA_KEY_PATTERN, MAX_DATA_BYTES, MAX_DATA_KEYS, SCRYPT_N
from .identity import (  # noqa: F401  (Teil der öffentlichen Schnittstelle dieses Moduls)
    InvalidCode,
    InvalidName,
    hash_code,
    normalize_code,
    normalize_name,
    verify_code,
)

_LOGGER = logging.getLogger(__name__)

FORMAT = 1
_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
_KEY_RE = re.compile(DATA_KEY_PATTERN)
_DAY_FILE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.json\.gz")
_DELETED_RE = re.compile(r"_deleted-.+-(\d{8})T\d{6}Z(?:\.\d+)?")
EMPTY_DIGEST = hashlib.sha256(b"{}").hexdigest()


# ---- Fehler --------------------------------------------------------------------------------------------------------
class StoreError(Exception):
    """Oberklasse aller Fehler dieses Moduls."""


class NotFound(StoreError):
    pass


class NameTaken(StoreError):
    pass


class StoreFull(StoreError):
    pass


class StorageError(StoreError):
    """Datei nicht lesbar/schreibbar (Platte voll, Rechte, kaputte Datei …)."""


class TooLarge(StoreError):
    pass


class InvalidData(StoreError):
    pass


# ---- kleine Hilfen -------------------------------------------------------------------------------------------------
def is_inside(path: str, parent: str) -> bool:
    """True, wenn `path` im Ordner `parent` liegt oder selbst `parent` ist.

    Verknüpfungen werden aufgelöst; die Pfade müssen nicht existieren (geprüft wird vor dem Anlegen).
    Dient dem Schutz des Datenordners: HACS ersetzt bei einer Aktualisierung den ganzen Ordner des Bausteins.
    """
    child = os.path.realpath(path)
    base = os.path.realpath(parent)
    return child == base or child.startswith(base.rstrip(os.sep) + os.sep)


def iso_utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_date(ts: float) -> dt.date:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()


def _no_constant(name: str):
    raise ValueError(f"ungültiger Zahlenwert {name}")


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Zahl außerhalb des Bereichs")
    return value


def loads_strict(text: str):
    """JSON lesen, aber NaN/Infinity/1e999 ablehnen (ValueError)."""
    return json.loads(text, parse_constant=_no_constant, parse_float=_parse_float)


def canonical(data) -> str:
    """Eindeutige Textform (sortierte Schlüssel, kompakt) – Grundlage für Größe, Vergleich und Speicherung."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def check_data(data) -> None:
    if not isinstance(data, dict):
        raise InvalidData("Die Daten müssen ein JSON-Objekt sein.")
    if len(data) > MAX_DATA_KEYS:
        raise InvalidData(f"Höchstens {MAX_DATA_KEYS} Einträge auf oberster Ebene erlaubt.")
    for key in data:
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise InvalidData("Ein Schlüssel auf oberster Ebene hat ein unerlaubtes Format.")


class Prepared(NamedTuple):
    raw: bytes
    digest: str


def prepare(data) -> Prepared:
    """Prüft die Daten und bringt sie in die gespeicherte Form (rechenintensiv -> im Thread-Pool aufrufen)."""
    check_data(data)
    try:
        raw = canonical(data).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as err:
        raise InvalidData("Die Daten enthalten ungültige Werte.") from err
    if len(raw) > MAX_DATA_BYTES:
        raise TooLarge(f"Die Daten sind größer als {MAX_DATA_BYTES} Bytes.")
    return Prepared(raw, hashlib.sha256(raw).hexdigest())


def _short(err: BaseException) -> str:
    text = f"{type(err).__name__}: {err}".replace("\n", " ").replace("\r", " ")
    return text[:160]


# ---- Dateien -------------------------------------------------------------------------------------------------------
def _fsync_dir(directory: str) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)


def _atomic_write(path: str, payload: bytes) -> None:
    """Temporärdatei -> fsync -> umbenennen: die Zieldatei ist immer entweder ganz alt oder ganz neu."""
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


@dataclasses.dataclass
class Meta:
    id: str
    name: str
    rev: int = 0
    updated_at: str = ""
    created: str = ""
    unreadable: bool = False
    auth: dict | None = None
    digest: str = ""


class WriteResult(NamedTuple):
    status: str  # "written" | "unchanged" | "conflict"
    rev: int
    updated_at: str


def _read_doc(path: str, pid: str) -> dict:
    """Liest und prüft eine Personen-Datei; jede Unstimmigkeit -> ValueError."""
    if os.path.getsize(path) > 2 * MAX_DATA_BYTES:
        raise ValueError("Datei ist zu groß")
    with open(path, "rb") as handle:
        raw = handle.read()
    doc = loads_strict(raw.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("Inhalt ist kein Objekt")
    if doc.get("format") != FORMAT:
        raise ValueError("unbekanntes Dateiformat")
    if doc.get("id") != pid:
        raise ValueError("Kennung passt nicht zum Dateinamen")
    if not isinstance(doc.get("name"), str) or not doc["name"]:
        raise ValueError("Name fehlt")
    if type(doc.get("rev")) is not int or doc["rev"] < 0:
        raise ValueError("rev fehlt oder ist ungültig")
    if not isinstance(doc.get("updatedAt"), str):
        raise ValueError("updatedAt fehlt")
    if not isinstance(doc.get("created", ""), str):
        raise ValueError("created ist ungültig")
    if not isinstance(doc.get("auth"), dict) or not doc["auth"]:
        raise ValueError("Zugangsdaten fehlen")
    if not isinstance(doc.get("data"), dict):
        raise ValueError("Daten fehlen")
    return doc


def _meta_light(doc: dict) -> Meta:
    return Meta(
        id=doc["id"],
        name=doc["name"],
        rev=doc["rev"],
        updated_at=doc["updatedAt"],
        created=doc.get("created", ""),
        auth=doc["auth"],
    )


def _meta_from_doc(doc: dict) -> Meta:
    meta = _meta_light(doc)
    meta.digest = hashlib.sha256(canonical(doc["data"]).encode("utf-8")).hexdigest()
    return meta


def _doc_bytes(meta: Meta, raw_data: bytes) -> bytes:
    head = json.dumps(
        {
            "format": FORMAT,
            "id": meta.id,
            "name": meta.name,
            "created": meta.created,
            "auth": meta.auth,
            "rev": meta.rev,
            "updatedAt": meta.updated_at,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return head[:-1].encode("utf-8") + b',"data":' + raw_data + b"}"


def _snapshot_bytes(doc: dict) -> bytes:
    """Sicherungskopie eines Standes – ohne Zugangsdaten."""
    snap = {
        "format": FORMAT,
        "id": doc["id"],
        "name": doc["name"],
        "rev": doc["rev"],
        "updatedAt": doc["updatedAt"],
        "data": doc["data"],
    }
    text = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    return gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0)


# ---- Speicher ------------------------------------------------------------------------------------------------------
class PersonStore:
    def __init__(
        self,
        base_dir,
        *,
        history_days: int = 14,
        max_persons: int = 20,
        scrypt_n: int = SCRYPT_N,
        clock=time.time,
    ) -> None:
        self._base = os.fspath(base_dir)
        self._persons_dir = os.path.join(self._base, "persons")
        self._history_dir = os.path.join(self._base, "history")
        self._history_days = max(0, int(history_days))
        self._max_persons = int(max_persons)
        self.scrypt_n = scrypt_n
        self._clock = clock
        self._metas: dict[str, Meta] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.dummy_auth: dict = {}

    # -- Hilfen --
    def make_auth(self, code: str) -> dict:
        """Hash für einen neuen Zugangscode (rechenintensiv -> im Thread-Pool aufrufen)."""
        return hash_code(code, self.scrypt_n)

    def find(self, pid: str) -> Meta | None:
        return self._metas.get(pid)

    def count(self) -> int:
        return len(self._metas)

    def _person_path(self, pid: str) -> str:
        return os.path.join(self._persons_dir, f"{pid}.json")

    def _lock_for(self, pid: str) -> asyncio.Lock:
        lock = self._locks.get(pid)
        if lock is None:
            lock = self._locks[pid] = asyncio.Lock()
        return lock

    async def _run(self, func, *args):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, func, *args)
        except StoreError:
            raise
        except (OSError, ValueError, RecursionError) as err:
            raise StorageError(_short(err)) from err

    def _usable(self, pid: str) -> Meta:
        meta = self._metas.get(pid)
        if meta is None:
            raise NotFound(pid)
        if meta.unreadable:
            raise StorageError("Die Datei dieser Person ist unlesbar und wird nicht verändert.")
        return meta

    # -- Laden --
    async def async_load(self) -> None:
        metas, dummy = await self._run(self._load_sync)
        self._metas = metas
        self.dummy_auth = dummy
        unreadable = sum(1 for m in metas.values() if m.unreadable)
        _LOGGER.info("Aikido-Tracker: %d Person(en) geladen, %d davon unlesbar", len(metas), unreadable)

    def _load_sync(self):
        _ensure_dir(self._base)
        _ensure_dir(self._persons_dir)
        _ensure_dir(self._history_dir)
        metas: dict[str, Meta] = {}
        with os.scandir(self._persons_dir) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            if not entry.is_file(follow_symlinks=False):
                continue
            if entry.name.endswith(".tmp"):
                try:
                    os.unlink(entry.path)
                except OSError:
                    pass
            elif entry.name.endswith(".json"):
                pid = entry.name[:-5]
                if not _ID_RE.fullmatch(pid):
                    continue
                try:
                    metas[pid] = _meta_from_doc(_read_doc(entry.path, pid))
                except Exception as err:  # noqa: BLE001 - jede Unstimmigkeit: Datei unberührt lassen
                    _LOGGER.error("Datei persons/%s ist unlesbar (%s); sie wird nicht verändert.", entry.name, _short(err))
                    metas[pid] = Meta(id=pid, name=pid, unreadable=True)
        self._remove_stale_tmp()
        self._prune_sync(remove_empty=True)
        return metas, hash_code("platzhalter-nie-gueltig", self.scrypt_n)

    def _remove_stale_tmp(self) -> None:
        try:
            with os.scandir(self._history_dir) as it:
                dirs = [e.path for e in it if e.is_dir(follow_symlinks=False)]
        except OSError:
            return
        for directory in dirs:
            try:
                for name in os.listdir(directory):
                    if name.endswith(".tmp"):
                        os.unlink(os.path.join(directory, name))
            except OSError:
                pass

    # -- Aufräumen der Tagessicherungen --
    async def prune(self) -> None:
        await self._run(self._prune_sync, False)

    def _cutoff(self) -> dt.date:
        return _utc_date(self._clock()) - dt.timedelta(days=self._history_days)

    def _prune_sync(self, remove_empty: bool = False) -> None:
        cutoff = self._cutoff()
        try:
            with os.scandir(self._history_dir) as it:
                entries = [e for e in it if e.is_dir(follow_symlinks=False)]
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("_deleted-"):
                match = _DELETED_RE.fullmatch(entry.name)
                if match and dt.datetime.strptime(match.group(1), "%Y%m%d").date() <= cutoff:
                    shutil.rmtree(entry.path, ignore_errors=True)
            else:
                self._prune_person_history(entry.path, cutoff, remove_empty)

    @staticmethod
    def _prune_person_history(directory: str, cutoff: dt.date, remove_empty: bool) -> None:
        try:
            names = os.listdir(directory)
        except OSError:
            return
        for name in names:
            match = _DAY_FILE_RE.fullmatch(name)
            if match and dt.date.fromisoformat(match.group(1)) <= cutoff:
                try:
                    os.unlink(os.path.join(directory, name))
                except OSError:
                    pass
        if remove_empty:
            try:
                os.rmdir(directory)  # nur wenn leer
            except OSError:
                pass

    def _deleted_target(self, pid: str, now: float) -> str:
        stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = os.path.join(self._history_dir, f"_deleted-{pid}-{stamp}")
        target, n = base, 1
        while os.path.exists(target):
            n += 1
            target = f"{base}.{n}"
        return target

    def _stash_history(self, pid: str, now: float) -> str | None:
        """Verschiebt vorhandene Sicherungen einer Person in einen _deleted-Ordner (oder löscht sie bei history_days=0)."""
        source = os.path.join(self._history_dir, pid)
        if not os.path.isdir(source):
            return None
        if self._history_days == 0:
            shutil.rmtree(source, ignore_errors=True)
            return None
        target = self._deleted_target(pid, now)
        os.rename(source, target)
        return target

    # -- Anlegen --
    async def create(self, pid: str, name: str, auth: dict) -> Meta:
        return await asyncio.shield(self._create(pid, name, auth))

    async def _create(self, pid: str, name: str, auth: dict) -> Meta:
        if pid in self._metas:
            raise NameTaken(pid)
        if len(self._metas) >= self._max_persons:
            raise StoreFull(str(self._max_persons))
        now = self._clock()
        meta = Meta(id=pid, name=name, rev=0, updated_at=iso_utc(now), created=iso_utc(now), auth=auth, digest=EMPTY_DIGEST)
        self._metas[pid] = meta  # Name sofort reservieren (gleichzeitige Anmeldungen desselben Namens)
        try:
            async with self._lock_for(pid):
                await self._run(self._create_sync, meta, now)
        except BaseException:
            self._metas.pop(pid, None)
            raise
        return dataclasses.replace(meta)

    def _create_sync(self, meta: Meta, now: float) -> None:
        _ensure_dir(self._persons_dir)
        self._stash_history(meta.id, now)
        _atomic_write(self._person_path(meta.id), _doc_bytes(meta, b"{}"))

    # -- Lesen --
    async def read(self, pid: str):
        self._usable(pid)
        async with self._lock_for(pid):
            self._usable(pid)
            doc = await self._run(_read_doc, self._person_path(pid), pid)
        return _meta_light(doc), doc["data"]

    # -- Schreiben --
    async def write(self, pid: str, base_rev: int, data) -> WriteResult:
        return await asyncio.shield(self._write(pid, base_rev, data))

    async def _write(self, pid: str, base_rev: int, data) -> WriteResult:
        self._usable(pid)
        prepared = await self._run(prepare, data)
        async with self._lock_for(pid):
            meta = self._usable(pid)
            if prepared.digest == meta.digest:
                return WriteResult("unchanged", meta.rev, meta.updated_at)
            if base_rev != meta.rev:
                return WriteResult("conflict", meta.rev, meta.updated_at)
            now = self._clock()
            new = dataclasses.replace(meta, rev=meta.rev + 1, updated_at=iso_utc(now), digest=prepared.digest)
            await self._run(self._commit_sync, meta, new, prepared.raw, now)
            meta.rev, meta.updated_at, meta.digest = new.rev, new.updated_at, new.digest
            return WriteResult("written", new.rev, new.updated_at)

    def _commit_sync(self, old: Meta, new: Meta, raw: bytes, now: float) -> None:
        path = self._person_path(new.id)
        person_history = os.path.join(self._history_dir, new.id)
        if self._history_days > 0:
            snapshot = os.path.join(person_history, f"{_utc_date(now).isoformat()}.json.gz")
            if old.rev >= 1 and not os.path.exists(snapshot):
                payload = _snapshot_bytes(_read_doc(path, new.id))
                _ensure_dir(self._history_dir)
                _ensure_dir(person_history)
                _atomic_write(snapshot, payload)
        _atomic_write(path, _doc_bytes(new, raw))
        if self._history_days > 0:
            self._prune_person_history(person_history, self._cutoff(), False)

    # -- Zugangscode ändern --
    async def set_auth(self, pid: str, auth: dict) -> None:
        await asyncio.shield(self._set_auth(pid, auth))

    async def _set_auth(self, pid: str, auth: dict) -> None:
        self._usable(pid)
        async with self._lock_for(pid):
            meta = self._usable(pid)
            await self._run(self._set_auth_sync, pid, auth)
            meta.auth = auth

    def _set_auth_sync(self, pid: str, auth: dict) -> None:
        path = self._person_path(pid)
        doc = _read_doc(path, pid)
        meta = _meta_light(doc)
        meta.auth = auth
        _atomic_write(path, _doc_bytes(meta, canonical(doc["data"]).encode("utf-8")))

    # -- Löschen --
    async def delete(self, pid: str) -> None:
        await asyncio.shield(self._delete(pid))

    async def _delete(self, pid: str) -> None:
        self._usable(pid)
        async with self._lock_for(pid):
            self._usable(pid)
            await self._run(self._delete_sync, pid, self._clock())
            self._metas.pop(pid, None)

    def _delete_sync(self, pid: str, now: float) -> None:
        path = self._person_path(pid)
        if self._history_days > 0:
            doc = _read_doc(path, pid)
            target = self._stash_history(pid, now)
            if target is None:
                target = self._deleted_target(pid, now)
                _ensure_dir(self._history_dir)
                _ensure_dir(target)
            _atomic_write(os.path.join(target, "final.json.gz"), _snapshot_bytes(doc))
        else:
            self._stash_history(pid, now)
        os.unlink(path)
        _fsync_dir(self._persons_dir)
