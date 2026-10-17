#!/usr/bin/env python3
"""Exercise the real subst.c append routine with UBSan and growth boundaries."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "subst.c").read_text(encoding="utf-8")
start = source.index("INLINE char *\nsub_append_string (")
end = source.index("\n}\n", start) + len("\n}")
function = source[start:end]
assert "#include <stdckdint.h>" in source
for required in (
    "ckd_add (&end, *indx, srclen)",
    "ckd_add (&required, end, (size_t)1)",
    "ckd_add (&capacity, required, padding)",
    "*indx = end;",
):
    assert required in function, required
assert "srclen + *indx" not in function
assert "n + DEFAULT_ARRAY_SIZE" not in function

fixture = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define INLINE static inline
#define DEFAULT_ARRAY_SIZE 128
#define STRLEN(s) strlen(s)
#define FASTCOPY(s, d, n) memcpy(d, s, n)
#define _(s) (s)
/* Same checked arithmetic contract as Bash's generated stdckdint.h. */
#define ckd_add(out, a, b) __builtin_add_overflow(a, b, out)
static void fatal_error(const char *message) {
    (void)message;
    exit(33);
}
static void *xrealloc(void *ptr, size_t size) {
    if (size > 65536) exit(size == SIZE_MAX ? 44 : 45);
    void *result = realloc(ptr, size);
    if (!result) abort();
    return result;
}
""" + function + r"""

static char *source_string(size_t len) {
    char *s = malloc(len + 1);
    if (!s) abort();
    memset(s, 'Z', len);
    s[len] = 0;
    return s;
}

int main(int argc, char **argv) {
    int mode = argc > 1 ? atoi(argv[1]) : 0;
    size_t index = 0, capacity = 0;
    char *buffer = NULL;
    if (mode) {
        index = mode == 1 ? SIZE_MAX :
                mode == 2 ? SIZE_MAX - 1 : SIZE_MAX - 2;
        capacity = 1;
        buffer = malloc(1);
        char *s = source_string(mode == 3 ? 2 : 1);
        (void)sub_append_string(s, buffer, &index, &capacity);
        return 50;
    }

    const size_t lengths[] = {0, 1, 125, 1, 128, 255, 512, 1000};
    for (size_t i = 0; i < sizeof(lengths)/sizeof(lengths[0]); ++i) {
        size_t next = index + lengths[i], previous_capacity = capacity;
        buffer = sub_append_string(source_string(lengths[i]),
                                   buffer, &index, &capacity);
        if (index != next || buffer[index] != 0) return 1;
        for (size_t j = 0; j < index; ++j)
            if (buffer[j] != 'Z') return 2;
        size_t expected = previous_capacity;
        if (next >= previous_capacity)
            expected = next + 128 - next % 128;
        if (capacity != expected) return 3;
    }
    size_t old_index = index, old_capacity = capacity;
    if (sub_append_string(NULL, buffer, &index, &capacity) != buffer)
        return 4;
    if (index != old_index || capacity != old_capacity) return 5;
    free(buffer);
    return 0;
}
"""

compiler = os.environ.get("CC") or shutil.which("clang") or shutil.which("cc")
if not compiler:
    raise SystemExit("A C compiler is required for Bash substitution tests")
with tempfile.TemporaryDirectory(prefix="whp-bash-subst-") as d:
    cfile, exe = Path(d) / "test.c", Path(d) / "test"
    cfile.write_text(fixture, encoding="utf-8")
    subprocess.run(
        [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
         str(cfile), "-o", str(exe)],
        check=True,
    )
    for mode, expected in [(0, 0), (1, 33), (2, 33), (3, 33), (4, 44)]:
        run = subprocess.run([str(exe), str(mode)], check=False)
        if run.returncode != expected:
            raise AssertionError(
                f"subst.c case {mode}: exit {run.returncode}, expected {expected}"
            )
print("WHP Bash subst.c checked string append: passed")
