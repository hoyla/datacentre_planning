Serving the reader from Google Cloud Run
========================================

An **authenticated** copy of the published reader (`index.html`), hosted on
Cloud Run behind Google Identity-Aware Proxy so any `@guardian.co.uk` account
signs in with their normal Google login — no shared password to distribute.
This replaces password administration, not the EdgeOne deployment itself:
EdgeOne keeps building from git until it is retired as a separate decision.

The pattern — and every gotcha below — is inherited from the two deployments
that proved it on the same personal GCP account with Guardian users:
the tribunal Datasette demo
(`journalism-scrapers/uk-employment-tribunals-scraper-luke/docker/CLOUDRUN.md`)
and the meridian portal (`meridian/portal_service/README.md`).

Deliberate scope:

- **Just nginx and one baked page.** No pipeline, no database, no GCS. The
  image contains `index.html` (precompressed) and `robots.txt`, nothing else.
- **Personal Google account, not the Guardian one** — same boundary as the
  two sibling demos. The material is public-register data plus credited
  Barbour ABI, already public in this repository.
- **Authenticated, never open.** Deployed `--no-allow-unauthenticated`
  (fail-closed: with no IAP grant the service 403s everyone), with IAP in
  front restricted to `domain:guardian.co.uk`.

How the auth works
------------------

- the service is **private**; Cloud Run IAM refuses anonymous requests on
  its own, so the page cannot leak even before (or without) IAP;
- **IAP sits directly on the Cloud Run service** (no load balancer) and, for
  a signed-in `@guardian.co.uk` user, forwards the request to nginx, which
  serves open inside the perimeter;
- IAP is a **service-level** setting, configured **once** and persisting
  across content redeploys — `deploy.sh` runs are content-only and never
  touch access.

> **The load-bearing fact for a personal (no Cloud organisation) project:**
> IAP's Google-managed OAuth client returns `Error 604` for external users,
> so a **custom OAuth client is mandatory**. Sibling services' clients are
> in principle reusable (the redirect URI is client-scoped, not
> service-scoped), but Google shows a client secret **only at creation** —
> if the saved copy can't be found, create a **new client for this
> service** rather than regenerating an existing client's secret, which
> would break the sibling's IAP until updated. That is what happened here:
> the reader uses its own client (`dc-reader-iap`), created 2026-08-26,
> with its redirect URI
> `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`.
> Client ID and secret are saved outside the repository.

One-time setup
--------------

```sh
gcloud auth login                      # your PERSONAL google account
gcloud config set project <PROJECT_ID> # the existing project hosting the siblings
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com    # already enabled in an existing project
```

IAP wiring (one-time, per service)
----------------------------------

Set the shared vars, then run in order. Steps mirror the tribunal recipe;
the consent screen and OAuth client steps from that document are **skipped**
because the project's existing published consent screen and custom client
are reused.

```sh
PROJECT=<this-project-id>
REGION=europe-west2
SERVICE=dc-reader
PNUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud config set project "$PROJECT"
```

**1. Deploy private** — `./cloudrun/deploy.sh` (deploys `--no-allow-unauthenticated`).

**2. Let the IAP service agent invoke the service** (the agent already exists
in a project with IAP-gated siblings; the invoker binding is per-service):

```sh
gcloud beta services identity create --service=iap.googleapis.com --project="$PROJECT"  # idempotent
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:service-${PNUM}@gcp-sa-iap.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**3. Point this service's IAP at the existing custom OAuth client**
(IAP settings are per-service, so this is repeated for each service even
though the client is shared):

```sh
cat > /tmp/iap-oauth.yaml <<EOF
accessSettings:
  oauthSettings:
    clientId: <CLIENT_ID>
    clientSecret: <CLIENT_SECRET>
EOF
gcloud iap settings set /tmp/iap-oauth.yaml --project="$PROJECT" \
  --resource-type=cloud-run --region="$REGION" --service="$SERVICE"
rm /tmp/iap-oauth.yaml
```

**4. Enable IAP** on the service — the flag is GA now (no `beta`
component needed), and as of gcloud 580 it also sets up the IAP service
agent itself ("Setting IAP service agent…" in the output), making step 2
belt-and-braces rather than load-bearing:

```sh
gcloud run services update "$SERVICE" --region="$REGION" --iap
```

**5. Grant Guardian staff** (the single, persistent domain grant):

```sh
gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run --service="$SERVICE" --region="$REGION" \
  --member="domain:guardian.co.uk" --role="roles/iap.httpsResourceAccessor"
```

**6. Test** in a fresh **incognito** window with a `@guardian.co.uk`
account. (Stale cookies from earlier attempts keep replaying old errors.)
`deploy.sh` already probed the logged-out side: a 3xx to Google sign-in on
every path is the pass condition.

Gotchas (symptom → fix)
-----------------------

| Symptom | Cause / fix |
|---|---|
| Build says "using Buildpacks" and fails | `--source` must point at the directory holding the Dockerfile — `deploy.sh` passes `cloudrun/` for exactly this reason |
| Build fails: `index.html` not found | The `.gcloudignore` in this directory is missing — without it gcloud inherits the repo `.gitignore`, which ignores the copied page |
| Build fails: `PERMISSION_DENIED … default service account is missing permissions` | Grant once: `gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${PNUM}-compute@developer.gserviceaccount.com" --role="roles/cloudbuild.builds.builder"` |
| IAP **`Error 604`** | Step 2 (service agent + invoker) and/or step 3 (custom OAuth client not set on THIS service — the setting is per-service) |
| **`redirect_uri_mismatch`** | Only possible with a NEW client — the shared client's URI is already right. If ever needed: `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`, suffix intact |
| Sign-in then **"Access blocked by your admin"** | Guardian Workspace blocking the OAuth client — shouldn't occur with the reused, already-proven client |
| Signed-in Guardian user gets IAP **"You don't have access"** on first try | The `domain:` grant (step 5) still propagating — wait a minute, retry in fresh incognito |
| Google sign-in shows the sibling project's app name | Cosmetic: the consent screen (and its name) is per-project and shared. Rename it neutrally in Console → Google Auth Platform → Branding, if it grates |

Redeploying content — the routine
---------------------------------

**Nothing deploys automatically.** There is no GitHub Action here: pushing
to main updates only the EdgeOne deployment (which builds from git). The
Cloud Run copy changes exactly when you run the script below, and serves
whatever `index.html` sits at the root of the checkout you run it from —
committed or not.

**Once per machine:**

```sh
cp cloudrun/config.env.example cloudrun/config.env   # then set PROJECT in it
gcloud auth login                                    # personal account
```

**Each release**, from the repo root:

```sh
# 1. Regenerate the page from the database (writes index.html at the root):
scripts/export_reader.py --publish index.html

# 2. Release process as usual — the release PR carrying index.html to main.

# 3. From main, after the release PR merges (so EdgeOne and Cloud Run serve
#    identical bytes):
./cloudrun/deploy.sh
```

**What success looks like:** the script ends with a probe table in which
every path is `gated` (302 redirect to Google sign-in) and the line
`✓ Verified: anonymous requests are redirected to Google sign-in`. Then
spot-check signed-in access in an incognito window with a
`@guardian.co.uk` account.

**What failure looks like:** `index.html is only N bytes` means a
truncated export — re-run step 1; any `OPEN 2xx` row means the page is
reaching the internet ungated — do not share the URL, investigate. IAP and
the domain grant are untouched by redeploys, so access never needs
re-doing.

(Running step 3 from a branch before the release merges is also fine when
you deliberately want colleagues to see a preview at the gated URL —
just re-run it from main once the release lands.)

Managing access
---------------

The `domain:guardian.co.uk` grant covers every Guardian colleague — no
per-user admin. To narrow it, edit the IAP IAM binding (swap the domain
member for `user:` members or a Google Group) without redeploying:

```sh
gcloud iap web remove-iam-policy-binding --resource-type=cloud-run \
  --service=dc-reader --region=europe-west2 \
  --member="domain:guardian.co.uk" --role="roles/iap.httpsResourceAccessor"
```

Tearing it down
---------------

```sh
gcloud run services delete dc-reader --region europe-west2
```

Cost
----

~$0/month at rest: scale-to-zero (`--min-instances 0` — nginx cold-starts in
about a second, so no warm instance is kept, unlike the tribunal demo whose
Datasette boot takes ~18s), IAP itself free, no load balancer, a few MB of
image in Artifact Registry.
