(async () => {
  const { default: mermaid } = await import(
    "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"
  );

  document.querySelectorAll("pre code.language-mermaid").forEach((code) => {
    const container = document.createElement("pre");
    container.className = "mermaid";
    container.textContent = code.textContent;
    code.parentElement.replaceWith(container);
  });

  mermaid.initialize({ startOnLoad: false, theme: "default" });
  await mermaid.run({ querySelector: ".mermaid" });
})();

