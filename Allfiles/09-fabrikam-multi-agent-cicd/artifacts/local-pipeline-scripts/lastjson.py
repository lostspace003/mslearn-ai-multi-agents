"""Keep only the script's final JSON document (az subcommands also print JSON/progress to stdout)."""
import sys
p, marker = sys.argv[1], sys.argv[2]
t = open(p, encoding="utf-8").read()
i = t.rfind(marker)
if i < 0:
    raise SystemExit(f"marker {marker!r} not found in {p}")
open(p.replace(".raw", ""), "w", encoding="utf-8").write(t[i:])
