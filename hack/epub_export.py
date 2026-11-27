"""Export the published documentation as EPUB books and an OPDS catalog."""

# Commit the Markdown or HTML source edits before rebuilding, since each
# article's latest source commit supplies its timestamp. Keep the full Git
# history in the Pages checkout (fetch-depth: 0).
#
# From the repository root, run `python hack/build-pages.py` to rebuild the
# website, individual EPUBs, and `_site/opds.xml` together. Pushing to main
# runs the same build and publishes its output through GitHub Pages.
#
# Verify that OPDS entries appear in descending `<updated>` order and that
# each matching EPUB's OPF `<dc:date>` equals the entry's `<updated>`.
# Readest uses the imported publication date when sorting its bookshelf.

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, urljoin, urlsplit
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from lxml import etree, html
from markdown.extensions.toc import slugify_unicode, unique
from PIL import Image, ImageChops

from epub_cover import cover_fonts, write_cover


SITE_URL = "https://ai-12345678.github.io/"
SITE_HOST = urlsplit(SITE_URL).netloc
SITE_AUTHOR = "ai-12345678"
BOOK_LANGUAGE = "zh-Hans"
CATALOG_TITLE = "技术学习笔记 · 电子书目录"
OPDS_MEDIA_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
SITE_TIMEZONE = timezone(timedelta(hours=8))
DIAGRAM_BACKGROUND = "#fffcf5"


@dataclass
class Document:
    path: Path
    url: str
    title: str
    chapter_id: str
    anchors: dict[str, str]
    body: html.HtmlElement
    updated: datetime


def article_epub_path(page: Path) -> Path:
    return Path("epub", "articles") / page.with_suffix(".epub")


def site_url(path: Path) -> str:
    return urljoin(SITE_URL, quote(path.as_posix()))


def read_document(page: Path, site: Path, updated: datetime) -> Document:
    path = page.relative_to(site)
    url = site_url(path)
    tree = html.document_fromstring(page.read_text(encoding="utf-8"))
    body = tree.find(".//article")
    if body is None:
        body = tree.find(".//main")
    if body is None:
        body = tree.find("body")
    for element in body.xpath(
        ".//nav | .//script | .//style | .//dialog | .//iframe | .//form | .//button | .//input"
    ):
        element.drop_tree()

    heading = body.find(".//h1")
    if heading is None:
        heading = html.Element("h1")
        heading.text = tree.findtext(".//title") or page.stem
        body.insert(0, heading)
    title = " ".join(heading.text_content().split())
    chapter_id = f"chapter-{uuid5(NAMESPACE_URL, url).hex}"
    anchors = {}
    ids = {chapter_id}
    for element in body.xpath(".//*[@id] | .//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6"):
        old_id = element.get("id") or slugify_unicode(element.text_content(), "-")
        new_id = chapter_id if element is heading else unique(f"{chapter_id}-{old_id}", ids)
        element.set("id", new_id)
        anchors.setdefault(old_id, new_id)
        if element is not heading and element.tag == "h1":
            element.tag = "h2"

    for image in body.xpath(".//img[@src]"):
        url_parts = urlsplit(urljoin(url, image.get("src")))
        local = (site / unquote(url_parts.path).lstrip("/")).resolve()
        if url_parts.netloc == SITE_HOST and local.is_relative_to(site) and local.is_file():
            image.set("src", quote(str(local)))
        else:
            replace_with_link(image, url_parts.geturl(), image.get("alt") or "查看图片")
    image_paragraphs = body.xpath(
        ".//p[count(*)=1 and img and not(text()[normalize-space()]) and not(ancestor::figure)]"
    )
    for paragraph in image_paragraphs:
        paragraph.tag = "figure"
        image = paragraph[0]
        caption = image.get("title") or image.get("alt")
        if caption:
            etree.SubElement(paragraph, "figcaption").text = caption
    for media in body.xpath(".//audio[@src] | .//video[@src]"):
        replace_with_link(media, media.get("src"), "试听音频" if media.tag == "audio" else "播放视频")

    return Document(path, url, title, chapter_id, anchors, body, updated)


def replace_with_link(element: html.HtmlElement, href: str, label: str) -> None:
    link = html.Element("a", href=href)
    link.text = label
    link.tail = element.tail
    element.getparent().replace(element, link)


def split_diagram(image_path: Path) -> list[Path]:
    with Image.open(image_path) as source:
        width, height = source.size
        if height <= width * 1.5:
            return [image_path]
        image = source.convert("RGB")

    # Near each desired break, prefer a row with little ink to keep text and
    # arrows intact. A short overlap keeps connections visible at the seam.
    paper = Image.new("RGB", image.size, DIAGRAM_BACKGROUND)
    ink = ImageChops.difference(image, paper).convert("L")
    mask = ink.point(lambda shade: 255 if shade > 32 else 0)
    density = tuple(mask.resize((1, height), Image.Resampling.BOX).get_flattened_data())
    count = (height + width - 1) // width
    tolerance = max(4, width // 12)
    overlap = min(48, width // 26)
    cuts = [0]
    for part in range(1, count):
        target = round(part * height / count)
        rows = range(target - tolerance, target + tolerance + 1)
        cuts.append(min(rows, key=lambda row: (max(density[row - 4:row + 5]), abs(row - target))))
    cuts.append(height)

    panels = []
    for part, (top, bottom) in enumerate(zip(cuts, cuts[1:]), 1):
        panel_path = image_path.with_stem(f"{image_path.stem}-part-{part}")
        image.crop((0, max(0, top - overlap), width, bottom)).save(panel_path)
        panels.append(panel_path)
    return panels


def render_diagrams(documents: list[Document], work: Path) -> None:
    diagrams = [
        (document.title, code)
        for document in documents
        for code in document.body.xpath(".//pre/code[@class='language-mermaid']")
    ]
    if not diagrams:
        return
    renderer = shutil.which("mmdc")
    if renderer is None:
        print("mmdc unavailable: retaining Mermaid source in EPUBs")
        return

    source = work / "mermaid.md"
    output = work / "diagram.md"
    config = work / "mermaid.json"
    blocks = [f"```mermaid\n{code.text_content().strip()}\n```\n" for _, code in diagrams]
    source.write_text("\n".join(blocks), encoding="utf-8")
    config.write_text(json.dumps({
        "theme": "base",
        "securityLevel": "strict",
        "fontFamily": "Noto Sans CJK SC, sans-serif",
        "themeVariables": {
            "primaryColor": "#e9f1ed",
            "primaryTextColor": "#193530",
            "primaryBorderColor": "#64877d",
            "lineColor": "#48625a",
            "actorBkg": "#e9f1ed",
            "actorBorder": "#64877d",
            "actorTextColor": "#193530",
            "signalColor": "#324943",
            "signalTextColor": "#193530",
            "noteBkgColor": "#f5ead3",
            "noteTextColor": "#3b3225",
        },
        "sequence": {"actorMargin": 32, "wrap": True},
    }), encoding="utf-8")
    result = subprocess.run(
        [renderer, "-i", str(source), "-o", str(output), "-e", "png", "-s", "3",
         "-b", DIAGRAM_BACKGROUND, "-c", str(config)],
        check=False,
    )
    if result.returncode != 0:
        print("Mermaid rendering reported an error: retaining source for diagrams without an image")

    rendered = 0
    panels_count = 0
    for index, (title, code) in enumerate(diagrams, 1):
        image = output.with_name(f"{output.stem}-{index}.png")
        if image.is_file():
            block = code.getparent()
            kind = code.text_content().split(maxsplit=1)[0]
            label = {"sequenceDiagram": "时序图", "flowchart": "流程图", "graph": "流程图"}.get(kind, "示意图")
            panels = split_diagram(image)
            diagram = html.Element("div", {"class": "book-diagram"})
            for part, panel in enumerate(panels, 1):
                caption = f"{label}（{part}/{len(panels)}）" if len(panels) > 1 else label
                figure = etree.SubElement(diagram, "figure")
                etree.SubElement(figure, "img", src=str(panel), alt=f"{title} · {caption}")
                etree.SubElement(figure, "figcaption").text = caption
            diagram.tail = block.tail
            block.getparent().replace(block, diagram)
            rendered += 1
            panels_count += len(panels)
    print(f"Rendered Mermaid diagrams: {rendered}/{len(diagrams)} ({panels_count} image panels)")


def write_article_epub(site: Path, document: Document, date: str, cover: Path | None) -> None:
    body = deepcopy(document.body)
    for link in body.xpath(".//a[@href]"):
        href = urljoin(document.url, link.get("href"))
        parts = urlsplit(href)
        if parts._replace(fragment="").geturl() == document.url:
            anchor = document.anchors.get(unquote(parts.fragment)) if parts.fragment else document.chapter_id
            if anchor:
                href = f"#{anchor}"
        link.set("href", href)
    imprint = html.Element("div", {"class": "book-imprint"})
    etree.SubElement(imprint, "p").text = f"{SITE_AUTHOR} · 更新于 {date}"
    body.find(f".//*[@id='{document.chapter_id}']").addnext(imprint)

    backmatter = etree.SubElement(body, "div", {"class": "book-source"})
    source = etree.SubElement(etree.SubElement(backmatter, "p"), "a", href=document.url)
    source.text = "阅读网页原文"

    book_body = html.Element("body")
    book_body.append(body)
    body.drop_tag()

    output = article_epub_path(document.path)
    destination = site / output
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_html = f'<!doctype html><html lang="{BOOK_LANGUAGE}">{html.tostring(book_body, encoding="unicode")}</html>'
    cover_option = ["--epub-cover-image", str(cover)] if cover is not None else []
    subprocess.run(
        ["pandoc", "--from=html+tex_math_single_backslash", "--to=epub3", "--toc", "--toc-depth=3",
         "--mathml", "--epub-title-page=false", "--css", str(Path(__file__).with_name("epub.css")),
         "--metadata", f"title={document.title}", "--metadata", f"author={SITE_AUTHOR}",
         "--metadata", f"lang={BOOK_LANGUAGE}", "--metadata", "toc-title=目录",
         "--metadata", f"identifier={site_url(output)}",
         *cover_option,
         "--output", str(destination)],
        input=source_html, text=True, encoding="utf-8", check=True,
        # Use the article timestamp for Pandoc's EPUB publication date.
        env={**os.environ, "SOURCE_DATE_EPOCH": str(int(document.updated.timestamp()))},
    )
    verify_epub_chapter(destination, document)


def verify_epub_chapter(destination: Path, document: Document) -> None:
    with ZipFile(destination) as book:
        for name in book.namelist():
            if name.endswith(".xhtml"):
                chapter = ET.fromstring(book.read(name))
                if chapter.find(f".//*[@id='{document.chapter_id}']") is not None:
                    return
    raise RuntimeError(f"{destination} is missing the article: {document.title}")


def document_updated_at(source_root: Path, source: Path) -> datetime:
    try:
        timestamp = subprocess.check_output(
            ["git", "--literal-pathspecs", "log", "-1", "--format=%cI", "--", source.relative_to(source_root).as_posix()],
            cwd=source_root, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        timestamp = ""
    if timestamp:
        return datetime.fromisoformat(timestamp)

    return datetime.fromtimestamp(source.stat().st_mtime, timezone.utc)


def atom_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_catalog(site: Path, articles: list[Document]) -> None:
    url = urljoin(SITE_URL, "opds.xml")
    ordered = sorted(articles, key=lambda article: article.updated, reverse=True)
    updated = ordered[0].updated if ordered else datetime.now(timezone.utc)
    feed = ET.Element("feed", {"xmlns": "http://www.w3.org/2005/Atom", "xml:lang": BOOK_LANGUAGE})
    ET.SubElement(feed, "id").text = url
    ET.SubElement(feed, "title").text = CATALOG_TITLE
    ET.SubElement(feed, "updated").text = atom_timestamp(updated)
    ET.SubElement(ET.SubElement(feed, "author"), "name").text = SITE_AUTHOR
    for rel in ("self", "start"):
        ET.SubElement(feed, "link", rel=rel, href=url, type=OPDS_MEDIA_TYPE)

    for article in ordered:
        book_url = site_url(article_epub_path(article.path))
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(entry, "id").text = book_url
        ET.SubElement(entry, "title").text = article.title
        ET.SubElement(entry, "updated").text = atom_timestamp(article.updated)
        paragraph = article.body.find(".//p")
        if paragraph is not None:
            summary = " ".join(paragraph.text_content().split())
            if summary and summary != article.title:
                ET.SubElement(entry, "summary", type="text").text = summary[:239] + "…" if len(summary) > 240 else summary
        ET.SubElement(
            entry, "link", rel="http://opds-spec.org/acquisition/open-access", href=book_url, type="application/epub+zip",
        )
        ET.SubElement(entry, "link", rel="alternate", href=article.url, type="text/html")

    ET.indent(feed)
    ET.ElementTree(feed).write(site / "opds.xml", encoding="utf-8", xml_declaration=True)


def build_article_epubs(site: Path, sources: dict[Path, Path], *, source_root: Path) -> int:
    articles = [
        read_document(page, site, document_updated_at(source_root, source))
        for page, source in sorted(sources.items())
    ]
    fonts = cover_fonts()
    if fonts is None:
        print("No CJK cover fonts found, using the typeset article opening")
    with TemporaryDirectory(prefix="blog-epub-") as work:
        render_diagrams(articles, Path(work))
        cover = Path(work) / "cover.png"
        for article in articles:
            date = article.updated.astimezone(SITE_TIMEZONE).date().isoformat()
            if fonts is not None:
                write_cover(cover, article.title, SITE_AUTHOR, date, fonts)
            write_article_epub(site, article, date, cover if fonts is not None else None)

    write_catalog(site, articles)
    return len(articles)
