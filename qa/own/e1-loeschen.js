'use strict';
/*
 * Zugang löschen, Teil 1 (App 2.10): Knopf, Fenster, Rechenaufgabe, Aufruf an den Server.
 *
 * Erwartet (Vertrag zwischen Test und App):
 *   Knopf  [data-action="sync-delete"] in #sync-card — nur wenn diese Person mit dem Server verbunden ist.
 *   Fenster #sync-delete-overlay mit:
 *     #sync-delete-task     Text der Rechenaufgabe (zwei Zahlen, Ergebnis eindeutig)
 *     #sync-delete-answer   Eingabefeld für das Ergebnis
 *     #sync-delete-error    Fehlermeldung (hidden, wenn keine)
 *     [data-action="sync-delete-submit"] / [data-action="sync-delete-close"]
 *   newDeleteChallenge() -> { a, b, text, answer }
 *   syncState.deleteAt   = ISO-Zeitpunkt der vorgemerkten Löschung oder null
 *
 *   node own/e1-loeschen.js   (APP=… für eine andere Fassung)
 */
const lib = require('../lib');
const APP = process.env.APP || lib.APP;
const NOW = '2026-11-20T09:00:00Z';
const VERBUNDEN = { 'aikido-sync': { v: 1, name: 'Daniel', code: 'geheim123', rev: null, base: null, at: null, rejected: false } };

let fehler = 0, n = 0;
const kanon = (v) => (Array.isArray(v) ? v.map(kanon) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, kanon(v[k])])) : v);
const J = (v) => JSON.stringify(kanon(v));
function check(name, ist, soll) {
  n++;
  if (J(ist) !== J(soll)) { fehler++; console.log(`  FALSCH ${name}\n    ist  = ${String(JSON.stringify(ist)).slice(0, 700)}\n    soll = ${String(JSON.stringify(soll)).slice(0, 700)}`); }
}
async function gruppe(name, fn) {
  try { await fn(); } catch (e) { n++; fehler++; console.log(`  FALSCH ${name}: abgebrochen – ${String(e.message).split('\n')[0]}`); }
}
const sauber = (errors) => errors.filter((x) => !/Failed to load resource|net::ERR/.test(x));

(async () => {
  const browser = await lib.launch();
  const oeffne = async (o = {}) => lib.open(browser, Object.assign({
    appPath: APP, now: NOW, seed: o.seed === undefined ? VERBUNDEN : o.seed,
    server: new lib.FakeServer({ now: NOW, persons: [{ name: 'Daniel', code: 'geheim123' }] }),
  }, o));
  const knopf = (d) => d.ev(() => {
    const el = document.querySelector('#sync-card [data-action="sync-delete"]');
    return el ? { text: el.textContent.replace(/\s+/g, ' ').trim(), hoehe: Math.round(el.getBoundingClientRect().height) } : null;
  });
  const fenster = (d) => d.ev(() => {
    const o = document.getElementById('sync-delete-overlay');
    if (!o || o.hidden) return null;
    const feld = document.getElementById('sync-delete-answer');
    const err = document.getElementById('sync-delete-error');
    return {
      aufgabe: (document.getElementById('sync-delete-task') || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim(),
      text: o.textContent.replace(/\s+/g, ' ').trim(),
      feld: !!feld, fehler: err && !err.hidden ? err.textContent.replace(/\s+/g, ' ').trim() : '',
    };
  });
  const antworte = async (d, wert) => {
    await d.ev((w) => { document.getElementById('sync-delete-answer').value = w; }, String(wert));
    await d.ev(() => document.querySelector('[data-action="sync-delete-submit"]').click());
    await d.page.waitForTimeout(400);
  };
  const oeffneFenster = async (d) => {
    await d.ev(() => document.querySelector('#sync-card [data-action="sync-delete"]').click());
    await d.page.waitForTimeout(300);
  };
  const loesung = (d) => d.ev(() => currentDeleteChallenge.answer);

  /* ================= L1: der Knopf ================= */
  await gruppe('L1', async () => {
    const ohne = await oeffne({ seed: {} });
    check('L1 ohne Verbindung gibt es den Knopf nicht', await knopf(ohne), null);
    await ohne.ctx.close();
    const d = await oeffne();
    const k = await knopf(d);
    check('L1 verbunden: Knopf da, beschriftet, groß genug', [!!k, /löschen/i.test(k.text), k.hoehe >= 36], [true, true, true]);
    check('L1 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= L2: Rechenaufgabe ================= */
  await gruppe('L2', async () => {
    const d = await oeffne();
    const ziehungen = await d.ev(() => Array.from({ length: 40 }, () => newDeleteChallenge()));
    check('L2 jede Aufgabe ist lösbar und das Ergebnis stimmt', ziehungen.every((z) => z.answer === z.a + z.b && z.text.includes(String(z.a)) && z.text.includes(String(z.b))), true);
    check('L2 die Zahlen liegen zwischen 2 und 9 (im Kopf lösbar, nicht trivial)', ziehungen.every((z) => z.a >= 2 && z.a <= 9 && z.b >= 2 && z.b <= 9), true);
    check('L2 die Aufgabe ist nicht immer dieselbe', new Set(ziehungen.map((z) => z.text)).size > 3, true);
    await oeffneFenster(d);
    const f = await fenster(d);
    check('L2 das Fenster nennt die Frist, stellt die Aufgabe und hat ein Eingabefeld',
          [!!f, /24 Stunden/.test(f.text), /\d\s*\+\s*\d/.test(f.aufgabe), f.feld, f.fehler], [true, true, true, true, '']);
    check('L2 noch nichts an den Server geschickt', d.server.calls.filter((c) => c.endpoint === 'delete').length, 0);
    await antworte(d, (await loesung(d)) + 1);
    const falsch = await fenster(d);
    check('L2 falsche Antwort: Fenster bleibt offen, Meldung sichtbar, nichts geschickt',
          [!!falsch, falsch && falsch.fehler.length > 0, d.server.calls.filter((c) => c.endpoint === 'delete').length], [true, true, 0]);
    await antworte(d, '');
    check('L2 leere Antwort: ebenfalls eine Meldung, nichts geschickt',
          [!!(await fenster(d)), d.server.calls.filter((c) => c.endpoint === 'delete').length], [true, 0]);
    check('L2 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= L3: richtige Antwort und Ergebnis ================= */
  await gruppe('L3', async () => {
    const d = await oeffne();
    await oeffneFenster(d);
    await antworte(d, await loesung(d));
    const aufrufe = d.server.calls.filter((c) => c.endpoint === 'delete');
    check('L3 genau ein Aufruf "delete" mit Name, Code und confirm: true',
          [aufrufe.length, aufrufe[0] && aufrufe[0].body.name, aufrufe[0] && aufrufe[0].body.confirm], [1, 'Daniel', true]);
    check('L3 das Fenster ist zu', await fenster(d), null);
    const termin = '2026-11-21T09:00:00Z';
    check('L3 der Termin steht im Zustand und ist gespeichert',
          [await d.ev(() => syncState.deleteAt), JSON.parse(await d.ev(() => localStorage.getItem('aikido-sync'))).deleteAt], [termin, termin]);
    check('L3 das Hinweisband ist sofort da', await d.ev(() => !!document.getElementById('sync-delete-band')), true);
    await d.page.reload();
    await d.page.waitForLoadState('load');
    await d.page.waitForTimeout(600);
    check('L3 nach dem Neuladen ist das Band immer noch da',
          [await d.ev(() => !!document.getElementById('sync-delete-band')), await d.ev(() => syncState.deleteAt)], [true, termin]);
    check('L3 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= L4: der Server sagt Nein ================= */
  await gruppe('L4', async () => {
    const d = await oeffne();
    d.server.fail = { endpoint: 'delete', status: 401, code: 'bad_credentials' };
    await oeffneFenster(d);
    await antworte(d, await loesung(d));
    const f = await fenster(d);
    check('L4 Fehler vom Server: Fenster bleibt offen mit Meldung, kein Band, kein Termin',
          [!!f, f && f.fehler.length > 0, await d.ev(() => !!document.getElementById('sync-delete-band')), await d.ev(() => syncState.deleteAt)],
          [true, true, false, null]);
    check('L4 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= L5: schmal und dunkel ================= */
  await gruppe('L5', async () => {
    for (const [breite, dark] of [[320, false], [320, true]]) {
      const d = await oeffne({ width: breite, dark });
      await oeffneFenster(d);
      const m = await d.ev(() => {
        const panel = document.querySelector('#sync-delete-overlay .modal-panel');
        const feld = document.getElementById('sync-delete-answer');
        const knopf = document.querySelector('[data-action="sync-delete-submit"]');
        return {
          ueberlauf: panel.scrollWidth > panel.clientWidth + 1,
          feld: Math.round(feld.getBoundingClientRect().height),
          knopf: Math.round(knopf.getBoundingClientRect().height),
        };
      });
      check(`L5 ${breite} px ${dark ? 'dunkel' : 'hell'}: kein Überlauf, Feld und Knopf mindestens 36 px hoch`,
            [m.ueberlauf, m.feld >= 36, m.knopf >= 36], [false, true, true]);
      check(`L5 keine Konsolenfehler (${breite} px ${dark ? 'dunkel' : 'hell'})`, sauber(d.errors), []);
      await d.ctx.close();
    }
  });

  await browser.close();
  console.log(`\nZugang löschen Teil 1 (Fenster): ${n - fehler} von ${n} Prüfungen bestanden — ${fehler ? fehler + ' FEHLGESCHLAGEN' : 'alles grün'}   (Datei: ${APP})`);
  process.exit(fehler ? 1 : 0);
})().catch((e) => { console.log('GESAMTFEHLER:', e && e.stack || e); process.exit(2); });
