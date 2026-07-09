#!/usr/bin/env python3
"""Merge a folder of audio parts into one chaptered ``.m4b``.

Multi-file audiobooks (e.g. a folder of numbered ``.mp3`` parts) are merged
into a single AAC ``.m4b`` with **one chapter per source file**, re-encoded at
roughly the source bitrate. Album/artist/title tags and the embedded cover
from the first part are carried over; the source parts are then removed. A
folder that already holds a single audio file is left untouched.

Usage: ``merge_to_m4b.py <folder> [<folder> ...]``  (no-op on single-file dirs)
"""
import json
import os
import subprocess
import sys
import tempfile

AUDIO_EXT = (".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".flac", ".wav")


def ffprobe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path]
    )
    return json.loads(out)


def esc(v):
    # escape for the ffmetadata format
    for a, b in (("\\", "\\\\"), ("=", "\\="), (";", "\\;"), ("#", "\\#"), ("\n", "\\\n")):
        v = v.replace(a, b)
    return v


def merge_folder(folder):
    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(AUDIO_EXT) and not f.startswith(".")
    )
    if len(files) < 2:
        return False  # single-file (or empty) — nothing to merge

    paths = [os.path.join(folder, f) for f in files]
    durations, first_tags, bitrate = [], {}, None
    for i, p in enumerate(paths):
        info = ffprobe(p)
        durations.append(float(info["format"]["duration"]))
        if i == 0:
            first_tags = {k.lower(): v for k, v in (info["format"].get("tags") or {}).items()}
            try:
                bitrate = int(info["format"]["bit_rate"])
            except (KeyError, ValueError):
                bitrate = None
    bitrate = max(bitrate or 128000, 64000)

    name = os.path.basename(folder.rstrip("/"))
    out = os.path.join(folder, name + ".m4b")

    with tempfile.TemporaryDirectory() as td:
        listfile = os.path.join(td, "list.txt")
        with open(listfile, "w") as fh:
            for p in paths:
                fh.write("file '%s'\n" % p.replace("'", "'\\''"))

        # 1) concat + re-encode audio to AAC
        tmp = os.path.join(td, "audio.m4b")
        subprocess.check_call([
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", listfile,
            "-vn", "-c:a", "aac", "-b:a", str(bitrate), tmp,
        ])

        # 2) pull the cover out of the first part (if any)
        art = os.path.join(td, "cover.jpg")
        try:
            subprocess.check_call(
                ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", paths[0],
                 "-an", "-frames:v", "1", art],
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            art = None
        if art and (not os.path.exists(art) or os.path.getsize(art) == 0):
            art = None

        # 3) ffmetadata: carried tags + one chapter per source file
        meta = os.path.join(td, "meta.txt")
        with open(meta, "w") as fh:
            fh.write(";FFMETADATA1\n")
            for key in ("album", "artist", "album_artist", "title", "genre",
                        "date", "composer", "publisher", "comment"):
                if first_tags.get(key):
                    fh.write("%s=%s\n" % (key, esc(first_tags[key])))
            start = 0.0
            for i, d in enumerate(durations):
                fh.write("[CHAPTER]\nTIMEBASE=1/1000\nSTART=%d\nEND=%d\ntitle=Part %d\n"
                         % (round(start * 1000), round((start + d) * 1000), i + 1))
                start += d

        # 4) mux chapters + tags (+ cover) into the final m4b
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", tmp, "-i", meta]
        maps = ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        if art:
            cmd += ["-i", art]
            maps += ["-map", "2:v", "-disposition:v:0", "attached_pic"]
        # write to a .m4b-suffixed temp in the same folder so ffmpeg picks the
        # right muxer and the rename stays on one filesystem
        tmp_out = os.path.join(folder, ".merge-tmp.m4b")
        cmd += maps + ["-c", "copy", "-movflags", "+faststart", tmp_out]
        subprocess.check_call(cmd)
        os.replace(tmp_out, out)

    for p in paths:
        os.remove(p)
    print("[merge] %s  <-  %d parts (%.0f min)"
          % (os.path.basename(out), len(paths), sum(durations) / 60))
    return True


def main(argv):
    rc = 0
    for folder in argv:
        if not os.path.isdir(folder):
            continue
        try:
            merge_folder(folder)
        except Exception as exc:  # noqa: BLE001 - never abort the whole pass
            print("[merge] FAILED for %s: %s" % (folder, exc), file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
