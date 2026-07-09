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

# Error counter lives in a file because the find|while pipelines below run
# in subshells and can't mutate a parent-shell variable. Every place that
# fails to safely file or park an input increments this.
ERR_COUNT_FILE="$(mktemp)"
echo 0 > "$ERR_COUNT_FILE"
trap 'rm -f "$ERR_COUNT_FILE"' EXIT

note_error() {
  # note_error <message>: log to stderr and bump the shared error counter.
  echo "[organize] WARN $1" >&2
  local n
  n="$(cat "$ERR_COUNT_FILE" 2>/dev/null || echo 0)"
  echo "$((n + 1))" > "$ERR_COUNT_FILE"
}

safe_mv() {
  # safe_mv <src> <dest>: move src to the exact path dest, never clobbering
  # an existing file. On a name collision, disambiguate the destination so
  # the file still gets moved instead of silently staying at src (mv -n
  # would otherwise no-op and leave it behind). Returns 0 on success.
  local src="$1" dest="$2" destdir base stem ext i
  destdir="$(dirname "$dest")"
  base="$(basename "$dest")"

  if [ -e "$dest" ]; then
    stem="${base%.*}"
    ext="${base##*.}"
    if [ "$stem" = "$ext" ]; then
      # no extension
      stem="$base"; ext=""
    fi
    i=1
    while :; do
      if [ -n "$ext" ] && [ "$ext" != "$base" ]; then
        dest="$destdir/${stem} (dup-$$-$i).${ext}"
      else
        dest="$destdir/${base} (dup-$$-$i)"
      fi
      [ -e "$dest" ] || break
      i=$((i + 1))
    done
    echo "[organize] WARN destination collision for $base, renaming to $(basename "$dest")" >&2
  fi

  if mv -n "$src" "$dest" 2>/dev/null && [ -e "$dest" ] && [ ! -e "$src" ]; then
    return 0
  fi

  note_error "move failed: $src -> $dest"
  return 1
}

park_path() {
  # park_path <path>: park a leftover inbox entry under $REVIEW. Directories
  # are moved as-is (one-book-per-folder already true). Loose files are
  # wrapped in their own folder first so $REVIEW stays uniformly
  # one-folder-per-book, mirroring the step 3 wrap convention.
  local p="$1" base name dir
  base="$(basename "$p")"
  if [ -d "$p" ]; then
    echo "[organize] parking for review: $base"
    safe_mv "$p" "$REVIEW/$base"
  else
    name="${base%.*}"
    [ -z "$name" ] && name="$base"
    dir="$INBOX/$name"
    if [ -e "$dir" ]; then
      dir="$INBOX/${name} (review-$$)"
    fi
    if mkdir -p "$dir" && safe_mv "$p" "$dir/$base"; then
      echo "[organize] parking for review: $name/$base"
      if ! safe_mv "$dir" "$REVIEW/$(basename "$dir")"; then
        note_error "failed to park wrapped file $p (left at $dir)"
      fi
    else
      note_error "failed to wrap+park loose file: $p"
    fi
  fi
}

echo "[organize] preprocessing $INBOX"

# 0) Merge multi-file books into one chaptered .m4b. A dropped folder holding
# more than one audio file (e.g. a set of numbered .mp3 parts) is merged into a
# single .m4b (one chapter per part) before matching. Single-file books and
# loose files are untouched. Runs only over inbox top-level folders.
find "$INBOX" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' d; do
  parts="$(find "$d" -maxdepth 1 -type f \( -iname '*.mp3' -o -iname '*.m4a' \
    -o -iname '*.m4b' -o -iname '*.aac' -o -iname '*.flac' -o -iname '*.ogg' \
    -o -iname '*.opus' -o -iname '*.wav' \) | wc -l | tr -d ' ')"
  if [ "$parts" -gt 1 ]; then
    echo "[organize] merging $parts parts in $(basename "$d")"
    python3 /usr/local/bin/merge_to_m4b.py "$d" || note_error "merge failed for $d"
  fi
done

# 1) Normalize .m4a -> .m4b. .m4a and .m4b are the same MP4/AAC container, so
# a plain rename is lossless and preserves chapters, tags, and every stream.
# We deliberately avoid an ffmpeg remux here: the strict m4b/ipod muxer
# rejects some perfectly valid inputs (e.g. timed-text chapter tracks) and
# there is nothing to transcode. Also scan $REVIEW so a previously-parked
# .m4a gets normalized on a later pass.
find "$INBOX" "$REVIEW" -type f -iname '*.m4a' -print0 | while IFS= read -r -d '' f; do
  out="${f%.*}.m4b"
  echo "[organize] rename $(basename "$f") -> $(basename "$out")"
  safe_mv "$f" "$out" || note_error "could not rename $f -> $out"
done

# 2) Strip macOS duplicate markers like " (1)" before the extension
find "$INBOX" -type f -iname '*.m4b' -print0 | while IFS= read -r -d '' f; do
  clean="$(echo "$f" | sed -E 's/ \([0-9]+\)(\.[A-Za-z0-9]+)$/\1/')"
  if [ "$clean" != "$f" ]; then
    safe_mv "$f" "$clean" || true
  fi
done

# 3) beets-audible expects one book per folder: wrap loose top-level files
find "$INBOX" -maxdepth 1 -type f -iname '*.m4b' -print0 | while IFS= read -r -d '' f; do
  base="$(basename "$f")"; name="${base%.*}"
  dir="$INBOX/$name"
  mkdir -p "$dir"
  safe_mv "$f" "$dir/$base" || true
done

echo "[organize] importing (interactive=$INTERACTIVE)"
if [ "$INTERACTIVE" -eq 1 ]; then
  beet import "$INBOX" "$REVIEW"
else
  beet import -q "$INBOX" "$REVIEW"
fi

# 4) Anything still in the inbox was not confidently matched -> park for
# review. Catches both per-book directories (the common case) and any
# loose files left behind (e.g. a book that failed remux and was parked
# above, or any other stray file) so nothing sits in the inbox unseen.
find "$INBOX" -mindepth 1 -maxdepth 1 \( -type d -o -type f \) -print0 | while IFS= read -r -d '' entry; do
  park_path "$entry"
done

# 5) Push covers + build series collections in Plex (best-effort; the new
# Plex Music agent won't show local audiobook art on its own, and series
# collections feed Prologue). Never fails the organize pass.
python3 /usr/local/bin/plex_sync.py || echo "[organize] plex sync skipped/failed (non-fatal)" >&2

TOTAL_ERRORS="$(cat "$ERR_COUNT_FILE" 2>/dev/null || echo 0)"
if [ "$TOTAL_ERRORS" -gt 0 ]; then
  echo "[organize] done with errors: $TOTAL_ERRORS item(s) had a park/move failure, see WARN lines above" >&2
  exit 1
fi

echo "[organize] done"
