#!/usr/bin/env bash
# Probe the published reader's password gate from outside, with no cookie.
#
# The gate has been wrong twice in ways a browser could not show. A double
# slash once skipped the middleware entirely and EdgeOne served the whole
# 7.4 MB dataset with a 200 to anyone who typed the extra slash; nothing
# about that was visible from a session that already had a cookie.
#
# So this asks the deployment itself, unauthenticated, with --path-as-is so
# curl does not helpfully normalise away the very thing being tested. It is
# the durable form of a battery that was run by hand on 2026-08-10 — which
# is precisely the "remembered, repeated, and broken anyway" pattern this
# project has a hook and a migration self-check for.
#
# Usage:
#   scripts/probe_gate.sh https://dc-review-gdn-hoyla.edgeone.app
#
# Exit 0 if every path is refused; 1 if anything leaks. Run it after every
# deploy — the reader is rebuilt and redeployed on merge, and a matcher
# change is exactly the kind of edit whose blast radius is invisible.

set -uo pipefail
BASE="${1:-}"
if [ -z "$BASE" ]; then
  echo "usage: $0 <base-url>   e.g. $0 https://example.edgeone.app" >&2
  exit 2
fi
BASE="${BASE%/}"

# Every path that must redirect. The first three are the bypass class that
# actually happened; the traversal and encoding forms are the neighbours it
# was found among.
PATHS=(
  "/" "/index.html"
  "//index.html" "///index.html" "////index.html"
  "/%2findex.html" "/%2Findex.html" "/%252findex.html"
  "/./index.html" "/../index.html" "/a/../index.html"
  "/..%2findex.html" "/%2e%2e/index.html" "/.%2e/index.html"
  "/index.html?x=1" "/INDEX.HTML" "/index.html#frag"
  "/robots.txt" "/data/priors/salesforce_documents.json"
  "/%00index.html" "/index.html%20" "/;/index.html"
)

fail=0; checked=0
printf '%-28s %-6s %-9s %s\n' "PATH" "CODE" "BYTES" "VERDICT"
for p in "${PATHS[@]}"; do
  read -r code size < <(curl -sS --path-as-is -m 20 -o /dev/null \
      -w '%{http_code} %{size_download}' "$BASE$p" 2>/dev/null || echo "000 0")
  checked=$((checked+1))
  # A redirect is right. A 200 carrying a payload is the failure that
  # matters: the dataset reached the client before anything asked who
  # they were. A 403/404 is odd but not a leak.
  if [ "$code" = "303" ] || [ "$code" = "302" ] || [ "$code" = "307" ]; then
    verdict="ok (redirected)"
  elif [ "$code" = "200" ] && [ "$size" -gt 5000 ]; then
    verdict="LEAK — served $size bytes unauthenticated"; fail=1
  elif [ "$code" = "200" ]; then
    verdict="200 but small ($size b) — check it is the login page"; fail=1
  elif [ "$code" = "000" ]; then
    verdict="no response (network?)"; fail=1
  else
    verdict="$code — not a leak, but unexpected"
  fi
  printf '%-28s %-6s %-9s %s\n' "$p" "$code" "$size" "$verdict"
done

echo
# A forged cookie must not be accepted: the session token is signed, and a
# gate that trusts an unsigned cookie is not a gate.
forged=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' \
  -H 'Cookie: dc_reader_session=v1.9999999999.deadbeefdeadbeefdeadbeef' \
  "$BASE/index.html" 2>/dev/null || echo 000)
if [ "$forged" = "303" ] || [ "$forged" = "302" ]; then
  echo "forged session cookie: rejected ($forged)"
else
  echo "forged session cookie: ACCEPTED ($forged) — the signature is not being checked"; fail=1
fi

echo
if [ "$fail" = "0" ]; then
  echo "PASS — $checked paths, all refused, forged cookie rejected"
else
  echo "FAIL — the gate is serving something it should not"
fi
exit "$fail"
