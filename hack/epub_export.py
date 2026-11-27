"""Export the published documentation as EPUB books and an OPDS catalog."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
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


SITE_URL = "https://ai-12345678.github.io/"
SITE_HOST = urlsplit(SITE_URL).netloc
SITE_AUTHOR = "ai-12345678"
BOOK_LANGUAGE = "zh-Hans"
CATALOG_TITLE = "技术学习文档站 · 专题电子书"
OPDS_MEDIA_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
TOPIC_TITLES = {
    "agents": "AI Agent 与开发工具",
    "asm": "汇编语言",
    "cpp": "C++",
    "golang": "Go",
    "kubernetes": "Kubernetes",
    "lang": "编程语言与对象模型",
    "linux": "Linux",
    "models": "AI、DSP 与算法",
    "network": "网络技术",
    "speech": "语音与音频",
    "tcp": "TCP",
    "webrtc": "WebRTC",
}


@dataclass
class Document:
    path: Path
    url: str
    title: str
    chapter_id: str
    anchors: dict[str, str]
    body: html.HtmlElement


def article_epub_path(page: Path) -> Path:
    return Path("epub", "articles") / page.with_suffix(".epub")


def site_url(path: Path) -> str:
    return urljoin(SITE_URL, quote(path.as_posix()))


def read_document(page: Path, site: Path) -> Document:
    path = page.relative_to(site)
    url = site_url(path)
    tree = html.document_fromstring(page.read_text(encoding="utf-8"))
    body = tree.find(".//article")
    if body is None:
        body = tree.find(".//main")
    if body is None:
        body = tree.find("body")
    for element in body.xpath(".//nav | .//script | .//style | .//dialog | .//iframe"):
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
    for media in body.xpath(".//audio[@src] | .//video[@src]"):
        replace_with_link(media, media.get("src"), "试听音频" if media.tag == "audio" else "播放视频")

    return Document(path, url, title, chapter_id, anchors, body)


def replace_with_link(element: html.HtmlElement, href: str, label: str) -> None:
    link = html.Element("a", href=href)
    link.text = label
    link.tail = element.tail
    element.getparent().replace(element, link)


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
    config.write_text(
        json.dumps({"securityLevel": "strict", "fontFamily": "Noto Sans CJK SC, sans-serif"}), encoding="utf-8",
    )
    result = subprocess.run(
        [renderer, "-i", str(source), "-o", str(output), "-e", "png", "-s", "2", "-c", str(config)],
        check=False,
    )
    if result.returncode != 0:
        print("Mermaid rendering reported an error: retaining source for diagrams without an image")

    rendered = 0
    for index, (title, code) in enumerate(diagrams, 1):
        image = output.with_name(f"{output.stem}-{index}.png")
        if image.is_file():
            block = code.getparent()
            figure = html.Element("img", src=str(image), alt=f"{title} · Mermaid 图")
            figure.tail = block.tail
            block.getparent().replace(block, figure)
            rendered += 1
    print(f"Rendered Mermaid diagrams: {rendered}/{len(diagrams)}")


def write_epub(site: Path, output: Path, title: str, documents: list[Document]) -> None:
    by_url = {document.url: document for document in documents}
    book_body = html.Element("body")
    for document in documents:
        body = deepcopy(document.body)
        for link in body.xpath(".//a[@href]"):
            href = urljoin(document.url, link.get("href"))
            parts = urlsplit(href)
            target = by_url.get(parts._replace(query="", fragment="").geturl())
            if target is not None and not parts.query:
                anchor = target.anchors.get(unquote(parts.fragment)) if parts.fragment else target.chapter_id
                if anchor:
                    href = f"#{anchor}"
            link.set("href", href)
        source = etree.SubElement(etree.SubElement(body, "p"), "a", href=document.url)
        source.text = "阅读网页原文"
        book_body.append(body)
        body.drop_tag()

    destination = site / output
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_html = f'<!doctype html><html lang="{BOOK_LANGUAGE}">{html.tostring(book_body, encoding="unicode")}</html>'
    subprocess.run(
        ["pandoc", "--from=html+tex_math_single_backslash", "--to=epub3", "--toc", "--toc-depth=3",
         "--mathml", "--epub-title-page=false", "--css", str(Path(__file__).with_name("epub.css")),
         "--metadata", f"title={title}", "--metadata", f"author={SITE_AUTHOR}",
         "--metadata", f"lang={BOOK_LANGUAGE}", "--metadata", "toc-title=目录",
         "--metadata", f"identifier={site_url(output)}",
         "--output", str(destination)],
        input=source_html, text=True, encoding="utf-8", check=True,
    )
    verify_epub_chapters(destination, documents)


def verify_epub_chapters(destination: Path, documents: list[Document]) -> None:
    missing = {document.chapter_id: document.title for document in documents}
    with ZipFile(destination) as book:
        for name in book.namelist():
            if name.endswith(".xhtml"):
                chapter = ET.fromstring(book.read(name))
                for element in chapter.findall(".//*[@id]"):
                    missing.pop(element.attrib["id"], None)
    if missing:
        raise RuntimeError(f"{destination} is missing chapters: {', '.join(missing.values())}")


def write_catalog(site: Path, books: list[tuple[str, str, Path, int]]) -> None:
    url = urljoin(SITE_URL, "opds.xml")
    updated = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    feed = ET.Element("feed", {"xmlns": "http://www.w3.org/2005/Atom", "xml:lang": BOOK_LANGUAGE})
    ET.SubElement(feed, "id").text = url
    ET.SubElement(feed, "title").text = CATALOG_TITLE
    ET.SubElement(feed, "updated").text = updated
    ET.SubElement(ET.SubElement(feed, "author"), "name").text = SITE_AUTHOR
    for rel in ("self", "start"):
        ET.SubElement(feed, "link", rel=rel, href=url, type=OPDS_MEDIA_TYPE)

    for topic, title, path, count in books:
        book_url = site_url(path)
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(entry, "id").text = book_url
        ET.SubElement(entry, "title").text = title
        ET.SubElement(entry, "updated").text = updated
        topic_label = TOPIC_TITLES.get(topic, topic)
        ET.SubElement(entry, "summary", type="text").text = f"收录 {count} 篇{topic_label}文档，可以下载后离线阅读。"
        ET.SubElement(entry, "category", term=topic, label=topic_label)
        ET.SubElement(
            entry, "link", rel="http://opds-spec.org/acquisition/open-access", href=book_url, type="application/epub+zip",
        )

    ET.indent(feed)
    ET.ElementTree(feed).write(site / "opds.xml", encoding="utf-8", xml_declaration=True)


def build_epub_collections(site: Path, topic_dirs: tuple[str, ...]) -> tuple[int, int]:
    topics = {}
    for topic in topic_dirs:
        pages = sorted((site / topic).rglob("*.html"))
        if pages:
            topics[topic] = [read_document(page, site) for page in pages]

    books = []
    articles = [document for documents in topics.values() for document in documents]
    with TemporaryDirectory(prefix="blog-epub-") as work:
        render_diagrams(articles, Path(work))
        for topic, documents in topics.items():
            title = f"{TOPIC_TITLES.get(topic, topic)}专题笔记"
            output = Path("epub") / f"{topic}.epub"
            write_epub(site, output, title, documents)
            books.append((topic, title, output, len(documents)))
        for document in articles:
            write_epub(site, article_epub_path(document.path), document.title, [document])

    write_catalog(site, books)
    return len(books), len(articles)
