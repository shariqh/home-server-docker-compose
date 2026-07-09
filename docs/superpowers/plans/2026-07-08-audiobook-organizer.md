# Audiobook Organizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically tag and file downloaded audiobooks into the `Author / Title, Book N /` library convention with Audible metadata, review the rare bad match from a phone via Audiobookshelf, and keep Plex + Prologue as the player.

**Architecture:** A custom `beets` + `beets-audible` container (`audiobook-organizer`) runs a daily import that auto-files confident Audible matches on disk and parks unsure ones in `_needs-review`. An `audiobookshelf` container is the mobile match UI: matching a book there embeds corrected tags into the file, and the next beets pass re-files it correctly on disk. Both containers live in the existing `media` stack and read the same `/mnt/media/books` library.

**Tech Stack:** Docker Compose, `beets` (Python), `beets-audible` plugin (Audnexus API), `ffmpeg`, Audiobookshelf.

## Global Constraints

- Target on-disk layout: `/mnt/media/books/<Author>/<Title, Book N>/<Title, Book N>.m4b` + sibling `cover.jpg`. Standalones fall back to `<Author>/<Title>/`. No ASIN in folder names.
- Drop folder is `/mnt/media/audiobook-inbox` — a sibling of `books`, **outside** both Plex's and ABS's library roots.
- Unsure matches go to `/mnt/media/books/_needs-review/` (never guessed into the library, never deleted until filed).
- Ownership: `PUID=1000`, `PGID=1000`, `TZ` from the shared root `.env` — matches the other media services.
- Config and scripts are version-controlled under `media/audiobook-organizer/` (appdata is gitignored). appdata holds only runtime state (`library.db`, ABS config/metadata).
- Media stack is brought up on the **server** with `op run --env-file=secrets.env -- docker compose up -d --build`. This project adds **no** new secrets.
- New host port: Audiobookshelf on `13378` (free; see README ports table).
- **VALIDATION GATE (Task 5) is a hard stop.** If the ABS→beets round-trip does not work as intended, STOP and rework the review surface before deploying to the server. Do not proceed to Tasks 6–8.

## Where each task runs

- **Tasks 1–5** run **locally on the Mac** with Docker and throwaway scratch folders — no server access, no real library touched. This is the fast iteration + de-risking phase.
- **Tasks 6–8** run against the **server** (media stack + real `/mnt/media`), after the gate passes.

Scratch layout for local tasks (create once, at the start of Task 1):

```bash
export SCRATCH="$HOME/abx-scratch"
mkdir -p "$SCRATCH"/{inbox,books,books/_needs-review,abs-config,abs-metadata,organizer-config}
```

Local test source books (copies, originals stay put):

```bash
cp "$HOME/Downloads/Matt Dinniman - Dungeon Crawler Carl.m4b"        "$SCRATCH/inbox/"
cp "$HOME/Downloads/Matt Dinniman - Carl's Doomsday Scenario.m4b"    "$SCRATCH/inbox/"
```

---

### Task 1: Organizer image + beets config that files one confident book

**Files:**
- Create: `media/audiobook-organizer/Dockerfile`
- Create: `media/audiobook-organizer/config.yaml`
- Create: `media/audiobook-organizer/organize.sh`
- Create: `media/audiobook-organizer/entrypoint.sh`

**Interfaces:**
- Produces: a container image `abx-organizer:dev`; `organize.sh` (the preprocess + import worker, callable as `organize` on PATH inside the container, accepting an optional `--interactive` flag); beets writes to `/books` from `/inbox` and `/books/_needs-review`.

- [ ] **Step 1: Write the Dockerfile**

`media/audiobook-organizer/Dockerfile`:

```dockerfile
FROM python:3.12-slim

# ffmpeg for lossless m4a->m4b remux; tini for clean signal handling
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tini \
 && rm -rf /var/lib/apt/lists/*

# beets + the audiobook plugin (Audnexus metadata) + mutagen for tag reads
RUN pip install --no-cache-dir beets beets-audible mutagen

# beets reads its config from BEETSDIR/config.yaml
ENV BEETSDIR=/config

COPY organize.sh /usr/local/bin/organize
COPY entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/organize /usr/local/bin/entrypoint

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/entrypoint"]
```

- [ ] **Step 2: Write the beets config**

`media/audiobook-organizer/config.yaml`. **NOTE:** the `audible:` and `fetchart:` option names below are from the beets-audible README and can drift between plugin versions. Before relying on them, `WebFetch https://raw.githubusercontent.com/Neurrone/beets-audible/main/README.md` and confirm each option name + that these behaviors hold: (a) `$album` resolves to `"Title, Book N"` for series books, (b) cover art lands as a sibling `cover.jpg`, (c) `-q` skips (not auto-accepts) low-confidence matches.

```yaml
directory: /books
library: /config/library.db

plugins:
  - audible
  - fromfilename
  - scrub
  - fetchart
  - edit

import:
  move: yes
  write: yes
  quiet_fallback: skip      # in -q (daily) mode, skip anything not confidently matched
  timid: no
  log: /config/beets-import.log

match:
  strong_rec_thresh: 0.04   # auto-accept threshold used by -q mode (lower = stricter)

audible:
  source_weight: 0.0            # prefer Audible metadata over MusicBrainz
  fetch_art: yes
  keep_series_reference_in_title: yes
  include_narrator_in_artists: no
  write_description_file: no
  write_reader_file: no

fetchart:
  cover_names: cover            # write cover.jpg
  sources:
    - filesystem
    - coverart

paths:
  default: $albumartist/$album%aunique{}/$album
  singleton: $albumartist/$title
  comp: $albumartist/$album%aunique{}/$album
```

- [ ] **Step 3: Write `organize.sh`** (preprocess + import worker)

`media/audiobook-organizer/organize.sh`:

```bash
#!/usr/bin/env bash
# Preprocess the inbox, then import inbox + needs-review into the library.
#   organize               -> quiet mode: only auto-file confident matches
#   organize --interactive -> prompt to confirm each Audible match
set -uo pipefail

INBOX="${INBOX:-/inbox}"
LIBRARY="${LIBRARY:-/books}"
REVIEW="$LIBRARY/_needs-review"
mkdir -p "$REVIEW"

INTERACTIVE=0
[ "${1:-}" = "--interactive" ] && INTERACTIVE=1

echo "[organize] preprocessing $INBOX"

# 1) Lossless remux any .m4a -> .m4b (stream copy, no re-encode)
find "$INBOX" -type f -iname '*.m4a' -print0 | while IFS= read -r -d '' f; do
  out="${f%.*}.m4b"
  echo "[organize] remux $(basename "$f") -> $(basename "$out")"
  if ffmpeg -nostdin -v error -i "$f" -map 0 -c copy -movflags +faststart "$out"; then
    rm -f "$f"
  else
    echo "[organize] WARN remux failed for $f (leaving as-is)" >&2
  fi
done

# 2) Strip macOS duplicate markers like " (1)" before the extension
find "$INBOX" -type f -iname '*.m4b' -print0 | while IFS= read -r -d '' f; do
  clean="$(echo "$f" | sed -E 's/ \([0-9]+\)(\.[A-Za-z0-9]+)$/\1/')"
  [ "$clean" != "$f" ] && mv -n "$f" "$clean"
done

# 3) beets-audible expects one book per folder: wrap loose top-level files
find "$INBOX" -maxdepth 1 -type f -iname '*.m4b' -print0 | while IFS= read -r -d '' f; do
  base="$(basename "$f")"; name="${base%.*}"
  dir="$INBOX/$name"
  mkdir -p "$dir"; mv -n "$f" "$dir/"
done

echo "[organize] importing (interactive=$INTERACTIVE)"
if [ "$INTERACTIVE" -eq 1 ]; then
  beet import "$INBOX" "$REVIEW"
else
  beet import -q "$INBOX" "$REVIEW"
fi

# 4) Anything still in the inbox was not confidently matched -> park for review
find "$INBOX" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' d; do
  echo "[organize] parking for review: $(basename "$d")"
  mv -n "$d" "$REVIEW/"
done

echo "[organize] done"
```

- [ ] **Step 4: Write `entrypoint.sh`** (daily loop; keeps container up for exec)

`media/audiobook-organizer/entrypoint.sh`:

```bash
#!/usr/bin/env bash
# Run one organize pass at start, then once per day. Staying alive also
# lets `docker exec -it audiobook-organizer organize --interactive` work.
set -uo pipefail
while true; do
  echo "[entrypoint] $(date) starting daily organize pass"
  organize || echo "[entrypoint] organize pass exited non-zero; continuing" >&2
  echo "[entrypoint] sleeping 24h"
  sleep 86400
done
```

- [ ] **Step 5: Create scratch dirs + build the image + define the check**

```bash
export SCRATCH="$HOME/abx-scratch"
mkdir -p "$SCRATCH"/{inbox,books,books/_needs-review,abs-config,abs-metadata,organizer-config}
cp "$HOME/Downloads/Matt Dinniman - Dungeon Crawler Carl.m4b" "$SCRATCH/inbox/"
docker build -t abx-organizer:dev media/audiobook-organizer
```

Expected: image builds successfully (`Successfully tagged abx-organizer:dev` or buildkit equivalent).

- [ ] **Step 6: Run one organize pass against scratch**

```bash
docker run --rm \
  -e BEETSDIR=/config \
  -v "$SCRATCH/organizer-config:/config" \
  -v "$PWD/media/audiobook-organizer/config.yaml:/config/config.yaml:ro" \
  -v "$SCRATCH/inbox:/inbox" \
  -v "$SCRATCH/books:/books" \
  abx-organizer:dev organize --interactive
```

Confirm the single Audible match interactively (it should offer "Dungeon Crawler Carl, Book 1" by Matt Dinniman).

- [ ] **Step 7: Verify the filed layout matches the convention**

```bash
find "$SCRATCH/books/Matt Dinniman" -print
```

Expected (allowing for exact series title from Audible):
```
.../Matt Dinniman/Dungeon Crawler Carl, Book 1/Dungeon Crawler Carl, Book 1.m4b
.../Matt Dinniman/Dungeon Crawler Carl, Book 1/cover.jpg
```
If the folder/file name or `cover.jpg` is wrong, adjust `paths` / `fetchart.cover_names` in `config.yaml` (Step 2) and rerun Step 6 into a cleaned scratch (`rm -rf "$SCRATCH/books/Matt Dinniman"`).

- [ ] **Step 8: Commit**

```bash
git add media/audiobook-organizer/
git commit -m "feat(media): audiobook-organizer image, beets config, organize worker

Files a confident Audible match into Author/Title, Book N/ with cover.jpg."
```

---

### Task 2: Quiet-mode safety — confident files land, unsure ones park in _needs-review

**Files:**
- Modify: `media/audiobook-organizer/organize.sh` (only if Step 3 reveals a gap — otherwise no change)

**Interfaces:**
- Consumes: `abx-organizer:dev`, `organize` from Task 1.
- Produces: verified behavior that `organize` (no `--interactive`) auto-files confident books and moves everything else to `/books/_needs-review/`.

- [ ] **Step 1: Define the check — make a deliberately un-matchable book**

Create a book beets cannot confidently match by wiping its tags and giving it a nonsense name:

```bash
rm -rf "$SCRATCH/inbox"/* ; mkdir -p "$SCRATCH/inbox"
cp "$HOME/Downloads/Matt Dinniman - Carl's Doomsday Scenario.m4b" "$SCRATCH/inbox/zzz-unknown-book.m4b"
# strip identifying tags so auto-match has nothing to latch onto
docker run --rm -v "$SCRATCH/inbox:/inbox" abx-organizer:dev \
  ffmpeg -nostdin -v error -i "/inbox/zzz-unknown-book.m4b" -map 0 -c copy -map_metadata -1 "/inbox/zzz-clean.m4b"
rm "$SCRATCH/inbox/zzz-unknown-book.m4b"
# also drop a clean confident book alongside it
cp "$HOME/Downloads/Matt Dinniman - The Gate of the Feral Gods.m4b" "$SCRATCH/inbox/"
```

- [ ] **Step 2: Run quiet mode**

```bash
docker run --rm \
  -e BEETSDIR=/config \
  -v "$SCRATCH/organizer-config:/config" \
  -v "$PWD/media/audiobook-organizer/config.yaml:/config/config.yaml:ro" \
  -v "$SCRATCH/inbox:/inbox" \
  -v "$SCRATCH/books:/books" \
  abx-organizer:dev organize
```

Expected: no prompts (quiet). "The Gate of the Feral Gods" auto-files; the tag-stripped book does not.

- [ ] **Step 3: Verify the split**

```bash
echo "== filed =="        ; find "$SCRATCH/books/Matt Dinniman" -name '*.m4b'
echo "== needs review ==" ; find "$SCRATCH/books/_needs-review" -name '*.m4b'
echo "== inbox (should be empty) ==" ; find "$SCRATCH/inbox" -type f
```

Expected: the Feral Gods book under `Matt Dinniman/...`; the tag-stripped book under `_needs-review/`; inbox empty.

If the tag-stripped book auto-filed anyway, `match.strong_rec_thresh` is too loose — lower it in `config.yaml` and rerun. If a genuinely-matchable book landed in review, it's too strict — raise it. Commit only once the split is correct.

- [ ] **Step 4: Commit (if organize.sh changed)**

```bash
git add media/audiobook-organizer/
git commit -m "fix(media): tune quiet-mode match threshold + review parking"
```
(If nothing changed, skip — the behavior was already correct; note that in the task report.)

---

### Task 3: Audiobookshelf container reads the scratch library

**Files:**
- Create: `media/audiobook-organizer/abs-test.md` (a 4-line scratch run note; deleted in Task 8) — OR skip the file and keep the command in the task report.

**Interfaces:**
- Consumes: `$SCRATCH/books` from Tasks 1–2.
- Produces: a locally-running ABS at `http://localhost:13378` with a library pointed at the scratch books, used for the Task 5 gate.

- [ ] **Step 1: Start ABS locally against scratch**

```bash
docker run -d --name abx-abs \
  -p 13378:80 \
  -v "$SCRATCH/books:/audiobooks" \
  -v "$SCRATCH/abs-config:/config" \
  -v "$SCRATCH/abs-metadata:/metadata" \
  ghcr.io/advplyr/audiobookshelf:latest
```

- [ ] **Step 2: Verify it's up**

```bash
sleep 5 && curl -fsS http://localhost:13378/healthcheck && echo OK
```
Expected: `OK` (or HTTP 200). If it fails, `docker logs abx-abs`.

- [ ] **Step 3: Create the library in the ABS web UI**

Open `http://localhost:13378`, create the initial admin user, then add a **Books** library pointing at `/audiobooks`. Confirm the already-filed books (from Tasks 1–2) appear.

Expected: filed books show with correct titles/covers; the `_needs-review` book appears (likely unmatched / grouped oddly). No commit — this is a runtime verification step.

---

### Task 4: Interactive on-demand path documented and exercised

**Files:**
- Modify: `media/audiobook-organizer/organize.sh` (only if the interactive path has a bug)

**Interfaces:**
- Consumes: `organize --interactive` from Task 1.
- Produces: confirmed one-command interactive re-file, the documented fallback if the gate is imperfect.

- [ ] **Step 1: Put the review book back through interactive import**

```bash
docker run --rm -it \
  -e BEETSDIR=/config \
  -v "$SCRATCH/organizer-config:/config" \
  -v "$PWD/media/audiobook-organizer/config.yaml:/config/config.yaml:ro" \
  -v "$SCRATCH/inbox:/inbox" \
  -v "$SCRATCH/books:/books" \
  abx-organizer:dev organize --interactive
```

Note: `organize` also scans `/books/_needs-review`, so the parked book is offered for matching. Use beets' `E` (enter search) / ASIN entry to force the correct Audible match ("Carl's Doomsday Scenario").

- [ ] **Step 2: Verify it filed correctly**

```bash
find "$SCRATCH/books/Matt Dinniman" -name '*.m4b'
find "$SCRATCH/books/_needs-review" -type f   # should no longer contain that book
```
Expected: the book now lives under `Matt Dinniman/Carl's Doomsday Scenario, Book 2/`.

- [ ] **Step 3: Commit (only if organize.sh changed)**

```bash
git add media/audiobook-organizer/organize.sh
git commit -m "fix(media): interactive re-file also scans _needs-review"
```

---

### Task 5: ★ VALIDATION GATE ★ — ABS match → embed → beets re-files on disk

**This is a HARD STOP.** If the round-trip below does not end with the book correctly renamed on disk by beets, **STOP**. Do not deploy to the server. Report the failure and the two fallbacks (interactive `docker exec` re-file from Task 4; or replace ABS's review role with Bragi Books), and wait for a human decision.

**Files:** none (verification only).

**Interfaces:**
- Consumes: `abx-abs` (Task 3), `organize` (Task 1), a parked `_needs-review` book.
- Produces: a proven (or disproven) sync-back mechanism.

- [ ] **Step 1: Ensure a book is parked in `_needs-review`**

Re-create the tag-stripped book from Task 2, Step 1 so exactly one book sits in `$SCRATCH/books/_needs-review/`. Confirm:
```bash
find "$SCRATCH/books/_needs-review" -name '*.m4b'
```

- [ ] **Step 2: Match it in ABS and embed metadata**

In the ABS web UI (`http://localhost:13378`):
1. Open the parked book.
2. Use **Match** → search Audible → pick the correct edition ("Carl's Doomsday Scenario", Dungeon Crawler Carl #2). Save.
3. Run **Tools → Embed Metadata** (or the item's "Embed Metadata in Audio Files" action) so the corrected tags are written **into the `.m4b`**.

- [ ] **Step 3: Confirm ABS actually wrote tags into the file**

```bash
docker run --rm -v "$SCRATCH/books:/books" abx-organizer:dev \
  python -c "import sys,glob; from mutagen.mp4 import MP4; \
f=glob.glob('/books/_needs-review/**/*.m4b', recursive=True)[0]; m=MP4(f); \
print('title:', m.tags.get('\xa9nam')); print('artist:', m.tags.get('\xa9ART')); \
print('album:', m.tags.get('\xa9alb'))"
```
Expected: title/artist/album now reflect the correct book (not empty/garbage). **If tags are still empty, the gate has already failed** — ABS did not embed. Stop here.

- [ ] **Step 4: Run a beets pass and confirm the on-disk re-file**

```bash
docker run --rm \
  -e BEETSDIR=/config \
  -v "$SCRATCH/organizer-config:/config" \
  -v "$PWD/media/audiobook-organizer/config.yaml:/config/config.yaml:ro" \
  -v "$SCRATCH/inbox:/inbox" \
  -v "$SCRATCH/books:/books" \
  abx-organizer:dev organize
find "$SCRATCH/books/Matt Dinniman" -name '*.m4b'
find "$SCRATCH/books/_needs-review" -type f
```

Expected (GATE PASSES): the book is now at `Matt Dinniman/Carl's Doomsday Scenario, Book 2/...` and no longer in `_needs-review`.

- [ ] **Step 5: Record the gate result**

- **Pass** → note it in the task report and continue to Task 6.
- **Fail** → STOP. Tear down scratch ABS (`docker rm -f abx-abs`) is optional; do **not** proceed. Surface: which sub-step failed, and recommend the fallback (Task 4 interactive exec, or Bragi Books). Await human decision.

No commit (verification only).

---

### Task 6: Wire both services into the media stack

**Files:**
- Modify: `media/docker-compose.yml` (append two services)

**Interfaces:**
- Consumes: the proven image build context `./audiobook-organizer` and `config.yaml`.
- Produces: `audiobook-organizer` and `audiobookshelf` services in the `media` stack.

- [ ] **Step 1: Append the two services to `media/docker-compose.yml`**

Add under `services:` (indentation matches the existing file — two spaces):

```yaml
  audiobook-organizer:
    build: ./audiobook-organizer
    image: audiobook-organizer:latest
    container_name: audiobook-organizer
    restart: unless-stopped
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=${TZ}
      - BEETSDIR=/config
    volumes:
      - /mnt/media/audiobook-inbox:/inbox
      - /mnt/media/books:/books
      - ../appdata/audiobook-organizer:/config
      - ./audiobook-organizer/config.yaml:/config/config.yaml:ro

  audiobookshelf:
    image: ghcr.io/advplyr/audiobookshelf:latest
    container_name: audiobookshelf
    restart: unless-stopped
    environment:
      - TZ=${TZ}
    volumes:
      - /mnt/media/books:/audiobooks
      - ../appdata/audiobookshelf/config:/config
      - ../appdata/audiobookshelf/metadata:/metadata
    ports:
      - "13378:80"
```

- [ ] **Step 2: Validate compose config locally**

```bash
cd media && docker compose config >/dev/null && echo "compose OK" && cd ..
```
Expected: `compose OK` (no YAML/interpolation errors). `${PUID}` etc. resolve from the `.env` symlink.

- [ ] **Step 3: Commit**

```bash
git add media/docker-compose.yml
git commit -m "feat(media): add audiobook-organizer + audiobookshelf services"
```

---

### Task 7: Deploy to the server and prep host folders

**Files:** none (server-side operations).

**Interfaces:**
- Consumes: the committed `media` stack.
- Produces: both containers running on the server; host drop folder + `_needs-review/.plexignore` in place.

- [ ] **Step 1: Push and pull on the server**

Local:
```bash
git push -u origin audiobook-organizer
```
On the server (via Tailscale SSH), in the repo clone:
```bash
git fetch && git checkout audiobook-organizer && git pull
```

- [ ] **Step 2: Create host folders**

On the server:
```bash
sudo mkdir -p /mnt/media/audiobook-inbox /mnt/media/books/_needs-review
printf '*\n' | sudo tee /mnt/media/books/_needs-review/.plexignore
sudo chown -R 1000:1000 /mnt/media/audiobook-inbox /mnt/media/books/_needs-review
mkdir -p appdata/audiobook-organizer appdata/audiobookshelf/config appdata/audiobookshelf/metadata
```

- [ ] **Step 3: Bring up the media stack**

On the server:
```bash
cd media && op run --env-file=secrets.env -- docker compose up -d --build && cd ..
```

- [ ] **Step 4: Verify both containers are healthy**

```bash
docker ps --filter name=audiobook-organizer --filter name=audiobookshelf
docker logs --tail=20 audiobook-organizer   # expect the daily-pass banner, no crash loop
curl -fsS http://localhost:13378/healthcheck && echo ABS_OK
```
Expected: both containers `Up`; organizer log shows `[entrypoint] ... starting daily organize pass`; `ABS_OK`.

- [ ] **Step 5: Point ABS at the real library**

Open `http://<server-ip>:13378`, create the admin user, add a **Books** library at `/audiobooks`. Confirm existing books (Harry Potter, LOTR, etc.) appear.

No commit (server runtime).

---

### Task 8: File the 7 Dungeon Crawler Carl books + docs

**Files:**
- Modify: `README.md` (stack description + ports table + audiobook workflow note)
- Delete: `media/audiobook-organizer/abs-test.md` if it was created in Task 3

**Interfaces:**
- Consumes: the running server stack.
- Produces: the 7 DCC books filed in the real library; updated README; closed loop on issue #3.

- [ ] **Step 1: Copy the 7 books to the server inbox**

From the Mac (adjust host/path for your Tailscale name):
```bash
scp "$HOME/Downloads/Matt Dinniman - "*.m4b "$HOME/Downloads/Matt Dinniman - "*.m4a \
  <server>:/mnt/media/audiobook-inbox/
```

- [ ] **Step 2: Run the interactive import on the server**

```bash
docker exec -it audiobook-organizer organize --interactive
```
Confirm each of the 7 Audible matches (series: Dungeon Crawler Carl). The lone `.m4a` (The Butcher's Masquerade) is remuxed to `.m4b` automatically first.

- [ ] **Step 3: Verify all 7 filed correctly**

```bash
find "/mnt/media/books/Matt Dinniman" -maxdepth 1 -type d | sort
find "/mnt/media/books/_needs-review" -type f   # expect empty
```
Expected: 7 folders `Dungeon Crawler Carl, Book 1` … `Book 7` (or Audible's exact titles), nothing left in review. Confirm they show in ABS and in Plex (rescan the Books library if needed).

- [ ] **Step 4: Update the README**

In `README.md`:
- `media/` row in the Stacks table → append `, Audiobookshelf, audiobook-organizer`.
- Ports table → add `| media | 13378 | Audiobookshelf |`.
- Add a short "Audiobooks" subsection: drop files into `/mnt/media/audiobook-inbox`; the daily pass auto-files confident matches into `Author/Title, Book N/`; unsure ones land in `books/_needs-review` and are fixed from the Audiobookshelf web/phone UI (Match → Embed Metadata), then re-filed on the next pass; on-demand interactive run is `docker exec -it audiobook-organizer organize --interactive`.

- [ ] **Step 5: Update issue #3**

```bash
gh issue comment 3 --repo shariqh/home-server-docker-compose \
  --body "Interactive + daily-quiet organizer shipped (see media/audiobook-organizer). The ABS match→embed→beets round-trip covers unattended review. Remaining for this issue: completion/needs-review notifications and threshold auto-tuning."
```

- [ ] **Step 6: Commit and open the PR**

```bash
rm -f media/audiobook-organizer/abs-test.md 2>/dev/null || true
git add README.md media/audiobook-organizer/
git commit -m "docs(media): document audiobook workflow + ports; file DCC series"
git push
gh pr create --repo shariqh/home-server-docker-compose --base main \
  --title "Automated audiobook organizer (beets-audible + Audiobookshelf)" \
  --body "Implements docs/superpowers/specs/2026-07-08-audiobook-organizer-design.md. Closes #3 partially (see comment). Daily beets auto-file into Author/Title, Book N/; Audiobookshelf as mobile match/embed UI; Plex+Prologue stays the player. Validation gate (ABS→beets round-trip) passed."
```

---

## Self-Review

**Spec coverage:**
- Target convention → Task 1 (Step 7 verifies), Global Constraints. ✓
- Drop folder outside library roots → Task 7 Step 2; compose Task 6. ✓
- `_needs-review` + `.plexignore` → Task 7 Step 2; parking in organize.sh Task 1. ✓
- beets + beets-audible + ffmpeg image → Task 1. ✓
- `.m4a`→`.m4b` remux + `(1)` cleanup + per-book foldering → organize.sh Task 1. ✓
- Daily unattended + confidence threshold + safe parking → Tasks 1 (entrypoint), 2 (threshold). ✓
- Audiobookshelf review surface → Tasks 3, 6, 7. ✓
- **Validation gate (ABS→beets round-trip) as hard stop** → Task 5. ✓
- Player = Plex + Prologue (ABS not a player) → no ABS-player config anywhere; README note Task 8. ✓
- One-time 7-book import → Task 8. ✓
- Fallbacks (interactive exec, Bragi) → Task 4 + Task 5 Step 5. ✓
- No new secrets; PUID/PGID/TZ; port 13378 → Global Constraints, Task 6. ✓
- Out of scope (no Readarr/search, no merge) → not implemented; issue #3 for auto-tuning. ✓

**Placeholder scan:** `config.yaml` option names carry an explicit verify-against-README step (Task 1 Step 2) rather than a silent guess — this is disclosure of third-party drift, with the concrete config present. No other TBDs.

**Type/name consistency:** `organize` (script name on PATH) and its `--interactive` flag are used identically across Tasks 1, 4, 5, 8. Volume paths (`/inbox`, `/books`, `/config`, `/config/config.yaml:ro`) are identical in every `docker run` and in the compose service. `_needs-review` path spelled consistently. Image tag `abx-organizer:dev` (local) vs `audiobook-organizer:latest` (server compose) is intentional and noted.
