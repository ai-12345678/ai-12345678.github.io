#!/usr/bin/env python3
"""Build the GitHub Pages site from the repository root.

Rules:
- Copy the hand-written home page and the Kubernetes/Linux content to _site/.
- Keep hand-written Kubernetes HTML unchanged.
- Generate a sibling HTML page for every Markdown file under linux/.
- Keep the original Markdown files available for download.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
LINUX = ROOT / "linux"
PUBLISH_ENTRIES = ("index.html", "kubernetes", "linux")


def extract_title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def render_page(title: str, body: str, md_href: str) -> str:
    safe_title = html.escape(title)
    safe_md_href = html.escape(md_href, quote=True)
    mermaid_script = ""
    if 'class="language-mermaid"' in body:
        mermaid_script = """<script type="module">
import mermaid from 'https://esm.sh/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
for (const [index, code] of Array.from(document.querySelectorAll('pre > code.language-mermaid')).entries()) {
  try {
    const { svg, bindFunctions } = await mermaid.render(`diagram-${index}`, code.textContent);
    const panel = document.createElement('div');
    panel.className = 'mermaid-diagram';
    panel.innerHTML = svg;
    code.parentElement.replaceWith(panel);
    bindFunctions?.(panel);
  } catch (error) {
    console.error('Unable to render Mermaid diagram', error);
  }
}
</script>"""
    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
<meta charset=\"UTF-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>{safe_title}</title>
<style>
  :root {{
    --bg: #f6f7f9;
    --panel: #ffffff;
    --text: #1f2328;
    --muted: #656d76;
    --border: #d8dee4;
    --blue: #0969da;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.75;
  }}
  .page {{
    width: min(920px, calc(100% - 32px));
    margin: 0 auto;
    padding: 36px 0 64px;
  }}
  .toolbar {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 18px;
    font-size: 14px;
  }}
  .toolbar a {{ color: var(--blue); text-decoration: none; }}
  article {{
    padding: 34px 40px;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: var(--panel);
  }}
  h1, h2, h3 {{ line-height: 1.3; }}
  h1 {{ margin-top: 0; }}
  h2 {{ margin-top: 32px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
  code {{
    padding: .15em .35em;
    border-radius: 6px;
    background: #eff1f3;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  pre {{
    overflow-x: auto;
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: #f6f8fa;
  }}
  pre code {{ padding: 0; background: transparent; }}
  .mermaid-diagram {{ overflow-x: auto; margin: 24px 0; }}
  .mermaid-diagram svg {{ display: block; max-width: none !important; margin: 0 auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 10px; border: 1px solid var(--border); text-align: left; }}
  blockquote {{ margin-left: 0; padding-left: 16px; border-left: 4px solid var(--border); color: var(--muted); }}
  @media (max-width: 640px) {{ article {{ padding: 24px 20px; }} }}
</style>
</head>
<body>
<main class=\"page\">
  <nav class=\"toolbar\">
    <a href=\"/\">← 返回文档首页</a>
    <a href=\"{safe_md_href}\" download>下载 Markdown</a>
  </nav>
  <article>
{body}
  </article>
</main>
{mermaid_script}
</body>
</html>
"""


def copy_publish_entries() -> None:
    for entry_name in PUBLISH_ENTRIES:
        source = ROOT / entry_name
        target = SITE / entry_name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    copy_publish_entries()

    generated = 0
    for md_path in LINUX.rglob("*.md"):
        rel = md_path.relative_to(ROOT)
        output_html = SITE / rel.with_suffix(".html")
        source = md_path.read_text(encoding="utf-8")
        title = extract_title(source, md_path.stem.replace("-", " ").title())
        body = markdown.markdown(
            source,
            extensions=["fenced_code", "tables", "sane_lists"],
            output_format="html5",
        )
        output_html.parent.mkdir(parents=True, exist_ok=True)
        output_html.write_text(
            render_page(title, body, md_path.name), encoding="utf-8"
        )
        generated += 1

    print(f"Pages build complete: generated={generated}, output={SITE}")


if __name__ == "__main__":
    main()
