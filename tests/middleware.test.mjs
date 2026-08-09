/**
 * Tests for the edge password gate.
 *
 * Security code, so the tests are about what must never happen: serving
 * the dataset without a session, accepting a forged or expired cookie,
 * and failing open when the environment is misconfigured.
 *
 *   node --test tests/middleware.test.mjs
 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';

// EdgeOne's runtime exposes WebCrypto as a global, as do browsers and
// Node 19 and later. Node 18 keeps it behind an import, so the harness
// supplies it here rather than the middleware reaching for a Node-only
// API it would never use in production.
if (!globalThis.crypto) globalThis.crypto = webcrypto;

import { config, middleware } from '../middleware.js';

const env = {
  DC_READER_PASSWORD: 'a long test password',
  DC_READER_SESSION_SECRET: 'test-session-secret-with-plenty-of-length',
};

const SERVED = 'the handover reader';

function context(request, overrides = {}) {
  return {
    request,
    env,
    next: () => new Response(SERVED, { status: 200 }),
    ...overrides,
  };
}

function post(password, next = '/') {
  const body = new URLSearchParams({ password, next });
  return new Request('https://dc.example/login', {
    method: 'POST',
    body,
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
  });
}

async function sessionCookie() {
  const response = await middleware(context(post(env.DC_READER_PASSWORD)));
  const setCookie = response.headers.get('set-cookie');
  return setCookie.split(';')[0];
}

test('the matcher is a catch-all, including paths with empty segments', () => {
  // '/:path*' left '//index.html' unmatched, and EdgeOne served the
  // reader unauthenticated. Assert the pattern, and that it really does
  // match the shapes that got through.
  assert.deepEqual(config.matcher, ['/(.*)']);
  const re = new RegExp('^' + config.matcher[0] + '$');
  for (const path of ['/', '/index.html', '//index.html', '///index.html',
                      '/data/priors/salesforce_documents.json',
                      '/%2findex.html', '/a/b/c']) {
    assert.ok(re.test(path), `${path} must be matched by the middleware`);
  }
});

test('fails closed when the environment is not configured', async () => {
  const response = await middleware(
    context(new Request('https://dc.example/'), { env: {} }));
  assert.equal(response.status, 503);
});

test('fails closed on a weak password or short signing secret', async () => {
  for (const bad of [
    { DC_READER_PASSWORD: 'short', DC_READER_SESSION_SECRET: env.DC_READER_SESSION_SECRET },
    { DC_READER_PASSWORD: env.DC_READER_PASSWORD, DC_READER_SESSION_SECRET: 'tiny' },
  ]) {
    const response = await middleware(
      context(new Request('https://dc.example/'), { env: bad }));
    assert.equal(response.status, 503);
  }
});

test('an anonymous request is redirected, never served', async () => {
  const response = await middleware(context(new Request('https://dc.example/')));
  assert.equal(response.status, 303);
  assert.match(response.headers.get('location'), /^\/login/);
});

test('a wrong password does not issue a session', async () => {
  const response = await middleware(context(post('not the password')));
  assert.equal(response.status, 401);
  assert.equal(response.headers.get('set-cookie'), null);
});

test('the right password issues a hardened session cookie', async () => {
  const response = await middleware(context(post(env.DC_READER_PASSWORD)));
  assert.equal(response.status, 303);
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Strict/);
});

test('a valid session reaches the reader', async () => {
  const cookie = await sessionCookie();
  const response = await middleware(context(
    new Request('https://dc.example/', { headers: { cookie } })));
  assert.equal(await response.text(), SERVED);
});

test('a tampered signature is rejected', async () => {
  const cookie = await sessionCookie();
  const [name, value] = cookie.split('=');
  const parts = value.split('.');
  parts[2] = parts[2].slice(0, -2) + (parts[2].endsWith('AA') ? 'BB' : 'AA');
  const response = await middleware(context(new Request('https://dc.example/', {
    headers: { cookie: `${name}=${parts.join('.')}` },
  })));
  assert.equal(response.status, 303, 'a forged cookie must not be honoured');
});

test('an extended expiry is rejected, because the expiry is signed', async () => {
  const cookie = await sessionCookie();
  const [name, value] = cookie.split('=');
  const parts = value.split('.');
  parts[1] = String(Number(parts[1]) + 60 * 60 * 24 * 365);
  const response = await middleware(context(new Request('https://dc.example/', {
    headers: { cookie: `${name}=${parts.join('.')}` },
  })));
  assert.equal(response.status, 303);
});

test('a session signed with a different secret is rejected', async () => {
  const cookie = await sessionCookie();
  const response = await middleware(context(
    new Request('https://dc.example/', { headers: { cookie } }),
    { env: { ...env, DC_READER_SESSION_SECRET: 'a-completely-different-secret-value!!' } }));
  assert.equal(response.status, 303);
});

test('the return path cannot be turned into an open redirect', async () => {
  for (const hostile of ['//evil.example/', 'https://evil.example/', 'javascript:alert(1)']) {
    const response = await middleware(context(post(env.DC_READER_PASSWORD, hostile)));
    assert.equal(response.headers.get('location'), '/',
      `${hostile} should collapse to the site root`);
  }
});

test('logout clears the cookie', async () => {
  const response = await middleware(context(new Request('https://dc.example/logout')));
  assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
});

test('the login page is not indexable and allows its own map tiles', async () => {
  const response = await middleware(context(new Request('https://dc.example/login')));
  const html = await response.text();
  assert.match(html, /noindex/);
  assert.match(response.headers.get('content-security-policy'),
    /img-src[^;]*tile\.openstreetmap\.org/);
});
