#!/usr/bin/env python3
"""Post-organize Plex sync for the audiobook library.

After the organizer files books, this:
  1. Triggers a Plex scan of the audiobook library so new books import.
  2. Uploads each thumb-less album's local ``cover.jpg`` as its Plex poster
     (Plex's Music agent won't use local audiobook cover art on its own).
  3. Puts each book into a Plex collection named after its series (read from
     the file's ``SERIES`` tag) so series group together and feed Prologue.

Best-effort and idempotent: albums that already have a poster are left alone,
collection membership is re-set each run (no duplicates), and it never fails
the caller (always exits 0) if Plex is unreachable or no token is found.

Config via env (all optional):
  PLEX_URL         default http://host.docker.internal:32400
  PLEX_TOKEN       if unset, read from /plex-prefs.xml (mounted read-only)
  PLEX_BOOKS_PATH  Plex library Location to match, default /books
"""
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

try:
    from mutagen.mp4 import MP4
except Exception:  # mutagen should always be present in this image
    MP4 = None

PLEX = os.environ.get("PLEX_URL", "http://host.docker.internal:32400").rstrip("/")
LIB_PATH = os.environ.get("PLEX_BOOKS_PATH", "/books")
SERIES_ATOM = "----:com.apple.iTunes:SERIES"
ALBUM_TYPE = "9"  # Plex metadata type for a music album (one audiobook)


def get_token():
    tok = os.environ.get("PLEX_TOKEN")
    if tok:
        return tok
    try:
        m = re.search(r'PlexOnlineToken="([^"]+)"', open("/plex-prefs.xml").read())
        return m.group(1) if m else None
    except OSError:
        return None


def series_of(m4b_path):
    if MP4 is None:
        return None
    try:
        val = MP4(m4b_path).tags.get(SERIES_ATOM)
        if val:
            return bytes(val[0]).decode("utf-8", "ignore").strip() or None
    except Exception:
        pass
    return None


def main():
    tok = get_token()
    if not tok:
        print("[plex-sync] no Plex token available; skipping")
        return 0

    def api(path, method="GET", data=None, ctype=None):
        url = f"{PLEX}{path}" + ("&" if "?" in path else "?") + "X-Plex-Token=" + tok
        req = urllib.request.Request(url, data=data, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        return urllib.request.urlopen(req, timeout=30)

    try:
        secs = ET.fromstring(api("/library/sections").read())
    except Exception as exc:
        print(f"[plex-sync] Plex unreachable ({exc}); skipping")
        return 0

    sec = next(
        (
            d.get("key")
            for d in secs.findall("Directory")
            if any(loc.get("path") == LIB_PATH for loc in d.findall("Location"))
        ),
        None,
    )
    if not sec:
        print(f"[plex-sync] no Plex library with location {LIB_PATH}; skipping")
        return 0

    # Scan so newly-filed books import, then wait (bounded) for scans to settle.
    try:
        api(f"/library/sections/{sec}/refresh")
    except Exception:
        pass
    for _ in range(18):  # up to ~3 min
        try:
            if not ET.fromstring(api("/activities").read()).findall("Activity"):
                break
        except Exception:
            break
        time.sleep(10)

    covers = collected = 0
    artists = ET.fromstring(api(f"/library/sections/{sec}/all").read())
    for artist in artists.findall("Directory"):
        albums = ET.fromstring(
            api(f"/library/metadata/{artist.get('ratingKey')}/children").read()
        )
        for album in albums.findall("Directory"):
            ak = album.get("ratingKey")
            tracks = ET.fromstring(api(f"/library/metadata/{ak}/children").read())
            part = tracks.find(".//Part")
            if part is None or not part.get("file"):
                continue
            m4b = part.get("file")  # Plex path == our /books mount path
            folder = os.path.dirname(m4b)

            # 1) Cover: only fill in missing posters; leave existing ones alone.
            cover = os.path.join(folder, "cover.jpg")
            if not album.get("thumb") and os.path.exists(cover):
                try:
                    api(
                        f"/library/metadata/{ak}/posters",
                        "POST",
                        open(cover, "rb").read(),
                        "image/jpeg",
                    )
                    covers += 1
                except Exception as exc:
                    print(f"[plex-sync] cover upload failed for {cover}: {exc}")

            # 2) Collection by series (idempotent).
            series = series_of(m4b)
            if series:
                query = urllib.parse.urlencode(
                    {
                        "type": ALBUM_TYPE,
                        "id": ak,
                        "collection[0].tag.tag": series,
                        "X-Plex-Token": tok,
                    }
                )
                try:
                    api(f"/library/sections/{sec}/all?{query}", "PUT")
                    collected += 1
                except Exception as exc:
                    print(f"[plex-sync] collection set failed for {ak}: {exc}")

    print(f"[plex-sync] covers pushed: {covers}, albums assigned to collections: {collected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
