# Deploying Cognith

The backend runs on **Cloud Run**, the frontend on **Firebase App Hosting**, and learner data
lives in **Firestore**. The knowledge engine (course packs, `knowledge/*.md`, `index.json`)
ships inside the backend image and is only ever read, never rebuilt, on Cloud Run.

```text
Browser ──▶ App Hosting (Next.js) ──fetch──▶ Cloud Run: cognith-api (FastAPI)
                                                ├──▶ courses/ + index.json   in the image, read-only
                                                ├──▶ Gemini API              key from Secret Manager
                                                └──▶ Firestore               learners, evidence, challenges
```

Do the parts in order. Part A is clicking in the console; the rest is a few commands.

## Names used in this guide

| What | Value |
|---|---|
| Project ID | `PROJECT_ID`, which you choose in A1. Replace it everywhere below. |
| Region | `us-central1`, for everything |
| Cloud Run service | `cognith-api` |
| Service account | `cognith-api@PROJECT_ID.iam.gserviceaccount.com` |
| Secret | `gemini-api-key` |
| App Hosting backend | `cognith-web` |
| `API_URL` | The backend URL that Part C prints |
| `WEB_URL` | The frontend URL that Part D shows |

## What you need

- A Google account.
- A payment card. Cloud Run and App Hosting need the Blaze (pay-as-you-go) plan.
- A Gemini API key, or create one in A5.
- Admin rights on the GitHub repo `Newstein123/cognipath`, to install the Firebase GitHub app in D2.
- On your laptop: `gcloud`, Python 3.10+, git. Docker is not needed; Cloud Build builds the image.
- About 45 minutes. The first deploy of each part takes 5–10 minutes.

---

## Part A — Create the project and services (console, once)

### A1. Create the Firebase project

1. Go to <https://console.firebase.google.com>.
2. Click **Create a project** (older consoles: **Add project**).
3. Enter a name, e.g. `cognith`. The **project ID** is shown under the name; it can be
   edited now and never again. This is your `PROJECT_ID`.
4. Turn **Google Analytics** off (not used). Click **Create project**.

This also creates the Google Cloud project with the same ID.

### A2. Turn on billing (Blaze plan)

1. At the bottom of the left sidebar, the plan shows **Spark**. Click **Upgrade**.
2. Choose **Blaze**. Pick or create a Cloud Billing account and add your card.
3. When offered, set a budget alert (e.g. $20). It emails you; it does not stop spending.

### A3. Create the Firestore database

1. In the left sidebar open **Firestore Database** (under **Build**, or **Databases &
   Storage** in newer consoles; the search box finds it too).
2. Click **Create database**.
3. If asked for an edition, choose **Standard**.
4. **Database ID:** leave it as `(default)`. The backend connects to that one.
5. **Location:** `us-central1 (Iowa)`. This cannot be changed later.
6. **Rules:** choose **Start in production mode**. That blocks all browser access, which is
   what we want: only the backend uses Firestore, through its service account.
7. Click **Create**.

### A4. Enable the Google Cloud APIs

Open each link. Check that the project picker at the top shows your project, then click
**Enable**.

- Cloud Run Admin API: <https://console.cloud.google.com/apis/library/run.googleapis.com?project=PROJECT_ID>
- Cloud Build API: <https://console.cloud.google.com/apis/library/cloudbuild.googleapis.com?project=PROJECT_ID>
- Artifact Registry API: <https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com?project=PROJECT_ID>
- Secret Manager API: <https://console.cloud.google.com/apis/library/secretmanager.googleapis.com?project=PROJECT_ID>

Firestore's API was turned on in A3. App Hosting turns on its own APIs in D2.

### A5. Store the Gemini key in Secret Manager

1. If you need a key: <https://aistudio.google.com/apikey> → **Create API key** → choose
   your project → copy the key.
2. Open <https://console.cloud.google.com/security/secret-manager?project=PROJECT_ID> and click
   **Create secret**.
3. **Name:** `gemini-api-key`. **Secret value:** paste the key, with no spaces or new line.
4. Click **Create secret**.

### A6. Create the backend's service account

1. Open <https://console.cloud.google.com/iam-admin/serviceaccounts?project=PROJECT_ID> and
   click **Create service account**.
2. **Name:** `cognith-api` → **Create and continue**.
3. Add two roles:
   - **Cloud Datastore User**. This is the Firestore read/write role; it still carries the
     old Datastore name.
   - **Secret Manager Secret Accessor**. This lets it read the Gemini key.
4. Click **Continue** → **Done**.

---

## Part B — Set up your laptop (once)

From the repo root:

```bash
gcloud auth login
gcloud config set project PROJECT_ID
gcloud auth application-default login                 # lets seed_firestore.py write to Firestore
gcloud auth application-default set-quota-project PROJECT_ID

cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

---

## Part C — Deploy the backend to Cloud Run

From `backend/`:

```bash
gcloud run deploy cognith-api \
  --source . \
  --region us-central1 \
  --service-account cognith-api@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --update-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --update-env-vars COGNITH_STORAGE=firestore \
  --memory 1Gi \
  --min-instances 1 \
  --max-instances 3
```

- The first run asks to create an Artifact Registry repository named
  `cloud-run-source-deploy`. Answer `Y`.
- It ends with **Service URL: https://cognith-api-….us-central1.run.app**. That is your
  `API_URL`.
- The flags say `--update-…`, not `--set-…`, so running this command again never removes
  the CORS setting you add in Part E.

Check it:

```bash
curl API_URL/health
# {"ok":true,"storage":"firestore","model":"..."}
```

Copy the demo learners into Firestore, once:

```bash
GOOGLE_CLOUD_PROJECT=PROJECT_ID .venv/bin/python seed_firestore.py
curl API_URL/api/learners           # lists demo, fresh, …
```

The script prints the project it writes to, so check that line. Running it again skips
learners that are already there.

---

## Part D — Deploy the frontend to Firebase App Hosting

### D1. Point the frontend at the backend

In `frontend/apphosting.yaml`, replace `https://REPLACE-WITH-CLOUD-RUN-URL.run.app` with your
`API_URL`, with no trailing slash. Commit and push to `main`.

Next.js puts this URL into the browser code **at build time**, so it must be pushed before
the first rollout. Changing it later needs a new rollout, which a push to `main` triggers.

### D2. Create the App Hosting backend

1. In the Firebase console open **App Hosting** (under **Build**, or **Hosting &
   Serverless**; the search box finds it). Click **Get started** (or **Create backend**).
2. **Region:** `us-central1`.
3. **Repository:** click **Connect to GitHub**, authorise, then install the Firebase App
   Hosting GitHub app on `Newstein123/cognipath`. This needs admin rights on that repo.
   Select the repo.
4. **Deployment settings:**
   - App root directory: `/frontend`
   - Live branch: `main`
   - Automatic rollouts: **on**
5. **Backend name:** `cognith-web`.
6. If asked to associate a Firebase web app, let it create one. The code doesn't use it,
   but it does no harm.
7. Click **Finish and deploy**. The first rollout takes 5–10 minutes; the **Rollouts** tab
   shows progress and build logs.

When it finishes, the backend's dashboard shows a URL like
`https://cognith-web--PROJECT_ID.us-central1.hosted.app`. That is your `WEB_URL`.

---

## Part E — Connect the two (CORS)

The backend only answers browsers coming from addresses it has been told about.

1. Open <https://console.cloud.google.com/run?project=PROJECT_ID> → **cognith-api** →
   **Edit & deploy new revision**.
2. In the container's **Variables & Secrets** tab, click **Add variable**:
   - **Name:** `COGNITH_CORS_ORIGINS`
   - **Value:** your `WEB_URL`, exactly: `https://`, no trailing slash. For more than one
     address, separate them with commas and no spaces.
3. Click **Deploy**.

The same thing from the command line:

```bash
gcloud run services update cognith-api --region us-central1 \
  --update-env-vars "^@^COGNITH_CORS_ORIGINS=WEB_URL"
```

`^@^` makes `@` the separator instead of the comma, so a comma-separated list survives.

---

## Part F — Check it end to end

1. Open `WEB_URL`. The start page loads with no error.
2. Open `WEB_URL/learn/demo`. The demo learner's plan loads.
3. Open a lesson. It shows an explanation with its sources from the course material. This
   is the knowledge engine working.
4. Answer an activity. You get a result and an updated skill.
5. Run the Part C deploy command again, then refresh the page. The progress is still
   there, which proves Firestore is keeping it.
6. Optional: in the Firebase console, **Firestore Database → Data** shows a `students`
   collection.

---

## Updating later

- **Backend:** run the Part C command again from `backend/`. Existing settings carry over.
- **Frontend:** push to `main`. App Hosting rolls it out on its own.
- **Course material:** rebuild the index locally with `.venv/bin/python build_pack.py <course-id>`,
  commit, then redeploy the backend. The index is never built on Cloud Run.

## If something goes wrong

Logs: Cloud Run → **cognith-api** → **Logs**. App Hosting → **cognith-web** → **Rollouts** / **Logs**.

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser console says "blocked by CORS policy" | `COGNITH_CORS_ORIGINS` does not match `WEB_URL` exactly | Part E: `https://`, no trailing slash |
| The frontend calls `localhost:8000` or the placeholder URL | `apphosting.yaml` was not updated before the rollout | D1, push, wait for the rollout |
| `/health` shows `"storage": "file"` | The env var is missing | Run the Part C command again |
| 500 errors; logs show `403` / `PermissionDenied` from Firestore | The service account lacks **Cloud Datastore User**, or the database ID is not `(default)` | A6 / A3 |
| Lessons and tutor fail; logs mention the secret or `GEMINI_API_KEY` | The service account lacks **Secret Manager Secret Accessor**, or the secret has a different name | A5 / A6 |
| `gcloud run deploy` fails during the build with a permission error | Newer projects build with the Compute Engine default service account | IAM → `PROJECT_NUMBER-compute@developer.gserviceaccount.com` → add role **Cloud Run Builder** → deploy again |
| `--allow-unauthenticated` rejected by an organisation policy | Work or school accounts can forbid public services | Use a project under a personal account, or ask the org admin |
| `seed_firestore.py` worked, but the learners are missing | It wrote to another project | Check the project line it prints; set `GOOGLE_CLOUD_PROJECT` |

## Costs and after the demo

- `--min-instances 1` keeps one backend instance always on, so the demo has no cold start
  (a new instance loads the course indexes on its first request). It is billed while on.
  After judging, turn it off:

  ```bash
  gcloud run services update cognith-api --region us-central1 --min-instances 0
  ```

- `--max-instances 3` caps the spend. The API has no login: anyone with the URL can create
  learners and use the Gemini quota.

## Fallback: if Firestore is not working at demo time

```bash
gcloud run services update cognith-api --region us-central1 \
  --update-env-vars COGNITH_STORAGE=file --min-instances 1 --max-instances 1
```

This runs one instance that keeps files on its own disk. Progress survives refreshes, but
resets on every redeploy or restart. The committed demo learners are in the image.

## Optional: run the Firestore tests on the emulator

This needs Java 11+. A snap or apt install of gcloud cannot add components: use
`sudo apt install google-cloud-cli-firestore-emulator`, or download the component's tarball
(listed in `https://dl.google.com/dl/cloudsdk/channels/rapid/components-v<gcloud version>.json`)
and run `cloud_firestore_emulator start --host=localhost --port=8085` from it.

```bash
gcloud components install cloud-firestore-emulator
gcloud emulators firestore start --host-port=localhost:8085      # terminal 1

cd backend                                                        # terminal 2
.venv/bin/pip install -r requirements-dev.txt
export FIRESTORE_EMULATOR_HOST=localhost:8085 GOOGLE_CLOUD_PROJECT=demo-cognith
COGNITH_TEST_STORAGE=firestore .venv/bin/python -m pytest tests -q
```
