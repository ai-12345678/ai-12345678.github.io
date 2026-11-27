#!/usr/bin/env python3
"""Build the GitHub Pages site from the repository root.

Rules:
- Copy the hand-written home page and publishable content directories to _site/.
- Keep hand-written Kubernetes HTML unchanged.
- Generate a sibling HTML page for every Markdown file under linux/, agents/, lang/, golang/, models/, network/, asm/, speech/, webrtc/, cpp/, and tcp/.
- Keep the original Markdown files available for download.
- Export documentation as topic and article EPUBs, and list the topics in opds.xml.
"""

from __future__ import annotations

import html
import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote

import markdown

from epub_export import article_epub_path, build_epub_collections

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
CONTENT_DIRS = (ROOT / "linux", ROOT / "agents", ROOT / "lang", ROOT / "golang", ROOT / "models", ROOT / "network", ROOT / "asm", ROOT / "speech", ROOT / "webrtc", ROOT / "cpp", ROOT / "tcp")
PUBLISH_ENTRIES = ("index.html", "download", "assets", "kubernetes", "linux", "agents", "lang", "golang", "models", "network", "asm", "speech", "webrtc", "cpp", "tcp")
PDF_ASSET = Path("assets", "pdf-export.js")
EPUB_STYLE = Path("assets", "epub-export.css")


def extract_title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def asset_href(page: Path, target: Path) -> str:
    relative = Path(os.path.relpath(SITE / target, page.parent)).as_posix()
    return html.escape(quote(relative), quote=True)


def epub_button(page: Path) -> str:
    path = page.relative_to(SITE)
    href = asset_href(page, article_epub_path(path))
    filename = html.escape("-".join(path.with_suffix("").parts) + ".epub", quote=True)
    return f'<a class="epub-export-button" href="{href}" download="{filename}">导出 EPUB</a>'


def epub_style(page: Path) -> str:
    return f'<link rel="stylesheet" href="{asset_href(page, EPUB_STYLE)}">'


def render_page(title: str, body: str, md_href: str, page: Path) -> str:
    safe_title = html.escape(title)
    safe_md_href = html.escape(md_href, quote=True)
    math_script = ""
    if 'class="arithmatex"' in body:
        math_script = r"""<script>
window.MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]']],
    processEscapes: true,
    processEnvironments: true
  },
  options: { ignoreHtmlClass: '.*', processHtmlClass: 'arithmatex' },
  svg: { fontCache: 'global' }
};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js"
  onerror="this.onerror=null;this.src='https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-svg.js'"></script>"""
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
    font-size: 16px;
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
  h1 {{ margin-top: 0; font-size: 30px; }}
  h2 {{ font-size: 21px; margin-top: 32px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
  h3 {{ font-size: 18px; }}
  code {{
    font-size: 14px;
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
  div.arithmatex {{ overflow-x: auto; margin: 24px 0; padding: 8px 0; }}
  .arithmatex mjx-container[display="true"] {{ margin: 0 !important; }}
  .mermaid-diagram {{ overflow-x: auto; margin: 24px 0; }}
  .mermaid-diagram svg {{ display: block; max-width: none !important; margin: 0 auto; }}
  img {{ display: block; max-width: 100%; height: auto; margin: 20px auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 10px; border: 1px solid var(--border); text-align: left; }}
  blockquote {{ margin-left: 0; padding-left: 16px; border-left: 4px solid var(--border); color: var(--muted); }}
  @media (max-width: 640px) {{ article {{ padding: 24px 20px; }} h1 {{ font-size: 26px; }} }}
</style>
{epub_style(page)}
{math_script}
</head>
<body>
<main class=\"page\">
  <nav class=\"toolbar\">
    <a href=\"/\">← 返回文档首页</a>
    <span class=\"export-actions\">
      <a href=\"{safe_md_href}\" download>下载 Markdown</a>
      {epub_button(page)}
    </span>
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


def inject_export_controls(generated_pages: set[Path]) -> int:
    """Attach download controls to the hand-written pages and keep PDF exports available."""
    injected = 0
    for html_path in SITE.rglob("*.html"):
        if html_path in (SITE / "index.html", SITE / "download" / "index.html"):
            continue
        page = html_path.read_text(encoding="utf-8")
        epub = SITE / article_epub_path(html_path.relative_to(SITE))
        if epub.is_file() and html_path not in generated_pages:
            controls = f'<div class="export-actions export-actions-static">{epub_button(html_path)}</div>'
            page = re.sub(r"</head\s*>", lambda match: epub_style(html_path) + "\n" + match[0],
                          page, count=1, flags=re.IGNORECASE)
            page = re.sub(r"<body\b[^>]*>", lambda match: match[0] + "\n" + controls + "\n",
                          page, count=1, flags=re.IGNORECASE)
        if 'pdf-export.js"></script>' in page:
            html_path.write_text(page, encoding="utf-8")
            continue

        # Relative URLs also work when the site is previewed under a subpath.
        tag = f'<script defer src="{asset_href(html_path, PDF_ASSET)}"></script>'
        closing_body = re.search(r"</body\s*>", page, flags=re.IGNORECASE)
        if closing_body:
            page = page[:closing_body.start()] + tag + "\n" + page[closing_body.start():]
        else:
            page += "\n" + tag + "\n"
        html_path.write_text(page, encoding="utf-8")
        injected += 1
    return injected


def main() -> None:
    if shutil.which("pandoc") is None:
        raise SystemExit("Pandoc is required to build the EPUB downloads.")
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    copy_publish_entries()

    generated_pages = set()
    for content_dir in CONTENT_DIRS:
        for md_path in content_dir.rglob("*.md"):
            rel = md_path.relative_to(ROOT)
            output_html = SITE / rel.with_suffix(".html")
            source = md_path.read_text(encoding="utf-8")
            title = extract_title(source, md_path.stem.replace("-", " ").title())
            body = markdown.markdown(
                source,
                extensions=["fenced_code", "tables", "sane_lists", "pymdownx.arithmatex"],
                extension_configs={"pymdownx.arithmatex": {"generic": True}},
                output_format="html5",
            )
            output_html.parent.mkdir(parents=True, exist_ok=True)
            output_html.write_text(
                render_page(title, body, md_path.name, output_html), encoding="utf-8"
            )
            generated_pages.add(output_html)

    topics = tuple(
        entry for entry in PUBLISH_ENTRIES if entry not in ("assets", "download") and (SITE / entry).is_dir()
    )
    topic_count, article_count = build_epub_collections(SITE, topics)
    injected = inject_export_controls(generated_pages)
    print(f"Pages build complete: generated={len(generated_pages)}, pdf_export={injected}, "
          f"topic_epubs={topic_count}, article_epubs={article_count}, output={SITE}")


if __name__ == "__main__":
    main()
