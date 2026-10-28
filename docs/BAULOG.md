# Baulog – Server-Baustein „aikido_tracker“

Selbstdokumentierendes Protokoll der Entwicklung (neueste Version zuerst).

## ✅ Version 1.1.0 (27.10.2026)

Installation über HACS: Das Ganze ist jetzt ein fertig aufgebautes GitHub-Repository mit der App im Baustein.

### Entscheidungen

* **Die App steckt im Baustein** (`custom_components/aikido_tracker/app/aikido-kyu-tracker.html`) und wird unter `/aikido-tracker` ausgeliefert. HACS kann nur den Ordner des Bausteins installieren, nicht Dateien nach `/config/www` legen; so installiert und aktualisiert HACS Server und App in einem Stück, und beide passen immer zusammen. `page_file` bleibt als Übersteuerung (jetzt optional).
* **Datenordner darf nicht im Ordner des Bausteins liegen.** HACS ersetzt bei einer Aktualisierung den ganzen Ordner; Daten darin wären weg. Der Baustein startet dann nicht und sagt im Protokoll warum (`is_inside` löst Verknüpfungen auf und prüft vor dem Anlegen).
* **Nur öffentliche Repositories.** HACS liest keine privaten Repositories (HACS-Dokumentation). Folgen: Der Inhalt des Repositories ist öffentlich; es gehören keine Zugangsdaten, keine privaten Namen und keine Pfade der Entwicklungsumgebung hinein (Prüfung K7).
* **Regeln aus dem HACS-Quelltext statt aus dem Gedächtnis:** Pflichtschlüssel im Manifest (`codeowners`, `documentation`, `domain`, `issue_tracker`, `name`, `version`), `hacs.json` nur mit bekannten Schlüsseln, Symbol unter `custom_components/<domain>/brand/icon.png`, hassfest verlangt sortierte Manifest-Schlüssel. Keine Mindestversion von Home Assistant in `hacs.json`: getestet ist 2026.2.3 (die neueste, die hier installierbar war), eine Sperre könnte nur unnötig blockieren.
* **Release-Ablauf:** Tag `vX.Y.Z` löst den Workflow aus, der Tag und Manifest vergleicht, testet und das Release mit dem Text aus `CHANGELOG.md` und dem ZIP des Bausteins anlegt (HACS zeigt nur echte Releases als Versionen). Wird das Release im Browser angelegt (dabei entsteht der Tag), ergänzt der Workflow es, statt am schon vorhandenen Release zu scheitern.
* **Lizenz bewusst offen gelassen** (Entscheidung des Autors); die HACS-Prüfung `license` wird bis dahin ignoriert.
* **Symbol:** eigene Gestaltung (Enso-Kreis mit dem Zeichen 合 auf indigoblauer Kachel), keine fremde Vorlage.

### Neu im Repository

| Datei/Ordner | Aufgabe |
|---|---|
| `hacs.json`, `README.md`, `CHANGELOG.md` | HACS, Anwender-Anleitung, Änderungsprotokoll |
| `custom_components/aikido_tracker/app`, `brand` | App und Symbol im Baustein |
| `.github/workflows/validate.yml` | HACS-Prüfung, hassfest, Tests (bei jedem Hochladen und täglich) |
| `.github/workflows/release.yml` | Release bei Tag `v*` |
| `tools/build.py` | `sync-app`, `notes`, `check-tag`, `files`, `zip` (reproduzierbare ZIP-Dateien) |
| `tests/test_package.py` | Prüft Aufbau, Manifest, hacs.json, Versionen, Symbol, App, Workflows, Doku, Werkzeug |

### Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `tests/test_server.py` – Baustein ohne Home Assistant; neu die Gruppe W (App im Baustein, Auslieferung, Datenordner-Schutz) | **229 von 229** |
| `tests/test_package.py` – Aufbau des Repositories, K1–K10 (Dateiliste, Manifest, `hacs.json`, Versionen, Symbol, App, Workflows, Anleitungen, Geheimnisse, Werkzeug) | **86 von 86** |
| `tests/test_live.py` – echtes Home Assistant 2026.2.3 headless, **ohne Datei in `www`** (so wie nach einer Installation durch HACS) | **55 von 55** |
| `tests/mutationen.py` – 117 absichtlich eingebaute Fehler: 69 im Baustein, 44 im Repository (jeder muss die **gemeinte** Prüfung auslösen, nicht irgendeine), 4 in `__init__.py` gegen echtes Home Assistant | **117 von 117 erkannt, 0 überlebt** |
| Abnahme: ZIP gebaut, in einem leeren Ordner entpackt, dort alle drei Läufe wiederholt | **229 / 86 / 55, alles grün** |

Test-Methode wie bisher: erst Tests schreiben und rot sehen, dann bauen; Fehler gezielt einbauen und prüfen, dass die richtige Prüfung rot wird.

Von hier aus nicht prüfbar: die HACS-Prüfung und hassfest selbst (sie laufen auf GitHub im Workflow „Validate“) sowie Home Assistant jenseits der Version 2026.2.3 (die neueste, die hier installierbar war).

### Beim Bauen gefunden und behoben

* **Eine Gegenprobe war zu schwach:** Der eingebaute Fehler „Werkzeug übernimmt eine App ohne HTML-Prüfung“ wurde zunächst von einer *anderen* Prüfung erkannt, nicht von der gemeinten (Testeingabe zu schwach). Seitdem muss jede Repository-Mutation die dafür vorgesehene Prüfnummer auslösen; die Eingabe wurde verschärft.
* **Prüfung K7 schlug an der eigenen Gegenprobe an** (ein Test enthielt den Namen, den er verbieten soll): Die Zeichenfolge wird dort jetzt zusammengesetzt.
* **Release im Browser statt per Tag-Upload:** Beim Anlegen eines Releases im Browser entsteht der Tag zugleich mit dem Release; der Workflow hätte dann beim Anlegen „Release existiert bereits“ gemeldet und wäre rot geworden. Er ergänzt jetzt ein vorhandenes Release (Text, ZIP) und legt nur sonst eines an; Prüfung K8 und eine Gegenprobe dafür sind neu.
* Ein Fehler in einem eigenen Test (Anzahl der `..` im Pfad) korrigiert; der Baustein war richtig.

### Bekannte Grenzen (neu in 1.1.0)

* Die App speichert noch nur im Browser; der Abgleich mit dem Server kommt mit App v2.2.
* Nach der ersten Installation über HACS muss Home Assistant neu gestartet werden (der Baustein hat noch keine Einrichtung über die Oberfläche; die Einstellungen stehen in `configuration.yaml`).

## ✅ Version 1.0.0 (26.10.2026)

Erste Fassung: zentraler Speicher für mehrere Personen als Custom Integration für Home Assistant.

### Entscheidungen

* **Custom Integration statt Add-on.** Gleiche Adresse und gleiches Zertifikat wie die Seite (kein zweiter Port, kein CORS, kein Mischinhalt), läuft auf jeder Home-Assistant-Installationsart, braucht keinen Docker-Bau, ist in der normalen Sicherung enthalten, besteht aus wenigen Dateien. Die Logik (`identity.py`, `store.py`, `api.py`, `limits.py`, `page.py`) kennt Home Assistant nicht und ließe sich später in ein Add-on verpacken.
* **Name + Zugangscode statt Home-Assistant-Benutzer.** Die Mitglieder brauchen kein Konto auf dem Home Assistant. Der Code wird nur als scrypt-Hash gespeichert.
* **Optimistische Versionsnummer (`rev`).** Der Server zählt hoch und meldet `409 conflict`, statt unbemerkt zu überschreiben; die Zusammenführung macht die App.
* **Eigene Auslieferung der Seite.** Praxistest: Home Assistant liefert `www`-Dateien unter `/local` mit `max-age=2678400` (31 Tage) aus – neue App-Versionen würden am Handy bis zu einem Monat nicht erscheinen. Darum liefert der Baustein die Datei selbst unter `/aikido-tracker` mit `no-cache` + ETag aus.

### Aufbau

| Datei | Aufgabe |
|---|---|
| `const.py` | Grenzen, Standardwerte |
| `identity.py` | Namen, Kennungen, Zugangscodes, scrypt-Hash |
| `store.py` | Speicherung (Datei je Person, atomar, Tagessicherungen, Löschen mit Sicherung, unlesbare Dateien bleiben unberührt) |
| `limits.py` | Zähler in gleitenden Zeitfenstern |
| `api.py` | HTTP-Aufrufe, Sperren, Fehlerantworten |
| `page.py` | Auslieferung der App-Seite |
| `__init__.py`, `manifest.json` | Anbindung an Home Assistant (einzige Datei mit Home-Assistant-Code) |

### Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `tests/test_server.py` – Namen/Codes (L), Speicherung (P), Schnittstelle (A), Sperren (R), Seite (S), ohne Home Assistant | **211 von 211** |
| `tests/test_live.py` – echtes Home Assistant 2026.2.3 headless: Schnittstelle über echtes HTTP, Neustart, Dateirechte, Protokolle ohne Geheimnisse, Zwischenspeicher-Befund, Seite | **41 von 41** |
| `tests/mutationen.py` – 60 absichtlich eingebaute Fehler (Namensregeln, Grenzen, Sperren, Sicherungen, Kopfzeilen …) | **60 von 60 erkannt** |

Test-Methode wie bei der App: erst Tests schreiben, dann bauen; Fehler gezielt einbauen und prüfen, dass die Tests rot werden; unabhängige Rechnung der Erwartungswerte.

### Beim Bauen gefunden und behoben

* **Sperre umgehbar:** Wer die Kopfzeilen sofort, den Inhalt aber verzögert schickt, ließ 40 gleichzeitige Anfragen die erste Sperrprüfung passieren (statt 10 wurden 30 geprüft). Jetzt wird Prüfen und Verbuchen in einem Zug gemacht (`_reserve_attempt`), der Test dafür arbeitet mit rohen Verbindungen.
* **Erfolg zählt nicht als Fehlversuch:** Der Versuch wird vor dem Rechnen verbucht (gegen gleichzeitiges Raten) und bei Erfolg wieder ausgebucht.
* Zwei Fehler in den eigenen Tests korrigiert (Wartezeit der Sperre, Grenze „höchstens 120“); sechs Lücken in den Tests durch die Gegenprobe gefunden und geschlossen (kaputte Angaben beim Hash mit *richtigem* Code prüfen, Größengrenze auf das Byte, Körpergrenze auch für Müll, sofortige Ablehnung angekündigter Riesen-Anfragen, gleichzeitiges Anlegen desselben Namens, Erfolge dürfen nicht sperren).
* Home Assistant braucht zum normalen Start die Oberflächen-Komponente (`home-assistant-frontend`), sonst startet es im Notfallmodus – nur für die Testinstanz relevant.

### Bekannte Grenzen

* Die Daten liegen unverschlüsselt in Dateien (Schutz = Zugriffsrechte auf dem Home Assistant).
* Wiederherstellen aus einer Tagessicherung geht nur von Hand (Beschreibung in `INSTALLATION.md`); ein kleines Werkzeug dafür wäre ein möglicher nächster Schritt.
* Gesperrt wird nach Adresse und Person; hinter einem Proxy ohne `use_x_forwarded_for` sähe der Baustein nur die Proxy-Adresse.
* Safari/iPhone wurde nicht getestet (Server-Seite braucht das nicht; die App-Seite folgt im nächsten Schritt).

### Nächste Schritte

1. App: Personen/Profile, Anmeldung, Abgleich (`pull`/`push`, Zusammenführen, Konflikte, Löschmarken).
2. Danach die übrigen App-Funktionen (Prüfungs-Chronik, Trainingseinheit mit Dauer, .ics-Erinnerungen, Wochenziel).

## Tests ausführen

```
# alles aus dem Hauptordner des Repositories:
# Baustein ohne Home Assistant (Python 3.11+ mit aiohttp und pyyaml):
python3 tests/test_server.py [L P A R S W]
# Aufbau des Repositories (HACS-Regeln, Versionen, Werkzeug, Geheimnisse):
python3 tests/test_package.py
# Gegenprobe (baut Fehler in Kopien ein; AIKIDO_NO_LIVE=1 lässt die Läufe mit echtem Home Assistant aus):
python3 tests/mutationen.py [Teil des Namens]
# gegen echtes Home Assistant (venv mit homeassistant, home-assistant-frontend und aiohttp; Näheres im Kopf von tests/test_live.py):
AIKIDO_HASS=/pfad/zu/venv/bin/hass python3 tests/test_live.py
```
