'use strict';
/*
 * Zugang löschen, Teil 2 (App 2.10): das Hinweisband mit Termin und Abbruch.
 *
 * Erwartet (Vertrag zwischen Test und App):
 *   #sync-delete-band  steht ganz oben, nur solange syncState.deleteAt gesetzt ist; nennt Datum und Uhrzeit
 *                      und die verbleibende Zeit; enthält [data-action="sync-delete-cancel"].
 *   deleteCountdownText(msVerbleibend) -> "noch 23 Stunden" | "noch 45 Minuten" | "jeden Moment"
 *   Der Termin kommt auch vom Server: jede Antwort auf login/pull/push mit "deleteAt" setzt ihn,
 *   jede Antwort ohne "deleteAt" löscht ihn wieder (woanders abgebrochen).
 *
 *   node own/e2-band.js   (APP=… für eine andere Fassung)
 */
const lib = require('../lib');
const APP = process.env.APP || lib.APP;
const NOW = '2026-11-20T09:00:00Z';
const TERMIN = '2026-11-21T09:00:00Z';
const verbunden = (deleteAt) => ({ 'aikido-sync': Object.assign({ v: 1, name: 'Daniel', code: 'geheim123', rev: null, base: null, at: null, rejected: false }, deleteAt ? { deleteAt } : {}) });

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
    appPath: APP, now: NOW,
    seed: o.seed === undefined ? verbunden(TERMIN) : o.seed,
    server: o.server || new lib.FakeServer({ now: NOW, persons: [{ name: 'Daniel', code: 'geheim123', deleteAt: TERMIN }] }),
  }, o));
  const band = (d) => d.ev(() => {
    const el = document.getElementById('sync-delete-band');
    if (!el) return null;
    const knopf = el.querySelector('[data-action="sync-delete-cancel"]');
    const kopf = document.querySelector('header, .app-header, #kopf');
    return {
      text: el.textContent.replace(/\s+/g, ' ').trim(),
      sichtbar: el.checkVisibility ? el.checkVisibility() : !!el.offsetParent,
      knopf: knopf ? Math.round(knopf.getBoundingClientRect().height) : null,
      obenAuf: !kopf || el.getBoundingClientRect().top <= kopf.getBoundingClientRect().bottom + 200,
      ueberlauf: el.scrollWidth > el.clientWidth + 1,
    };
  });

  /* ================= B1: das Band ================= */
  await gruppe('B1', async () => {
    const ohne = await lib.open(browser, { appPath: APP, now: NOW, seed: verbunden(null), server: new lib.FakeServer({ now: NOW, persons: [{ name: 'Daniel', code: 'geheim123' }] }) });
    check('B1 ohne vorgemerkte Löschung gibt es kein Band', await band(ohne), null);
    check('B1 keine Konsolenfehler (ohne Band)', sauber(ohne.errors), []);
    await ohne.ctx.close();
    const d = await oeffne();
    const b = await band(d);
    check('B1 mit Termin: Band sichtbar, nennt Datum und Uhrzeit, Knopf zum Abbrechen groß genug',
          [!!b, b && b.sichtbar, /21\.11\.2026/.test(b.text), /10[:.]00/.test(b.text), b && b.knopf >= 36], [true, true, true, true, true]);
    check('B1 das Band nennt auch die verbleibende Zeit', /noch\s+\d+\s+Stunden?/.test(b.text), true);
    check('B1 das Band steht weit oben auf der Seite', b.obenAuf, true);
    check('B1 solange eine Löschung läuft, gibt es keinen zweiten Knopf "Zugang löschen"',
          await d.ev(() => !!document.querySelector('#sync-card [data-action="sync-delete"]')), false);
    check('B1 ... und das Fenster lässt sich auch nicht auf anderem Weg öffnen',
          await (async () => { await d.ev(() => openSyncDeleteModal()); await d.page.waitForTimeout(200); return d.ev(() => !document.getElementById('sync-delete-overlay').hidden); })(), false);
    check('B1 nur ein echter Zeitpunkt in der Schreibweise des Servers zählt als Termin',
          await d.ev(() => [cleanDeleteAt('2026-11-21T09:00:00Z'), cleanDeleteAt('irgendwann'), cleanDeleteAt('2026-02-30T10:00:00Z'), cleanDeleteAt('2026-11-21T09:00:00.000Z'), cleanDeleteAt(5), cleanDeleteAt(null)]),
          ['2026-11-21T09:00:00Z', null, null, null, null, null]);
    check('B1 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
    const kaputt = await lib.open(browser, { appPath: APP, now: NOW, seed: verbunden('irgendwann'), server: new lib.FakeServer({ now: NOW, persons: [{ name: 'Daniel', code: 'geheim123' }] }) });
    check('B1 ein unbrauchbarer gespeicherter Termin gilt als "keine Löschung" (kein Band, keine kaputte Anzeige)',
          [await band(kaputt), await kaputt.ev(() => syncState.deleteAt)], [null, null]);
    check('B1 keine Konsolenfehler (unbrauchbarer Termin)', sauber(kaputt.errors), []);
    await kaputt.ctx.close();
  });

  /* ================= B2: die verbleibende Zeit in Worten ================= */
  await gruppe('B2', async () => {
    const d = await oeffne();
    const texte = await d.ev(() => [
      deleteCountdownText(23.5 * 3600 * 1000),
      deleteCountdownText(2 * 3600 * 1000),
      deleteCountdownText(3600 * 1000),
      deleteCountdownText(59 * 60 * 1000),
      deleteCountdownText(60 * 1000),
      deleteCountdownText(30 * 1000),
      deleteCountdownText(0),
      deleteCountdownText(-5000),
    ]);
    check('B2 Stunden, Minuten, und ganz zum Schluss "jeden Moment"',
          texte, ['noch 23 Stunden', 'noch 2 Stunden', 'noch 1 Stunde', 'noch 59 Minuten', 'noch 1 Minute', 'jeden Moment', 'jeden Moment', 'jeden Moment']);
    await d.advance(22 * 3600 * 1000);
    await d.ev(() => renderUebersicht());
    await d.page.waitForTimeout(200);
    check('B2 22 Stunden später steht die kleinere Zahl im Band', /noch 2 Stunden/.test((await band(d)).text), true);
    check('B2 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= B3: abbrechen ================= */
  await gruppe('B3', async () => {
    const d = await oeffne();
    await d.ev(() => document.querySelector('[data-action="sync-delete-cancel"]').click());
    await d.page.waitForTimeout(500);
    check('B3 Abbrechen: Aufruf "delete-cancel" an den Server, Band weg, Termin weg, gespeichert',
          [d.server.calls.filter((c) => c.endpoint === 'delete-cancel').length, await band(d), await d.ev(() => syncState.deleteAt),
           JSON.parse(await d.ev(() => localStorage.getItem('aikido-sync'))).deleteAt || null],
          [1, null, null, null]);
    check('B3 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();

    const e = await oeffne();
    e.server.fail = { endpoint: 'delete-cancel', status: 500, code: 'server_error' };
    await e.ev(() => document.querySelector('[data-action="sync-delete-cancel"]').click());
    await e.page.waitForTimeout(500);
    check('B3 geht der Abbruch schief, bleibt das Band stehen (nichts wird vorgetäuscht)',
          [!!(await band(e)), await e.ev(() => syncState.deleteAt)], [true, TERMIN]);
    check('B3 keine Konsolenfehler (Fehlerfall)', sauber(e.errors), []);
    await e.ctx.close();
  });

  /* ================= B4: der Termin kommt vom Server ================= */
  await gruppe('B4', async () => {
    // auf diesem Gerät ist nichts bekannt, der Server meldet aber eine Löschung (woanders ausgelöst)
    const d = await lib.open(browser, { appPath: APP, now: NOW, seed: verbunden(null),
      server: new lib.FakeServer({ now: NOW, persons: [{ name: 'Daniel', code: 'geheim123', deleteAt: TERMIN }] }) });
    await d.ev(() => syncNow("Test"));
    await d.page.waitForTimeout(800);
    check('B4 der Abgleich bringt den Termin mit: das Band erscheint',
          [!!(await band(d)), await d.ev(() => syncState.deleteAt)], [true, TERMIN]);
    // woanders abgebrochen: der Server meldet keinen Termin mehr
    d.server.persons.get('daniel').deleteAt = null;
    await d.ev(() => syncNow("Test"));
    await d.page.waitForTimeout(800);
    check('B4 wurde woanders abgebrochen, verschwindet das Band beim nächsten Abgleich',
          [await band(d), await d.ev(() => syncState.deleteAt)], [null, null]);
    check('B4 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= B5: trennen und Darstellung ================= */
  await gruppe('B5', async () => {
    const d = await oeffne();
    await d.ev(() => syncDisconnect());
    await d.page.waitForTimeout(300);
    check('B5 nach dem Trennen ist kein Band mehr da', await band(d), null);
    await d.ctx.close();
    for (const [breite, dark] of [[320, false], [320, true]]) {
      const e = await oeffne({ width: breite, dark });
      const b = await band(e);
      check(`B5 ${breite} px ${dark ? 'dunkel' : 'hell'}: Band sichtbar, kein Überlauf, Knopf groß genug`,
            [b && b.sichtbar, b && b.ueberlauf, b && b.knopf >= 36], [true, false, true]);
      check(`B5 keine Konsolenfehler (${breite} px ${dark ? 'dunkel' : 'hell'})`, sauber(e.errors), []);
      await e.ctx.close();
    }
  });

  await browser.close();
  console.log(`\nZugang löschen Teil 2 (Band): ${n - fehler} von ${n} Prüfungen bestanden — ${fehler ? fehler + ' FEHLGESCHLAGEN' : 'alles grün'}   (Datei: ${APP})`);
  process.exit(fehler ? 1 : 0);
})().catch((e) => { console.log('GESAMTFEHLER:', e && e.stack || e); process.exit(2); });
