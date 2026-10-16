// The download function and the download proxy together: links for other sources' apps carry the
// source URL only encrypted, the proxy streams the file under "<App>_<version>.ipa", and changed,
// expired or made-up links are refused.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');
const { pathToFileURL } = require('node:url');

const KEY = Buffer.alloc(32, 7).toString('base64url'); // fictional test key
const ORIGIN = 'https://dl.fictional.invalid';
const UPSTREAM = 'https://source.fictional.invalid/files/ASJTube_21.40.5_1.4.ipa';

function downloadFunction(links, hosted = []) {
  let handler;
  const issued = [];
  const admin = {
    auth: { getUser: async () => ({ data: { user: { id: 'fictional-user' } } }) },
    storage: { from: () => ({ createSignedUrl: async (p) => (hosted.length ? { data: { signedUrl: `https://copy.fictional.invalid/${p}` }, error: null } : { data: null, error: { message: 'none' } }) }) },
    from(table) {
      const query = {
        select() { return this; }, eq() { return this; }, gte() { return this; },
        async maybeSingle() { return { data: { banned: false }, error: null }; },
        then(resolve, reject) {
          const result = table === 'download_log' ? { count: 0, error: null }
            : table === 'hosted_builds' ? { data: hosted, error: null }
            : { data: links, error: null };
          return Promise.resolve(result).then(resolve, reject);
        },
        async insert(row) { issued.push(row); return { error: null }; },
      };
      return query;
    },
  };
  const env = { DOWNLOAD_PROXY_ORIGIN: ORIGIN, DOWNLOAD_PROXY_KEY: KEY };
  const source = fs.readFileSync(path.join(__dirname, '../../supabase/functions/download/index.ts'), 'utf8')
    .replace(/^import[^\n]+\r?\n/gm, '');
  vm.runInNewContext(stripTypeScriptTypes(source), {
    createClient: () => admin,
    Deno: { env: { get: (k) => env[k] ?? '' }, serve: fn => { handler = fn; } },
    Request, Response, URL, Date, AbortSignal, crypto, btoa, atob, TextEncoder, Uint8Array, String, JSON,
    console: { warn() {} },
  });
  return {
    issued,
    get: (query) => handler(new Request(`https://fictional.invalid/download?${query}`, { headers: { Authorization: 'Bearer fictional' } })),
  };
}

async function worker() {
  return (await import(pathToFileURL(path.join(__dirname, '../../workers/download-proxy/index.js')).href)).default;
}

function withUpstream(fn, respond) {
  const real = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, init) => { seen.push({ url, init }); return respond(url, init); };
  return fn(seen).finally(() => { globalThis.fetch = real; });
}

const LINKS = [
  { version: '21.40.5', url: UPSTREAM, name: 'ASJTube + Bonus Tweaks (1.4.0 - mrdrvt99)' },
  { version: '21.39.4', url: 'https://source.fictional.invalid/files/old.ipa', name: 'ASJTube + Bonus Tweaks (1.4.0 - mrdrvt99)' },
];

test('other sources: the redirect names the file and never shows the source URL', async () => {
  const f = downloadFunction(LINKS);
  const response = await f.get('app=com.google.ios.youtube.asjtube.1.4.0');
  assert.equal(response.status, 302);
  const location = response.headers.get('Location');
  assert.ok(location.startsWith(`${ORIGIN}/ASJTube-Bonus-Tweaks_21.40.5.ipa?t=`), location);
  assert.ok(!location.includes('source.fictional.invalid'), 'source host is not in the link');
  assert.ok(!decodeURIComponent(location).includes('files/'), 'source path is not in the link');
  assert.equal(f.issued.length, 1, 'the download is logged and counted');
});

test('a particular version and an unknown one', async () => {
  const f = downloadFunction(LINKS);
  const old = await f.get('app=com.fixture&version=21.39.4');
  assert.ok(old.headers.get('Location').includes('_21.39.4.ipa?t='));
  const none = await downloadFunction([]).get('app=com.fixture');
  assert.equal(none.status, 404);
  assert.equal(none.headers.has('Location'), false);
});

test('the proxy streams the file under the app name', async () => {
  const location = (await downloadFunction(LINKS).get('app=com.fixture')).headers.get('Location');
  const proxy = await worker();
  await withUpstream(async (seen) => {
    const r = await proxy.fetch(new Request(location, { headers: { Range: 'bytes=0-3' } }), { DOWNLOAD_PROXY_KEY: KEY });
    assert.equal(r.status, 206);
    assert.equal(r.headers.get('Content-Disposition'), 'attachment; filename="ASJTube-Bonus-Tweaks_21.40.5.ipa"');
    assert.equal(r.headers.get('Content-Type'), 'application/octet-stream');
    assert.equal(r.headers.get('Cache-Control'), 'private, no-store');
    assert.equal(r.headers.get('Content-Range'), 'bytes 0-3/10');
    assert.equal(r.headers.get('Set-Cookie'), null, 'source headers are not passed on');
    assert.equal(await r.text(), 'IPA!');
    assert.equal(seen[0].url, UPSTREAM);
    assert.equal(seen[0].init.headers.Range, 'bytes=0-3');
  }, () => new Response('IPA!', { status: 206, headers: { 'Content-Range': 'bytes 0-3/10', 'Set-Cookie': 'tracker=1' } }));
});

test('changed, swapped, expired and made-up links are refused without contacting the source', async () => {
  const location = (await downloadFunction(LINKS).get('app=com.fixture')).headers.get('Location');
  const proxy = await worker();
  const url = new URL(location);
  const token = url.searchParams.get('t');
  const flipped = token.slice(0, -2) + (token.at(-2) === 'A' ? 'B' : 'A') + token.at(-1);
  await withUpstream(async (seen) => {
    const cases = [
      [`${ORIGIN}${url.pathname}?t=${flipped}`, 403],
      [`${ORIGIN}/Other-App_1.0.ipa?t=${token}`, 403],
      [`${ORIGIN}${url.pathname}?t=AAAA`, 403],
      [`${ORIGIN}${url.pathname}`, 403],
    ];
    for (const [link, status] of cases) {
      const r = await proxy.fetch(new Request(link), { DOWNLOAD_PROXY_KEY: KEY });
      assert.equal(r.status, status, link);
    }
    const wrongKey = await proxy.fetch(new Request(location), { DOWNLOAD_PROXY_KEY: Buffer.alloc(32, 9).toString('base64url') });
    assert.equal(wrongKey.status, 403);
    const realNow = Date.now;
    Date.now = () => realNow() + 11 * 60_000;
    try {
      assert.equal((await proxy.fetch(new Request(location), { DOWNLOAD_PROXY_KEY: KEY })).status, 410);
    } finally {
      Date.now = realNow;
    }
    assert.equal(seen.length, 0, 'the source was never contacted');
  }, () => new Response('should not be fetched'));
});

test('a failing source becomes a short message, not its own page', async () => {
  const location = (await downloadFunction(LINKS).get('app=com.fixture')).headers.get('Location');
  const proxy = await worker();
  await withUpstream(async () => {
    const r = await proxy.fetch(new Request(location), { DOWNLOAD_PROXY_KEY: KEY });
    assert.equal(r.status, 502);
    assert.ok(!(await r.text()).includes('secret page'));
  }, () => new Response('secret page', { status: 404 }));
});

test('our own builds go through the proxy too: only the proxy address is shown', async () => {
  const sha = 'a'.repeat(64);
  const f = downloadFunction([], [{ path: `com.fixture/1.2-${sha}.ipa`, version: '1.2', sha256: sha }]);
  const location = (await f.get('app=com.fixture')).headers.get('Location');
  assert.ok(location.startsWith(`${ORIGIN}/fixture_1.2.ipa?t=`), location);
  assert.ok(!location.includes('copy.fictional.invalid'), 'the storage host is not in the link');
  const proxy = await worker();
  await withUpstream(async (seen) => {
    const r = await proxy.fetch(new Request(location), { DOWNLOAD_PROXY_KEY: KEY });
    assert.equal(r.status, 200);
    assert.equal(r.headers.get('Content-Disposition'), 'attachment; filename="fixture_1.2.ipa"');
    assert.equal(seen[0].url, `https://copy.fictional.invalid/com.fixture/1.2-${sha}.ipa`);
  }, () => new Response('IPA!'));
});

test('/download is the download function under our address, its answer passed on', async () => {
  const proxy = await worker();
  const env = { DOWNLOAD_PROXY_KEY: KEY, DOWNLOAD_FUNCTION: 'https://fn.fictional.invalid/functions/v1/download' };
  await withUpstream(async (seen) => {
    const r = await proxy.fetch(new Request(`${ORIGIN}/download?app=com.fixture&key=k`, {
      headers: { Authorization: 'Bearer fictional', Cookie: 'c=1', Accept: 'text/html' },
    }), env);
    assert.equal(r.status, 302);
    assert.equal(r.headers.get('Location'), `${ORIGIN}/fixture_1.2.ipa?t=x`);
    assert.equal(r.headers.get('Set-Cookie'), null);
    assert.equal(seen[0].url, 'https://fn.fictional.invalid/functions/v1/download?app=com.fixture&key=k');
    assert.equal(seen[0].init.redirect, 'manual', 'the redirect is passed on, not followed');
    assert.equal(seen[0].init.headers.authorization, 'Bearer fictional');
    assert.equal(seen[0].init.headers.accept, 'text/html');
    assert.equal(seen[0].init.headers.cookie, undefined, 'nothing else is forwarded');
    const refused = await proxy.fetch(new Request(`${ORIGIN}/download?app=x`, { method: 'POST' }), env);
    assert.equal(refused.status, 405);
  }, () => new Response(null, { status: 302, headers: { Location: `${ORIGIN}/fixture_1.2.ipa?t=x`, 'Set-Cookie': 'a=1' } }));
});

test('/manifest points iOS at an IPA on the device or its network, nowhere else', async () => {
  const proxy = await worker();
  const ask = (fetchurl, name = 'Alarmy <&>') => proxy.fetch(new Request(`${ORIGIN}/manifest?bundleid=com.fixture&name=${encodeURIComponent(name)}&version=1.0&fetchurl=${encodeURIComponent(fetchurl)}`), {});
  const ok = await ask('http://192.168.1.104:8080/tempsigned.ipa');
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get('Content-Type'), 'application/xml; charset=utf-8');
  const plist = await ok.text();
  assert.ok(plist.includes('<string>http://192.168.1.104:8080/tempsigned.ipa</string>'));
  assert.ok(plist.includes('<string>Alarmy &lt;&amp;&gt;</string>'), 'the name is escaped');
  for (const bad of ['https://evil.invalid/a.ipa', 'http://8.8.8.8/a.ipa', 'http://127.0.0.1/a.zip', 'ftp://127.0.0.1/a.ipa', 'nonsense']) {
    assert.equal((await ask(bad)).status, 400, bad);
  }
});
