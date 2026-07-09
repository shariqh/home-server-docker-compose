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
