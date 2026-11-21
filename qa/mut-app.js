'use strict';
/*
 * Gegenprobe für den App-Teil "Zugang löschen": baut absichtlich Fehler in eine KOPIE der App ein und prüft,
 * ob die Prüfreihen sie bemerken.   Aufruf: node mut-app.js [Teil des Namens]
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const QUELLE = path.join(__dirname, 'app.html');
const ARBEIT = path.join(__dirname, '.mut');
const SUITEN = ['own/e1-loeschen.js', 'own/e2-band.js', 'own/f1-notizen.js'];

const M = [
  // (Die Schreibweisen-Prüfung in cleanDeleteAt ist seit der Rückprobe über toISOString eine redundante Vorprüfung:
  //  ein Mutant, der sie entfernt, ändert nichts — deshalb steht hier keiner.)
  ['termin-unmoeglicher-tag-erlaubt', [['return d.toISOString().replace(/\\.\\d{3}Z$/, "Z") === value ? value : null;', 'return value;']]],
  ['aufgabe-immer-gleich', [['const a = 2 + Math.floor(Math.random() * 8);\n  const b = 2 + Math.floor(Math.random() * 8);', 'const a = 5;\n  const b = 5;']]],
  ['aufgabe-falsche-loesung', [['return { a, b, text: `${a} + ${b} = ?`, answer: a + b };', 'return { a, b, text: `${a} + ${b} = ?`, answer: a * b };']]],
  ['aufgabe-zahlen-ab-null', [['const a = 2 + Math.floor(Math.random() * 8);', 'const a = Math.floor(Math.random() * 8);']]],
  ['countdown-eine-minute-verschluckt', [['if (!(ms >= 60000)) return "jeden Moment";', 'if (!(ms > 60000)) return "jeden Moment";']]],
  ['countdown-stundengrenze', [['if (minuten < 60) return', 'if (minuten <= 60) return']]],
  ['countdown-immer-mehrzahl', [['return `noch ${stunden} ${stunden === 1 ? "Stunde" : "Stunden"}`;', 'return `noch ${stunden} Stunden`;']]],
  ['antwort-wird-nicht-geprueft', [['if (!/^\\d{1,3}$/.test(eingabe) || Number(eingabe) !== currentDeleteChallenge.answer) {', 'if (false) {']]],
  ['falsche-antwort-ohne-meldung', [['    setSyncDeleteError(`Das Ergebnis stimmt nicht.', '    setSyncDeleteError(``.concat(`Das Ergebnis stimmt nicht.']]],
  ['ohne-bestaetigung-geschickt', [['{ name: state.name, code: state.code, confirm: true }', '{ name: state.name, code: state.code, confirm: false }']]],
  ['termin-nicht-gemerkt', [['  if (!(await setSyncDeleteAt(pid, when))) return syncFail("local_storage");', '  if (false) return syncFail("local_storage");']]],
  ['termin-nicht-gespeichert', [['  if (!(await saveSyncState(pid, next))) return false;\n  if (activeProfileId !== pid) return false;', '  if (activeProfileId !== pid) return false;']]],
  ['band-fehlt', [['  if (!syncState || !syncState.deleteAt) return "";\n  const rest', '  if (true) return "";\n  const rest']]],
  ['band-ohne-abbruchknopf', [['<button type="button" class="delete-band-btn" data-action="sync-delete-cancel">Löschung abbrechen</button>', '']]],
  ['abbruch-geht-an-den-falschen-weg', [['const r = await syncRequest("delete-cancel", { name: state.name, code: state.code });', 'const r = await syncRequest("delete", { name: state.name, code: state.code, confirm: true });']]],
  ['abbruch-trotz-fehler-geglaubt', [['  const r = await syncRequest("delete-cancel", { name: state.name, code: state.code });\n  if (!r.ok) return syncFail(r.code, r);', '  const r = await syncRequest("delete-cancel", { name: state.name, code: state.code });']]],
  ['server-termin-beim-abholen-ignoriert', [['    await noteServerDeleteAt(pid, state, pull.data);\n', '']]],
  ['server-abbruch-wird-nicht-uebernommen', [['  const wert = cleanDeleteAt(data.deleteAt);', '  const wert = cleanDeleteAt(data.deleteAt) || syncState.deleteAt || null;']]],
  ['knopf-auch-waehrend-der-frist', [['${syncState.deleteAt ? "" : \'<button type="button" class="sync-btn danger" data-action="sync-delete">Zugang löschen</button>\'}', '<button type="button" class="sync-btn danger" data-action="sync-delete">Zugang löschen</button>']]],
  ['fenster-oeffnet-trotz-laufender-frist', [['if (!syncState || !syncServer.available || syncState.deleteAt) return;', 'if (!syncState || !syncServer.available) return;']]],
  // ---- Notizen je Technik (Verlauf, gruppierte Sicht) ----
  ['notizen-zaehlt-eintraege-statt-tage', [['      g._tage.add(tag);', '      g._tage.add(tag + e.id);']]],
  ['notizen-aelteste-technik-zuerst', [['liste.sort((a, b) => (a.letzte === b.letzte ? a.technik.localeCompare(b.technik, "de") : a.letzte < b.letzte ? 1 : -1));', 'liste.sort((a, b) => (a.letzte === b.letzte ? a.technik.localeCompare(b.technik, "de") : a.letzte < b.letzte ? -1 : 1));']]],
  ['notizen-ohne-namenssortierung', [['liste.sort((a, b) => (a.letzte === b.letzte ? a.technik.localeCompare(b.technik, "de")', 'liste.sort((a, b) => (a.letzte === b.letzte ? (b.technik.localeCompare(a.technik, "de"))']]],
  ['notizen-aelteste-notiz-zuerst', [['g.notizen.sort((a, b) => (a.date === b.date ? 0 : a.date < b.date ? 1 : -1));', 'g.notizen.sort((a, b) => (a.date === b.date ? 0 : a.date < b.date ? -1 : 1));']]],
  ['notizen-leere-notizen-mitgezaehlt', [['    if (textOrEmpty(e.note)) g.notizen.push({ date: textOrEmpty(e.date), text: e.note });', '    g.notizen.push({ date: textOrEmpty(e.date), text: e.note });']]],
  ['notizen-gruppe-nur-nach-namen', [['const key = textOrEmpty(e.techniqueId) || `${textOrEmpty(e.technik)}|${textOrEmpty(e.attack)}|${textOrEmpty(e.category)}`;', 'const key = textOrEmpty(e.technik);']]],
  ['notizen-umschalter-wirkungslos', [['  if (historyView === "technik") {', '  if (false) {']]],
  ['notizen-umschalter-merkt-nichts', [['  historyView = e.target.value === "technik" ? "technik" : "zeit";', '  historyView = "zeit";']]],
  ['notizen-werden-nicht-angezeigt', [['      ${notizen}\n    </div>`;', '      \n    </div>`;']]],
  ['notizen-ohne-tageszahl', [['<div class="tech-group-meta">${tage}${zuletzt}', '<div class="tech-group-meta">${zuletzt}']]],
  ['notizen-immer-mehrzahl', [['const tage = `${g.tage} ${g.tage === 1 ? "Trainingstag" : "Trainingstage"}`;', 'const tage = `${g.tage} Trainingstage`;']]],
];

const wahl = process.argv.slice(2);
const liste = wahl.length ? M.filter(([name]) => wahl.some((w) => name.includes(w))) : M;
fs.mkdirSync(ARBEIT, { recursive: true });
const original = fs.readFileSync(QUELLE, 'utf8');
let erkannt = 0, ueberlebt = 0, ungueltig = 0;

for (const [name, paare] of liste) {
  let text = original, fehlerhaft = false;
  for (const [alt, neu] of paare) {
    const treffer = text.split(alt).length - 1;
    if (treffer !== 1) { console.log(`FEHLER    ${name.padEnd(42)} Ersetzungstext kommt ${treffer}x vor`); fehlerhaft = true; break; }
    text = text.replace(alt, neu);
  }
  if (fehlerhaft) { ungueltig++; continue; }
  const ziel = path.join(ARBEIT, 'app.html');
  fs.writeFileSync(ziel, text);
  let meldung = '', gefallen = false;
  for (const suite of SUITEN) {
    try {
      execFileSync('node', [suite], { cwd: __dirname, env: Object.assign({}, process.env, { APP: ziel }), stdio: 'pipe', timeout: 300000 });
    } catch (e) {
      gefallen = true;
      const aus = String(e.stdout || '') + String(e.stderr || '');
      meldung = (aus.split('\n').find((z) => z.includes('FALSCH')) || 'Lauf abgebrochen').trim().slice(0, 100);
      break;
    }
  }
  if (gefallen) { erkannt++; console.log(`erkannt   ${name.padEnd(42)} ${meldung}`); }
  else { ueberlebt++; console.log(`ÜBERLEBT  ${name.padEnd(42)}`); }
}
console.log(`\nGegenprobe (App): ${erkannt} von ${liste.length} eingebauten Fehlern erkannt; ${ueberlebt} überlebt, ${ungueltig} Mutation ungültig`);
process.exit(ueberlebt || ungueltig ? 1 : 0);
