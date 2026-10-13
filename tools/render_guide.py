#!/usr/bin/env python3
"""Render DEPLOYMENT-GUIDE.md to a self-contained HTML page (no external files).
Needs the 'markdown' package: pip install markdown"""
import sys
import markdown

src, dst = sys.argv[1], sys.argv[2]
body = markdown.markdown(open(src, encoding="utf-8").read(),
                         extensions=["tables", "fenced_code", "toc", "sane_lists"])
title = "Data Centre Kit – Deployment Guide"
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#ffffff; --text:#14201f; --muted:#4f6664; --accent:#007f75; --line:#d5e0df; --code:#f2f6f6; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0b1113; --text:#dff7f4; --muted:#8aa6a2; --accent:#00ffea; --line:#23363a; --code:#121c1f; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:16px/1.6 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }}
h1 {{ color:var(--accent); font-size:2em; line-height:1.2; }}
h2 {{ color:var(--accent); border-bottom:2px solid var(--accent); padding-bottom:4px; margin-top:2.2em; }}
h3 {{ margin-top:1.6em; }}
a {{ color:var(--accent); }}
code {{ font-family: Consolas, 'Courier New', monospace; background:var(--code); padding:1px 5px; border-radius:4px; font-size:.92em; }}
pre {{ background:var(--code); border-left:3px solid var(--accent); padding:12px 14px; overflow-x:auto; border-radius:4px; }}
pre code {{ background:none; padding:0; }}
table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:.95em; display:block; overflow-x:auto; }}
th, td {{ border:1px solid var(--line); padding:6px 10px; text-align:left; vertical-align:top; }}
th {{ background:var(--code); }}
li {{ margin:3px 0; }}
hr {{ border:0; border-top:1px solid var(--line); margin:2em 0; }}
@media print {{
  body {{ font-size:11pt; }} main {{ max-width:none; padding:0; }}
  h2 {{ page-break-before: always; }} pre, table {{ page-break-inside: avoid; }}
  a {{ color: inherit; }}
}}
</style>
</head>
<body><main>
{body}
</main></body>
</html>
"""
open(dst, "w", encoding="utf-8").write(html)
print("wrote", dst)
