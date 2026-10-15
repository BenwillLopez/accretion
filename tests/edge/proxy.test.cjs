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

function downloadFunction(links) {
  let handler;
  const issued = [];
  const admin = {
    auth: { getUser: async () => ({ data: { user: { id: 'fictional-user' } } }) },
    storage: { from: () => ({ createSignedUrl: async () => ({ data: null, error: { message: 'none' } }) }) },
    from(table) {
      const query = {
        select() { return this; }, eq() { return this; }, gte() { return this; },
        async maybeSingle() { return { data: { banned: false }, error: null }; },
        then(resolve, reject) {
          const result = table === 'download_log' ? { count: 0, error: null }
            : table === 'hosted_builds' ? { data: [], error: null }
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
