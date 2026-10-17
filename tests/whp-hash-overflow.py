#!/usr/bin/env python3
"""WHP hash-table allocation and signed-overflow regression.

Builds the *actual* hash_grow() source with a minimal HASH_TABLE and a stub
hash_rehash(). Runs boundary cases with a C undefined-behavior sanitizer.
Does not need a configured or fully built Bash tree.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "hashlib.c").read_text(encoding="utf-8")

# Verify both allocation sites use Bash's existing overflow-checking helper.
assert "xreallocarray (NULL, buckets, sizeof (BUCKET_CONTENTS *))" in source
assert "xreallocarray (NULL, table->nbuckets, sizeof (BUCKET_CONTENTS *))" in source
assert "xmalloc (buckets * sizeof" not in source
assert "xmalloc (table->nbuckets * sizeof" not in source

macros = source.split("/* tunable constants for rehashing */", 1)[1].split(
    "/* an initial approximation */", 1
)[0]
body = source.split("static void\nhash_grow (HASH_TABLE *table)\n{", 1)[1].split(
    "\n}\n", 1
)[0]
assert "INT_MAX / HASH_REHASH_MULTIPLIER" in body

fixture = (
    "#include <limits.h>\n"
    "typedef struct { int nbuckets; int nentries; } HASH_TABLE;\n"
    + macros
    + "\nstatic int calls, last_size;\n"
    + "static void hash_rehash (HASH_TABLE *table, int nsize)\n"
    + "{ (void)table; ++calls; last_size = nsize; }\n"
    + "static void hash_grow (HASH_TABLE *table)\n{"
    + body + "\n}\n"
    + r"""
int main(void)
{
    HASH_TABLE t;
    struct test_case { int buckets, expected; };
    const struct test_case cases[] = {
        {128, 512},
        {INT_MAX / 4, (INT_MAX / 4) * 4},
        {INT_MAX / 4 + 1, 0},
        {INT_MAX, 0},
        {0, 0},
        {-1, 0}
    };
    unsigned int i;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        t.nbuckets = cases[i].buckets;
        t.nentries = 0;
        calls = last_size = 0;
        hash_grow(&t);
        if (calls != (cases[i].expected != 0))
            return 10 + (int)i;
        if (calls && last_size != cases[i].expected)
            return 20 + (int)i;
    }
    t.nbuckets = 128;
    t.nentries = 255;
    if (HASH_SHOULDGROW(&t)) return 30;
    t.nentries = 256;
    if (!HASH_SHOULDGROW(&t)) return 31;
    t.nbuckets = INT_MAX;
    t.nentries = INT_MAX;
    if (HASH_SHOULDGROW(&t)) return 32;
    return 0;
}
"""
)

compiler = os.environ.get("CC") or shutil.which("clang") or shutil.which("cc")
if not compiler:
    raise SystemExit("A C compiler is required for the WHP hash-overflow test")
with tempfile.TemporaryDirectory(prefix="whp-bash-hash-") as d:
    source_file = Path(d) / "check.c"
    binary = Path(d) / "check"
    source_file.write_text(fixture, encoding="utf-8")
    subprocess.run(
        [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
         str(source_file), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
print("WHP Bash hash growth and checked bucket allocation: passed")
