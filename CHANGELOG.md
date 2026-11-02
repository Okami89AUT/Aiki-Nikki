# Änderungsprotokoll

Alle nennenswerten Änderungen am Baustein „Aikido Tracker“. Jede Fassung bringt die dazu passende App mit
(„App v…“ = Version des Aikido Kyu Trackers, die im Baustein steckt).

## [1.5.0] – 2026-11-02

Trainingsdauer, Kalender-Eintrag und Wochenziel (App v2.9).

### Geändert
- Mitgelieferte App von v2.6 auf v2.9:
  - **Trainingsdauer** (v2.7): beim Erfassen optional „Dauer in Minuten“; die Dauer gehört zum Trainingstag, nicht zur einzelnen Technik. Angezeigt werden die Stunden dieser Woche und die Stunden seit der letzten Prüfung.
  - **Prüfungstermin als Kalender-Eintrag** (v2.8): „Termin in den Kalender“ lädt eine .ics-Datei mit zwei Erinnerungen (eine Woche und einen Tag vorher).
  - **Wochenziel** (v2.9): „3× pro Woche“ setzen, der Stand der laufenden Woche steht in der Karte „Trainings-Rhythmus“.
  - Kleinigkeiten: die Kennzahlen im Kopf sind eine Zeile statt drei Kacheln, gezählt werden überall Trainingstage statt Einträge.
- Am Baustein selbst ändert sich wieder nichts: Er speichert den Datenstand einer Person als Ganzes – die Schnittstelle bleibt unverändert (`api: 1`).

### Hinweis
- Der abgeglichene Datenstand hat jetzt `schemaVersion: 5` (neue Bereiche `sessionMinutes` und `weeklyGoal`). Geräte mit einer älteren App gleichen nicht mehr ab, bis sie ebenfalls auf v2.9 sind – **alle Geräte aktualisieren**. Der auf dem Server gespeicherte Stand bleibt dabei unangetastet.

## [1.4.0] – 2026-11-01

Prüfungs-Chronik, aufgeräumte Übersicht und MIT-Lizenz (App v2.6).

### Neu
- **MIT-Lizenz** für das ganze Repository (vorher gab es keine Lizenzdatei, damit galt „alle Rechte vorbehalten“). Damit darf jede und jeder die Software nutzen, ändern und weitergeben; Gewährleistung und Haftung sind im Lizenztext ausgeschlossen.

### Geändert
- Mitgelieferte App von v2.4 auf v2.6:
  - **Prüfungs-Chronik** (v2.5): abgelegte Prüfungen mit Grad, Datum, Prüfer und Notiz — je Person gespeichert, im Backup, im Abgleich, und verknüpft mit dem Prüfungsziel („Aktuelles Kyu seit“ kommt aus der letzten Prüfung, der nächste Grad wird als Ziel vorgeschlagen).
  - **Aufgeräumte Übersicht** (v2.6): Trainings-Rhythmus als acht Wochenbalken statt 98-Kästchen-Heatmap, Bereitschaft und Prüfungsziel in einer Karte, „Braucht Aufmerksamkeit“ auf drei Techniken mit „mehr anzeigen“, Daten-Sicherung und „Über diese App“ in einem eingeklappten Bereich „Verwaltung“. Die Übersicht ist dadurch auf dem Handy von 2042 auf 1512 px geschrumpft.
  - Gezählt werden jetzt **Trainingstage** statt Einträge (drei Techniken an einem Abend sind ein Training); die Zahl der Techniken steht klein darunter.
- Am Baustein selbst ändert sich nichts: Er speichert den Datenstand einer Person als Ganzes, ohne die Bereiche zu kennen – die Schnittstelle bleibt unverändert (`api: 1`).

### Hinweis
- Der abgeglichene Datenstand hat jetzt `schemaVersion: 3` (vierter Bereich `exams`). Geräte mit App v2.4 oder älter erkennen diesen Stand als „neuer als ich“ und gleichen nicht mehr ab, bis sie ebenfalls auf v2.5 sind. Der auf dem Server gespeicherte Stand bleibt dabei unangetastet.

## [1.3.0] – 2026-10-31

Der Server-Zugang bestimmt den Namen der Person (App v2.4).

### Geändert
- Mitgelieferte App von v2.3 auf v2.4: Ist eine Person in der App mit einem Server-Zugang verbunden, heißt sie genauso wie dort – auf jedem Gerät gleich. Solange sie verbunden ist, lässt sie sich in der App nicht umbenennen; nach dem Trennen wieder schon.
- Am Baustein selbst ändert sich nichts (Schnittstelle unverändert, `api: 1`).

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
