# Änderungsprotokoll

Alle nennenswerten Änderungen am Baustein „Aikido Tracker“. Jede Fassung bringt die dazu passende App mit
(„App v…“ = Version des Aikido Kyu Trackers, die im Baustein steckt).

## [1.2.0] – 2026-10-31

Abgleich mehrerer Geräte aus der App heraus (App v2.3).

### Neu
- Die mitgelieferte App kann sich jetzt selbst mit diesem Baustein abgleichen: Anmelden oder Anlegen je Person (Karte „Abgleich“ in der Übersicht), Zusammenführen statt Überschreiben, Konflikte ohne Datenverlust, Arbeiten ohne Netz und automatischer Abgleich im Hintergrund.
- Die Schnittstelle des Bausteins ist dafür unverändert geblieben (`docs/SCHNITTSTELLE.md`, `api: 1`): ältere App-Fassungen laufen weiter.

### Geändert
- Mitgelieferte App von v2.1 auf v2.3 (Version 2.2 brachte mehrere Personen auf einem Gerät, 2.3 den Abgleich).

## [1.1.0] – 2026-10-27

Installation und Aktualisierung über HACS; die App wird im Baustein mitgeliefert (App v2.1).

### Neu
- Installation und Aktualisierung über HACS als benutzerdefiniertes Repository (Anleitung im README).
- Die App liegt im Baustein (`app/aikido-kyu-tracker.html`) und wird unter `/aikido-tracker` ausgeliefert. Das Kopieren nach `/config/www` entfällt; Server und App sind immer aufeinander abgestimmt.
- Symbol für Home Assistant und HACS (`brand/icon.png`, `brand/icon@2x.png`).
- Schutz des Datenordners: Liegt `data_dir` im Ordner des Bausteins, startet der Baustein nicht und nennt den Grund im Protokoll. HACS ersetzt bei einer Aktualisierung den ganzen Ordner des Bausteins, Daten darin wären weg.
- Prüfung des gesamten Repositories (`tests/test_package.py`), Bauwerkzeug (`tools/build.py`) und GitHub-Workflows (HACS-Prüfung, hassfest, Tests, Release).

### Geändert
- `page_file` ist jetzt optional. Ohne Angabe wird die mitgelieferte App ausgeliefert. Wer die App bisher selbst in `/config/www` abgelegt hatte, entfernt diese Datei (und die Einstellung) oder trägt `page_file: www/aikido-kyu-tracker.html` ein.
- Manifest nach den Regeln von hassfest und HACS: Schlüssel sortiert, `documentation`, `issue_tracker` und `codeowners` ergänzt.

## [1.0.0] – 2026-10-26

Erste Fassung (App v2.1): zentraler Speicher für mehrere Personen als Custom Integration für Home Assistant.

- Eine Datei je Person, Anmeldung mit Name und Zugangscode (nur als scrypt-Hash gespeichert), Anlegen neuer Personen mit Einladungscode.
- Versionsnummer `rev` gegen unbemerktes Überschreiben (Konflikt statt Datenverlust), Tagessicherungen, Löschen mit Sicherung.
- Sperren gegen Raten von Zugangscodes, Größen- und Zeitgrenzen für Anfragen.
- Auslieferung der App-Seite unter `/aikido-tracker` mit Zwischenspeicher-Regeln, die neue Fassungen sofort sichtbar machen.
