/* On-demand PDF export for generated and handwritten GitHub Pages HTML. */
(() => {
  "use strict";

  const PDF_LIB_URLS = [
    "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js",
    "https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js",
  ];
  let libraryPromise;

  function loadScript(url) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timeout = setTimeout(() => {
        script.remove();
        reject(new Error("PDF library timed out: " + url));
      }, 15000);
      script.src = url;
      script.async = true;
      script.onload = () => {
        clearTimeout(timeout);
        resolve();
      };
      script.onerror = () => {
        clearTimeout(timeout);
        script.remove();
        reject(new Error("PDF library failed to load: " + url));
      };
      document.head.appendChild(script);
    });
  }

  function loadPdfLibrary() {
    if (typeof window.html2pdf === "function") return Promise.resolve(window.html2pdf);
    if (!libraryPromise) {
      libraryPromise = (async () => {
        for (const url of PDF_LIB_URLS) {
          try {
            await loadScript(url);
            if (typeof window.html2pdf === "function") return window.html2pdf;
          } catch (error) {
            console.warn(error);
          }
        }
        throw new Error("PDF export library is unavailable");
      })().catch(error => {
        libraryPromise = undefined; // Allow retry after a temporary network failure.
        throw error;
      });
    }
    return libraryPromise;
  }

  function pdfFileName() {
    const heading = document.querySelector("h1");
    const title = (heading?.textContent || document.title || "页面").trim();
    const safeName = title.replace(/[\x00-\x1f\\/:*?"<>|]/g, "-").replace(/[.\s]+$/g, "").slice(0, 100);
    return (safeName || "页面") + ".pdf";
  }

  function exportTarget() {
    return document.querySelector("article") || document.querySelector("main") || document.body;
  }

  async function waitForImages(element) {
    const pending = Array.from(element.querySelectorAll("img"))
      .filter(img => !img.complete)
      .map(img => new Promise(resolve => {
        img.addEventListener("load", resolve, { once: true });
        img.addEventListener("error", resolve, { once: true });
      }));
    if (document.fonts?.ready) pending.push(document.fonts.ready);
    await Promise.race([Promise.all(pending), new Promise(resolve => setTimeout(resolve, 6000))]);
  }

  async function downloadPdf(button) {
    const target = exportTarget();
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "生成 PDF 中…";
    button.setAttribute("aria-busy", "true");

    try {
      const html2pdf = await loadPdfLibrary();
      await waitForImages(target);
      // Keep the canvas within common browser limits on longer articles.
      const pageHeight = Math.max(target.scrollHeight, target.offsetHeight, 1);
      const scale = Math.min(2, Math.max(1, Math.floor(18000 / pageHeight * 10) / 10));
      const isWide = target.scrollWidth > 1150;

      await html2pdf().set({
        filename: pdfFileName(),
        margin: [10, 10, 10, 10],
        image: { type: "jpeg", quality: 0.97 },
        html2canvas: {
          scale,
          backgroundColor: "#ffffff",
          useCORS: true,
          scrollX: 0,
          scrollY: 0,
          ignoreElements: node => node.classList?.contains("pdf-export-button") || false,
        },
        jsPDF: { unit: "mm", format: "a4", orientation: isWide ? "landscape" : "portrait" },
        pagebreak: { mode: ["css", "legacy"], avoid: ["figure", ".mermaid-diagram"] },
        enableLinks: true,
      }).from(target).save();
    } catch (error) {
      console.error("Unable to export PDF:", error);
      if (window.confirm("自动下载 PDF 失败。是否改用浏览器打印，并选择“保存为 PDF”？")) {
        window.print();
      }
    } finally {
      button.disabled = false;
      button.textContent = label;
      button.removeAttribute("aria-busy");
    }
  }

  function install() {
    if (document.querySelector(".pdf-export-button")) return;

    const style = document.createElement("style");
    style.textContent = [
      ".pdf-export-actions { display: inline-flex; align-items: center; gap: 14px; flex-wrap: wrap; }",
      ".pdf-export-button { appearance: none; cursor: pointer; font: 600 13px/1.4 -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; padding: 8px 13px; border: 1px solid #0969da; border-radius: 8px; color: #fff; background: #0969da; box-shadow: 0 2px 8px #1f232822; }",
      ".pdf-export-button:hover:not(:disabled) { background: #0550ae; }",
      ".pdf-export-button:focus-visible { outline: 3px solid #80baff; outline-offset: 2px; }",
      ".pdf-export-button:disabled { cursor: progress; opacity: .65; }",
      ".pdf-export-floating { position: fixed; top: 16px; right: 16px; z-index: 10000; }",
      "@media (max-width: 640px) { nav.toolbar { flex-wrap: wrap; } .pdf-export-floating { top: 8px; right: 8px; } }",
      "@media print {",
      "  .pdf-export-button, .pdf-export-actions, nav.toolbar { display: none !important; }",
      "  html, body { background: #fff !important; }",
      "  article { border: 0 !important; box-shadow: none !important; }",
      "  img, figure, pre, .mermaid-diagram { break-inside: avoid; }",
      "  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }",
      "}",
    ].join("\n");
    document.head.appendChild(style);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "pdf-export-button";
    button.textContent = "↓ 下载 PDF";
    button.setAttribute("aria-label", "将当前页面下载为 PDF");
    button.addEventListener("click", () => downloadPdf(button));

    const toolbar = document.querySelector("nav.toolbar");
    if (toolbar) {
      const actions = document.createElement("span");
      actions.className = "pdf-export-actions";
      const markdownLink = toolbar.querySelector("a[download]");
      if (markdownLink) actions.appendChild(markdownLink);
      actions.appendChild(button);
      toolbar.appendChild(actions);
    } else {
      button.classList.add("pdf-export-floating");
      document.body.appendChild(button);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
