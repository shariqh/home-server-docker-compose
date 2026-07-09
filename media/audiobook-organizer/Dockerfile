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
COPY plex_sync.py /usr/local/bin/plex_sync.py
RUN chmod +x /usr/local/bin/organize /usr/local/bin/entrypoint

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/entrypoint"]
