#!/usr/bin/env python3
"""Build one page that loads every captured company page in an iframe grid.

Not for looking at -- for MEASURING. Each saved page is self-contained (no
external stylesheet, no external script), so an iframe renders exactly what
the server served, and one browser pass can audit all ten at a given width
and colour scheme instead of ten navigations.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                    else "/Users/prathamsharma/intent-engine-econ")
ui = root / "reports" / "ui"
pages = sorted(p.name for p in ui.glob("*.html") if p.name != "index.html")
rows = "\n".join(
    f'<section><h3>{p[:-5]}</h3>'
    f'<iframe data-company="{p[:-5]}" src="{p}" loading="eager"></iframe>'
    f'</section>' for p in pages)
(ui / "index.html").write_text(f"""<!doctype html><meta charset=utf-8>
<title>captured pages</title>
<style>body{{font:13px system-ui;margin:0}}
section{{margin:0 0 24px}} h3{{margin:6px}}
iframe{{width:100%;height:900px;border:1px solid #999}}</style>
{rows}
""", encoding="utf-8")
print(f"{len(pages)} page(s) indexed at reports/ui/index.html")
