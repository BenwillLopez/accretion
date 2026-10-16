// Accretion 1.0.33 asked for its own update under its own (re-signed) bundle ID. The download
// function serves the matching fingerprinted Accretion build to such requests, and nothing else.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');

const ACCRETION = 'io.github.getaccretion.Accretion';
const SHA = 'f'.repeat(64);

function fixture({ hosted = {}, links = {} } = {}) {
  let handler;
  const issued = [];
  const admin = {
    auth: { getUser: async () => ({ data: { user: { id: 'fictional-user' } } }) },
    storage: { from: () => ({ createSignedUrl: async (p) => ({ data: { signedUrl: `https://private.invalid/${p}` }, error: null }) }) },
    from(table) {
      const filters = {};
      const query = {
        select() { return this; },
        eq(column, value) { filters[column] = value; return this; },
        gte() { return this; },
        async maybeSingle() { return { data: { banned: false }, error: null }; },
        then(resolve, reject) {
          const rows = table === 'hosted_builds' ? hosted[filters.bundle_id] ?? []
            : table === 'upstream_links' ? links[filters.bundle_id] ?? [] : null;
          const result = table === 'download_log' ? { count: 0, error: null } : { data: rows, error: null };
          return Promise.resolve(result).then(resolve, reject);
        },
        async insert(row) { issued.push(row); return { error: null }; },
      };
      return query;
    },
  };
  const source = fs.readFileSync(path.join(__dirname, '../../supabase/functions/download/index.ts'), 'utf8')
    .replace(/^import[^\n]+\r?\n/gm, '');
  vm.runInNewContext(stripTypeScriptTypes(source), {
    createClient: () => admin,
    Deno: { env: { get: () => '' }, serve: (fn) => { handler = fn; } },
    Request, Response, URL, Date, AbortSignal, crypto, btoa, atob, TextEncoder, Uint8Array, String, JSON,
    fetch: async () => new Response('{"minimumVersion":"1.0.5"}'),
    console: { warn() {} },
  });
  return { issued, get: (q) => handler(new Request(`https://fictional.invalid/download?${q}`, { headers: { Authorization: 'Bearer fictional' } })) };
}

const OURS = { [ACCRETION]: [{ path: `${ACCRETION}/1.0.34-${SHA}.ipa`, version: '1.0.34', sha256: SHA }] };

test('a re-signed Accretion asking for its update under its own ID gets the Accretion build', async () => {
  const f = fixture({ hosted: OURS });
  const r = await f.get('app=app.salmon1492.dusk2163&version=1.0.34&key=x&av=1.0.33');
  assert.equal(r.status, 302);
  assert.equal(r.headers.get('Location'), `https://private.invalid/${ACCRETION}/1.0.34-${SHA}.ipa`);
  assert.equal(f.issued[0].bundle_id, ACCRETION, 'logged as Accretion');
});

test('without the app tag, an unknown version, or an unverified build: nothing', async () => {
  assert.equal((await fixture({ hosted: OURS }).get('app=app.other.id&version=1.0.34')).status, 404);
  assert.equal((await fixture({ hosted: OURS }).get('app=app.other.id&version=9.9.9&av=1.0.33')).status, 404);
  assert.equal((await fixture({ hosted: OURS }).get('app=app.other.id&av=1.0.33')).status, 404, 'needs an exact version');
  const unverified = { [ACCRETION]: [{ path: 'x.ipa', version: '1.0.34', sha256: null }] };
  assert.equal((await fixture({ hosted: unverified }).get('app=app.other.id&version=1.0.34&av=1.0.33')).status, 404);
});

test('a real app from another source is never swapped for Accretion', async () => {
  const f = fixture({ hosted: OURS, links: { 'com.real.app': [{ version: '1.0.34', url: 'https://src.invalid/a.ipa', name: 'Real' }] } });
  const r = await f.get('app=com.real.app&version=1.0.34&av=1.0.33');
  // its link exists, so it goes to the download proxy (not configured in this fixture: 500), never to Accretion
  assert.equal(r.status, 500);
  assert.equal(r.headers.has('Location'), false);
  assert.equal(f.issued.length, 0);
});
