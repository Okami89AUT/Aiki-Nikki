# Prüfstand für die App (Browser)

Die Prüfreihen laufen gegen eine Kopie der App im Browser (Playwright + Chromium) und gegen einen
nachgebauten Server (`lib.js`), der sich jeden Aufruf merkt. Die Uhr der Seite steht fest und lässt
sich weiterstellen.

    npm i playwright        # einmalig, falls nicht vorhanden
    cp ../custom_components/aikido_tracker/app/aikido-kyu-tracker.html app.html
    node own/e1-loeschen.js         # Zugang löschen: Knopf, Fenster, Rechenaufgabe
    node own/e2-band.js             # Hinweisband, verbleibende Zeit, Abbruch
    node mut-app.js                 # Gegenprobe: eingebaute Fehler, jeder muss auffallen

`APP=/pfad/zu/app.html` prüft eine andere Fassung. `app.html` selbst gehört nicht ins Repository –
geprüft wird immer die Datei aus dem Baustein.

**Stand 20.11.2026:** Die Prüfreihen der Fassungen bis 2.9 sind verloren gegangen (der Arbeitsbereich
einer Sitzung wurde ersetzt). Was hier liegt, deckt nur „Zugang löschen" ab; eine vollständige
Regression über die ganze App gibt es derzeit nicht.
