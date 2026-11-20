'use strict';
/*
 * Prüfstand für den Aikido Kyu Tracker (neu aufgebaut am 20.11.2026).
 *   launch()                        -> Browser
 *   open(browser, { ... })          -> { page, ctx, errors, server, ev, advance }
 * Die Seite wird unter http://aikido.test/ ausgeliefert (echte Herkunft, damit relative Server-Adressen funktionieren).
 * Der Server ist nachgebaut (siehe FakeServer) und merkt sich jeden Aufruf in server.calls.
 * Die Uhr der Seite steht fest und lässt sich mit advance(ms) weiterstellen.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const APP = process.env.APP || path.join(__dirname, 'app.html');

/* ---- nachgebauter Server ------------------------------------------------------------------------------------------ */
class FakeServer {
  constructor(opts = {}) {
    this.api = opts.api === undefined ? 1 : opts.api;
    this.registration = opts.registration !== false;
    this.persons = new Map();            // name(klein) -> { name, code, rev, data, updatedAt, deleteAt }
    this.calls = [];                     // { endpoint, body }
    this.fail = null;                    // { endpoint, status, code } erzwungene Antwort
    this.now = opts.now || '2026-11-20T09:00:00Z';
    this.delayHours = 24;
    (opts.persons || []).forEach((p) => this.add(p));
  }
  add({ name, code, data = {}, rev = 0, deleteAt = null }) {
    this.persons.set(name.toLowerCase(), { name, code, rev, data, updatedAt: this.now, deleteAt });
    return this;
  }
  person(body) {
    const p = this.persons.get(String(body && body.name || '').toLowerCase());
    return p && p.code === body.code ? p : null;
  }
  termin(from) { return new Date(new Date(from).getTime() + this.delayHours * 3600 * 1000).toISOString().replace(/\.\d+Z$/, 'Z'); }
  mit(p, payload) { if (p.deleteAt) payload.deleteAt = p.deleteAt; return payload; }

  handle(endpoint, body) {
    this.calls.push({ endpoint, body });
    if (this.fail && this.fail.endpoint === endpoint) {
      const f = this.fail;
      return { status: f.status, json: { ok: false, code: f.code, error: f.error || 'Fehler vom Server.' } };
    }
    if (endpoint === 'ping') return { status: 200, json: { ok: true, app: 'aikido-tracker-server', api: this.api, version: '1.6.0', registration: this.registration } };
    const p = this.person(body);
    if (endpoint === 'register') {
      if (!this.registration) return { status: 403, json: { ok: false, code: 'registration_disabled', error: 'Hier können keine Personen angelegt werden.' } };
      const key = String(body.name || '').toLowerCase();
      if (this.persons.has(key)) return { status: 409, json: { ok: false, code: 'name_taken', error: 'Name vergeben.' } };
      this.add({ name: body.name, code: body.code });
      return { status: 201, json: { ok: true, person: { id: key, name: body.name }, rev: 0, updatedAt: this.now } };
    }
    if (!p) return { status: 401, json: { ok: false, code: 'bad_credentials', error: 'Name oder Zugangscode stimmt nicht.' } };
    if (endpoint === 'login') return { status: 200, json: this.mit(p, { ok: true, person: { id: p.name.toLowerCase(), name: p.name }, rev: p.rev, updatedAt: p.updatedAt }) };
    if (endpoint === 'pull') {
      if (body.sinceRev === p.rev) return { status: 200, json: this.mit(p, { ok: true, unchanged: true, rev: p.rev, updatedAt: p.updatedAt }) };
      return { status: 200, json: this.mit(p, { ok: true, person: { id: p.name.toLowerCase(), name: p.name }, rev: p.rev, updatedAt: p.updatedAt, data: p.data }) };
    }
    if (endpoint === 'push') {
      if (body.baseRev !== p.rev) return { status: 409, json: { ok: false, code: 'conflict', error: 'Neuerer Stand.', rev: p.rev, updatedAt: p.updatedAt } };
      p.data = body.data; p.rev += 1; p.updatedAt = this.now;
      return { status: 200, json: this.mit(p, { ok: true, rev: p.rev, updatedAt: p.updatedAt }) };
    }
    if (endpoint === 'delete') {
      if (body.confirm !== true) return { status: 400, json: { ok: false, code: 'bad_request', error: 'Bestätigung fehlt.' } };
      if (!p.deleteAt) p.deleteAt = this.termin(this.now);
      return { status: 200, json: { ok: true, deleteAt: p.deleteAt } };
    }
    if (endpoint === 'delete-cancel') { p.deleteAt = null; return { status: 200, json: { ok: true, deleteAt: null } }; }
    return { status: 404, json: { ok: false, code: 'not_found', error: 'Unbekannt.' } };
  }
}

async function launch() { return chromium.launch(); }

async function open(browser, opts = {}) {
  const { appPath = APP, width = 390, height = 844, dark = false, now = '2026-11-20T09:00:00Z', seed = {}, server } = opts;
  const srv = server || new FakeServer({ now });
  const html = fs.readFileSync(appPath, 'utf8');
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: dark ? 'dark' : 'light', timezoneId: 'Europe/Vienna', locale: 'de-AT' });
  const errors = [];
  await ctx.addInitScript(({ now, seed }) => {
    const basis = new Date(now).getTime();
    window.__offset = 0;
    window.__jetzt = () => basis + window.__offset;
    const Echt = Date;
    class FesteZeit extends Echt {
      constructor(...a) { if (a.length === 0) super(window.__jetzt()); else super(...a); }
      static now() { return window.__jetzt(); }
    }
    window.Date = FesteZeit;
    try { for (const [k, v] of Object.entries(seed)) localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v)); } catch (e) { /* egal */ }
  }, { now, seed });
  await ctx.route('http://aikido.test/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/aikido_tracker/')) {
      const endpoint = url.pathname.replace('/api/aikido_tracker/', '');
      let body = null;
      try { body = JSON.parse(route.request().postData() || 'null'); } catch (e) { body = null; }
      const antwort = srv.handle(endpoint, body);
      return route.fulfill({ status: antwort.status, contentType: 'application/json', headers: { 'Cache-Control': 'no-store' }, body: JSON.stringify(antwort.json) });
    }
    return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: html });
  });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e && e.message || e)));
  page.setDefaultTimeout(60000);
  await page.goto('http://aikido.test/');
  await page.waitForLoadState('load');
  await page.waitForTimeout(400);
  return {
    page, ctx, errors, server: srv,
    ev: (fn, arg) => page.evaluate(fn, arg),
    advance: async (ms) => { await page.evaluate((v) => { window.__offset += v; }, ms); },
  };
}

module.exports = { launch, open, FakeServer, APP };
