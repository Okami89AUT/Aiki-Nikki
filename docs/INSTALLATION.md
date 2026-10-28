# Aikido Tracker – Installation und Betrieb

Getestet mit Home Assistant 2026.2.3. Die Einrichtung dauert etwa 10 Minuten.

## Was der Baustein macht

* Speichert die Daten des „Aikido Kyu Tracker“ **zentral auf deinem Home Assistant**: eine Datei je Person, abrufbar mit **Name + Zugangscode** von jedem Gerät, im Heimnetz und über DuckDNS.
* Läuft **innerhalb von Home Assistant** (eine „Custom Integration“): kein Add-on, kein zweiter Port, keine zusätzliche Freigabe am Router, in der normalen Home-Assistant-Sicherung enthalten.
* Bringt die **App selbst mit** und liefert sie unter `/aikido-tracker` aus, so dass eine neue App-Version sofort erscheint (Home Assistant selbst würde Dateien aus `www` 31 Tage zwischenspeichern lassen).

## Installation mit HACS (empfohlen)

**1. Repository hinzufügen.** In HACS oben rechts die drei Punkte, **Benutzerdefinierte Repositories**. Adresse `https://github.com/Okami89AUT/Aiki-Nikki`, Typ **Integration**, hinzufügen. (Alternativ im README auf die Schaltfläche „Dieses Repository in meinem HACS öffnen“ klicken.)

**2. Herunterladen.** „Aikido Tracker“ in HACS suchen, **Herunterladen**. HACS legt den Ordner `/config/custom_components/aikido_tracker` an, samt App.

**3. Einladungscode festlegen.** In `/config/secrets.yaml` eine Zeile ergänzen:

```yaml
aikido_invite_code: mein-einladungscode-2026
```

Das ist das „Passwort zum Anlegen neuer Personen“ (6–64 Zeichen). Nur an Mitglieder weitergeben, die sich einen Zugang anlegen sollen.

**4. Baustein einschalten.** In `/config/configuration.yaml` ergänzen:

```yaml
aikido_tracker:
  invite_code: !secret aikido_invite_code
```

**5. Neu starten.** Entwicklerwerkzeuge → YAML → „Konfiguration prüfen“, dann Home Assistant neu starten (Einstellungen → System → Neu starten).

**6. Testen.**

* `http://homeassistant.local:8123/api/aikido_tracker/ping` (bzw. deine Adresse) zeigt `{"ok":true, … "registration":true}`.
* `http://homeassistant.local:8123/aikido-tracker` zeigt die App.
* Im Protokoll (Einstellungen → System → Protokolle, Suche „aikido“) steht „Aikido Tracker bereit: 0 Person(en)“. Die Warnung „custom integration … has not been tested by Home Assistant“ ist bei jeder eigenen Integration normal.

## Manuelle Installation (ohne HACS)

1. Auf der Seite des Repositories unter **Releases** die Datei `aikido_tracker.zip` der neuesten Version laden.
2. Den Inhalt in den Ordner `/config/custom_components/aikido_tracker/` entpacken (Samba-Freigabe, „File editor“ oder „Studio Code Server“). Danach muss es die Datei `/config/custom_components/aikido_tracker/manifest.json` geben.
3. Weiter wie oben ab Schritt 3. Aktualisieren: Ordner ersetzen, neu starten.

## Zugriff über das Internet (DuckDNS)

* Öffne die App über **https**: `https://DEINNAME.duckdns.org/aikido-tracker` (mit Port, falls dein Home Assistant einen eigenen nutzt). **Nie über http aus dem Internet**: Name und Zugangscode wandern in jeder Anfrage mit und wären sonst mitlesbar.
* Läuft Home Assistant hinter einem Proxy (z. B. Add-on „NGINX Home Assistant SSL proxy“), braucht die Home-Assistant-Konfiguration – wie für Home Assistant selbst – diesen Eintrag. Ohne ihn lehnt Home Assistant Proxy-Anfragen ab, bzw. alle Besucher teilen sich die Sperren:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24     # Adresse deines Proxys
```

* Am Router ist nichts Zusätzliches freizugeben: Der Baustein nutzt dieselbe Adresse und denselben Port wie Home Assistant.

## Aktualisieren

* **Über HACS:** Bei einer neuen Version erscheint in HACS ein Update. Herunterladen, Home Assistant neu starten. Die App wird mitgeliefert; am Handy die Seite einmal neu laden. Die Daten bleiben unberührt (sie liegen getrennt in `/config/aikido_tracker`).
* **Eigene App-Datei statt der mitgelieferten:** Mit `page_file` (siehe unten) lässt sich eine andere Datei einstellen, z. B. zum Ausprobieren einer eigenen Fassung. Wer die App früher selbst nach `www` gelegt hatte, kann diese Datei entfernen: Ohne `page_file` wird die mitgelieferte App ausgeliefert.

## Einstellungen (alle außer `invite_code` optional)

```yaml
aikido_tracker:
  invite_code: !secret aikido_invite_code   # ohne ihn kann niemand neu angelegt werden (Vorhandene bleiben nutzbar)
  max_persons: 20                           # höchstens so viele Personen (1–200)
  history_days: 14                          # Tagessicherungen so lange aufbewahren (0 = keine, höchstens 365)
  data_dir: aikido_tracker                  # Speicherort, relativ zu /config oder absolut; nicht im Ordner des Bausteins
  page_file: www/meine-seite.html           # andere App-Datei als die mitgelieferte (relativ zu /config oder absolut)
```

`data_dir` darf nicht im Ordner des Bausteins (`custom_components/aikido_tracker`) liegen: HACS ersetzt diesen Ordner bei jeder Aktualisierung, Daten darin wären danach weg. Der Baustein startet in diesem Fall bewusst nicht und nennt den Grund im Protokoll.

## Wo liegen die Daten, wie sichere ich sie?

```
/config/aikido_tracker/persons/<name>.json     aktueller Stand je Person (der Zugangscode nur als Hash)
/config/aikido_tracker/history/<name>/<Datum>.json.gz   Tagessicherung: Stand vor der ersten Änderung des Tages
/config/aikido_tracker/history/_deleted-…/     Sicherung gelöschter Personen (auch sie verfällt nach history_days)
```

* Der Ordner gehört zu `/config` und ist damit in den **normalen Home-Assistant-Sicherungen** enthalten.
* **Wiederherstellen von Hand:** Home Assistant stoppen → Tagessicherung entpacken (`gunzip`) → in `persons/<name>.json` den Teil `"data"` durch den `data`-Teil der Sicherung ersetzen und `"rev"` um 1 erhöhen → Home Assistant starten.
* Jede Datei wird atomar geschrieben (erst Temporärdatei, dann umbenannt); eine **unlesbare Datei wird nie überschrieben oder gelöscht**: Diese Person kann sich dann nicht anmelden, alle anderen laufen weiter, und der Grund steht im Protokoll.

## Sicherheit und Datenschutz – was du wissen solltest

* Zugang nur mit **Name + Zugangscode** (6–64 Zeichen). Der Code wird nur als scrypt-Hash gespeichert; „falscher Name“ und „falscher Code“ sind von außen nicht unterscheidbar. Empfehlung an die Mitglieder: Codes mit **mindestens 8 Zeichen**.
* **Sperren:** 10 Fehlversuche je Adresse oder 30 je Person in 15 Minuten sperren für den Rest dieser Zeit; höchstens 120 Anfragen je Minute und Adresse. Nebenwirkung: Wer nur deinen Namen kennt, kann dich durch absichtliche Fehlversuche für bis zu 15 Minuten aussperren – hineinkommen kann er so nicht.
* Der **Einladungscode** ist das Tor zum Anlegen neuer Personen (bis `max_persons`). Geht er verloren/herum: in `secrets.yaml` ändern und neu starten – vorhandene Personen bleiben.
* Die Daten liegen **unverschlüsselt** in Dateien: Wer Administrator auf deinem Home Assistant ist oder deine Sicherungen bekommt, kann sie lesen. Name und Trainingsnotizen von Vereinsmitgliedern sind personenbezogene Daten – sag den Mitgliedern, wo ihre Daten liegen und wer Zugriff hat.
* Beim Löschen einer Person (in der App) bleiben ihre Tagessicherungen noch `history_days` Tage erhalten; danach ist sie vollständig weg.
* Die App lädt ihre Schriften derzeit von einem externen Schriftendienst. Wer die App öffentlich anbietet, sollte das bedenken (Datenschutz); die Schriften lassen sich später mitliefern.

## Wenn etwas nicht klappt

| Beobachtung | Ursache / Abhilfe |
|---|---|
| `ping` liefert 404 | Der Baustein ist nicht geladen: Ordnerpfad prüfen (`/config/custom_components/aikido_tracker/manifest.json`), Einrückung in `configuration.yaml`, Protokoll nach „aikido“ durchsuchen, neu starten. |
| Im Protokoll: „Datenordner … liegt im Ordner des Bausteins“ | `data_dir` ändern (oder entfernen: Standard ist `/config/aikido_tracker`), neu starten. |
| `/aikido-tracker` zeigt „Die App-Seite fehlt auf dem Server“ | Baustein in HACS neu herunterladen (Ordner `app` fehlt) – oder `page_file` zeigt auf eine Datei, die es nicht gibt. |
| Anmelden: 429 „Zu viele Fehlversuche“ | Sperre (siehe oben): die Meldung nennt die Wartezeit. |
| Anfragen aus dem Internet scheitern mit 400 | Proxy-Einstellung `use_x_forwarded_for` / `trusted_proxies` fehlt (siehe oben). |
| Registrieren: 403 | Falscher Einladungscode – oder `invite_code` ist nicht eingestellt. |
| Mehr Einzelheiten nötig | In `configuration.yaml`: `logger:` → `logs:` → `custom_components.aikido_tracker: debug`. |

Passwörter, Zugangscodes und Einladungscodes erscheinen **nie** im Protokoll; Fehlversuche stehen mit Adresse und Kennung darin.

## Für Entwickler: Prüfungen

Im Ordner `tests/` liegen die Tests: Server-Baustein ohne Home Assistant (`tests/test_server.py`), Repository-Prüfung (`tests/test_package.py`), Prüfung gegen ein echtes, headless laufendes Home Assistant inklusive Neustart (`tests/test_live.py`) und eine „Gegenprobe“, die absichtlich eingebaute Fehler einspielt und prüft, dass die Tests jeden bemerken (`tests/mutationen.py`). Einzelheiten und Ergebnisse: [BAULOG.md](BAULOG.md).
