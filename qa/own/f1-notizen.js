'use strict';
/*
 * Notizen je Technik, Teil 1 (App 2.11): der Umschalter im Verlauf.
 *
 * Erwartet (Vertrag zwischen Test und App):
 *   #history-view in .history-controls: "zeit" (Standard, chronologisch) und "technik" (nach Technik gruppiert)
 *   groupByTechnique(eintraege) -> [{ key, technik, attack, category, family, kyu, tage, letzte, notizen: [{date, text}] }]
 *       tage    = Zahl der verschiedenen Trainingstage dieser Technik (nicht der Einträge)
 *       letzte  = jüngstes Datum
 *       notizen = alle nicht-leeren Notizen, jüngste zuerst
 *       Reihenfolge: jüngste Technik zuerst; bei gleichem Datum nach Name
 *   Gruppierte Ansicht: .tech-group je Technik, .tech-group-note je Notiz; Filter und Suche wirken wie bisher.
 *
 *   node own/f1-notizen.js   (APP=… für eine andere Fassung)
 */
const lib = require('../lib');
const APP = process.env.APP || lib.APP;
const NOW = '2026-11-21T09:00:00Z';

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

/* Verlauf setzen: [Technik-Index, Datum, Notiz] */
const setzeVerlauf = (d, zeilen) => d.ev(async (rows) => {
  log = rows.map((r, i) => {
    const t = TECHNIQUES[r[0]];
    return { id: `g-${i}`, techniqueId: t.id, kyu: t.kyu, category: t.category, attack: t.attack, technik: t.technik,
             family: t.family, date: r[1], note: r[2] || "", trainingsart: 'Tachi Waza', createdAt: `${r[1]}T10:00:00.000Z` };
  });
  await saveLog();
  renderAll();
}, zeilen);

(async () => {
  const browser = await lib.launch();
  const oeffne = async (o = {}) => lib.open(browser, Object.assign({ appPath: APP, now: NOW, seed: {} }, o));
  const umschalten = async (d, wert) => {
    await d.ev((w) => { const s = document.getElementById('history-view'); s.value = w; s.dispatchEvent(new Event('change', { bubbles: true })); }, wert);
    await d.page.waitForTimeout(250);
  };
  const gruppen = (d) => d.ev(() => [...document.querySelectorAll('#history-content .tech-group')].map((el) => ({
    text: el.textContent.replace(/\s+/g, ' ').trim(),
    notizen: [...el.querySelectorAll('.tech-group-note')].map((x) => x.textContent.replace(/\s+/g, ' ').trim()),
  })));

  /* ================= N1: die Gruppierung selbst ================= */
  await gruppe('N1', async () => {
    const d = await oeffne();
    await setzeVerlauf(d, [
      [0, '2026-11-02', 'Hüfte tiefer'],
      [0, '2026-11-02', ''],                  // zweiter Eintrag am selben Tag
      [0, '2026-11-10', 'Uke besser führen'],
      [1, '2026-11-18', ''],
      [1, '2026-11-05', 'Abstand zu groß'],
    ]);
    const g = await d.ev(() => groupByTechnique(log).map((x) => ({ technik: x.technik, tage: x.tage, letzte: x.letzte, notizen: x.notizen })));
    check('N1 zwei Gruppen, jüngste Technik zuerst', [g.length, g[0].letzte, g[1].letzte], [2, '2026-11-18', '2026-11-10']);
    check('N1 Trainingstage werden gezählt, nicht Einträge (zweimal am 2.11. ist ein Tag)',
          [g[1].tage, g[0].tage], [2, 2]);
    check('N1 Notizen: nur die nicht-leeren, jüngste zuerst, mit Datum',
          [g[1].notizen, g[0].notizen],
          [[{ date: '2026-11-10', text: 'Uke besser führen' }, { date: '2026-11-02', text: 'Hüfte tiefer' }],
           [{ date: '2026-11-05', text: 'Abstand zu groß' }]]);
    check('N1 eine Technik ohne jede Notiz hat eine leere Liste (und fällt nicht weg)',
          await d.ev(async () => { log = log.map((e) => Object.assign({}, e, { note: "" })); await saveLog(); const g = groupByTechnique(log); return [g.length, g.every((x) => x.notizen.length === 0)]; }), [2, true]);
    check('N1 bei gleichem Datum entscheidet der Name, damit die Liste nicht springt',
          await d.ev(async () => {
            const a = TECHNIQUES[0], b = TECHNIQUES.find((t) => t.technik.localeCompare(a.technik, 'de') < 0) || TECHNIQUES[1];
            log = [a, b].map((t, i) => ({ id: `s-${i}`, techniqueId: t.id, kyu: t.kyu, category: t.category, attack: t.attack, technik: t.technik,
                     family: t.family, date: '2026-11-12', note: '', trainingsart: 'Tachi Waza', createdAt: '2026-11-12T10:00:00.000Z' }));
            await saveLog();
            const g = groupByTechnique(log).map((x) => x.technik);
            return [g, [...g].sort((x, y) => x.localeCompare(y, 'de'))];
          }).then((r) => r[0].join('|') === r[1].join('|')), true);
    check('N1 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= N2: gleiche Technik, anderer Angriff ================= */
  await gruppe('N2', async () => {
    const d = await oeffne();
    const paar = await d.ev(() => {
      const erste = TECHNIQUES[0];
      const zwilling = TECHNIQUES.find((t) => t.technik === erste.technik && t.id !== erste.id);
      return zwilling ? [TECHNIQUES.indexOf(erste), TECHNIQUES.indexOf(zwilling)] : null;
    });
    if (!paar) { check('N2 (übersprungen: keine zwei Einträge mit gleichem Technik-Namen im Programm)', true, true); }
    else {
      await setzeVerlauf(d, [[paar[0], '2026-11-10', 'A'], [paar[1], '2026-11-11', 'B']]);
      check('N2 gleicher Technik-Name mit anderem Angriff bleibt eine eigene Gruppe',
            await d.ev(() => groupByTechnique(log).length), 2);
    }
    check('N2 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= N3: der Umschalter ================= */
  await gruppe('N3', async () => {
    const d = await oeffne();
    await setzeVerlauf(d, [[0, '2026-11-02', 'Hüfte tiefer'], [0, '2026-11-10', 'Uke besser führen'], [1, '2026-11-18', '']]);
    await d.ev(() => switchTab('verlauf'));
    await d.page.waitForTimeout(250);
    const sel = await d.ev(() => {
      const s = document.getElementById('history-view');
      return s ? { wert: s.value, optionen: [...s.options].map((o) => o.value), hoehe: Math.round(s.getBoundingClientRect().height), inLeiste: !!s.closest('.history-controls') } : null;
    });
    check('N3 Umschalter ist in der Filterleiste, zwei Stellungen, chronologisch als Standard',
          [!!sel, sel.optionen, sel.wert, sel.inLeiste, sel.hoehe >= 36], [true, ['zeit', 'technik'], 'zeit', true, true]);
    check('N3 chronologisch: einzelne Einträge, keine Gruppen',
          await d.ev(() => [document.querySelectorAll('#history-content .history-item').length, document.querySelectorAll('.tech-group').length]), [3, 0]);
    await umschalten(d, 'technik');
    const g = await gruppen(d);
    check('N3 nach Technik: zwei Gruppen, die Notizen stehen bei der richtigen Technik',
          [g.length, g[1].notizen.length, /Uke besser führen/.test(g[1].notizen[0]), /10\.11\./.test(g[1].notizen[0])], [2, 2, true, true]);
    check('N3 die Technik ohne Notiz steht trotzdem da, nur ohne Notizzeilen', [g[0].notizen.length, g[0].text.length > 0], [0, true]);
    check('N3 jede Gruppe nennt die Zahl der Trainingstage', /2\s*(Trainingstage|Tage|×)/i.test(g[1].text), true);
    check('N3 bei einem einzigen Tag steht die Einzahl', /\b1 Trainingstag\b/.test(g[0].text), true);
    await d.ev(() => { const i = document.getElementById('search-input'); i.value = 'Uke besser'; i.dispatchEvent(new Event('input', { bubbles: true })); });
    await d.page.waitForTimeout(300);
    check('N3 die Suche wirkt auch in der gruppierten Ansicht', (await gruppen(d)).length, 1);
    await d.ev(() => { const i = document.getElementById('search-input'); i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); });
    await d.page.waitForTimeout(300);
    await umschalten(d, 'zeit');
    check('N3 zurück auf chronologisch: wieder Einzeleinträge',
          await d.ev(() => [document.querySelectorAll('#history-content .history-item').length, document.querySelectorAll('.tech-group').length]), [3, 0]);
    check('N3 keine Konsolenfehler', sauber(d.errors), []);
    await d.ctx.close();
  });

  /* ================= N4: leer und schmal ================= */
  await gruppe('N4', async () => {
    const d = await oeffne();
    await d.ev(() => switchTab('verlauf'));
    await d.page.waitForTimeout(200);
    await umschalten(d, 'technik');
    check('N4 ohne Einträge steht auch hier der Hinweis statt einer leeren Liste',
          await d.ev(() => [!!document.querySelector('#history-content .empty-state'), document.querySelectorAll('.tech-group').length]), [true, 0]);
    await d.ctx.close();
    for (const [breite, dark] of [[320, false], [320, true]]) {
      const e = await oeffne({ width: breite, dark });
      await setzeVerlauf(e, [[0, '2026-11-02', 'Eine ziemlich lange Notiz, die auf einem schmalen Gerät umbrechen muss und nicht über den Rand laufen darf'], [1, '2026-11-18', '']]);
      await e.ev(() => switchTab('verlauf'));
      await e.page.waitForTimeout(200);
      await umschalten(e, 'technik');
      const m = await e.ev(() => {
        const el = document.querySelector('.tech-group');
        const c = document.getElementById('history-content');
        return { ueberlauf: c.scrollWidth > c.clientWidth + 1, breiter: el.getBoundingClientRect().width <= c.getBoundingClientRect().width + 1 };
      });
      check(`N4 ${breite} px ${dark ? 'dunkel' : 'hell'}: kein Überlauf, lange Notiz bricht um`, [m.ueberlauf, m.breiter], [false, true]);
      check(`N4 keine Konsolenfehler (${breite} px ${dark ? 'dunkel' : 'hell'})`, sauber(e.errors), []);
      await e.ctx.close();
    }
  });

  await browser.close();
  console.log(`\nNotizen je Technik, Teil 1 (Verlauf): ${n - fehler} von ${n} Prüfungen bestanden — ${fehler ? fehler + ' FEHLGESCHLAGEN' : 'alles grün'}   (Datei: ${APP})`);
  process.exit(fehler ? 1 : 0);
})().catch((e) => { console.log('GESAMTFEHLER:', e && e.stack || e); process.exit(2); });
