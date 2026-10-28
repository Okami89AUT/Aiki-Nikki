#!/usr/bin/env python3
"""Tests für den Server-Baustein "aikido_tracker" (ohne Home Assistant).

Gruppen:  L Namen/Codes/Hash   P Speicherung (Dateien, Neustart, Sicherungen)   A Schnittstelle (HTTP)   R Sperren/Schutz
          S Auslieferung der App-Seite   W Pfade (mitgelieferte App, page_file, Datenordner-Schutz)
Aufruf:   python3 tests/test_server.py [L P A R S W]      (AIKIDO_SRC=… prüft einen anderen Quellordner)
Ausgabe wie bei den App-Tests: "  FALSCH <Name>" je Fehler, am Ende eine Zusammenfassung, Exitcode 1 bei Fehlern.
"""
import asyncio
import gzip
import json
import os
import pathlib
import stat
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import API, CONST, INVITE, START, STORE, Env, FakeClock, SRC  # noqa: E402

N = 0
FEHLER = 0


def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def check(name, ist, soll):
    global N, FEHLER
    N += 1
    if canon(ist) != canon(soll):
        FEHLER += 1
        print(f"  FALSCH {name}\n    ist  = {canon(ist)[:500]}\n    soll = {canon(soll)[:500]}")


CODE = "geheim-123"
ISO = "2026-10-25T10:00:00Z"


# =====================================================================================================================
# L: Namen, Codes, Hash
# =====================================================================================================================
async def gruppe_L():
    S = STORE

    def nn(x):
        try:
            return list(S.normalize_name(x))
        except S.InvalidName:
            return "ungültig"

    check('L1 "Daniel" -> daniel', nn("Daniel"), ["daniel", "Daniel"])
    check('L1 Akzente/Umlaute: "Sebastián Müller" -> sebastian-muller', nn("Sebastián Müller"), ["sebastian-muller", "Sebastián Müller"])
    check('L1 Leerzeichen werden zusammengefasst und abgeschnitten', nn("  Anna   Maria "), ["anna-maria", "Anna Maria"])
    check('L1 Steuerzeichen am Rand (Tab/Zeilenumbruch) werden abgeschnitten', [nn("  Daniel\t"), nn("Daniel\n")], [["daniel", "Daniel"]] * 2)
    check('L1 Apostroph, Punkt, Bindestrich, Unterstrich', [nn("O'Brien"), nn("St. Pölten"), nn("Jean-Luc"), nn("Müller_2")],
          [["o-brien", "O'Brien"], ["st-polten", "St. Pölten"], ["jean-luc", "Jean-Luc"], ["muller-2", "Müller_2"]])
    check('L1 typografischer Apostroph (iPhone) wird zum geraden', nn("O’Brien"), ["o-brien", "O'Brien"])
    check('L1 ß und nordische Buchstaben werden umschrieben', [nn("Weiß")[0], nn("Øystein")[0], nn("Łukasz")[0], nn("Ærø")[0]], ["weiss", "oystein", "lukasz", "aero"])
    check('L1 Groß-/Kleinschreibung zählt für die Kennung nicht, der Name bleibt wie getippt', nn("DANIEL"), ["daniel", "DANIEL"])
    check('L1 zusammengesetzte und zerlegte Umlaute ergeben dasselbe', [nn("Müller"), nn("Müller")], [["muller", "Müller"]] * 2)
    check('L1 Leerzeichen anderer Schriften (geschütztes, Breitleerzeichen) zählen als Leerzeichen', [nn("Anna Maria"), nn("田　中")[1]], [["anna-maria", "Anna Maria"], "田 中"])
    j1, j2, j3 = nn("田中"), nn("田中"), nn("山田")
    check('L2 Name ohne lateinische Zeichen: Kennung p- + 12 Hexzeichen, stabil, je Name verschieden', [bool(__import__("re").fullmatch(r"p-[0-9a-f]{12}", j1[0])), j1 == j2, j1[0] != j3[0], j1[1]], [True, True, True, "田中"])
    check('L3 40 Zeichen sind erlaubt, 41 nicht', [nn("a" * 40), nn("a" * 41)], [["a" * 40, "a" * 40], "ungültig"])
    check('L3 die Kennung ist höchstens 40 Zeichen lang (auch wenn ß zu ss wächst)', nn("ß" * 40)[0], "ss" * 20)
    ungueltig = ["", "   ", "../x", "a/b", "a\\b", "<b>x</b>", 'a"b', "a\x00b", "a\nb", "a\tb", "a‍b", "💥", "x\ud800", "---", "...", "_", "a;b", "a:b", "a%b", "a&b", None, 5, ["a"], {"a": 1}, True]
    check('L4 ungültige Namen (Pfadzeichen, Tags, Steuer-/Formatzeichen, Emoji, einzelnes Surrogat, nur Satzzeichen, falsche Typen)',
          [x for x in ungueltig if nn(x) != "ungültig"], [])

    def nc(x):
        try:
            return S.normalize_code(x)
        except S.InvalidCode:
            return "ungültig"

    check('L5 Zugangscode: 6 bis 64 Zeichen sind gültig, auch mit Leerzeichen am Rand (bleiben erhalten)', [nc("abcdef"), nc("a" * 64), nc(" abcdef "), nc("päßwörd 1")], ["abcdef", "a" * 64, " abcdef ", "päßwörd 1"])
    check('L5 ungültige Codes: zu kurz/lang, nur Leerzeichen, Steuerzeichen, falsche Typen',
          [nc(x) for x in ["abcde", "a" * 65, "      ", "abc\x00def", "ab\ncdef", "abc‍def", "ab\ud800cdef", None, 123, ["abcdef"]]], ["ungültig"] * 10)
    check('L5 zerlegte und zusammengesetzte Umlaute im Code sind gleich', nc("Müllerx") == nc("Müllerx"), True)

    h1, h2 = S.hash_code("geheim-123", 16), S.hash_code("geheim-123", 16)
    check('L6 Hash: Verfahren scrypt, Parameter und Hexwerte', [h1["alg"], h1["n"], h1["r"], h1["p"], len(h1["salt"]), len(h1["hash"]), set(h1) == {"alg", "n", "r", "p", "salt", "hash"}], ["scrypt", 16, 8, 1, 32, 64, True])
    check('L6 gleicher Code, verschiedene Salze -> verschiedene Hashes', [h1["salt"] != h2["salt"], h1["hash"] != h2["hash"]], [True, True])
    check('L6 verify: richtig/falsch/Groß-Kleinschreibung', [S.verify_code("geheim-123", h1), S.verify_code("geheim-124", h1), S.verify_code("Geheim-123", h1), S.verify_code("", h1)], [True, False, False, False])
    c = "geheim-123"  # der RICHTIGE Code: False kommt hier nur von den kaputten Angaben, nicht vom falschen Code
    check('L6 verify mit kaputten Angaben liefert False statt Fehler', [S.verify_code(c, None), S.verify_code(c, {}), S.verify_code(c, {**h1, "alg": "md5"}), S.verify_code(c, {**h1, "salt": "zz"}), S.verify_code(c, {**h1, "n": "viel"}),
                                                                  S.verify_code(c, {**h1, "n": 3}), S.verify_code(c, "text"), S.verify_code(c, {**h1, "n": True}), S.verify_code(c, {**h1, "n": 2 ** 40}), S.verify_code(c, {**h1, "hash": h1["hash"][:-2]}), S.verify_code(c, {**h1, "r": 0}), S.verify_code(5, h1)], [False] * 12)
    check('L6 Gegenprobe: mit richtigem Code und unveränderten Angaben ist es True', S.verify_code(c, h1), True)
    check('L6 Standardkosten: scrypt n = 16384', S.hash_code("abcdef")["n"], 16384)
    check('L6 verify nutzt die gespeicherten Parameter (anderes n bleibt prüfbar)', [S.verify_code("abcdef", S.hash_code("abcdef", 32)), S.verify_code("abcdef", S.hash_code("abcdef", 64))], [True, True])


# =====================================================================================================================
# P: Speicherung
# =====================================================================================================================
def mk_store(d, clock, **kw):
    kw.setdefault("history_days", 14)
    kw.setdefault("max_persons", 50)
    return STORE.PersonStore(d, scrypt_n=16, clock=clock, **kw)


def files(d):
    return sorted(str(p.relative_to(d)) for p in pathlib.Path(d).rglob("*") if p.is_file())


async def gruppe_P():
    S = STORE
    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p-")
    try:
        st = mk_store(d, clock, max_persons=3)
        await st.async_load()
        auth = S.hash_code(CODE, 16)
        m = await st.create("daniel", "Daniel", auth)
        check('P1 create: Kennung, Name, rev 0, Zeitstempel', [m.id, m.name, m.rev, m.updated_at, m.unreadable], ["daniel", "Daniel", 0, ISO, False])
        f = pathlib.Path(d) / "persons" / "daniel.json"
        check('P1 Datei persons/daniel.json: vorhanden, Rechte 600, Ordner 700', [f.exists(), stat.S_IMODE(f.stat().st_mode), stat.S_IMODE(f.parent.stat().st_mode)], [True, 0o600, 0o700])
        check('P1 Datei enthält den Zugangscode nicht im Klartext', CODE not in f.read_text(), True)
        doc = json.loads(f.read_text())
        check('P1 Dateiinhalt: id, name, rev 0, data leer, auth', [doc["id"], doc["name"], doc["rev"], doc["data"], doc["auth"] == auth, "created" in doc, doc["updatedAt"]], ["daniel", "Daniel", 0, {}, True, True, ISO])

        r = await st.write("daniel", 0, {"log": [1, 2]})
        check('P2 write rev 0 -> 1', [r.status, r.rev, r.updated_at], ["written", 1, ISO])
        meta, data = await st.read("daniel")
        check('P2 read liefert Stand und Daten', [meta.rev, data], [1, {"log": [1, 2]}])
        r = await st.write("daniel", 0, {"log": [1, 2, 3]})
        check('P2 veraltete baseRev -> conflict mit aktueller rev, nichts geändert', [r.status, r.rev, (await st.read("daniel"))[1]], ["conflict", 1, {"log": [1, 2]}])
        r = await st.write("daniel", 0, {"log": [1, 2]})
        check('P2 gleiche Daten (auch mit veralteter baseRev) -> unchanged ohne neue rev', [r.status, r.rev], ["unchanged", 1])
        r = await st.write("daniel", 1, {"b": 1, "a": 2})
        r2 = await st.write("daniel", 2, {"a": 2, "b": 1})
        check('P2 andere Schlüsselreihenfolge zählt als gleiche Daten', [r.status, r.rev, r2.status, r2.rev], ["written", 2, "unchanged", 2])
        for fn in (st.read, ):
            try:
                await fn("niemand")
                got = "kein Fehler"
            except S.NotFound:
                got = "NotFound"
            check('P3 read einer unbekannten Person -> NotFound', got, "NotFound")
        try:
            await st.write("niemand", 0, {})
            got = "kein Fehler"
        except S.NotFound:
            got = "NotFound"
        check('P3 write bei unbekannter Person -> NotFound', got, "NotFound")
        check('P4 nur die erwarteten Dateien (kein Rest von Temporärdateien); Tagessicherung existiert ab dem 2. Schreiben', files(d), [f"history/daniel/{clock.date()}.json.gz", "persons/daniel.json"])

        # Absturz beim Umbenennen: Datei bleibt unverändert, kein Rest
        vorher = f.read_bytes()
        echt_replace = os.replace
        def kaputt(*a, **k):
            raise OSError(28, "Platte voll")
        os.replace = kaputt
        try:
            try:
                await st.write("daniel", 2, {"log": ["neu"]})
                got = "kein Fehler"
            except S.StorageError:
                got = "StorageError"
        finally:
            os.replace = echt_replace
        check('P5 Fehler beim Speichern: StorageError, Datei unverändert, rev unverändert, keine Temporärdateien',
              [got, f.read_bytes() == vorher, st.find("daniel").rev, files(d)], ["StorageError", True, 2, [f"history/daniel/{clock.date()}.json.gz", "persons/daniel.json"]])
        r = await st.write("daniel", 2, {"log": ["neu"]})
        check('P5 danach funktioniert Speichern wieder', [r.status, r.rev], ["written", 3])

        st2 = mk_store(d, clock, max_persons=3)
        await st2.async_load()
        check('P6 Neustart: Person, rev und Daten sind wieder da', [st2.count(), st2.find("daniel").rev, st2.find("daniel").name, (await st2.read("daniel"))[1]], [1, 3, "Daniel", {"log": ["neu"]}])

        await st2.create("anna", "Anna", auth)
        await st2.create("bert", "Bert", auth)
        for pid, exc in (("carl", S.StoreFull), ("daniel", S.NameTaken)):
            try:
                await st2.create(pid, pid, auth)
                got = "kein Fehler"
            except S.NameTaken:
                got = "NameTaken"
            except S.StoreFull:
                got = "StoreFull"
            check(f'P7 create "{pid}" bei {st2.count()} von 3 Personen', got, exc.__name__)

        # Tagessicherung: Inhalt
        snap = pathlib.Path(d) / "history" / "daniel" / f"{clock.date()}.json.gz"
        s1 = json.loads(gzip.decompress(snap.read_bytes()))
        check('P8 Tagessicherung = Stand VOR der ersten Änderung des Tages (rev 1), ohne Zugangsdaten', [s1["rev"], s1["data"], s1["id"], s1["name"], "auth" in s1, "updatedAt" in s1], [1, {"log": [1, 2]}, "daniel", "Daniel", False, True])
        n_vorher = len(list(snap.parent.iterdir()))
        await st2.write("daniel", 3, {"log": ["x"]})
        check('P8 zweite Änderung am selben Tag legt keine weitere Sicherung an', len(list(snap.parent.iterdir())), n_vorher)
        clock.advance_days(1)
        await st2.write("daniel", 4, {"log": ["y"]})
        s2 = json.loads(gzip.decompress((snap.parent / f"{clock.date()}.json.gz").read_bytes()))
        check('P8 am nächsten Tag: neue Sicherung mit dem Stand vom Vortag (rev 4)', [s2["rev"], s2["data"]], [4, {"log": ["x"]}])

        # Zugangscode ändern: bleibt nach Neustart
        neu = S.hash_code("anderer-code-9", 16)
        await st2.set_auth("anna", neu)
        st3 = mk_store(d, clock, max_persons=3)
        await st3.async_load()
        check('P9 neuer Zugangscode-Hash bleibt nach Neustart erhalten', st3.find("anna").auth == neu, True)
        check('P9 set_auth ändert rev und Daten nicht', [st3.find("anna").rev, (await st3.read("anna"))[1]], [0, {}])
    finally:
        os.replace = os.replace
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ---- Aufräumen der Tagessicherungen ----
    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p2-")
    try:
        st = mk_store(d, clock, history_days=3)
        await st.async_load()
        await st.create("p", "P", S.hash_code(CODE, 16))
        tage = []
        for i in range(7):
            await st.write("p", i, {"tag": i})
            tage.append(str(clock.date()))
            clock.advance_days(1)
        sicherungen = sorted(x.name for x in (pathlib.Path(d) / "history" / "p").iterdir())
        # Tag 0: keine Sicherung (vorher rev 0). Tag i: Sicherung. Letzter Schreibtag = tage[6]; behalten: Daten jünger als 3 Tage = tage[4..6]
        check('P10 history_days=3: nach 7 Tagen bleiben nur die 3 jüngsten Sicherungen', sicherungen, [f"{t}.json.gz" for t in tage[4:7]])
        st_neu = mk_store(d, clock, history_days=3)
        clock.advance_days(10)
        await st_neu.async_load()
        check('P10 beim Start werden alte Sicherungen entfernt (hier alle), ohne Person zu berühren', [list((pathlib.Path(d) / "history" / "p").iterdir()) if (pathlib.Path(d) / "history" / "p").exists() else [], st_neu.find("p").rev], [[], 7])
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p3-")
    try:
        st = mk_store(d, clock, history_days=0)
        await st.async_load()
        await st.create("p", "P", S.hash_code(CODE, 16))
        for i in range(3):
            await st.write("p", i, {"i": i})
        check('P11 history_days=0: es entsteht keine Sicherung', files(d), ["persons/p.json"])
        await st.delete("p")
        check('P11 history_days=0: Löschen entfernt alles', files(d), [])
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ---- Löschen mit Sicherung ----
    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p4-")
    try:
        st = mk_store(d, clock, history_days=5)
        await st.async_load()
        await st.create("sebastian", "Sebastian", S.hash_code(CODE, 16))
        await st.write("sebastian", 0, {"a": 1})
        await st.write("sebastian", 1, {"a": 2})
        await st.delete("sebastian")
        gone = st.find("sebastian")
        dirs = sorted(p.name for p in (pathlib.Path(d) / "history").iterdir())
        check('P12 delete: Person weg, Datei weg, Sicherungsordner umbenannt in _deleted-…', [gone, (pathlib.Path(d) / "persons" / "sebastian.json").exists(), [x.startswith("_deleted-sebastian-") for x in dirs]], [None, False, [True]])
        fin = pathlib.Path(d) / "history" / dirs[0] / "final.json.gz"
        final = json.loads(gzip.decompress(fin.read_bytes())) if fin.exists() else None
        check('P12 delete: letzter Stand liegt als final.json.gz in der Sicherung (ohne Zugangsdaten)', [final and final["rev"], final and final["data"], final and "auth" in final], [2, {"a": 2}, False])
        m = await st.create("sebastian", "Sebastian", S.hash_code(CODE, 16))
        check('P12 derselbe Name lässt sich danach neu anlegen: leer, rev 0, alte Sicherungen nicht vermischt', [m.rev, (await st.read("sebastian"))[1], (pathlib.Path(d) / "history" / "sebastian").exists()], [0, {}, False])
        clock.advance_days(4)
        await st.prune()
        check('P12 nach 4 von 5 Tagen ist die Sicherung der gelöschten Person noch da', len([p for p in (pathlib.Path(d) / "history").iterdir() if p.name.startswith("_deleted-")]), 1)
        clock.advance_days(1)
        await st.prune()
        check('P12 nach genau 5 Tagen (history_days) ist sie entfernt', len([p for p in (pathlib.Path(d) / "history").iterdir() if p.name.startswith("_deleted-")]), 0)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ---- kaputte Dateien ----
    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p5-")
    try:
        pdir = pathlib.Path(d) / "persons"
        pdir.mkdir(parents=True)
        auth = S.hash_code(CODE, 16)
        gut = {"format": 1, "id": "gut", "name": "Gut", "created": ISO, "auth": auth, "rev": 4, "updatedAt": ISO, "data": {"x": 1}}
        (pdir / "gut.json").write_text(json.dumps(gut))
        kaputte = {
            "kaputt.json": "{nicht json",
            "falsch.json": json.dumps({**gut, "id": "anderer"}),
            "ohnerev.json": json.dumps({k: v for k, v in {**gut, "id": "ohnerev"}.items() if k != "rev"}),
            "ohneauth.json": json.dumps({k: v for k, v in {**gut, "id": "ohneauth"}.items() if k != "auth"}),
            "ohnedata.json": json.dumps({k: v for k, v in {**gut, "id": "ohnedata"}.items() if k != "data"}),
            "ohnename.json": json.dumps({k: v for k, v in {**gut, "id": "ohnename"}.items() if k != "name"}),
            "revtext.json": json.dumps({**gut, "id": "revtext", "rev": "4"}),
            "revminus.json": json.dumps({**gut, "id": "revminus", "rev": -1}),
            "revkomma.json": json.dumps({**gut, "id": "revkomma", "rev": 1.5}),
            "authleer.json": json.dumps({**gut, "id": "authleer", "auth": {}}),
            "formatneu.json": json.dumps({**gut, "id": "formatneu", "format": 2}),
            "nan.json": json.dumps({**gut, "id": "nan", "data": {"x": 1}}).replace('"x": 1', '"x": NaN'),
            "leer.json": "",
            "liste.json": "[1,2]",
            "datastring.json": json.dumps({**gut, "id": "datastring", "data": "text"}),
        }
        for n, t in kaputte.items():
            (pdir / n).write_text(t)
        (pdir / ".alt.123.tmp").write_text("rest")
        (pdir / "README.txt").write_text("fremd")
        before = {n: (pdir / n).read_bytes() for n in kaputte}
        st = mk_store(d, clock, max_persons=50)
        await st.async_load()
        check('P13 gesunde Person wird normal geladen', [st.find("gut").unreadable, st.find("gut").rev, (await st.read("gut"))[1]], [False, 4, {"x": 1}])
        check('P13 kaputte Dateien: als unlesbar markiert (nicht gelöscht)', {n[:-5]: st.find(n[:-5]).unreadable for n in kaputte}, {n[:-5]: True for n in kaputte})
        try:
            await st.read("kaputt")
            got = "kein Fehler"
        except S.StorageError:
            got = "StorageError"
        check('P13 Lesen einer unlesbaren Person -> StorageError', got, "StorageError")
        try:
            await st.write("kaputt", 0, {"a": 1})
            got = "kein Fehler"
        except S.StorageError:
            got = "StorageError"
        check('P13 Schreiben bei unlesbarer Person -> StorageError', got, "StorageError")
        try:
            await st.create("kaputt", "Kaputt", auth)
            got = "kein Fehler"
        except S.NameTaken:
            got = "NameTaken"
        check('P13 unlesbare Person: Name bleibt belegt', got, "NameTaken")
        await st.write("gut", 4, {"x": 2})
        check('P13 kaputte Dateien sind Byte für Byte unverändert, auch nach Arbeit mit anderen Personen', {n: (pdir / n).read_bytes() == b for n, b in before.items()}, {n: True for n in kaputte})
        check('P13 Reste von Temporärdateien werden beim Start entfernt, fremde Dateien bleiben', [(pdir / ".alt.123.tmp").exists(), (pdir / "README.txt").exists()], [False, True])
        check('P13 unlesbare Personen zählen mit (Obergrenze)', st.count(), 1 + len(kaputte))
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ---- Größe ----
    clock = FakeClock()
    d = tempfile.mkdtemp(prefix="aikido-p6-")
    try:
        st = mk_store(d, clock)
        await st.async_load()
        await st.create("g", "G", S.hash_code(CODE, 16))
        gross = {"log": [{"id": f"id-{i}", "note": "Übung " * 30, "date": "2026-10-01", "n": i} for i in range(20000)]}
        t0 = time.time()
        r = await st.write("g", 0, gross)
        t1 = time.time()
        _, back = await st.read("g")
        check('P14 große Daten (20000 Einträge, ca. 5 MB): speichern und wieder lesen ohne Verlust', [r.status, back == gross], ["written", True])
        check('P14 große Daten brauchen weniger als 10 s (speichern + lesen)', time.time() - t0 < 10, True)
        try:
            await st.write("g", 1, {"x": "a" * (CONST.MAX_DATA_BYTES + 1)})
            got = "kein Fehler"
        except S.TooLarge:
            got = "TooLarge"
        check('P14 Daten über der Grenze -> TooLarge, Stand unverändert', [got, st.find("g").rev], ["TooLarge", 1])
        r = await st.write("g", 1, {"x": "a" * (CONST.MAX_DATA_BYTES - 8)})  # {"x":"…"} hat 8 Zeichen Rahmen -> genau MAX_DATA_BYTES
        check('P14 genau an der Grenze (8 MiB) wird gespeichert', [r.status, r.rev], ["written", 2])
        try:
            await st.write("g", 2, {"x": "a" * (CONST.MAX_DATA_BYTES - 7)})
            got = "kein Fehler"
        except S.TooLarge:
            got = "TooLarge"
        check('P14 ein Byte darüber nicht', [got, st.find("g").rev], ["TooLarge", 2])
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# =====================================================================================================================
# A: Schnittstelle
# =====================================================================================================================
def body_ok(r):
    return bool(r.json) and r.json.get("ok") is True


def fehler(r):
    return [r.status, (r.json or {}).get("ok"), (r.json or {}).get("code")]


async def gruppe_A():
    # ---- ping ----
    async with Env() as e:
        r = await e.call("ping", method="GET")
        check('A1 ping: 200, ok, Name, api 1, Version, registration true', [r.status, r.json["ok"], r.json["app"], r.json["api"], r.json["version"], r.json["registration"]], [200, True, "aikido-tracker-server", 1, CONST.VERSION, True])
        check('A1 Kopfzeilen: no-store, nosniff, JSON', [r.headers.get("Cache-Control"), r.headers.get("X-Content-Type-Options"), r.headers.get("Content-Type", "").split(";")[0]], ["no-store", "nosniff", "application/json"])
        r = await e.call("ping", {}, method="POST")
        check('A1 ping nur mit GET (POST -> 405)', r.status, 405)
    async with Env(invite=None) as e:
        r = await e.call("ping", method="GET")
        check('A1 ohne Einladungscode: registration false', r.json["registration"], False)

    # ---- register ----
    async with Env() as e:
        alle = []
        r = await e.register("Sebastian", CODE)
        alle.append(r)
        check('A2 Anlegen: 201, ok, Person (Kennung, Name), rev 0, Zeit', [r.status, r.json.get("ok"), r.json.get("person"), r.json.get("rev"), r.json.get("updatedAt")], [201, True, {"id": "sebastian", "name": "Sebastian"}, 0, ISO])
        check('A2 Datei angelegt, Code nicht im Klartext', [e.person_file("sebastian").exists(), CODE in e.person_file("sebastian").read_text()], [True, False])
        for name in ("sebastian", "SEBASTIÁN", " Sebastian "):
            r = await e.register(name, "anderer-code")
            alle.append(r)
            check(f'A2 gleicher Name "{name}" -> 409 name_taken', fehler(r), [409, False, "name_taken"])
        r = await e.register("Anna", CODE, invite="falsch")
        alle.append(r)
        check('A2 falscher Einladungscode -> 403 bad_invite', fehler(r), [403, False, "bad_invite"])
        r = await e.register("Anna", CODE, invite="")
        check('A2 leerer Einladungscode -> 403 bad_invite', fehler(r), [403, False, "bad_invite"])
        r = await e.call("register", {"name": "Anna", "code": CODE})
        check('A2 Einladungscode fehlt im Körper -> 400 bad_request', fehler(r), [400, False, "bad_request"])
        r = await e.register("a/b", CODE, invite="falsch")
        check('A2 Reihenfolge: falscher Einladungscode wird vor der Namensprüfung gemeldet (403 statt 422)', fehler(r), [403, False, "bad_invite"])
        r = await e.register("a/b", CODE)
        alle.append(r)
        check('A2 ungültiger Name -> 422 invalid_name mit deutscher Meldung', [r.status, r.json.get("code"), isinstance(r.json.get("error"), str) and len(r.json["error"]) > 10], [422, "invalid_name", True])
        r = await e.register("Anna", "abc")
        alle.append(r)
        check('A2 zu kurzer Zugangscode -> 422 invalid_code', fehler(r), [422, False, "invalid_code"])
        for bad in ({"name": 123, "code": CODE, "invite": INVITE}, {"name": "Anna", "code": None, "invite": INVITE}, {"name": "Anna", "code": CODE, "invite": ["x"]}, {"code": CODE, "invite": INVITE}, {}):
            r = await e.call("register", bad)
            check(f'A2 falsche Typen/fehlende Felder {canon(bad)[:50]} -> 400 bad_request', fehler(r), [400, False, "bad_request"])
        r = await e.register("Anna", CODE)
        alle.append(r)
        check('A2 weitere Person anlegen klappt', [r.status, r.json["person"]["id"]], [201, "anna"])
        check('A2 der Zugangscode taucht in keiner Antwort auf', [CODE in x.text or INVITE in x.text or "anderer-code" in x.text for x in alle].count(True), 0)
        r = await e.call("register", raw=b'{"name": "Zed", "code": "abcdef", "invite": "' + INVITE.encode() + b'", "extra": {"x": [1,2,3]}, "name": "Zeta"}')
        check('A2 unbekannte Felder werden ignoriert, bei doppelten Schlüsseln gilt der letzte', [r.status, r.json["person"]["name"]], [201, "Zeta"])
    async with Env(max_persons=2) as e:
        await e.register("A1", CODE)
        await e.register("B1", CODE)
        r = await e.register("C1", CODE)
        check('A2 Obergrenze der Personen erreicht -> 409 full', fehler(r), [409, False, "full"])
    async with Env() as e:
        rs = await asyncio.gather(*[e.register("Gleich", CODE) for _ in range(6)])
        check('A2 6 gleichzeitige Anmeldungen desselben Namens: genau eine gewinnt, genau eine Datei', [sorted(r.status for r in rs), len(list((pathlib.Path(e.dir) / "persons").glob("*.json")))], [[201] + [409] * 5, 1])
    async with Env(invite=None) as e:
        r = await e.register("Anna", CODE, invite="irgendwas")
        check('A2 ohne eingerichteten Einladungscode -> 403 registration_disabled', fehler(r), [403, False, "registration_disabled"])
        check('A2 ... und es wird nichts angelegt', e.all_files(), [])

    # ---- login ----
    spy = []
    def verify_spy(code, auth):
        spy.append(1)
        return STORE.verify_code(code, auth)
    async with Env(verify=verify_spy) as e:
        await e.register("Sebastian", CODE)
        spy.clear()
        r = await e.login("Sebastian", CODE)
        check('A3 Anmelden: 200, Person, rev, Zeit', [r.status, r.json.get("ok"), r.json.get("person"), r.json.get("rev"), r.json.get("updatedAt")], [200, True, {"id": "sebastian", "name": "Sebastian"}, 0, ISO])
        check('A3 Groß-/Kleinschreibung und Akzente im Namen sind egal', [(await e.login(n, CODE)).status for n in ("SEBASTIAN", "sebastián", "Sebastian ", "Sebastian")], [200] * 4)
        check('A3 der Zugangscode unterscheidet Groß-/Kleinschreibung', (await e.login("Sebastian", CODE.upper())).status, 401)
        spy.clear()
        fälle = {
            "falscher Code": ("Sebastian", "falsch-999"),
            "unbekannter Name": ("Niemand", CODE),
            "Name mit Pfadzeichen": ("../etc/passwd", CODE),
            "zu kurzer Code": ("Sebastian", "abc"),
            "Name sehr lang": ("x" * 500, CODE),
        }
        antworten = {}
        for k, (n, c) in fälle.items():
            antworten[k] = await e.login(n, c, remote=f"10.1.1.{len(antworten) + 1}")
        check('A3 alle Fehlschläge: 401 bad_credentials', {k: fehler(v) for k, v in antworten.items()}, {k: [401, False, "bad_credentials"] for k in fälle})
        check('A3 Fehlschläge sind nicht unterscheidbar (gleicher Körper, gleicher Statuscode)', len({v.text for v in antworten.values()}), 1)
        check('A3 jeder Anmeldeversuch rechnet genau einen Hash (kein Zeitunterschied für unbekannte Namen)', len(spy), len(fälle))
        r = await e.call("login", {"name": "Sebastian"})
        check('A3 fehlender Code -> 400 bad_request', fehler(r), [400, False, "bad_request"])
        r = await e.call("login", method="GET")
        check('A3 GET statt POST -> 405', r.status, 405)

    # ---- pull / push ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        r = await e.pull("Sebastian", CODE)
        check('A4 frische Person: rev 0, data leer', [r.status, r.json.get("ok"), r.json.get("rev"), r.json.get("data"), r.json.get("person")], [200, True, 0, {}, {"id": "sebastian", "name": "Sebastian"}])
        r = await e.pull("Sebastian", CODE, since=0)
        check('A4 sinceRev = aktuelle rev -> unchanged ohne data', [r.status, r.json.get("unchanged"), "data" in r.json, r.json.get("rev")], [200, True, False, 0])
        daten = {"app": "aikido-kyu-tracker", "schemaVersion": 2, "log": [{"id": "a1", "date": "2026-10-01", "note": "Übung 日本語 \"zitiert\" \\ / <b>", "n": 1.5, "ok": True, "nix": None, "big": 12345678901234567890}], "techLinks": {}, "examTarget": {"kyu": 5}}
        r = await e.push("Sebastian", CODE, 0, daten)
        check('A5 Hochladen mit baseRev 0: 200, rev 1, Zeit', [r.status, r.json.get("ok"), r.json.get("rev"), r.json.get("updatedAt"), r.json.get("unchanged")], [200, True, 1, ISO, None])
        r = await e.pull("Sebastian", CODE)
        check('A5 Abholen liefert exakt die hochgeladenen Daten (Unicode, Zahlen, null, große Zahl)', [r.json.get("rev"), r.json.get("data") == daten, r.json["data"]["log"][0]["n"], r.json["data"]["log"][0]["big"]], [1, True, 1.5, 12345678901234567890])
        r = await e.pull("Sebastian", CODE, since=1)
        check('A5 sinceRev gleich -> unchanged, sinceRev älter -> volle Daten', [r.json.get("unchanged"), (await e.pull("Sebastian", CODE, since=0)).json.get("data") == daten], [True, True])
        for bad in ("1", 1.5, True, -1, None, [1]):
            r = await e.call("pull", {"name": "Sebastian", "code": CODE, "sinceRev": bad})
            check(f'A4 ungültiges sinceRev {bad!r} -> 400', fehler(r), [400, False, "bad_request"])
        d2 = {**daten, "examTarget": {"kyu": 4}}
        r = await e.push("Sebastian", CODE, 0, d2)
        check('A5 veraltete baseRev -> 409 conflict mit aktueller rev', [r.status, r.json.get("ok"), r.json.get("code"), r.json.get("rev"), isinstance(r.json.get("updatedAt"), str)], [409, False, "conflict", 1, True])
        check('A5 ... und gespeichert ist weiterhin der alte Stand', (await e.pull("Sebastian", CODE)).json["data"]["examTarget"], {"kyu": 5})
        r = await e.push("Sebastian", CODE, 0, daten)
        check('A5 gleicher Stand mit veralteter baseRev (verlorene Antwort wiederholt) -> 200 unchanged, rev bleibt', [r.status, r.json.get("ok"), r.json.get("unchanged"), r.json.get("rev")], [200, True, True, 1])
        r = await e.push("Sebastian", CODE, 1, d2)
        check('A5 richtige baseRev -> rev 2', [r.status, r.json.get("rev")], [200, 2])
        check('A5 Datei auf der Platte enthält den neuen Stand', json.loads(e.person_file("sebastian").read_text())["data"], d2)
        r = await e.push("Sebastian", "falsch-999", 2, d2)
        check('A5 falscher Code beim Hochladen -> 401, nichts geändert', [fehler(r), (await e.pull("Sebastian", CODE)).json["rev"]], [[401, False, "bad_credentials"], 2])

        # ungültige Anfragen: nie 500, Stand bleibt
        basis = {"name": "Sebastian", "code": CODE, "baseRev": 2, "data": {"ok": 1}}
        def mit(**kw):
            b = dict(basis); b.update(kw); return b
        fälle = [
            ("kein JSON '{'", dict(raw=b"{"), 400, "bad_request"),
            ("leer", dict(raw=b""), 400, "bad_request"),
            ("Liste statt Objekt", dict(raw=b"[]"), 400, "bad_request"),
            ("null", dict(raw=b"null"), 400, "bad_request"),
            ("Text", dict(raw=b'"abc"'), 400, "bad_request"),
            ("abgeschnitten", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"a"'), 400, "bad_request"),
            ("kein UTF-8", dict(raw=b'{"name":"S\xff\xfe"}'), 400, "bad_request"),
            ("baseRev fehlt", dict(body={k: v for k, v in basis.items() if k != "baseRev"}), 400, "bad_request"),
            ("baseRev Text", dict(body=mit(baseRev="2")), 400, "bad_request"),
            ("baseRev Kommazahl", dict(body=mit(baseRev=2.5)), 400, "bad_request"),
            ("baseRev Wahrheitswert", dict(body=mit(baseRev=True)), 400, "bad_request"),
            ("baseRev negativ", dict(body=mit(baseRev=-1)), 400, "bad_request"),
            ("data fehlt", dict(body={k: v for k, v in basis.items() if k != "data"}), 400, "bad_request"),
            ("data Liste", dict(body=mit(data=[1])), 422, "invalid_data"),
            ("data Text", dict(body=mit(data="x")), 422, "invalid_data"),
            ("data Zahl", dict(body=mit(data=5)), 422, "invalid_data"),
            ("data null", dict(body=mit(data=None)), 422, "invalid_data"),
            ("data true", dict(body=mit(data=True)), 422, "invalid_data"),
            ("Schlüssel __proto__", dict(body=mit(data={"__proto__": 1})), 422, "invalid_data"),
            ("Schlüssel mit Ziffer vorn", dict(body=mit(data={"1a": 1})), 422, "invalid_data"),
            ("Schlüssel mit Bindestrich", dict(body=mit(data={"a-b": 1})), 422, "invalid_data"),
            ("Schlüssel leer", dict(body=mit(data={"": 1})), 422, "invalid_data"),
            ("Schlüssel zu lang", dict(body=mit(data={"a" * 42: 1})), 422, "invalid_data"),
            ("31 Schlüssel", dict(body=mit(data={f"k{i}": i for i in range(31)})), 422, "invalid_data"),
            ("NaN", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":NaN}}'), 422, "invalid_data"),
            ("Infinity", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":Infinity}}'), 422, "invalid_data"),
            ("-Infinity", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":-Infinity}}'), 422, "invalid_data"),
            ("1e999", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":1e999}}'), 422, "invalid_data"),
            ("einzelnes Surrogat", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":"\\ud800"}}'), 422, "invalid_data"),
            ("Zahl mit 5000 Ziffern", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"x":' + b"9" * 5000 + b'}}'), 422, "invalid_data"),
            ("100000 Ebenen tief verschachtelt", dict(raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":2,"data":{"a":' + b"[" * 100000 + b"]" * 100000 + b"}}"), 422, "invalid_data"),
        ]
        ergebnis = {}
        for name, kw, status, code in fälle:
            r = await e.call("push", kw.get("body"), raw=kw.get("raw"))
            ergebnis[name] = fehler(r)
        check('A5 ungültige Anfragen: erwarteter Statuscode, nie 500', ergebnis, {name: [status, False, code] for name, kw, status, code in fälle})
        check('A5 nach allen ungültigen Anfragen ist der Stand unverändert (rev 2)', [(await e.pull("Sebastian", CODE)).json["rev"], json.loads(e.person_file("sebastian").read_text())["data"]], [2, d2])
        r = await e.push("Sebastian", CODE, 2, {f"k{i}": i for i in range(30)})
        check('A5 genau 30 Schlüssel sind erlaubt', [r.status, r.json.get("rev")], [200, 3])
        r = await e.push("Sebastian", CODE, 3, {"x": "a" * (CONST.MAX_DATA_BYTES)})
        check('A5 Daten über 8 MiB -> 413 too_large', fehler(r), [413, False, "too_large"])
        r = await e.call("push", raw=b'{"name":"Sebastian","code":"geheim-123","baseRev":3,"data":{"x":"' + b"a" * (CONST.MAX_BODY_BYTES + 10) + b'"}}')
        check('A5 Anfrage über der Körpergrenze (mit Content-Length) -> 413 too_large', fehler(r), [413, False, "too_large"])
        async def stuecke():
            yield b'{"name":"Sebastian","code":"geheim-123","baseRev":3,"data":{"x":"'
            for _ in range((CONST.MAX_BODY_BYTES // 65536) + 3):
                yield b"a" * 65536
            yield b'"}}'
        rr = await e.client.post("/api/aikido_tracker/push", data=stuecke(), headers={"Content-Type": "application/json"})
        body = await rr.read()
        check('A5 dieselbe Anfrage in Stücken (ohne Content-Length) -> 413 too_large', [rr.status, json.loads(body).get("code") if body[:1] == b"{" else body[:40]], [413, "too_large"])
        reader, writer = await asyncio.open_connection("127.0.0.1", e.server.port)
        writer.write(b"POST /api/aikido_tracker/push HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\nContent-Length: 104857600\r\nConnection: close\r\n\r\n")
        await writer.drain()
        try:
            statuszeile = await asyncio.wait_for(reader.readline(), 3)  # nur die erste Zeile: die Verbindung selbst darf kurz offen bleiben
            status = int(statuszeile.split(b" ", 2)[1])
        except asyncio.TimeoutError:
            status = "keine Antwort"
        writer.close()
        check('A5 angekündigte Inhaltslänge von 100 MiB: sofort 413, ohne auf den Inhalt zu warten', status, 413)
        r = await e.call("push", raw=b"x" * (CONST.MAX_BODY_BYTES + 10))
        check('A5 die Körpergrenze gilt auch für Müll (kein JSON): 413 statt 400', fehler(r), [413, False, "too_large"])
        async def muell():
            for _ in range((CONST.MAX_BODY_BYTES // 65536) + 3):
                yield b"x" * 65536
        rr = await e.client.post("/api/aikido_tracker/push", data=muell(), headers={"Content-Type": "application/json"})
        body = await rr.read()
        check('A5 dasselbe in Stücken ohne Content-Length', [rr.status, json.loads(body).get("code") if body[:1] == b"{" else body[:40]], [413, "too_large"])
        check('A5 Stand nach den Größenfehlern unverändert (rev 3)', (await e.pull("Sebastian", CODE)).json["rev"], 3)
        gross = {"log": [{"id": f"id-{i}", "note": "Übung " * 30, "n": i} for i in range(15000)]}
        t0 = time.time()
        r = await e.push("Sebastian", CODE, 3, gross)
        back = await e.pull("Sebastian", CODE)
        check('A5 großer Stand (ca. 4 MB) wird gespeichert und vollständig zurückgegeben, unter 15 s', [r.status, back.json["data"] == gross, time.time() - t0 < 15], [200, True, True])
        check('A5 die Antwort auf große Abholungen ist komprimiert', back.headers.get("Content-Encoding"), "gzip")

    # ---- gleichzeitige Zugriffe ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        rs = await asyncio.gather(*[e.push("Sebastian", CODE, 0, {"von": i}) for i in range(10)])
        stat = sorted(r.status for r in rs)
        check('A6 10 gleichzeitige Uploads auf rev 0: genau einer gewinnt, 9 Konflikte', stat, [200] + [409] * 9)
        gewinner = [i for i, r in enumerate(rs) if r.status == 200][0]
        check('A6 gespeichert ist genau der Stand des Gewinners, rev 1, Datei lesbar', [(await e.pull("Sebastian", CODE)).json["data"], json.loads(e.person_file("sebastian").read_text())["rev"]], [{"von": gewinner}, 1])
        rs = await asyncio.gather(*[e.push("Sebastian", CODE, 1, {"gleich": True}) for _ in range(8)])
        check('A6 8 gleichzeitige identische Uploads: alle 200, nur eine Änderung (rev 2)', [sorted(r.status for r in rs), (await e.pull("Sebastian", CODE)).json["rev"]], [[200] * 8, 2])
        rs = await asyncio.gather(*([e.login("Sebastian", CODE) for _ in range(5)] + [e.pull("Sebastian", CODE) for _ in range(5)]))
        check('A6 gleichzeitiges Anmelden und Abholen', sorted(set(r.status for r in rs)), [200])
        await e.register("Anna", CODE)
        rs = await asyncio.gather(*[e.push(n, CODE, 2 if n == "Sebastian" else 0, {"wer": n}) for n in ("Sebastian", "Anna")] * 1)
        check('A6 verschiedene Personen blockieren sich nicht', [r.status for r in rs], [200, 200])

    # ---- Zugangscode ändern / Löschen ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        await e.push("Sebastian", CODE, 0, {"a": 1})
        r = await e.call("change-code", {"name": "Sebastian", "code": "falsch-999", "newCode": "neuer-code-1"})
        check('A7 Code ändern mit falschem Code -> 401', fehler(r), [401, False, "bad_credentials"])
        r = await e.call("change-code", {"name": "Sebastian", "code": CODE, "newCode": "kurz"})
        check('A7 neuer Code zu kurz -> 422 invalid_code', fehler(r), [422, False, "invalid_code"])
        r = await e.call("change-code", {"name": "Sebastian", "code": CODE})
        check('A7 neuer Code fehlt -> 400', fehler(r), [400, False, "bad_request"])
        r = await e.call("change-code", {"name": "Sebastian", "code": CODE, "newCode": "neuer-code-1"})
        check('A7 Code ändern: 200', [r.status, r.json.get("ok"), "neuer-code-1" in r.text], [200, True, False])
        check('A7 alter Code geht nicht mehr, neuer geht, Daten bleiben', [(await e.login("Sebastian", CODE, remote="10.9.9.1")).status, (await e.login("Sebastian", "neuer-code-1")).status, (await e.pull("Sebastian", "neuer-code-1")).json["data"]], [401, 200, {"a": 1}])
        await e.restart()
        check('A7 neuer Code gilt auch nach Neustart', [(await e.login("Sebastian", "neuer-code-1")).status, (await e.login("Sebastian", CODE, remote="10.9.9.2")).status], [200, 401])

    async with Env() as e:
        await e.register("Sebastian", CODE)
        await e.push("Sebastian", CODE, 0, {"a": 1})
        await e.push("Sebastian", CODE, 1, {"a": 2})
        r = await e.call("delete", {"name": "Sebastian", "code": CODE})
        check('A8 Löschen ohne confirm -> 400, nichts gelöscht', [fehler(r), e.person_file("sebastian").exists()], [[400, False, "bad_request"], True])
        r = await e.call("delete", {"name": "Sebastian", "code": CODE, "confirm": "ja"})
        check('A8 confirm muss genau true sein -> 400', fehler(r), [400, False, "bad_request"])
        r = await e.call("delete", {"name": "Sebastian", "code": "falsch-999", "confirm": True}, remote="10.8.8.1")
        check('A8 Löschen mit falschem Code -> 401, nichts gelöscht', [fehler(r), e.person_file("sebastian").exists()], [[401, False, "bad_credentials"], True])
        r = await e.call("delete", {"name": "Sebastian", "code": CODE, "confirm": True})
        check('A8 Löschen: 200 ok, Datei weg', [r.status, r.json.get("ok"), e.person_file("sebastian").exists()], [200, True, False])
        check('A8 danach: Anmelden -> 401, Abholen -> 401', [(await e.login("Sebastian", CODE, remote="10.8.8.2")).status, (await e.pull("Sebastian", CODE, remote="10.8.8.3")).status], [401, 401])
        check('A8 Sicherung der gelöschten Person bleibt (history_days > 0): Tagessicherung + letzter Stand',
              sorted(os.path.basename(p) for p in e.all_files() if p.startswith("history/_deleted-sebastian-")), sorted([f"{e.clock.date()}.json.gz", "final.json.gz"]))
        check('A8 ... und es liegt nichts anderes mehr unter history/ oder persons/', [p for p in e.all_files() if not p.startswith("history/_deleted-sebastian-")], [])
        r = await e.register("Sebastian", "neuer-code-2")
        check('A8 derselbe Name lässt sich neu anlegen (leer)', [r.status, (await e.pull("Sebastian", "neuer-code-2")).json["data"]], [201, {}])

    # ---- Kopfzeilen, Methoden, Pfade ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        antworten = [
            await e.login("Sebastian", CODE),
            await e.login("Sebastian", "falsch-999", remote="10.7.7.1"),
            await e.pull("Sebastian", CODE),
            await e.push("Sebastian", CODE, 0, {"a": 1}),
            await e.call("push", raw=b"{"),
        ]
        check('A9 alle Antworten: JSON, no-store, nosniff', [[r.headers.get("Cache-Control"), r.headers.get("X-Content-Type-Options"), r.headers.get("Content-Type", "").split(";")[0]] for r in antworten], [["no-store", "nosniff", "application/json"]] * 5)
        r = await e.call("login", {"name": "Sebastian", "code": CODE}, headers={"Origin": "https://boese.example", "Access-Control-Request-Method": "POST"})
        check('A9 keine CORS-Freigabe (auch nicht bei fremdem Origin)', [r.headers.get("Access-Control-Allow-Origin"), r.headers.get("Access-Control-Allow-Credentials")], [None, None])
        r = await e.call("login", method="OPTIONS")
        check('A9 OPTIONS wird nicht freigegeben', r.headers.get("Access-Control-Allow-Origin"), None)
        r = await e.call("gibtsnicht", {})
        check('A9 unbekannter Pfad -> 404', r.status, 404)
        for p in ("login", "pull", "push", "register", "change-code", "delete"):
            r = await e.call(p, method="GET")
            check(f'A9 GET auf {p} -> 405', r.status, 405)
        r = await e.call("login", raw=b'{"name":"Sebastian","code":"geheim-123"}', headers={"Content-Type": "text/plain"})
        check('A9 Inhaltstyp text/plain mit gültigem JSON wird wie JSON behandelt (kein Cookie/CSRF-Risiko, Zugang steckt im Körper)', r.status, 200)

    # ---- Protokolle ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        await e.login("Sebastian", "falsch-999", remote="10.6.6.1")
        await e.login("Sebastian\nGEFÄLSCHTE ZEILE", "falsch-998", remote="10.6.6.2")
        await e.register("X", CODE, invite="falscher-einladungscode")
        await e.call("change-code", {"name": "Sebastian", "code": CODE, "newCode": "neuer-code-777"})
        await e.push("Sebastian", "neuer-code-777", 0, {"a": 1})
        text = "\n".join(e.logs.lines)
        check('A10 Protokoll enthält weder Zugangscodes noch Einladungscodes', [s in text for s in (CODE, "falsch-999", "falsch-998", "neuer-code-777", INVITE, "falscher-einladungscode")], [False] * 6)
        check('A10 Namen aus Anfragen können keine Protokollzeilen fälschen (kein Zeilenumbruch in einer Zeile)', [("\n" in line) for line in e.logs.lines].count(True), 0)
        check('A10 Fehlversuche werden protokolliert (Warnung mit Adresse)', any("10.6.6.1" in line for line in e.logs.lines), True)

    # ---- Neustart ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        await e.push("Sebastian", CODE, 0, {"a": [1, 2, 3]})
        await e.restart()
        r = await e.login("Sebastian", CODE)
        check('A11 nach Neustart: Anmelden klappt, rev bleibt', [r.status, r.json.get("rev")], [200, 1])
        check('A11 nach Neustart: Daten vollständig', (await e.pull("Sebastian", CODE)).json["data"], {"a": [1, 2, 3]})
        r = await e.register("Sebastian", CODE)
        check('A11 nach Neustart: Name weiterhin belegt', fehler(r), [409, False, "name_taken"])

    # ---- Datei einer Person unlesbar ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        await e.register("Anna", CODE)
        e.person_file("sebastian").write_text("{kaputt")
        await e.restart()
        r = await e.pull("Sebastian", CODE)
        check('A12 unlesbare Datei: 500 storage_error mit Meldung (Anmeldung ist nicht möglich, da der Hash fehlt -> gleiche Meldung wie bei falschem Code ODER storage_error)', r.status in (401, 500) and (r.json or {}).get("ok") is False, True)
        check('A12 andere Personen laufen weiter', (await e.pull("Anna", CODE)).status, 200)
        check('A12 die kaputte Datei bleibt unverändert', e.person_file("sebastian").read_text(), "{kaputt")
        r = await e.register("Sebastian", CODE)
        check('A12 der Name der unlesbaren Person bleibt belegt', fehler(r), [409, False, "name_taken"])


# =====================================================================================================================
# R: Sperren und Schutz
# =====================================================================================================================
async def gruppe_R():
    # ---- je Adresse: 10 Fehlversuche in 15 Minuten ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        ip = "10.0.0.1"
        for i in range(10):
            r = await e.login("Sebastian", f"falsch-{i}00", remote=ip)
            e.clock.advance(1)
            if r.status != 401:
                check(f'R1 Fehlversuch {i + 1} von 10 liefert 401', r.status, 401)
        r = await e.login("Sebastian", CODE, remote=ip)
        check('R1 nach 10 Fehlversuchen: auch der richtige Code wird abgewiesen (429 rate_limited)', fehler(r), [429, False, "rate_limited"])
        ra = r.headers.get("Retry-After")
        check('R1 Retry-After (Sekunden) steht im Kopf und im Körper, ca. 890', [ra is not None and 880 <= int(ra) <= 891, r.json.get("retryAfter") == int(ra)], [True, True])
        check('R1 andere Adresse ist nicht betroffen', (await e.login("Sebastian", CODE, remote="10.0.0.2")).status, 200)
        for p in ("pull", "push", "register", "change-code", "delete"):
            body = {"name": "Sebastian", "code": CODE, "invite": INVITE, "baseRev": 0, "data": {}, "newCode": "neuer-code-1", "confirm": True}
            r = await e.call(p, body, remote=ip)
            check(f'R1 gesperrte Adresse: auch {p} wird abgewiesen', r.status, 429)
        r = await e.call("ping", method="GET", remote=ip)
        check('R1 ping bleibt für gesperrte Adressen erreichbar', r.status, 200)
        e.clock.advance(int(ra) - 1)
        check('R1 eine Sekunde vor Ablauf von Retry-After ist die Adresse noch gesperrt', (await e.login("Sebastian", CODE, remote=ip)).status, 429)
        e.clock.advance(1)
        check('R1 nach Ablauf von Retry-After (15 Minuten ab dem ältesten Fehlversuch) geht es wieder', (await e.login("Sebastian", CODE, remote=ip)).status, 200)

    async with Env() as e:
        await e.register("Sebastian", CODE)
        ip = "10.0.0.3"
        for i in range(9):
            await e.login("Sebastian", f"falsch-{i}00", remote=ip)
        check('R2 ein Erfolg setzt den Zähler nicht zurück', (await e.login("Sebastian", CODE, remote=ip)).status, 200)
        await e.login("Sebastian", "falsch-999", remote=ip)
        check('R2 der 10. Fehlversuch sperrt trotz Erfolg dazwischen', (await e.login("Sebastian", CODE, remote=ip)).status, 429)

    async with Env() as e:
        await e.register("Sebastian", CODE)
        stati = [(await e.login("Sebastian", CODE, remote="10.0.0.6")).status for _ in range(15)]
        check('R2 erfolgreiche Anmeldungen zählen nicht als Fehlversuche (15 Mal 200, keine Sperre)', stati, [200] * 15)

    async with Env() as e:
        ip = "10.0.0.4"
        for i in range(10):
            await e.login(f"Niemand{i}", "falsch-999", remote=ip)
        check('R3 Fehlversuche mit lauter unbekannten Namen sperren die Adresse ebenso', (await e.login("Niemand", "falsch-999", remote=ip)).status, 429)

    async with Env() as e:
        for i in range(10):
            await e.register("Anna", CODE, invite=f"falsch-{i}", remote="10.0.0.5")
        r = await e.register("Anna", CODE, remote="10.0.0.5")
        check('R4 10 falsche Einladungscodes sperren die Adresse (auch für den richtigen Code)', [fehler(r), e.all_files()], [[429, False, "rate_limited"], []])

    # ---- je Person: 30 Fehlversuche in 15 Minuten, von beliebigen Adressen ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        for ip in range(3):
            for i in range(10):
                await e.login("Sebastian", f"falsch-{i}00", remote=f"10.1.0.{ip}")
        r = await e.login("Sebastian", CODE, remote="10.1.0.99")
        check('R5 30 Fehlversuche von 3 Adressen sperren die Person für alle (429)', fehler(r), [429, False, "rate_limited"])
        e.clock.advance(901)
        check('R5 nach 15 Minuten geht es wieder', (await e.login("Sebastian", CODE, remote="10.1.0.99")).status, 200)

    async with Env() as e:
        for ip in range(3):
            for i in range(10):
                await e.login("Niemand", "falsch-999", remote=f"10.2.0.{ip}")
        r = await e.login("Niemand", "falsch-999", remote="10.2.0.99")
        check('R6 unbekannte Namen verhalten sich genauso (keine Möglichkeit, Namen zu erraten)', fehler(r), [429, False, "rate_limited"])
        r2 = await e.login("Sebastian", CODE, remote="10.2.0.98")
        check('R6 eine andere (unbekannte) Person ist nicht mitgesperrt', fehler(r2), [401, False, "bad_credentials"])

    # ---- Schreibgrenze ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        rev = 0
        stati = []
        for i in range(31):
            r = await e.push("Sebastian", CODE, rev, {"i": i}, remote=f"10.3.0.{i}")
            stati.append(r.status)
            if r.status == 200:
                rev = r.json["rev"]
        check('R7 30 Uploads pro Minute gehen durch, der 31. -> 429', [stati.count(200), stati[-1]], [30, 429])
        e.clock.advance(61)
        r = await e.push("Sebastian", CODE, rev, {"i": 99})
        check('R7 nach einer Minute geht es wieder', r.status, 200)

    # ---- allgemeine Anfragegrenze je Adresse ----
    async with Env() as e:
        await e.register("Sebastian", CODE)
        stati = [(await e.pull("Sebastian", CODE, since=0, remote="10.4.0.1")).status for _ in range(125)]
        check('R8 je Adresse höchstens 120 Anfragen pro Minute (danach 429)', [stati.count(200) + stati.count(429), stati[:120].count(200), stati[120:]], [125, 120, [429] * 5])
        e.clock.advance(61)
        check('R8 nach einer Minute geht es wieder', (await e.pull("Sebastian", CODE, since=0, remote="10.4.0.1")).status, 200)

    # ---- gleichzeitige Fehlversuche dürfen die Sperre nicht überholen ----
    gerechnet = []

    def zaehler(code, auth):
        gerechnet.append(1)
        return STORE.verify_code(code, auth)

    async with Env(verify=zaehler) as e:
        await e.register("Sebastian", CODE)
        gerechnet.clear()
        rs = await asyncio.gather(*[e.login("Sebastian", f"falsch-{i}00", remote="10.5.0.1") for i in range(40)])
        stati = sorted(r.status for r in rs)
        check('R9 40 gleichzeitige Fehlversuche von einer Adresse: nur 10 werden geprüft, 30 sofort abgewiesen', [stati.count(401), stati.count(429), len(gerechnet)], [10, 30, 10])
        rs = await asyncio.gather(*[e.register("Neu", CODE, invite=f"falsch-{i}", remote="10.5.0.2") for i in range(40)])
        stati = sorted(r.status for r in rs)
        check('R9 dasselbe bei gleichzeitigen falschen Einladungscodes: 10 mal 403, 30 mal 429', [stati.count(403), stati.count(429)], [10, 30])

        # Kopfzeilen kommen sofort, der Körper erst später (rohe Verbindungen): alle 40 Anfragen passieren die erste Sperrprüfung
        loslassen = asyncio.Event()

        async def roh(name, code, remote):
            reader, writer = await asyncio.open_connection("127.0.0.1", e.server.port)
            inhalt = json.dumps({"name": name, "code": code}).encode()
            kopf = (f"POST /api/aikido_tracker/login HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\nX-Test-Remote: {remote}\r\n"
                    f"Content-Length: {len(inhalt)}\r\nConnection: close\r\n\r\n").encode()
            writer.write(kopf)
            await writer.drain()
            await loslassen.wait()
            writer.write(inhalt)
            await writer.drain()
            antwort = await reader.read()
            writer.close()
            return int(antwort.split(b" ", 2)[1])

        gerechnet.clear()
        aufgaben = [asyncio.ensure_future(roh("Sebastian2", f"falsch-{i}00", "10.5.0.3")) for i in range(40)]
        await asyncio.sleep(0.5)
        loslassen.set()
        stati = sorted(await asyncio.gather(*aufgaben))
        check('R9 Körper erst nach den Kopfzeilen (alle passieren die erste Prüfung): trotzdem nur 10 geprüft, 30 mal 429', [stati.count(401), stati.count(429), len(gerechnet)], [10, 30, 10])

    # ---- Hilfsfunktionen: Adressschlüssel und gleitendes Zeitfenster ----
    ck = API._client_key
    check('R10 Adressschlüssel: IPv4 unverändert, IPv6 nach /64 zusammengefasst, IPv4-in-IPv6 als IPv4, fehlende/ungültige Angaben',
          [ck("10.0.0.1"), ck("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == ck("2001:db8:1:2::1"), ck("2001:db8:1:3::1") != ck("2001:db8:1:2::1"), ck("::ffff:10.0.0.9"), ck(None), ck("kein-ip")],
          ["10.0.0.1", True, True, "10.0.0.9", "unbekannt", "ungueltig"])
    SlidingLog = sys.modules["aikido_tracker.limits"].SlidingLog
    log = SlidingLog(limit=3, window=10, max_keys=5)
    for i in range(3):
        log.add("a", 100 + i)
    check('R10 Zeitfenster: voll -> Wartezeit bis das älteste Ereignis abläuft', [log.retry_after("a", 102), log.retry_after("a", 109.5), log.retry_after("a", 110), log.retry_after("b", 102)], [8, 1, 0, 0])
    log2 = SlidingLog(limit=3, window=10, max_keys=5)
    for t in (100, 101, 102):
        log2.add("a", t)
    stamp = log2.add("a", 103)
    vorher = log2.count("a", 103)
    log2.discard("a", stamp)
    check('R10 Ausbuchen einer Marke und Zählen', [vorher, log2.count("a", 103), log2.count("a", 130)], [4, 3, 0])
    for i in range(12):
        log.add(f"k{i}", 200 + i)
    check('R10 Obergrenze der gemerkten Schlüssel (Schutz des Arbeitsspeichers)', [len(log._events) <= 5, log.count("k11", 211)], [True, 1])


# =====================================================================================================================
# S: Auslieferung der App-Seite
# =====================================================================================================================
async def gruppe_S():
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from harness import PAGE
    d = tempfile.mkdtemp(prefix="aikido-s-")
    seite = pathlib.Path(d) / "aikido-kyu-tracker.html"
    app = web.Application()
    PAGE.add_page_route(app, lambda: str(seite))
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        async def holen(pfad="/aikido-tracker", **kw):
            r = await client.get(pfad, **kw)
            return r.status, r.headers, await r.read()

        st, h, b = await holen()
        check('S1 Datei fehlt: 404 mit deutschem Hinweis (neu herunterladen / page_file), nicht zwischenspeichern', [st, h.get("Cache-Control"), b"HACS" in b, b"page_file" in b, b"www" in b, h.get("Content-Type", "").split(";")[0]], [404, "no-store", True, True, False, "text/plain"])
        v1 = "<!doctype html><meta charset=utf-8><title>Version 1</title>Übung".encode("utf-8")
        seite.write_bytes(v1)
        os.utime(seite, (1_700_000_000, 1_700_000_000))
        st, h, b = await holen()
        check('S2 Datei da: 200, HTML (UTF-8), no-cache, nosniff, ETag und Last-Modified vorhanden', [st, h.get("Content-Type"), h.get("Cache-Control"), h.get("X-Content-Type-Options"), bool(h.get("ETag")), bool(h.get("Last-Modified")), b == v1], [200, "text/html; charset=utf-8", "no-cache", "nosniff", True, True, True])
        check('S2 kein "max-age": der Browser darf nicht wochenlang ohne Nachfrage zwischenspeichern', "max-age" in (h.get("Cache-Control") or ""), False)
        etag1 = h["ETag"]
        st, h2, b2 = await holen(headers={"If-None-Match": etag1})
        check('S3 unverändert: Nachfrage mit ETag -> 304 ohne Inhalt', [st, b2], [304, b""])
        v2 = "<!doctype html><meta charset=utf-8><title>Version 2 – länger</title>Übung Übung".encode("utf-8")
        seite.write_bytes(v2)
        os.utime(seite, (1_700_000_100, 1_700_000_100))
        st, h3, b3 = await holen(headers={"If-None-Match": etag1})
        check('S3 Datei ersetzt: dieselbe Nachfrage liefert sofort die neue Fassung mit neuem ETag', [st, b3 == v2, h3.get("ETag") != etag1], [200, True, True])
        st, h4, b4 = await holen("/aikido-tracker/")
        check('S4 auch mit Schrägstrich am Ende erreichbar', [st, b4 == v2], [200, True])
        r = await client.post("/aikido-tracker", data=b"x")
        check('S4 nur GET (POST -> 405)', r.status, 405)
        seite.unlink()
        st, h5, b5 = await holen()
        check('S5 Datei wieder entfernt: 404 (kein alter Inhalt aus dem Speicher)', [st, b5 == v2], [404, False])
    finally:
        await client.close()
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# =====================================================================================================================
# W: Pfade – welche Seite wird ausgeliefert, und wo dürfen die Daten NICHT liegen
# =====================================================================================================================
async def gruppe_W():
    from harness import PAGE

    # ---- W1-W3: Standard = die mit dem Baustein gelieferte App, page_file übersteuert ----
    paket = "/config/custom_components/aikido_tracker"
    gebuendelt = paket + "/app/aikido-kyu-tracker.html"
    check("W1 ohne page_file: die im Baustein mitgelieferte App", PAGE.resolve_page_path("/config", None, paket), gebuendelt)
    check("W1 leeres page_file zählt als nicht eingestellt", PAGE.resolve_page_path("/config", "", paket), gebuendelt)
    check("W2 page_file relativ: gilt ab dem Konfigurationsordner", PAGE.resolve_page_path("/config", "www/meine-seite.html", paket), "/config/www/meine-seite.html")
    check("W2 page_file absolut: wird so übernommen", PAGE.resolve_page_path("/config", "/srv/seiten/app.html", paket), "/srv/seiten/app.html")
    check("W3 der Name der mitgelieferten Datei ist festgelegt (HACS, README und Prüfungen verlassen sich darauf)", [PAGE.BUNDLED_DIR, PAGE.BUNDLED_FILE], ["app", "aikido-kyu-tracker.html"])
    check("W3 Konstanten und Auflösung passen zusammen", PAGE.resolve_page_path("/c", None, "/p"), f"/p/{PAGE.BUNDLED_DIR}/{PAGE.BUNDLED_FILE}")

    # ---- W4: die Datei liegt wirklich im Paket (kein toter Standardpfad) ----
    echt = pathlib.Path(SRC) / PAGE.BUNDLED_DIR / PAGE.BUNDLED_FILE
    check("W4 die mitgelieferte App existiert im Baustein-Ordner und ist eine HTML-Seite", [echt.is_file(), echt.read_bytes()[:15].lower() if echt.is_file() else b""], [True, b"<!doctype html>"])

    # ---- W5: Datenordner im Ordner des Bausteins wäre bei einem HACS-Update weg ----
    d = pathlib.Path(tempfile.mkdtemp(prefix="aikido-w-"))
    try:
        paketdir = d / "config" / "custom_components" / "aikido_tracker"
        (paketdir / "daten").mkdir(parents=True)
        (d / "config" / "custom_components" / "aikido_tracker_zwei").mkdir()
        (d / "config" / "aikido_tracker").mkdir()
        inside = STORE.is_inside
        check("W5 Ordner im Baustein-Ordner -> ja", inside(str(paketdir / "daten"), str(paketdir)), True)
        check("W5 noch nicht vorhandener Ordner im Baustein-Ordner -> ja (die Prüfung läuft vor dem Anlegen)", inside(str(paketdir / "neu" / "tiefer"), str(paketdir)), True)
        check("W5 der Baustein-Ordner selbst -> ja", inside(str(paketdir), str(paketdir)), True)
        check("W5 mit Schrägstrich am Ende -> ja", inside(str(paketdir / "daten") + "/", str(paketdir) + "/"), True)
        check("W5 der Standard-Datenordner neben custom_components -> nein", inside(str(d / "config" / "aikido_tracker"), str(paketdir)), False)
        check("W5 Nachbar mit gleichem Namensanfang (aikido_tracker_zwei) -> nein", inside(str(d / "config" / "custom_components" / "aikido_tracker_zwei"), str(paketdir)), False)
        check("W5 der übergeordnete Ordner -> nein (nur 'darin' zählt)", inside(str(paketdir.parent), str(paketdir)), False)
        check("W5 mit '..' hinaus -> nein", inside(str(paketdir / "daten" / ".." / ".." / ".." / "aikido_tracker"), str(paketdir)), False)
        check("W5 mit '..' hinein -> ja", inside(str(d / "config" / "aikido_tracker" / ".." / "custom_components" / "aikido_tracker" / "daten"), str(paketdir)), True)
        os.symlink(paketdir, d / "config" / "verknuepfung")
        check("W5 Verknüpfung in den Baustein-Ordner -> ja (kein Schlupfloch über Symlinks)", inside(str(d / "config" / "verknuepfung" / "daten"), str(paketdir)), True)
        os.symlink(d / "config" / "aikido_tracker", paketdir / "zeigt-hinaus")
        check("W5 Verknüpfung im Baustein-Ordner, die hinaus zeigt -> nein (die Daten liegen dann wirklich draußen)", inside(str(paketdir / "zeigt-hinaus"), str(paketdir)), False)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# =====================================================================================================================
async def main():
    gruppen = {"L": gruppe_L, "P": gruppe_P, "A": gruppe_A, "R": gruppe_R, "S": gruppe_S, "W": gruppe_W}
    wahl = [a.upper() for a in sys.argv[1:]] or list(gruppen)
    global N, FEHLER
    for g in wahl:
        try:
            await gruppen[g]()
        except Exception as err:
            N += 1
            FEHLER += 1
            print(f"  FALSCH {g}: abgebrochen – {type(err).__name__}: {err}")
            traceback.print_exc(limit=4)
    print(f"\nServer-Baustein: {N - FEHLER} von {N} Prüfungen bestanden{f' — {FEHLER} FEHLGESCHLAGEN' if FEHLER else ' — alles grün'}   (Quelle: {SRC})")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
