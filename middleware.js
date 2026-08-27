/**
 * A signpost, not a gate. Every path here redirects to the reader's new
 * home behind Guardian sign-in.
 *
 * The reader moved to Cloud Run on 2026-08-26, where Google Identity-
 * Aware Proxy lets any @guardian.co.uk account in with their normal
 * login — no shared password to distribute, rotate or explain. This
 * deployment stays alive only so that the links colleagues have already
 * saved keep working, and it will be deleted once they have drained.
 *
 * What this replaced: a shared password exchanged for an HMAC-signed,
 * expiring, HttpOnly session cookie, enforced at the edge so that the
 * page and its embedded dataset were unreachable without a session.
 * That code is in the history of this file if it is ever wanted again;
 * it is not kept here commented out or behind an unreachable return,
 * because dead code in a security-relevant file is a liability that
 * reads like a fallback.
 *
 * Three deliberate choices:
 *
 * **It serves nothing.** Not the page, not the dataset, not robots.txt.
 * That is strictly safer than the gate it replaces — a gate can be
 * bypassed, and this one once was, by a double slash that skipped the
 * middleware and served 7.4 MB to anyone who typed the extra
 * character. There is nothing left here to leak.
 *
 * **It is unauthenticated, on purpose.** Gating the redirect would make
 * someone type the old password to be told where the reader went. The
 * destination is IAP-protected and fails closed, so an anonymous
 * visitor meets Google sign-in — which is exactly where they should
 * land.
 *
 * **302, not 301.** A permanent redirect is cached by browsers more or
 * less for ever, and this URL may need to change once more before the
 * deployment is retired.
 */

/**
 * The project-number hostname, not the legacy
 * `<service>-<hash>-<regioncode>.a.run.app` form that Cloud Run still
 * reports as `status.url`. Both answer today; this is the form Google
 * is moving to, and a redirect is a bookmark's second chance rather
 * than its third.
 */
const CLOUD_RUN = 'https://dc-reader-406994886626.europe-west2.run.app';

export async function middleware(context) {
  const url = new URL(context.request.url);

  // The query string is carried because it reaches us. The fragment is
  // not, and does not need to be: fragments are never sent to a server,
  // and a browser reapplies the original one to the redirect target
  // when the target carries none. So a bookmark of
  // `#site-SITE-Barrow/B14/2018/0568` still opens that site.
  return new Response(null, {
    status: 302,
    headers: {
      Location: CLOUD_RUN + url.pathname + url.search,
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer',
    },
  });
}
