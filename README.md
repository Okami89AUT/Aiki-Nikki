# Aikido Tracker für Home Assistant

Der **Aikido Kyu Tracker** (Prüfungsprogramm 6. bis 1. Kyu und Trainingstagebuch, läuft im Browser, auch am iPhone) zusammen mit einem **zentralen Speicher auf deinem Home Assistant**. Jede Person legt sich mit Name und Zugangscode einen eigenen Datenstand an und holt ihn von jedem Gerät ab, im Heimnetz und über das Internet (zum Beispiel mit DuckDNS).

[![Dieses Repository in meinem HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Okami89AUT&repository=Aiki-Nikki&category=integration)

> Inoffizielles Hilfsmittel für das eigene Training. Das Prüfungsprogramm in der App ist nach bestem Wissen erfasst, aber nicht aus einer Quelle abgeglichen: bitte vom Trainer gegenlesen lassen.

## Was drin ist

* **Server-Baustein** („Custom Integration“) für Home Assistant: eine Datei je Person, Anmeldung mit Name und Zugangscode, Anlegen neuer Personen nur mit Einladungscode, Konflikterkennung statt stilles Überschreiben, Tagessicherungen, Sperren gegen Raten von Zugangscodes. Er läuft innerhalb von Home Assistant: kein Add-on, kein zweiter Port, keine zusätzliche Freigabe am Router.
* **Die App** (`aikido-kyu-tracker.html`) steckt im Baustein und wird unter `/aikido-tracker` ausgeliefert, mit Zwischenspeicher-Regeln, die neue Fassungen sofort sichtbar machen. HACS installiert und aktualisiert beides gemeinsam.

**Stand:** Der Server-Baustein ist fertig und getestet. Die App speichert vorerst noch im Browser; Anmelden und Abgleich mit dem Server folgen im nächsten Schritt (siehe [Änderungsprotokoll](CHANGELOG.md)).

## Installation

1. In Home Assistant **HACS** öffnen, oben rechts die drei Punkte, **Benutzerdefinierte Repositories**. Als Adresse `https://github.com/Okami89AUT/Aiki-Nikki` eintragen, als Typ **Integration** wählen und hinzufügen. (Oder oben auf die Schaltfläche klicken.)
2. **Aikido Tracker** in HACS suchen und **herunterladen**.
3. Einladungscode festlegen: In `/config/secrets.yaml` eine Zeile ergänzen (6 bis 64 Zeichen; nur an Personen weitergeben, die sich einen Zugang anlegen sollen):

   ```yaml
   aikido_invite_code: mein-einladungscode-2026
   ```

4. Baustein einschalten: In `/config/configuration.yaml` ergänzen:

   ```yaml
   aikido_tracker:
     invite_code: !secret aikido_invite_code
   ```

5. Home Assistant neu starten (Einstellungen, System, Neu starten).

Ausführliche Anleitung, auch ohne HACS: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Einrichtung

* Die App ist danach unter `http://homeassistant.local:8123/aikido-tracker` erreichbar (bzw. deine Adresse). Öffne sie **immer über diese Adresse**, nicht über `/local/…`: Home Assistant lässt Dateien aus `www` bis zu 31 Tage zwischenspeichern, neue App-Versionen würden dann am Handy lange nicht erscheinen.
* Test des Servers: `…/api/aikido_tracker/ping` zeigt `{"ok": true, …}`.
* Aus dem Internet nur über **https** (zum Beispiel `https://deinname.duckdns.org/aikido-tracker`). Name und Zugangscode wandern in jeder Anfrage mit; über http wären sie mitlesbar. Hinter einem Proxy braucht Home Assistant `use_x_forwarded_for` und `trusted_proxies` (siehe [docs/INSTALLATION.md](docs/INSTALLATION.md)).
* Alle Einstellungen (`max_persons`, `history_days`, `data_dir`, `page_file`) stehen in der Anleitung. Die Schnittstelle für Entwickler ist in [docs/SCHNITTSTELLE.md](docs/SCHNITTSTELLE.md) beschrieben.

## Aktualisieren

In HACS erscheint bei einer neuen Version ein Update. Herunterladen, Home Assistant neu starten, die App einmal neu laden. Die Daten liegen getrennt in `/config/aikido_tracker` und bleiben unberührt. Der Baustein startet bewusst nicht, wenn `data_dir` im Ordner des Bausteins läge, weil HACS diesen Ordner bei Aktualisierungen ersetzt.

## Sicherheit

* Zugang nur mit **Name und Zugangscode** (6 bis 64 Zeichen, empfohlen ab 8). Der Code wird nur als scrypt-Hash gespeichert; „falscher Name“ und „falscher Code“ sind von außen nicht unterscheidbar.
* Nach 10 Fehlversuchen je Adresse oder 30 je Person in 15 Minuten wird gesperrt; höchstens 120 Anfragen je Minute und Adresse. Wer nur einen Namen kennt, kann eine Person durch absichtliche Fehlversuche für bis zu 15 Minuten aussperren, hineinkommen kann er nicht.
* Die Daten liegen **unverschlüsselt** in Dateien auf deinem Home Assistant. Wer dort Administrator ist oder deine Sicherungen bekommt, kann sie lesen. Name und Trainingsnotizen von Mitgliedern sind personenbezogene Daten: sag ihnen, wo die Daten liegen und wer Zugriff hat.
* Home Assistant nur über https ins Internet stellen; den Einladungscode nicht herumreichen.

## Für Entwickler

Tests (ohne Home Assistant: `pip install aiohttp pyyaml`):

```
python tests/test_server.py     # Server-Baustein: Namen, Speicherung, Schnittstelle, Sperren, App-Seite, Pfade
python tests/test_package.py    # Repository: Aufbau für HACS, Manifest, Versionen, Workflows, Werkzeug
```

`tests/test_live.py` startet ein echtes, lokal installiertes Home Assistant (Pfad zu `hass` in `AIKIDO_HASS`) und prüft die Schnittstelle über echtes HTTP samt Neustart. `tests/mutationen.py` baut absichtlich Fehler ein und prüft, dass die Tests jeden bemerken. Das Bauwerkzeug `tools/build.py` übernimmt neue App-Versionen und baut die ZIP-Dateien. Verlauf und Entscheidungen: [docs/BAULOG.md](docs/BAULOG.md). Veröffentlichen einer neuen Version: [docs/VEROEFFENTLICHEN.md](docs/VEROEFFENTLICHEN.md).

Getestet mit Home Assistant 2026.2.3.

## Lizenz

Noch nicht festgelegt.
