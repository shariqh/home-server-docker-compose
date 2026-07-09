# Audiobook Organizer — Design

**Date:** 2026-07-08
**Status:** Approved, pending implementation plan
**Stack:** `media`

## Problem

Audiobooks are downloaded as loose files and organized into Plex **by hand** — renaming
and foldering each one to a preferred convention. There are 7 new books waiting (the
Dungeon Crawler Carl series by Matt Dinniman). We want this automated: drop files
somewhere, have them tagged with real Audible metadata and filed into the library
convention, and be able to fix the occasional bad match **from a phone/browser** without
SSHing into the server.

## Existing convention (from the current library)

```
J.K Rowling/
  Harry Potter and the Chamber of Secrets, Book 2 [B017V4IWVG]/
    Harry Potter and the Chamber of Secrets, Book 2.m4b
    Harry Potter and the Chamber of Secrets, Book 2.jpg   (cover)
    Harry Potter and the Chamber of Secrets, Book 2.cue   (optional)
J.R.R. Tolkien/
  The Silmarillion/                (standalone, no series/ASIN)
    The Silmarillion.m4b
```

Pattern: `Author / <Title, Book N> / <same-name>.{m4b,jpg}`.
The `[ASIN]` suffix present on some folders is **not required** going forward — it was
incidental. Target naming drops it.

## Target convention (this project)

```
/mnt/media/books/
  Matt Dinniman/
    Dungeon Crawler Carl, Book 1/
      Dungeon Crawler Carl, Book 1.m4b
      cover.jpg
    Carl's Doomsday Scenario, Book 2/
      ...
```

- Top level = **Author**.
- Book folder = **`Title, Book N`** (series position from Audible metadata so books sort
  in reading order). Standalones fall back to `Author/Title/`.
- One `.m4b` per book + a sibling `cover.jpg`.
- No ASIN in the folder name.

## Players and consumers

- **Player = Plex + Prologue** (iOS, offline). This is fixed. Prologue reads from Plex,
  and Plex's audiobook experience depends on correct **on-disk** folder/file naming — so
  every book, including recovered "unsure" ones, must end up correctly named on disk.
- Audiobookshelf's own player is beta/stalled and is **not** used for playback. ABS is
  used **only** as a mobile matching UI + tag writer (see round-trip below).

## Architecture

Two new containers in the `media` stack, both reading the same library folder.

### 1. `audiobook-organizer` — the filing engine

- Custom image: `python:slim` + `beets` + [`beets-audible`](https://github.com/Neurrone/beets-audible)
  plugin + `ffmpeg`.
- Purpose-built for producing the `Author / Title, Book N /` audiobook convention with
  Audible metadata (via the Audnexus API). Actively maintained; not Readarr (retired).
- **Volumes:**
  - `/mnt/media/audiobook-inbox:/inbox` — drop folder (see below)
  - `/mnt/media/books:/books` — library root (organized output)
  - `../appdata/audiobook-organizer:/config` — beets `config.yaml` + `library.db` + scripts
- `PUID=1000 / PGID=1000 / TZ` — matches the other media services so output ownership is
  consistent with Plex.
- **Runs a daily scheduled import** (cron inside the container, ~4am). Also supports an
  on-demand interactive run via `docker exec` for edge cases.

### 2. `audiobookshelf` — mobile review + tag writer

- Image: `ghcr.io/advplyr/audiobookshelf:latest` (or linuxserver equivalent).
- Library points at `/mnt/media/books`. Confident, already-filed books appear fully
  matched. `_needs-review` books appear unmatched.
- From phone/browser, the **Match** UI searches Audible (covers, series, narrator) and,
  crucially, its **Embed Metadata** tool writes corrected tags back into the `.m4b`.
- Volumes: `/mnt/media/books:/audiobooks`, `../appdata/audiobookshelf/config:/config`,
  `../appdata/audiobookshelf/metadata:/metadata`. Web UI port exposed (e.g. `13378`).
- **Not** used as an audio player.

## Folders

- **Drop folder: `/mnt/media/audiobook-inbox`** — a sibling of `books`, easy to drop into
  from the Synology share, and deliberately **outside** both Plex's and ABS's library
  roots so neither indexes half-copied files.
- **`/mnt/media/books/_needs-review/`** — holding area for unsure matches. Carries a
  `.plexignore` so Plex skips it; ABS still surfaces it for matching. beets re-scans it
  each run.

## Data flow

### Daily automated run (unattended, safe)

1. Remux any `.m4a` → `.m4b` losslessly (`ffmpeg -c copy`, no re-encode); strip macOS
   `(1)` duplicate markers from filenames.
2. `beet import` over `/inbox` **and** `/books/_needs-review` in quiet mode with a
   **match-confidence threshold**:
   - **Confident** match → embed tags + write `cover.jpg` → **move** into
     `/books/Author/Title, Book N/`.
   - **Not confident** → move to `/books/_needs-review/` (never guessed into the library).
3. Plex/Prologue pick up newly filed books.

### Review round-trip (the "sync back")

The key mechanism that lets ABS corrections reach on-disk naming:

1. Unsure book sits in `_needs-review` (visible in ABS).
2. From phone/browser, **Match** it in ABS → ABS **embeds corrected tags into the `.m4b`**.
3. **Next daily beets pass** re-scans `_needs-review`, reads the corrected tags, now
   matches confidently, and **renames/moves** the book into `Author/Title, Book N/`.
4. Plex/Prologue see the properly-named book.

So ABS is the mobile matching UI + tag writer; **beets remains the sole thing that renames
on disk**; Plex+Prologue stays the player. Corrections sync back to disk on the next tick.

## VALIDATION GATE (hard stop)

The ABS→beets round-trip (review section, steps 2–3) is **unproven on real data** and is a
**blocking checkpoint**. Before building the rest of the automation, prove on **one book**:

1. Place a deliberately-mis-taggable / unmatched book in `_needs-review`.
2. Match + embed it in ABS.
3. Run a beets pass and confirm it auto-files into the correct `Author/Title, Book N/`
   folder from the embedded tags.

**If this does not work as intended, STOP and rework the review surface** — do not proceed
with the full build. Documented fallbacks to evaluate at that point:

- On-demand `docker exec` interactive re-file (reintroduces minimal server access).
- Replace ABS's review role with **Bragi Books** (a web audiobook matcher that renames on
  disk directly), keeping beets for the confident-auto-file path.

## One-time task: the 7 DCC books

Currently in the Mac's `~/Downloads` as single files (`Author - Title.m4b`, one `.m4a`):

```
Matt Dinniman - Dungeon Crawler Carl.m4b
Matt Dinniman - Carl's Doomsday Scenario.m4b
Matt Dinniman - The Dungeon Anarchist's Cookbook.m4b
Matt Dinniman - The Gate of the Feral Gods.m4b
Matt Dinniman - The Butcher's Masquerade.m4a
Matt Dinniman - The Eye of the Bedlam Bride.m4b
Matt Dinniman - This Inevitable Ruin.m4b
```

Single files → **no merging needed**. Copy them to `/mnt/media/audiobook-inbox`, run the
import, confirm they land as `Matt Dinniman/Dungeon Crawler Carl, Book N/`.

## Error handling

- Daily run only auto-files above the confidence threshold; ambiguous items are parked,
  never guessed.
- `.m4a`→`.m4b` is a lossless remux (stream copy).
- Files only transit `/inbox`; the organizer waits for stable file size before acting so it
  never grabs a half-copied file.
- Nothing is deleted from `_needs-review` until it has been successfully filed.

## Config notes (to pin during implementation)

- beets `import.move: yes`; `paths` set to reproduce `$albumartist/$album/$title` where
  `$album` resolves to `Title, Book N` from beets-audible's series handling. Exact plugin
  config to be pinned against the beets-audible README.
- Scheduling: cron inside the organizer container (documented alternative: a host
  systemd timer that runs `docker exec`).
- Secrets: none expected for beets-audible (Audnexus is unauthenticated). ABS needs no
  external token. If any token is later required, it goes in the stack's `secrets.env` /
  1Password like the other media services.

## Out of scope

- Automated *searching/downloading* of books (no Readarr replacement; downloads stay
  manual via the existing qbittorrent/jackett flow).
- Fully unattended matching of low-confidence books (tracked in issue #3 — notifications,
  threshold tuning, review-folder polish).
- Multi-file / per-chapter book merging (current inputs are single-file; add later if
  needed via `m4b-tool`).
