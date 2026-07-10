#!/usr/bin/env python3
"""Merge a folder of audio parts into one chaptered ``.m4b``.

Multi-file audiobooks (e.g. a folder of numbered ``.mp3`` parts) are merged
into a single AAC ``.m4b`` with **one chapter per source file**, re-encoded at
roughly the source bitrate. Album/artist/title tags and a cover are carried
over, and a sibling ``cover.jpg`` is written if none exists. A folder holding a
single audio file is left untouched.

**Safety:** the merged file's duration is checked against the sum of the parts
*before* the source parts are removed. On a mismatch the merge output is
discarded and the parts are kept — these files may be the only copy.

Usage: ``merge_to_m4b.py <folder> [<folder> ...]``  (no-op on single-file dirs)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

AUDIO_EXT = (".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".flac", ".wav")
COVER_NAMES = ("cover.jpg", "cover.png", "folder.jpg")


def ffprobe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path]
    )
    return json.loads(out)


def esc(v):
    for a, b in (("\\", "\\\\"), ("=", "\\="), (";", "\\;"), ("#", "\\#"), ("\n", "\\\n")):
        v = v.replace(a, b)
    return v


def merge_folder(folder):
    folder = folder.rstrip("/")
    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(AUDIO_EXT) and not f.startswith(".")
    )
    if len(files) < 2:
        return False  # single-file (or empty) — nothing to merge

    paths = [os.path.join(folder, f) for f in files]
    durations, first_tags = [], {}
    for i, p in enumerate(paths):
        info = ffprobe(p)
        durations.append(float(info["format"]["duration"]))
        if i == 0:
            first_tags = {k.lower(): v for k, v in (info["format"].get("tags") or {}).items()}
    total_dur = sum(durations)
    total_size = sum(os.path.getsize(p) for p in paths)
    # match the source's effective bitrate (avoids quality loss / bloat), 64–320k
    est = int(total_size * 8 / total_dur) if total_dur else 128000
    bitrate = min(max(est, 64000), 320000)

    name = os.path.basename(folder)
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

        # 2) cover: first part that actually has attached art
        art = os.path.join(td, "cover.jpg")
        have_art = False
        for p in paths:
            try:
                subprocess.check_call(
                    ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", p,
                     "-an", "-frames:v", "1", art],
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue
            if os.path.exists(art) and os.path.getsize(art) > 0:
                have_art = True
                break

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

        # 4) mux chapters + tags (+ cover) into a .m4b temp in the same folder
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", tmp, "-i", meta]
        maps = ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        if have_art:
            cmd += ["-i", art]
            maps += ["-map", "2:v", "-disposition:v:0", "attached_pic"]
        tmp_out = os.path.join(folder, ".merge-tmp.m4b")
        cmd += maps + ["-c", "copy", "-movflags", "+faststart", tmp_out]
        subprocess.check_call(cmd)

        # 5) SAFETY: verify duration before touching the source parts
        got = float(ffprobe(tmp_out)["format"]["duration"])
        tol = max(5.0, 0.02 * total_dur)
        if abs(got - total_dur) > tol:
            os.remove(tmp_out)
            raise RuntimeError(
                "duration check failed: got %.0fs vs expected %.0fs — source parts kept"
                % (got, total_dur)
            )
        os.replace(tmp_out, out)

        # 6) also drop a sibling cover.jpg if the folder has none
        if have_art and not any(os.path.exists(os.path.join(folder, c)) for c in COVER_NAMES):
            shutil.copyfile(art, os.path.join(folder, "cover.jpg"))

    # remove source parts (never the merged output itself)
    out_abs = os.path.abspath(out)
    for p in paths:
        if os.path.abspath(p) != out_abs:
            os.remove(p)
    print("[merge] %s  <-  %d parts (%.0f min, %dk)"
          % (os.path.basename(out), len(paths), total_dur / 60, bitrate // 1000))
    return True


def main(argv):
    rc = 0
    for folder in argv:
        if not os.path.isdir(folder):
            continue
        try:
            merge_folder(folder)
        except Exception as exc:  # noqa: BLE001 - never abort the whole batch
            print("[merge] FAILED for %s: %s" % (folder, exc), file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
