# Aikido Tracker – Server-Baustein für Home Assistant: Schnittstelle (API 1)

Stand: 31.10.2026 · Baustein: Custom Integration `aikido_tracker` · Version 1.2.0

## Zweck

Zentraler Speicher für den „Aikido Kyu Tracker“: Jede Person hat einen **Namen** und einen **Zugangscode**.
Wer beides kennt, kann seinen kompletten Datenstand abholen und hochladen – von jedem Gerät, im Heimnetz und über DuckDNS.
Der Server kennt das Datenformat der App **nicht**: Er speichert ein JSON-Objekt (`data`) je Person, zählt eine
**Versionsnummer** (`rev`) hoch und verhindert so, dass ein Gerät unbemerkt den Stand eines anderen überschreibt.

Der Baustein läuft **innerhalb von Home Assistant** unter derselben Adresse wie die Seite (`/api/aikido_tracker/…`).
Damit gibt es keinen zweiten Port, kein CORS und keinen Mischinhalt (https-Seite → http-Server).
Er liefert außerdem die App selbst aus (`/aikido-tracker`, siehe unten); die App steckt im Baustein.

## Grundregeln

* Alle Aufrufe sind `POST` mit JSON-Körper (außer `ping` = `GET`). Zugangsdaten stehen nie in der Adresse.
* Antworten sind immer JSON mit `Cache-Control: no-store`. Erfolg: `{"ok": true, …}`. Fehler: `{"ok": false, "code": "<kurzcode>", "error": "<deutsche Meldung>"}`.
* Kein Aufruf braucht eine Anmeldung bei Home Assistant. Geschützt wird nur durch Name + Zugangscode (bzw. Einladungscode zum Anlegen).
* Zeiten sind UTC im Format `2026-10-25T10:05:00Z`.
* Neue Felder in Antworten können jederzeit dazukommen; die App muss unbekannte Felder ignorieren. Die Zahl `api` (derzeit 1) steigt nur bei unverträglichen Änderungen.
* Der Inhaltstyp der Anfrage ist egal (auch `text/plain` wird als JSON gelesen); es gibt keine Cookies.
* Antworten auf `pull` sind mit gzip komprimiert, wenn der Browser es anbietet und die Antwort größer als 16 KiB ist (der Browser entpackt selbst).

## Namen und Codes

| | Regel |
|---|---|
| Name | 1–40 Zeichen: Buchstaben (auch Umlaute, Japanisch …), Ziffern, `_`, Leerzeichen, `.`, `'`, `-`. Führende/abschließende Leerzeichen entfallen, mehrfache werden zu einem. Unicode wird normalisiert (NFC); der typografische Apostroph ’ wird zu `'`. |
| Kennung (`id`) | wird aus dem Namen gebildet: ohne Akzente, kleingeschrieben, Zeichenfolgen außerhalb a–z/0–9 → `-` („Sebastián Müller“ → `sebastian-muller`, „Weiß“ → `weiss`, „Øystein“ → `oystein`). Hat der Name keine lateinischen Buchstaben/Ziffern (z. B. „田中“), ist die Kennung `p-` + 12 Hexzeichen. Zwei Namen mit gleicher Kennung gelten als derselbe Name („Muller“ = „Müller“). |
| Zugangscode | 6–64 Zeichen, keine Steuerzeichen, Unicode NFC; Groß-/Kleinschreibung zählt, Leerzeichen am Rand bleiben erhalten. Gespeichert wird nur ein scrypt-Hash (nie der Code). |
| Einladungscode | in `configuration.yaml` festgelegt (6–64 Zeichen); ohne ihn ist das Anlegen neuer Personen gesperrt. |

## Grenzen und Schutz

* Anfrage höchstens 8 MiB + 64 KiB, `data` serialisiert höchstens 8 MiB → sonst `413 too_large`. Eine angekündigte Länge über der Grenze wird sofort abgewiesen.
* `data` muss ein JSON-Objekt sein, höchstens 30 Schlüssel auf oberster Ebene (Muster `[A-Za-z][A-Za-z0-9_]{0,40}`), nur endliche Zahlen
  (`NaN`, `Infinity`, `1e999` werden abgelehnt), keine einzelnen Surrogat-Zeichen → sonst `422 invalid_data`.
  Der Server speichert die Schlüssel sortiert; die Reihenfolge von Schlüsseln in Objekten geht verloren (Reihenfolge in Listen bleibt).
* Fehlversuche (falscher Name/Code/Einladungscode): je Absender-Adresse höchstens 10 in 15 Minuten, je Person höchstens 30 in 15 Minuten → `429 rate_limited` mit `Retry-After` (Sekunden, auch als `retryAfter` im Körper).
  Der Zähler läuft nur über die Zeit ab (ein erfolgreicher Aufruf setzt ihn nicht zurück, zählt aber selbst nicht als Fehlversuch). Unbekannter Name und falscher Code sind **nicht unterscheidbar** (gleiche Antwort, gleiche Rechenzeit).
  Gleichzeitige Anfragen können die Grenze nicht überholen. Eine gesperrte Adresse wird bei **allen** Aufrufen (außer `ping`) abgewiesen.
* Anfragen insgesamt: höchstens 120 pro Minute und Adresse (ohne `ping`) → `429 rate_limited`.
* Schreiben (`push`): höchstens 30 pro Minute und Person → `429 rate_limited`.
* IPv6-Adressen werden als /64-Netz gezählt.
* Höchstens `max_persons` Personen (Vorgabe 20) → danach `409 full`.
* Hinter einem Proxy (nginx, Caddy …) muss in Home Assistant `http: use_x_forwarded_for: true` und `trusted_proxies` eingestellt sein – sonst sieht der Baustein nur die Proxy-Adresse (alle teilen sich dann die Sperren), und Home Assistant lehnt Anfragen mit `X-Forwarded-For` mit 400 ab.

## Aufrufe

### `GET /api/aikido_tracker/ping`
Ohne Anmeldung, ohne Zähler. Antwort: `{"ok": true, "app": "aikido-tracker-server", "api": 1, "version": "1.2.0", "registration": true|false}`.
`registration` = ob ein Einladungscode eingerichtet ist (Anlegen möglich).

### `POST /api/aikido_tracker/register` – Person anlegen
Körper: `{"name": "Sebastian", "code": "geheim123", "invite": "<Einladungscode>"}`.
Antwort `201`: `{"ok": true, "person": {"id": "sebastian", "name": "Sebastian"}, "rev": 0, "updatedAt": "…"}`; der Datenstand ist leer (`rev` 0).
Fehler: `403 registration_disabled` (kein Einladungscode eingerichtet), `403 bad_invite`, `409 name_taken`, `409 full`, `422 invalid_name`, `422 invalid_code`, `429 rate_limited`.
Reihenfolge der Prüfungen: Felder → Einladungscode → Name → Code → Platz/Vergabe.

### `POST /api/aikido_tracker/login` – Zugang prüfen
Körper: `{"name": "Sebastian", "code": "geheim123"}`.
Antwort: `{"ok": true, "person": {"id", "name"}, "rev": 7, "updatedAt": "…"}`. Fehler: `401 bad_credentials`, `429 rate_limited`.

### `POST /api/aikido_tracker/pull` – Datenstand abholen
Körper: `{"name", "code", "sinceRev": 7}` (`sinceRev` optional, ganze Zahl ≥ 0).
Antwort: `{"ok": true, "person": {…}, "rev": 9, "updatedAt": "…", "data": { … }}`.
Ist `sinceRev` gleich der aktuellen `rev`, kommt statt `data` nur `{"ok": true, "unchanged": true, "rev": 9, "updatedAt": "…"}` (spart Datenvolumen).
Bei `rev` 0 ist `data` ein leeres Objekt `{}`. Fehler wie `login`; zusätzlich `500 storage_error` (Datei dieser Person lässt sich nicht lesen).

### `POST /api/aikido_tracker/push` – Datenstand hochladen
Körper: `{"name", "code", "baseRev": 9, "data": { … }}`.
`baseRev` ist die `rev`, auf der der Stand des Geräts aufbaut.
* `baseRev` = aktuelle `rev` → gespeichert, Antwort `{"ok": true, "rev": 10, "updatedAt": "…"}`.
* `data` ist **identisch** mit dem gespeicherten Stand → nichts wird geschrieben, Antwort `{"ok": true, "unchanged": true, "rev": 9, …}` (egal welche `baseRev`; macht Wiederholungen nach verlorener Antwort harmlos).
* sonst bei abweichender `baseRev` → `409 conflict` mit `{"rev": <aktuelle>, "updatedAt": …}`. Die App holt dann den Stand ab, führt zusammen und lädt erneut hoch.
Fehler außerdem: `413 too_large`, `422 invalid_data`, `429 rate_limited`, `401 bad_credentials`, `500 storage_error` (z. B. Platte voll).
Reihenfolge der Prüfungen: Felder (`baseRev`, `data` vorhanden) → Anmeldung → Form von `data` → Schreibgrenze → Speichern.

### `POST /api/aikido_tracker/change-code` – Zugangscode ändern
Körper: `{"name", "code", "newCode"}`. Antwort `{"ok": true}`. Fehler: `401`, `422 invalid_code`, `429`.

### `POST /api/aikido_tracker/delete` – Person und Daten löschen
Körper: `{"name", "code", "confirm": true}`. Antwort `{"ok": true}`. Ohne `"confirm": true` (genau der Wert `true`) → `400 bad_request`.
Die Tagessicherungen der Person bleiben noch `history_days` Tage erhalten (Wiederherstellung von Hand) und werden danach gelöscht.

### Weitere Fehlercodes
`400 bad_request` (kein JSON, falscher Typ, Feld fehlt; auch `408` bei unvollständig übertragener Anfrage), `500 server_error` (unerwarteter Fehler; steht mit Einzelheiten im Home-Assistant-Protokoll).
Eine Person, deren Datei unlesbar ist, kann sich nicht anmelden (`401`, wie bei falschem Code) – der Grund steht im Protokoll.

## Die App-Seite: `GET /aikido-tracker`

Der Baustein liefert die im Baustein mitgelieferte App (`custom_components/aikido_tracker/app/aikido-kyu-tracker.html`)
unter `/aikido-tracker` aus (auch mit `/` am Ende). Mit `page_file` lässt sich stattdessen eine andere Datei einstellen
(relativ zum Konfigurationsordner oder absolut). So installiert und aktualisiert HACS Server und App gemeinsam. Anders als Dateien unter `/local/…` (Home Assistant erlaubt dort 31 Tage Zwischenspeicher) sendet er
`Cache-Control: no-cache` mit `ETag`/`Last-Modified`: Der Browser fragt bei jedem Öffnen kurz nach und lädt nur bei einer Änderung neu.
Eine neue App-Version ist damit sofort sichtbar, sobald die Datei ersetzt wurde (bei HACS: nach Update und Neustart). Fehlt die Datei: `404` mit Hinweistext.
Die App erreicht den Speicher dann über **relative** Adressen (`/api/aikido_tracker/…`) – keine Servereinstellung nötig.

## Speicherung

Ordner (Vorgabe `<config>/aikido_tracker/`, einstellbar mit `data_dir`; Teil der normalen HA-Sicherung). Der Ordner darf **nicht im Ordner des Bausteins** liegen, sonst startet der Baustein nicht: HACS ersetzt bei Aktualisierungen den ganzen Ordner des Bausteins.

```
persons/<id>.json                 Stand je Person (Name, Hash des Zugangscodes, rev, updatedAt, data)
history/<id>/<JJJJ-MM-TT>.json.gz Tagessicherung: der Stand VOR der ersten Änderung des Tages (UTC)
history/_deleted-<id>-<Zeit>/     Sicherungen gelöschter Personen (Tagessicherungen + final.json.gz)
```

* Schreiben ist atomar (Temporärdatei → `fsync` → umbenennen); Dateirechte `600`, Ordner `700`.
* Tagessicherungen: `history_days` Tage (Vorgabe 14, `0` = aus), komprimiert, ohne Zugangsdaten; ältere werden beim Start, bei jedem Schreiben der Person und alle 6 Stunden gelöscht.
* Eine unlesbare Datei einer Person wird **nie** gelöscht oder überschrieben; diese Person kann sich nicht anmelden, ihr Name bleibt belegt (zählt für `max_persons`), alle anderen laufen weiter.
* Beim Start prüft der Baustein alle Personen-Dateien; Sperrzähler (Fehlversuche) liegen nur im Arbeitsspeicher und beginnen nach einem Neustart bei null.
* Wiederherstellen von Hand: Home Assistant stoppen, in `persons/<id>.json` den Teil `"data"` durch den `data`-Teil der gewünschten Tagessicherung (`gunzip` der `.json.gz`) ersetzen, `"rev"` um 1 erhöhen, Home Assistant starten.

## Einrichtung in `configuration.yaml`

```yaml
aikido_tracker:
  invite_code: !secret aikido_invite_code   # ohne diesen Eintrag können keine Personen angelegt werden
  max_persons: 20                           # optional, 1–200
  history_days: 14                          # optional, 0–365
  data_dir: aikido_tracker                  # optional; relativ zum Konfigurationsordner oder absolut
  page_file: www/meine-seite.html           # optional; Standard ist die im Baustein mitgelieferte App
```

## Hinweise für die App (nächster Schritt)

* Daten vom Server sind **unvertrauenswürdig**: beim Abholen dieselbe Prüfung wie beim Import einer Sicherungsdatei verwenden (nichts ungeprüft übernehmen).
* Lokal bleibt die Arbeitskopie (schnell, offline); der Server ist der gemeinsame Stand. Die App merkt sich je Person die zuletzt abgeglichene `rev` und ob es ungesendete Änderungen gibt.
* Abgleich: `pull` (mit `sinceRev`) → bei neuerer `rev` zusammenführen → `push` mit `baseRev` = abgeholte `rev`; bei `409 conflict` erneut abholen und zusammenführen (Schleife mit Obergrenze).
* Zugangscode nur lokal auf dem Gerät speichern (wie die übrigen Daten); nie in Adressen oder Protokolle schreiben.
