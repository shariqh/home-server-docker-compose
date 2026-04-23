FROM myoung34/github-runner:ubuntu-noble

# Install the 1Password CLI so workflows can `op run -- <command>` to
# resolve secret references at job time without ever writing plaintext
# values to disk.
#
# The APT signing key is pinned to 1Password's published fingerprint
# (3FEF9748469ADBE15DA7CA80AC2D62742012EA22, valid through 2032-05-16).
# The build fails loudly if the downloaded key's fingerprint doesn't
# match, closing the supply-chain risk of silently trusting whatever
# the downloads endpoint serves.
RUN set -eux; \
    expected_fingerprint='3FEF9748469ADBE15DA7CA80AC2D62742012EA22'; \
    key_tmp="$(mktemp)"; \
    curl --fail --silent --show-error --location \
        --output "${key_tmp}" \
        'https://downloads.1password.com/linux/keys/1password.asc'; \
    actual_fingerprint="$(gpg --batch --with-colons --show-keys "${key_tmp}" \
        | awk -F: '/^fpr:/ { print $10; exit }')"; \
    [ "${actual_fingerprint}" = "${expected_fingerprint}" ] \
        || { echo "1Password signing key fingerprint mismatch: ${actual_fingerprint} != ${expected_fingerprint}" >&2; exit 1; }; \
    gpg --dearmor --output /usr/share/keyrings/1password-archive-keyring.gpg "${key_tmp}"; \
    rm -f "${key_tmp}"; \
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/1password-archive-keyring.gpg] https://downloads.1password.com/linux/debian/amd64 stable main' \
        > /etc/apt/sources.list.d/1password.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends 1password-cli; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*
