#!/bin/bash
# Deploy the datacentre reader to Google Cloud Run as a PRIVATE service for
# Guardian colleagues, following the pattern proven by the tribunal Datasette
# demo and the meridian portal (personal GCP account, IAP at the Cloud Run
# edge, domain:guardian.co.uk grant — see CLOUDRUN.md for the one-time IAP
# wiring, which this script never touches).
#
# It will:
#   1. copy the repo-root index.html and robots.txt into this build context
#      (the root stays canonical — EdgeOne keeps building from it unchanged);
#   2. deploy via Cloud Build from source as a PRIVATE service
#      (--no-allow-unauthenticated);
#   3. verify the LIVE deployment refuses anonymous access — on the front
#      page and on the bypass-class path variants that once caught EdgeOne —
#      before declaring success.
#
# Fail-closed by construction: a private service with no IAP grant 403s
# everyone, so the page can never reach the internet open. The gate is IAP,
# configured ONCE per service in GCP and persisting across content
# redeploys; this script is content-only.
#
# One-time prereqs (see CLOUDRUN.md):
#   gcloud auth login                              # your PERSONAL google account
#   gcloud config set project <PROJECT_ID>
#   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
#
# Usage:
#   ./cloudrun/deploy.sh          # deploy the current repo-root index.html
#
# Tunables (env): PROJECT, REGION, SERVICE, MEMORY, MAX_INSTANCES, MIN_INSTANCES.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
READER="$REPO/index.html"
ROBOTS="$REPO/robots.txt"

# The target PROJECT lives in a gitignored config.env (copy config.env.example)
# so the routine is just `./cloudrun/deploy.sh` — an explicit PROJECT=<id> on
# the command line still wins. Deliberately NO fallback to the gcloud default
# project: a config default silently shared across repos is how a deploy for
# one tool lands in another tool's project.
[ -f "$HERE/config.env" ] && . "$HERE/config.env"

REGION="${REGION:-europe-west2}"
SERVICE="${SERVICE:-dc-reader}"
# nginx serving one baked file needs almost nothing; cold start is ~1s so
# scale-to-zero costs no meaningful latency (unlike the tribunal demo's 18s
# Datasette boot, which is why THAT keeps a warm instance and this doesn't).
MEMORY="${MEMORY:-256Mi}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
PROJECT="${PROJECT:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not found on PATH"
[ -n "$PROJECT" ] || die "no PROJECT set — copy cloudrun/config.env.example to cloudrun/config.env and fill it in (or PROJECT=<id> $0)"
gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q . \
    || die "no active gcloud account — run: gcloud auth login (use your personal account)"

# --- sanity: the page we are about to publish -------------------------------
# The reader runs to ~17MB; a floor of 5MB catches a truncated or empty
# export long before it reaches colleagues.
[ -f "$READER" ] || die "no reader at $READER — run scripts/export_reader.py --publish index.html first"
size=$(wc -c < "$READER" | tr -d ' ')
[ "$size" -ge 5000000 ] || die "index.html is only $size bytes — looks truncated, refusing to deploy"
[ -f "$ROBOTS" ] || die "no robots.txt at $ROBOTS"
echo "Reader: $(ls -lh "$READER" | awk '{print $5}'), built $(date -r "$READER" '+%Y-%m-%d %H:%M')"

# --- build context ----------------------------------------------------------
# The copies are gitignored; .gcloudignore in this directory is what keeps
# them IN the Cloud Build upload (without it, gcloud silently inherits the
# repo .gitignore and the build fails with index.html missing).
cp -f "$READER" "$HERE/index.html"
cp -f "$ROBOTS" "$HERE/robots.txt"

# --- deploy ------------------------------------------------------------------
echo "Deploying '$SERVICE' to Cloud Run ($REGION, project $PROJECT)..."
gcloud run deploy "$SERVICE" \
    --project "$PROJECT" \
    --source "$HERE" \
    --region "$REGION" \
    --no-allow-unauthenticated \
    --memory "$MEMORY" \
    --cpu 1 \
    --max-instances "$MAX_INSTANCES" \
    --min-instances "$MIN_INSTANCES" \
    --port 8080

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" \
        --format='value(status.url)' 2>/dev/null || true)
[ -n "$URL" ] || { echo "Deployed, but could not read the service URL. Check the Cloud Run console."; exit 0; }

# --- verify the LIVE deployment is gated ------------------------------------
# With IAP live, an anonymous request is redirected to Google sign-in (3xx to
# accounts.google.com). Before IAP is wired, a private service answers 401/403
# from IAM. EITHER is "gated"; a 2xx means the page is reaching the internet
# open. We probe the front page plus the bypass-class variants — a double
# slash once skipped the EdgeOne middleware entirely; IAP gates at the edge
# so the class shouldn't apply, but prove it every deploy rather than assume.
echo ""
open_paths=""
saw_iap=false
for path in "/" "//" "/index.html" "//index.html" "/robots.txt" "/%2e/index.html"; do
    read -r code dest <<< "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$URL$path" || echo "000")"
    case "$code" in
        301|302|303|307|308)
            # Only a redirect to Google sign-in is IAP; Cloud Run's front end
            # also 302s path-normalisation cases (/%2e/… → /…) whose targets
            # are themselves gated — count those as same-host, not sign-in.
            case "$dest" in
                https://accounts.google.com/*|https://iap.googleapis.com/*)
                    echo "  gated  $code  $path (redirect to sign-in — IAP)"; saw_iap=true ;;
                "$URL"/*)
                    echo "  -      $code  $path (same-host normalisation → ${dest#"$URL"})" ;;
                *)
                    echo "  OPEN   $code  $path (redirects to $dest — investigate)"
                    open_paths="$open_paths $path" ;;
            esac ;;
        401|403)             echo "  gated  $code  $path (private — not open)" ;;
        404)                 echo "  -      $code  $path" ;;
        000)                 echo "  ?      ---  $path (unreachable)" ;;
        *)                   echo "  OPEN   $code  $path"; open_paths="$open_paths $path" ;;
    esac
done
echo ""
if [ -n "$open_paths" ]; then
    echo "⚠ WARNING: anonymous 2xx on:$open_paths"
    echo "  The reader may be serving OPEN. Investigate before sharing the URL."
    exit 1
elif $saw_iap; then
    echo "✓ Verified: anonymous requests are redirected to Google sign-in (IAP gating)."
    echo "Share with colleagues — any @guardian.co.uk account: $URL/"
else
    echo "✓ Verified: the service is private (401/403), but IAP is not fully wired yet"
    echo "  (service agent + invoker, custom OAuth client, IAP enabled, domain grant)."
    echo "  Finish CLOUDRUN.md's one-time setup, then re-test in an incognito window."
fi
