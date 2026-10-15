// The source function's store lists (name=store|curated): every download-server link gets the
// personal key, nothing else changes, and bad keys get nothing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');

const BASE = 'https://fixture.supabase.co';
const KEY = 'a'.repeat(64);
const STORE = {
  apps: [
    { bundleIdentifier: 'com.other.app', downloadURL: `${BASE}/functions/v1/download?app=com.other.app&version=2.0`,
      versions: [{ version: '2.0', downloadURL: `${BASE}/functions/v1/download?app=com.other.app&version=2.0` }] },
    { bundleIdentifier: 'com.elsewhere.app', downloadURL: 'https://elsewhere.invalid/app.ipa', versions: [] },
  ],
};

function sourceFunction({ validKey = true } = {}) {
  let handler;
  const admin = {
    from(table) {
      return {
        select() { return this; }, eq() { return this; },
        async maybeSingle() { return { data: validKey ? { owner: 'fictional-user' } : null }; },
        then(resolve) { return Promise.resolve({ data: table === 'hosted_builds' ? [] : null }).then(resolve); },
      };
    },
  };
  const env = { SUPABASE_URL: BASE };
  const fetched = [];
  const code = fs.readFileSync(path.join(__dirname, '../../supabase/functions/source/index.ts'), 'utf8')
    .replace(/^import[^\n]+\r?\n/gm, '');
  vm.runInNewContext(stripTypeScriptTypes(code), {
    createClient: () => admin,
    Deno: { env: { get: (k) => env[k] ?? '' }, serve: (fn) => { handler = fn; } },
    fetch: async (url) => { fetched.push(url); return new Response(JSON.stringify(STORE)); },
    Request, Response, URL, JSON, Date, Map, Set, Object, encodeURIComponent,
  });
  return { fetched, get: (q) => handler(new Request(`${BASE}/functions/v1/source?${q}`)) };
}

test('store list: every download-server link carries the key, other links are untouched', async () => {
  const f = sourceFunction();
  const r = await f.get(`name=store&key=${KEY}`);
  assert.equal(r.status, 200);
  const body = await r.json();
  assert.equal(f.fetched[0], 'https://getaccretion.app/source.json');
  assert.equal(body.apps[0].downloadURL, `${BASE}/functions/v1/download?app=com.other.app&version=2.0&key=${KEY}`);
  assert.equal(body.apps[0].versions[0].downloadURL, `${BASE}/functions/v1/download?app=com.other.app&version=2.0&key=${KEY}`);
  assert.equal(body.apps[1].downloadURL, 'https://elsewhere.invalid/app.ipa');
});

test('curated list comes from curated.json', async () => {
  const f = sourceFunction();
  assert.equal((await f.get(`name=curated&key=${KEY}`)).status, 200);
  assert.equal(f.fetched[0], 'https://getaccretion.app/curated.json');
});

test('a missing, malformed or replaced key gets no list', async () => {
  assert.equal((await sourceFunction().get('name=store')).status, 401);
  assert.equal((await sourceFunction().get('name=store&key=short')).status, 401);
  assert.equal((await sourceFunction({ validKey: false }).get(`name=store&key=${KEY}`)).status, 401);
  assert.equal((await sourceFunction().get(`name=other&key=${KEY}`)).status, 400);
});
