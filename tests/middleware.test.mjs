/**
 * The EdgeOne deployment is a signpost now, and these are the rules a
 * signpost has to keep.
 *
 * It replaced a password gate on 2026-08-26, when the reader moved
 * behind Guardian sign-in. The tests that stood here checked the gate:
 * timing-safe comparison, cookie signing, the double-slash bypass that
 * once served 7.4 MB to anyone who typed an extra character. None of
 * that applies to a page that serves nothing — but the failure it was
 * guarding against does, in a new form. A redirect that drops a path,
 * loses a query string or answers some routes and not others sends a
 * reporter somewhere other than the link they saved, and looks like it
 * worked.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { middleware } from '../middleware.js';

const CLOUD_RUN = 'https://dc-reader-406994886626.europe-west2.run.app';

const context = (url, method = 'GET') => ({
  request: new Request(url, { method }),
  next: async () => new Response('the reader', { status: 200 }),
  env: {},
});

const PATHS = [
  '/',
  '/index.html',
  '//index.html',            // the bypass that defeated the old gate
  '/%2e%2e/index.html',
  '/robots.txt',
  '/data/priors/salesforce_documents.json',
  '/login',                  // nothing to log in to any more
  '/logout',
  '/anything/at/all',
];

for (const path of PATHS) {
  test(`redirects ${path}`, async () => {
    const response = await middleware(context(`https://example.test${path}`));
    assert.equal(response.status, 302, `${path} did not redirect`);
    assert.ok(
      response.headers.get('Location').startsWith(CLOUD_RUN),
      `${path} redirected somewhere other than Cloud Run`);
  });
}

test('serves no body, on any path', async () => {
  for (const path of PATHS) {
    const response = await middleware(context(`https://example.test${path}`));
    assert.equal(await response.text(), '',
      `${path} returned a body; this deployment must serve nothing at all`);
  }
});

test('never calls next(), so no asset is ever served', async () => {
  let called = false;
  const ctx = context('https://example.test/index.html');
  ctx.next = async () => { called = true; return new Response('leak'); };
  await middleware(ctx);
  assert.equal(called, false,
    'middleware fell through to the origin, which still holds the reader');
});

test('carries the path, so a deep link lands where it was pointing', async () => {
  const response = await middleware(
    context('https://example.test/some/deep/path.html'));
  assert.equal(response.headers.get('Location'),
    `${CLOUD_RUN}/some/deep/path.html`);
});

test('carries the query string, which does reach a server', async () => {
  const response = await middleware(
    context('https://example.test/index.html?view=sites&q=slough'));
  assert.equal(response.headers.get('Location'),
    `${CLOUD_RUN}/index.html?view=sites&q=slough`);
});

test('redirects POST as well as GET', async () => {
  const response = await middleware(
    context('https://example.test/login', 'POST'));
  assert.equal(response.status, 302);
});

test('is 302, not 301: this URL may change again before retirement', async () => {
  const response = await middleware(context('https://example.test/'));
  assert.equal(response.status, 302);
});

test('is not cached, so a later change is not stuck in a browser', async () => {
  const response = await middleware(context('https://example.test/'));
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

test('points at the project-number hostname, not the legacy one', async () => {
  const response = await middleware(context('https://example.test/'));
  const location = response.headers.get('Location');
  assert.ok(!location.includes('.a.run.app'),
    'redirects to the legacy Cloud Run hostname, which is the form Google '
    + 'is moving away from — a bookmark gets one second chance, not two');
  assert.ok(location.includes('.europe-west2.run.app'));
});
