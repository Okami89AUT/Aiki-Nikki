# Veröffentlichen auf GitHub und Installieren über HACS

HACS installiert Bausteine aus GitHub-Repositories. Dieses Repository ist dafür fertig aufgebaut (`custom_components/aikido_tracker`, `hacs.json`, Symbol, README, Workflows). Hier steht, was einmalig auf GitHub zu tun ist und wie später neue Versionen erscheinen.

## Einmalig: Repository für HACS freigeben

Das Repository `Okami89AUT/Aiki-Nikki` ist angelegt, der Inhalt dieses Pakets liegt im Standardzweig. Damit HACS es installieren kann, bleiben drei Handgriffe auf GitHub:

1. **Öffentlich machen.** HACS kann keine privaten Repositories lesen, und die HACS-Prüfung auf GitHub verweigert sie ebenfalls. Im Repository **Settings**, ganz unten **Danger Zone**, **Change visibility**, **Make public**. Danach kann jeder den Inhalt und den Verlauf der Änderungen lesen. Zugangsdaten und private Angaben sind nicht enthalten (Prüfung K7 in `tests/test_package.py`).
2. **Beschreibung und Themen eintragen** (Zahnrad neben „About“ auf der Startseite des Repositories), falls noch nicht geschehen:
   * **Beschreibung:** „Aikido Kyu Tracker mit zentralem Speicher für Home Assistant“. HACS zeigt sie an und prüft, dass es sie gibt.
   * **Themen:** `hacs`, `home-assistant`, `home-assistant-custom-component`, `aikido`. HACS prüft, dass es Themen gibt.
   * **Issues** eingeschaltet lassen (HACS prüft auch das).
3. **Release anlegen** (siehe unten): HACS zeigt nur echte Releases als Versionen an, ein Tag allein genügt nicht.

Andere Datei hochladen oder ändern geht im Browser (**Add file**, **Upload files**; der Ordner `.github` mit den Workflows gehört dazu) oder mit Git (`git add .`, `git commit`, `git push`). Soll das Paket in ein Repository mit anderem Namen umziehen, dann die Adresse überall ersetzen (`manifest.json`: `documentation`, `issue_tracker`, `codeowners`; `README.md`; `docs/INSTALLATION.md`). `tests/test_package.py` (K2, K9) prüft, dass alles übereinstimmt.

## Release: neue Version veröffentlichen

1. Version erhöhen: `custom_components/aikido_tracker/manifest.json` (`version`) und `const.py` (`VERSION`) auf dieselbe Nummer setzen, einen Eintrag oben in `CHANGELOG.md` und `docs/BAULOG.md` schreiben, im Änderungsprotokoll die App-Version nennen („App v…“).
2. Neue App-Version übernehmen: `python3 tools/build.py sync-app <aikido-kyu-tracker.html>`.
3. Prüfen: `python3 tests/test_server.py` und `python3 tests/test_package.py` müssen grün sein.
4. Hochladen (Commit), dann das Release anlegen, z. B. für `v1.1.0`. Im Browser: **Releases**, **Draft a new release**, bei **Choose a tag** `v1.1.0` eingeben und **Create new tag on publish** wählen, als Titel „Aikido Tracker 1.1.0“, **Publish release**. Mit Git geht es auch: `git tag v1.1.0 && git push origin v1.1.0`. Der Workflow „Release“ startet mit dem neuen Tag, vergleicht ihn mit der Version im Manifest, führt die Tests aus und ergänzt das Release um den Text aus `CHANGELOG.md` und die Datei `aikido_tracker.zip` (gibt es das Release noch nicht, legt er es an). Wird er rot, steht der Grund im Reiter **Actions**; für HACS genügt das Release selbst.
5. In Home Assistant zeigt HACS das Update an.

## Prüfungen auf GitHub

Der Workflow „Validate“ läuft bei jedem Hochladen und täglich: die offizielle HACS-Prüfung, hassfest (die Prüfung von Home Assistant für Bausteine) und die Tests dieses Repositories. Schlägt etwas fehl, steht der Grund im Reiter **Actions**. Die HACS-Prüfung ignoriert nur `license`, solange keine Lizenz gewählt ist; wird später eine Lizenz hinzugefügt, die Zeile `ignore: license` in `.github/workflows/validate.yml` entfernen.

## Installation durch Anwender

Siehe [README](../README.md) und [INSTALLATION.md](INSTALLATION.md): HACS, Benutzerdefinierte Repositories, Adresse des Repositories, Typ Integration.
