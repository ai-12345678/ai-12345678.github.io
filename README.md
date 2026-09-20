# docs

Markdown 文档站，使用 MkDocs 构建并发布到 GitHub Pages。

## 目录结构

```text
.
├── index.md
├── kubernetes/
├── linux/
├── mkdocs.yml
└── .github/workflows/pages.yml
```

## 本地预览

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdocs serve -f ./mkdocs.yml
```

访问 <http://127.0.0.1:8000/>。

## 构建

```bash
mkdocs build -f ./mkdocs.yml --strict
```

默认输出到仓库同级的 `docs-site/` 目录，避免生成内容混入 Markdown 源码目录。
