/**
 * Password gate for the handover reader, enforced at the EdgeOne edge.
 *
 * This runs before any asset is served, so the page, its embedded data
 * and anything else under the deployment are unreachable without a
 * session. That is the difference between this and a password prompt
 * written in the page itself: a client-side gate ships the data to the
 * browser and then asks permission to show it, which view-source
 * defeats in a second.
 *
 * Adapted from the same pattern in the myplants project, deliberately
 * unchanged in its essentials — a shared password exchanged for an
 * HMAC-signed, expiring, HttpOnly session cookie, with timing-safe
 * comparison and no third-party dependency.
 *
 * Two environment variables, set in the EdgeOne dashboard and never in
 * the repository:
 *
 *   DC_READER_PASSWORD        the shared password (>= 12 characters)
 *   DC_READER_SESSION_SECRET  signing key for the cookie (>= 32 characters)
 *
 * Missing or too-short values fail closed with a 503 rather than
 * serving the dataset unprotected.
 *
 * IMPORTANT: this protects the EdgeOne deployment, not the repository.
 * If the reader is also committed to a public GitHub repository, it is
 * readable there regardless of what this does — see README.
 */

const COOKIE_NAME = 'dc_reader_session';
const SESSION_SECONDS = 14 * 24 * 60 * 60;   // a fortnight; a reporting sprint
const MIN_PASSWORD = 12;
const MIN_SECRET = 32;
const encoder = new TextEncoder();

function securityHeaders(contentType = 'text/html; charset=utf-8') {
  return {
    'Cache-Control': 'no-store, max-age=0',
    // The reader is self-contained apart from its map tiles, so the
    // policy names exactly that one origin and nothing else.
    'Content-Security-Policy': [
      "default-src 'none'",
      "img-src 'self' data: https://tile.openstreetmap.org",
      "style-src 'unsafe-inline'",
      "script-src 'unsafe-inline'",
      "form-action 'self'",
      "base-uri 'none'",
      "frame-ancestors 'none'",
    ].join('; '),
    'Content-Type': contentType,
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function bytesToBase64Url(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

function base64UrlToBytes(value) {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function hmacKey(secret, usages) {
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    usages,
  );
}

async function sign(value, secret) {
  const key = await hmacKey(secret, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(value));
  return bytesToBase64Url(new Uint8Array(signature));
}

async function createSessionToken(secret, now = Date.now()) {
  const expiresAt = Math.floor(now / 1000) + SESSION_SECONDS;
  const payload = `v1.${expiresAt}`;
  return `${payload}.${await sign(payload, secret)}`;
}

async function verifySessionToken(token, secret, now = Date.now()) {
  if (typeof token !== 'string') return false;

  const parts = token.split('.');
  if (parts.length !== 3 || parts[0] !== 'v1') return false;

  const expiresAt = Number(parts[1]);
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= Math.floor(now / 1000)) return false;

  try {
    const key = await hmacKey(secret, ['verify']);
    return crypto.subtle.verify(
      'HMAC',
      key,
      base64UrlToBytes(parts[2]),
      encoder.encode(`${parts[0]}.${parts[1]}`),
    );
  } catch {
    return false;
  }
}

/** Compare digests rather than strings, so timing does not leak length. */
async function secureEqual(left, right) {
  const digest = async (value) => new Uint8Array(
    await crypto.subtle.digest('SHA-256', encoder.encode(String(value))),
  );
  const [leftDigest, rightDigest] = await Promise.all([digest(left), digest(right)]);
  let difference = 0;
  for (let index = 0; index < leftDigest.length; index += 1) {
    difference |= leftDigest[index] ^ rightDigest[index];
  }
  return difference === 0;
}

function readCookie(request, name) {
  const cookieHeader = request.headers.get('cookie') || '';
  for (const part of cookieHeader.split(';')) {
    const separator = part.indexOf('=');
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() === name) {
      return part.slice(separator + 1).trim();
    }
  }
  return null;
}

/** Only same-site absolute paths, so ?next= cannot become an open redirect. */
function safeReturnPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/';
  return value;
}

function loginPage(nextPath, error = '', status = 200) {
  const message = error
    ? `<p class="error" role="alert">${escapeHtml(error)}</p>`
    : '<p class="intro">This dataset supports unpublished reporting. Enter the password you were given.</p>';

  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>UK data-centre planning — handover</title>
  <style>
    :root { color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --bg:#f6f7f9; --card:#fff; --fg:#16171b; --mut:#63666e; --line:#e4e5e9; --accent:#0b5fff; }
    @media (prefers-color-scheme: dark) {
      :root { --bg:#0f1014; --card:#17181e; --fg:#e9eaee; --mut:#989aa4; --line:#282a33; --accent:#7ea6ff; }
    }
    * { box-sizing: border-box; }
    body { min-height:100vh; margin:0; display:grid; place-items:center; padding:1.25rem;
           background:var(--bg); color:var(--fg); }
    main { width:min(100%,25rem); padding:clamp(1.5rem,5vw,2.25rem); border:1px solid var(--line);
           border-radius:14px; background:var(--card); }
    .eyebrow { margin:0 0 .55rem; color:var(--mut); font-size:.7rem; font-weight:700;
               letter-spacing:.12em; text-transform:uppercase; }
    h1 { margin:0; font-size:1.4rem; line-height:1.25; letter-spacing:-.01em; }
    .intro, .error { margin:1rem 0; line-height:1.55; font-size:.9rem; }
    .intro { color:var(--mut); }
    .error { padding:.7rem .85rem; border-radius:8px; color:#8a2a16; background:#fae7df; font-weight:600; }
    label { display:block; margin-bottom:.4rem; font-size:.72rem; font-weight:700;
            text-transform:uppercase; letter-spacing:.08em; color:var(--mut); }
    input { width:100%; min-height:2.9rem; padding:.7rem .9rem; border:1px solid var(--line);
            border-radius:8px; background:var(--bg); color:var(--fg); font:inherit; }
    input:focus { outline:2px solid var(--accent); border-color:var(--accent); }
    button { width:100%; min-height:2.9rem; margin-top:.9rem; border:0; border-radius:8px;
             background:var(--accent); color:#fff; font:inherit; font-weight:700; cursor:pointer; }
    .foot { margin:1.1rem 0 0; font-size:.75rem; color:var(--mut); line-height:1.5; }
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">Guardian data team</p>
    <h1>UK data-centre planning</h1>
    ${message}
    <form method="post" action="/login">
      <input type="hidden" name="next" value="${escapeHtml(nextPath)}">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
      <button type="submit">Open the handover</button>
    </form>
    <p class="foot">Contains licensed Barbour ABI data and material relating to
      unpublished reporting. Please do not forward the link or the password.</p>
  </main>
</body>
</html>`;

  return new Response(html, { status, headers: securityHeaders() });
}

function configurationError() {
  return new Response(
    'The handover reader is not configured for access yet.',
    { status: 503, headers: securityHeaders('text/plain; charset=utf-8') },
  );
}

function redirectResponse(location, headers = {}) {
  return new Response(null, {
    status: 303,
    headers: {
      ...securityHeaders('text/plain; charset=utf-8'),
      Location: location,
      ...headers,
    },
  });
}

export async function middleware(context) {
  const { request, next, env } = context;
  const password = env?.DC_READER_PASSWORD;
  const sessionSecret = env?.DC_READER_SESSION_SECRET;

  // Fail closed. An unset variable must never mean "serve it to anyone".
  if (
    typeof password !== 'string'
    || password.length < MIN_PASSWORD
    || typeof sessionSecret !== 'string'
    || sessionSecret.length < MIN_SECRET
  ) return configurationError();

  const url = new URL(request.url);

  if (url.pathname === '/logout') {
    return redirectResponse('/login', {
      'Set-Cookie': `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`,
    });
  }

  if (url.pathname === '/login') {
    const nextPath = safeReturnPath(url.searchParams.get('next'));

    if (request.method === 'GET' || request.method === 'HEAD') {
      return loginPage(nextPath);
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', {
        status: 405,
        headers: { ...securityHeaders('text/plain; charset=utf-8'), Allow: 'GET, HEAD, POST' },
      });
    }

    let form;
    try {
      form = await request.formData();
    } catch {
      return loginPage('/', 'The login request could not be read. Please try again.', 400);
    }

    const submittedPassword = form.get('password');
    const submittedNextPath = safeReturnPath(form.get('next'));
    if (typeof submittedPassword !== 'string' || !(await secureEqual(submittedPassword, password))) {
      return loginPage(submittedNextPath, 'That password did not match.', 401);
    }

    const token = await createSessionToken(sessionSecret);
    return redirectResponse(submittedNextPath, {
      'Set-Cookie': `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_SECONDS}`,
    });
  }

  const token = readCookie(request, COOKIE_NAME);
  if (await verifySessionToken(token, sessionSecret)) return next();

  const returnPath = `${url.pathname}${url.search}`;
  return redirectResponse(`/login?next=${encodeURIComponent(returnPath)}`);
}

export const config = {
  matcher: ['/:path*'],
};
