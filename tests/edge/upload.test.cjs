const assert = require('node:assert/strict');
const { createHash, webcrypto } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const { test } = require('node:test');

const fictionalKey = 'fictional-upload-key-used-only-in-tests';
const bundle = 'io.github.getaccretion.Fictional';
const digest = text => createHash('sha256').update(text).digest('hex');

function fixture(options = {}) {
  const objects = new Map();
  const s3Objects = new Map();
  const s3Writes = [];
  const builds = new Map();
  const announcements = [];
  const deleted = [];
  let handler;
  const storage = {
    async list(folder, { search }) {
      const prefix = folder + '/';
      return { data: [...objects.keys()].filter(k => k.startsWith(prefix) && k.slice(prefix.length).includes(search)).map(k => ({ name: k.slice(prefix.length) })), error: null };
    },
    async download(key) { return objects.has(key) ? { data: new Blob([objects.get(key)]), error: null } : { data: null, error: { statusCode: '404' } }; },
    async upload(key, bytes, options) {
      if (objects.has(key) && !options.upsert) return { data: null, error: { statusCode: '409', error: 'Duplicate' } };
      objects.set(key, Buffer.from(bytes));
      return { data: { path: key }, error: null };
    },
    async remove(keys) { for (const key of keys) { deleted.push(key); objects.delete(key); } return { error: null }; },
    async createSignedUploadUrl(key) { return { data: { signedUrl: 'https://upload.invalid/' + key }, error: null }; },
  };
  const admin = {
    storage: { from: () => storage },
    from(table) {
      const filters = {};
      return {
        select() { return this; },
        eq(key, value) { filters[key] = value; return this; },
        async maybeSingle() { return { data: builds.get(filters.bundle_id + '/' + filters.version) ?? null, error: null }; },
        async insert(row) {
          if (table === 'announcements') { announcements.push(row); return { error: null }; }
          const key = row.bundle_id + '/' + row.version;
          if (builds.has(key)) return { error: { code: '23505' } };
          builds.set(key, { ...row });
          return { data: null, error: null };
        },
      };
    },
  };
  const source = fs.readFileSync(path.join(__dirname, '../../supabase/functions/upload/index.ts'), 'utf8')
    .replace(/^import[\s\S]*?from "[^"]+";\r?\n/gm, '');
  vm.runInNewContext(stripTypeScriptTypes(source), {
    createClient: () => admin,
    S3Client: class {
      async send(command) {
        const { Key, Body, IfNoneMatch } = command.input;
        if (command.kind === 'head') {
          if (options.unavailable) throw new Error('fictional outage');
          return {};
        }
        if (command.kind === 'get') {
          if (!s3Objects.has(Key)) throw new Error('missing');
          return { Body: { transformToByteArray: async () => s3Objects.get(Key) } };
        }
        if (command.kind === 'delete') { s3Objects.delete(Key); return {}; }
        s3Writes.push(command.input);
        if (options.failWrites) throw new Error('fictional outage');
        if (s3Objects.has(Key) && IfNoneMatch === '*') throw { $metadata: { httpStatusCode: 412 } };
        s3Objects.set(Key, Buffer.from(Body));
        return {};
      }
    },
    HeadBucketCommand: class { kind = 'head'; constructor(input) { this.input = input; } },
    GetObjectCommand: class { kind = 'get'; constructor(input) { this.input = input; } },
    PutObjectCommand: class { kind = 'put'; constructor(input) { this.input = input; } },
    DeleteObjectCommand: class { kind = 'delete'; constructor(input) { this.input = input; } },
    getSignedUrl: async (_client, command) => 'https://s3-upload.invalid/' + command.input.Key,
    Deno: { env: { get: key => ({ SUPABASE_URL: 'https://fictional.invalid', SUPABASE_SERVICE_ROLE_KEY: 'fictional', UPLOAD_KEY: fictionalKey, ...(options.s3 ? { BUILDS_BUCKET: 'fictional', BUILDS_AWS_KEY_ID: 'fictional', BUILDS_AWS_SECRET: 'fictional' } : {}) })[key] }, serve: fn => { handler = fn; } },
    Request, Response, URL, Blob, TextEncoder, Uint8Array, crypto: webcrypto, AbortSignal,
    console: { warn() {} },
  });
  return {
    objects, builds, announcements, deleted, s3Objects, s3Writes,
    async request(body, finish = false, key = fictionalKey) {
      const response = await handler(new Request('https://fictional.invalid/upload' + (finish ? '?finish=1' : ''), {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-upload-key': key }, body: JSON.stringify(body),
      }));
      return { status: response.status, body: await response.json() };
    },
  };
}

test('a rejected finish request leaves every published object unchanged', async () => {
  const f = fixture();
  const original = 'published bytes';
  const key = bundle + '/1.0.0.ipa';
  f.objects.set(key, Buffer.from(original));
  f.builds.set(bundle + '/1.0.0', { path: key, sha256: digest(original) });
  const result = await f.request({ bundle_id: bundle, version: '1.0.0', sha256: '0'.repeat(64) }, true);
  assert.equal(result.status, 409);
  assert.equal(f.objects.get(key).toString(), original);
  assert.deepEqual(f.deleted, []);
});

test('S3 publications use conditional final writes and retain a Supabase fallback', async () => {
  const f = fixture({ s3: true });
  const body = { bundle_id: bundle, version: '1.0.0', sha256: digest('S3 bytes') };
  const prepared = await f.request(body);
  assert.match(prepared.body.signedUrl, /^https:\/\/s3-upload.invalid\/staging\//);
  f.s3Objects.set(prepared.body.path, Buffer.from('S3 bytes'));
  const finalPath = bundle + '/1.0.0-' + body.sha256 + '.ipa';
  // Another request already wrote these identical, content-addressed bytes.
  f.s3Objects.set(finalPath, Buffer.from('S3 bytes'));
  const result = await f.request({ ...body, upload_id: prepared.body.upload_id }, true);
  assert.equal(result.status, 200);
  assert.equal(f.s3Writes[0].IfNoneMatch, '*');
  assert.equal(f.s3Objects.get(finalPath).toString(), 'S3 bytes');
  assert.equal(f.objects.get(finalPath).toString(), 'S3 bytes');
  assert.equal(f.s3Objects.has(prepared.body.path), false);
});

test('an S3 outage falls back to a complete Supabase publication', async () => {
  const f = fixture({ s3: true, unavailable: true, failWrites: true });
  const body = { bundle_id: bundle, version: '1.0.0', sha256: digest('fallback bytes') };
  const prepared = await f.request(body);
  assert.match(prepared.body.signedUrl, /^https:\/\/upload.invalid\/staging\//);
  f.objects.set(prepared.body.path, Buffer.from('fallback bytes'));
  const result = await f.request({ ...body, upload_id: prepared.body.upload_id }, true);
  assert.equal(result.status, 200);
  assert.equal(f.objects.get(result.body.path).toString(), 'fallback bytes');
  assert.equal(f.builds.size, 1);
  assert.equal(f.objects.has(prepared.body.path), false);
});

test('preparation returns an isolated staging path and publication is idempotent', async () => {
  const f = fixture();
  const body = { bundle_id: bundle, version: '1.0.0', sha256: digest('new bytes') };
  const prepared = await f.request(body);
  assert.equal(prepared.status, 200);
  assert.match(prepared.body.upload_id, /^[0-9a-f-]{36}$/);
  assert.match(prepared.body.path, /^staging\//);
  f.objects.set(prepared.body.path, Buffer.from('new bytes'));
  const complete = await f.request({ ...body, upload_id: prepared.body.upload_id }, true);
  assert.equal(complete.status, 200);
  const published = f.builds.get(bundle + '/1.0.0');
  assert.equal(published.path, bundle + '/1.0.0-' + digest('new bytes') + '.ipa');
  assert.equal(f.objects.get(published.path).toString(), 'new bytes');
  const replay = await f.request({ ...body, upload_id: prepared.body.upload_id }, true);
  assert.equal(replay.status, 200);
  assert.equal(f.builds.size, 1);
  assert.equal(f.announcements.length, 1);
  assert.equal(f.objects.get(published.path).toString(), 'new bytes');
  assert.equal(f.deleted.includes(published.path), false);
  const preparedAgain = await f.request(body);
  assert.equal(preparedAgain.body.published, true);
  assert.equal(preparedAgain.body.signedUrl, undefined);
});

test('conflicting completions cannot replace the winning publication', async () => {
  const f = fixture();
  const bodies = ['one', 'two'].map(text => ({ bundle_id: bundle, version: '1.0.0', sha256: digest(text) }));
  const prepared = await Promise.all(bodies.map(body => f.request(body)));
  prepared.forEach((result, i) => f.objects.set(result.body.path, Buffer.from(['one', 'two'][i])));
  const results = await Promise.all(bodies.map((body, i) => f.request({ ...body, upload_id: prepared[i].body.upload_id }, true)));
  assert.deepEqual(results.map(r => r.status).sort(), [200, 409]);
  assert.equal(f.builds.size, 1);
  assert.equal(f.announcements.length, 1);
  const winner = f.builds.get(bundle + '/1.0.0');
  assert.equal(digest(f.objects.get(winner.path)), winner.sha256);
  assert.equal(f.deleted.includes(winner.path), false);
});

test('invalid JSON shapes, missing fingerprints and invalid upload IDs fail safely', async () => {
  const f = fixture();
  for (const value of [null, [], {}, { bundle_id: bundle, version: '1.0.0' }]) {
    assert.equal((await f.request(value)).status, 400);
  }
  assert.equal((await f.request({ bundle_id: bundle, version: '1.0.0', sha256: digest('x'), upload_id: '../bad' }, true)).status, 400);
  assert.equal((await f.request({}, false, 'wrong')).status, 401);
  assert.equal(f.builds.size, 0);
  assert.deepEqual(f.deleted, []);
});

test('malformed optional metadata is rejected before preparing or publishing', async () => {
  const f = fixture();
  const body = { bundle_id: bundle, version: '1.0.0', sha256: digest('new bytes') };
  const prepared = await f.request(body);
  f.objects.set(prepared.body.path, Buffer.from('new bytes'));
  for (const extra of [{ name: 123 }, { notes: {} }, { announce: 'false' }, { name: null }]) {
    assert.equal((await f.request({ ...body, ...extra })).status, 400);
    assert.equal((await f.request({ ...body, ...extra, upload_id: prepared.body.upload_id }, true)).status, 400);
  }
  assert.equal(f.builds.size, 0);
  assert.equal(f.announcements.length, 0);
  assert.equal(f.objects.get(prepared.body.path).toString(), 'new bytes');
  assert.deepEqual(f.deleted, []);
});
