#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke-test Bash input-descriptor saving and ordinary pipeline semantics.
# Usage: sh tests/whp-posix-fd.sh /path/to/built/bash
set -eu
BASH_BIN=$1
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/whp-bash-fd.XXXXXX")
trap 'rm -rf "$TMP_ROOT"' 0
trap 'exit 1' 1 2 3 15
cat > "$TMP_ROOT/stdin.sh" <<'EOF'
printf 'before\n'
exec 0</dev/null
printf 'after\n'
EOF
"$BASH_BIN" --noprofile --norc -s < "$TMP_ROOT/stdin.sh" > "$TMP_ROOT/stdin.out"
printf 'before\n' > "$TMP_ROOT/stdin.expected"
diff "$TMP_ROOT/stdin.expected" "$TMP_ROOT/stdin.out"
cat > "$TMP_ROOT/script.sh" <<'EOF'
printf 'start\n'
# A script may already be read from fd 3; redirecting that descriptor must
# preserve remaining buffered commands as Bash moves its private input fd.
eval 'exec 3>"$1/out"'
printf 'continues\n'
printf 'payload\n' >&3
exec 3>&-
printf 'done\n'
EOF
"$BASH_BIN" --noprofile --norc "$TMP_ROOT/script.sh" "$TMP_ROOT" > "$TMP_ROOT/script.out"
printf 'start\ncontinues\ndone\n' > "$TMP_ROOT/script.expected"
diff "$TMP_ROOT/script.expected" "$TMP_ROOT/script.out"
printf 'payload\n' > "$TMP_ROOT/out.expected"
diff "$TMP_ROOT/out.expected" "$TMP_ROOT/out"
"$BASH_BIN" --noprofile --norc -c 'printf "pipeline\n" | /bin/cat; trap ":" INT; ( : )' > "$TMP_ROOT/pipe.out"
printf 'pipeline\n' > "$TMP_ROOT/pipe.expected"
diff "$TMP_ROOT/pipe.expected" "$TMP_ROOT/pipe.out"
