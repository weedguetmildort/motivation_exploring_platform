# Handoff — `feat/all-variant-study-flow`

Status as of 2026-09-23. Covers what is on the branch, what is still pending, and
how to deploy this branch to Heroku **without touching the existing production
app**.

---

## 1. What this branch changes

Participants used to take **2 quizzes** (base + one round-robin-assigned
variant). They now take **4** (base + every variant), with a survey between each
— 9 steps instead of 5. Each quiz draws from its **own question set**, so no
participant sees the same question twice.

```
1  Survey 1      pre_quiz          5  Survey 3    post_<v2>
2  Quiz Part 1   base   (set a)    6  Quiz Part 3 <v3>  (set c)
3  Survey 2      post_base         7  Survey 4    post_<v3>
4  Quiz Part 2   <v1>   (set b)    8  Quiz Part 4 <v4>  (set d)
                                   9  Survey 5    post_<v4>
```

Variant order is counterbalanced per participant (cyclic Latin square), so each
variant lands in each position equally often. The base quiz is always first.

### Committed (3 commits, pushed to `origin/feat/all-variant-study-flow`)

| Commit | What |
|---|---|
| `2ebbd1a` | The multi-variant flow engine — `services/study_flow.py`, `GET /study/next`, `/study_flow_panel`, server-side step gating |
| `a7eae21` | `build_user_public` was dropping `step_order`/`completed_steps`, which left every routing caller reading an empty flow |
| `f550568` | Markdown display-math fence pairing |

### Uncommitted — per-quiz question sets (18 files + 1 new test file)

This is the whole "each quiz has its own set" feature. **It is not committed and
not pushed.**

- `ALL_SET_IDS` derived from `SetId` (`schemas/question.py`) — one source of truth
  for the set letters, which were hand-enumerated in 5 places.
- `StudyConfig` gains `quiz_set_mode` (`preset` | `random`) and `quiz_set_map`,
  persisted in the existing `study_config/active_flow` document.
- `resolve_quiz_set_assignment` — preset uses the map verbatim; random shuffles
  the sets across that participant's quizzes. Snapshotted onto the user at signup
  as `quiz_set_assignment`, like `variant_sequence`.
- Pool-query precedence in `_build_pool_query`:
  **per-quiz set → participant `quiz_sets` (Phase 11) → whole pool.**
- Each attempt records `question_set` at draw time, and `GET /export/quiz-answers`
  gains a `question_set` column.
- `PUT /study/config` rejects unknown quiz ids, unknown set letters, and **two
  quizzes sharing a set** (that is exactly the repetition this prevents).
- Admin UI: a "Question sets" section in `/study_flow_panel`.

Two bugs were found and fixed while building it, both worth knowing about:

1. **The freeze bug.** `quiz_set_assignment` was only recomputed when the field
   was `null`. The map starts empty, so on deploy every existing participant's
   next request would write `{}` — and `{}` is not `null`, so configuring the map
   afterwards would never reach them. Fixed by falling back to the current preset
   map **at draw time** (`preset_quiz_set`), deliberately not in
   `ensure_user_flow`, which runs on every authenticated request and must not
   cost a config read.
2. **Admin reset didn't re-point the set.** `reset_quiz_attempt` now calls
   `repoint_quiz_set`, so changing the map and resetting actually shows the new
   set. Preset mode only — re-rolling one quiz in random mode could hand it a set
   another of that participant's quizzes already uses.

### Test status (verified 2026-09-23)

| | Result |
|---|---|
| Backend, in the CI image (`backend/Dockerfile.test`) | **953 passed**, 93.65% coverage (gate: 80%) |
| Frontend `npm run test:coverage` | **601 passed**, 49 suites, 95.65% |
| `tsc --noEmit` (source) | clean |

> Running `tsc` and `jest --coverage` concurrently makes suites flake — they
> contend for workers. Run them one after the other.

---

## 2. Pending

### Must do before this is usable

1. **Commit and push the per-quiz-sets work.** It is the largest piece and exists
   only in the working tree. One logical commit.
2. **Open the PR.** A full PR body was drafted in the working session; re-check
   its claims against the final diff before posting, since it was written before
   the per-quiz-sets work existed.
3. **Populate sets C and D.** Only ~2 sets currently hold real questions. Until
   then, map the 2 populated sets and leave the other two quizzes unmapped — they
   fall back to the whole pool and can overlap with each other. The seed script
   (`backend/scripts/seed_questions.py`, dev DB only) creates 20 per set.
4. **Configure the map after deploying.** It ships empty; nothing is isolated
   until an admin sets it in `/study_flow_panel`.
5. **Delete the `juan-branch` backup** once this merges. It still exists on the
   remote and holds the original pre-rebase commit.

### Known issues, not addressed here

- **Survey Likert scales never render as configured.** `frontend/lib/surveys.ts`
  declares `scale_min` / `scale_max`, but the API returns
  `scale: { min, max, anchors }`. Every Likert item silently falls back to 1–5
  with default labels, so admin-configured ranges and endpoint labels are
  ignored. Pre-existing, unrelated to this branch, but it affects the surveys
  this flow now shows five times per participant.
- **Chat errors are indistinguishable.** Two bare `except Exception:` blocks in
  `backend/app/api/chat.py` discard the exception with no logging, so a network
  failure, a bad key and a wrong model all surface as
  `"Upstream AI request failed"`.
- **`UF_OPENAI_BASE_URL` may be missing `/v1`.** It is set to
  `https://api.ai.it.ufl.edu`. The UF proxy resolves to `10.51.17.62` — a
  UF-internal address reachable only on campus or VPN — so this could not be
  verified off-network. If you get a **404** (rather than a connection error)
  while on VPN, append `/v1`.
- **Never exercised against a live Mongo.** `docker-compose.yml` has the mongo
  service commented out and the configured DB is remote, so verification was done
  against the test suites plus an in-memory Mongo double. See §4.

---

## 3. Deploying this branch separately on Heroku

### How deployment works today

`.github/workflows/cd.yml` runs **on push to `main`**: it runs the test suites,
builds `backend/Dockerfile` and `frontend/Dockerfile`, pushes both to the Heroku
Container Registry, and runs `heroku container:release`. Two Heroku apps, both on
the `container` stack, driven by these repo secrets:

`HEROKU_API_KEY`, `HEROKU_EMAIL`, `HEROKU_APP_BACKEND`, `HEROKU_APP_FRONTEND`,
`BACKEND_URL`.

So yes — it is an auto-deploy from `main`, and this branch will not deploy
anywhere until you add a second pipeline.

### Three things that will bite you

**1. Use a separate MongoDB database. This is the important one.**
`ensure_user_flow` backfills `step_order`, `completed_steps` and
`quiz_set_assignment` onto user documents **on login**. If the new app points at
the production database, it will rewrite live participants' records and convert
them to the 9-step flow. At minimum use a different `MONGO_DB` name; a separate
Atlas cluster or user is safer.

**2. `BACKEND_URL` is baked in at build time, not read at runtime.**
`next.config.js` rewrites are evaluated by `next build` and written into
`.next/routes-manifest.json` (verified: the value appears 15 times there). Setting
it as a Heroku config var on the frontend app does **nothing**. The frontend image
must be **rebuilt** with the new backend URL as a `--build-arg`.

**3. Heroku's registry rejects OCI manifests.**
It only accepts Docker v2 schema-2. Modern BuildKit defaults to OCI media types
and the push fails with `unsupported`. `cd.yml` already works around this with
`outputs: type=image,oci-mediatypes=false,push=true`; any manual push needs the
same.

### Options

| | Approach | Pros | Cons |
|---|---|---|---|
| **A** ✅ | Second workflow file on this branch | No risk to the `main` pipeline; explicit; delete it when done | ~90 lines of duplicated YAML |
| B | Extract a `workflow_call` reusable workflow, called by both | DRY | Edits the production pipeline to set it up |
| C | GitHub Environments, branch-selected secrets | Most elegant, scales to more envs | Edits the production pipeline; needs repo-settings work |
| D | Manual `docker push` + `heroku container:release` from your machine | Fastest; zero CI changes | Not automatic; needs local Docker + Heroku CLI |

**Recommended: A**, with **D** to get something up immediately. Option A is a
throwaway file you delete when the branch merges, and it cannot break the
production deploy. Reach for B or C only if this staging app becomes permanent.

Not recommended: Heroku Pipelines with review apps. Those expect the Heroku
GitHub integration (`app.json` / `heroku.yml`), which does not compose cleanly
with the container-registry-via-Actions approach already in use here.

### Setup (one-time)

```bash
heroku login

# 1. Two new apps on the container stack
heroku apps:create mep-v2-backend  --stack container
heroku apps:create mep-v2-frontend --stack container

# 2. Backend config — NOTE the separate MONGO_DB and a fresh JWT_SECRET
heroku config:set -a mep-v2-backend \
  MONGO_URL="<same cluster or a separate one>" \
  MONGO_DB="mep_v2" \
  JWT_SECRET="$(openssl rand -hex 32)" \
  JWT_EXPIRES_MIN=180 \
  COOKIE_SECURE=true \
  COOKIE_SAMESITE=None \
  FRONTEND_ORIGIN="https://mep-v2-frontend-xxxx.herokuapp.com" \
  UF_OPENAI_API_KEY="..." \
  UF_OPENAI_BASE_URL="https://api.ai.it.ufl.edu" \
  UF_OPENAI_API_MODEL="gpt-4.1" \
  ENV=production
```

`COOKIE_SAMESITE=None` (with `COOKIE_SECURE=true`) is needed because the frontend
and backend are separate Heroku apps — the session cookie is cross-site. See
`.env.example` for the full variable list.

The frontend app needs no config vars; its only input is the build arg.

### Option A — the workflow file

Add `.github/workflows/cd-v2.yml`. It is `cd.yml` with the trigger branch,
concurrency group and secret names changed:

```yaml
name: CD (v2 — all-variant study flow)

on:
  push:
    branches: [ "feat/all-variant-study-flow" ]
  workflow_dispatch:

concurrency:
  group: deploy-v2
  cancel-in-progress: false

jobs:
  tests:
    uses: ./.github/workflows/tests.yml

  build-and-deploy:
    needs: tests
    runs-on: ubuntu-latest
    env:
      HEROKU_API_KEY:  ${{ secrets.HEROKU_API_KEY }}
      HEROKU_EMAIL:    ${{ secrets.HEROKU_EMAIL }}
      APP_BACKEND:     ${{ secrets.HEROKU_APP_BACKEND_V2 }}
      APP_FRONTEND:    ${{ secrets.HEROKU_APP_FRONTEND_V2 }}
      HEROKU_REGISTRY: registry.heroku.com
    steps:
      - uses: actions/checkout@v5
      - uses: docker/setup-buildx-action@v4

      - name: Login to Heroku Container Registry
        run: echo "${HEROKU_API_KEY}" | docker login -u "${HEROKU_EMAIL}" --password-stdin ${HEROKU_REGISTRY}

      - name: Build & Push Backend Image
        uses: docker/build-push-action@v7
        with:
          context: ./backend
          file: ./backend/Dockerfile
          platforms: linux/amd64
          provenance: false
          sbom: false
          tags: ${{ env.HEROKU_REGISTRY }}/${{ env.APP_BACKEND }}/web
          outputs: type=image,oci-mediatypes=false,push=true
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build & Push Frontend Image
        uses: docker/build-push-action@v7
        with:
          context: ./frontend
          file: ./frontend/Dockerfile
          platforms: linux/amd64
          provenance: false
          sbom: false
          no-cache: true
          build-args: |
            BACKEND_URL=https://${{ secrets.BACKEND_URL_V2 }}
          tags: ${{ env.HEROKU_REGISTRY }}/${{ env.APP_FRONTEND }}/web
          outputs: type=image,oci-mediatypes=false,push=true
          cache-to: type=gha,mode=max

      - name: Install Heroku CLI
        run: curl https://cli-assets.heroku.com/install-ubuntu.sh | sh

      - name: Release
        run: |
          heroku container:release web -a "${APP_BACKEND}"
          heroku container:release web -a "${APP_FRONTEND}"
```

Then add three repo secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `HEROKU_APP_BACKEND_V2` | `mep-v2-backend` |
| `HEROKU_APP_FRONTEND_V2` | `mep-v2-frontend` |
| `BACKEND_URL_V2` | `mep-v2-backend-xxxx.herokuapp.com` (**no** scheme — the workflow prepends `https://`) |

Pushing the branch now deploys it. `main` is untouched.

### Option D — manual deploy, no CI changes

```bash
heroku container:login

# Backend
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  --output type=image,oci-mediatypes=false,push=true \
  -t registry.heroku.com/mep-v2-backend/web ./backend
heroku container:release web -a mep-v2-backend

# Frontend — the backend URL must be baked in here
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  --build-arg BACKEND_URL=https://mep-v2-backend-xxxx.herokuapp.com \
  --output type=image,oci-mediatypes=false,push=true \
  -t registry.heroku.com/mep-v2-frontend/web ./frontend
heroku container:release web -a mep-v2-frontend
```

### After the first deploy

1. Promote yourself to admin in the **new** database
   (`db.users.updateOne({email: "..."}, {$set: {is_admin: true}})`).
2. Seed or import questions, and assign set letters in `/questions_panel`.
3. Open `/study_flow_panel` → **Preset** → map each quiz to its own set → Save.
   The version banner should increment.
4. Sign up a throwaway participant and confirm their user document has a
   `quiz_set_assignment`.

---

## 4. Verifying the flow end to end

The fastest confirmation is not "did the questions change" — resetting always
re-draws. It is **which set they came from**.

1. Walk a participant through all four quizzes.
2. In Mongo, read the four `quiz_attempts` documents for that user and check the
   **`question_set`** field: four attempts, four different letters.
3. Confirm `question_order` across the four has **zero** overlap.
4. Cross-check in `/questions_panel` — a quiz mapped to `a` should only show
   items badged **Set A**.

Expect two things that look like bugs but are not: repeated resets of the same
quiz give different questions *from the same set*, and any quiz left unmapped
records `question_set: null` and draws from the whole pool.

A scripted version of this walk (against an in-memory Mongo double, so it needs
no database) was used during development and can be reconstructed from
`backend/tests/test_quiz_service.py::TestLoadOrCreateAttemptQuizSet` and
`test_study_flow_service.py::TestQuizSetAssignmentAtSignup`.
