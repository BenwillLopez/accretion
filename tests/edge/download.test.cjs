const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');

function fixture(options = {}) {
  let handler;
  const issued = [];
  const admin = {
    auth: { getUser: async () => ({ data: { user: options.anonymous ? null : { id: 'fictional-user' } } }) },
    storage: { from: () => ({ createSignedUrl: async () => ({ data: { signedUrl: 'https://private.invalid/signed-build' }, error: null }) }) },
    from(table) {
      const query = {
        select() { return this; }, eq() { return this; }, gte() { return this; },
        async maybeSingle() { return { data: options.missingProfile ? null : { banned: !!options.banned }, error: options.profileError ? { code: 'offline' } : null }; },
        then(resolve, reject) {
          const result = table === 'download_log'
            ? { count: options.count ?? 0, error: options.quotaError ? { code: 'offline' } : null }
            : { data: [{ path: 'app/stable.ipa', version: '1.0.30' }, { path: 'app/beta.ipa', version: '1.0.30.1' }], error: options.buildsError ? { code: 'offline' } : null };
          return Promise.resolve(result).then(resolve, reject);
        },
        async insert(row) { issued.push(row); return { error: options.logError ? { code: options.logError } : null }; },
      };
      return query;
    },
  };
  const source = fs.readFileSync(path.join(__dirname, '../../supabase/functions/download/index.ts'), 'utf8')
    .replace(/^import[^\n]+\r?\n/gm, '');
  vm.runInNewContext(stripTypeScriptTypes(source), {
    createClient: () => admin,
    Deno: { env: { get: () => '' }, serve: fn => { handler = fn; } },
    Request, Response, URL, Date, AbortSignal, console: { warn() {} },
  });
  return {
    issued,
    request: () => handler(new Request('https://fictional.invalid/download?app=io.github.getaccretion.Accretion', { headers: { Authorization: 'Bearer fictional' } })),
  };
}

test('authorized downloads redirect only after recording issuance', async () => {
  const f = fixture();
  const response = await f.request();
  assert.equal(response.status, 302);
  assert.equal(response.headers.get('Location'), 'https://private.invalid/signed-build');
  assert.equal(f.issued.length, 1);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

test('access, catalogue and quota failures never disclose a signed redirect', async () => {
  for (const [options, expected] of [
    [{ anonymous: true }, 401], [{ banned: true }, 403], [{ missingProfile: true }, 403],
    [{ profileError: true }, 503], [{ quotaError: true }, 503], [{ buildsError: true }, 503],
    [{ count: 30 }, 429], [{ logError: 'PT403' }, 403], [{ logError: 'PT429' }, 429], [{ logError: 'offline' }, 503],
  ]) {
    const f = fixture(options);
    const response = await f.request();
    assert.equal(response.status, expected, JSON.stringify(options));
    assert.equal(response.headers.has('Location'), false);
  }
});
