# 仓库协作指南

## 项目定位

这是 ai-12345678.github.io 技术学习文档站，使用中文记录人工智能、数字信号处理（DSP）、算法、Kubernetes、Linux 等主题。按主题逐篇整理，保持概念准确、例子可复现。

## 目录与来源

- `index.html`：手写首页、文档卡片与入口数量。
- `models/`：人工智能、DSP、算法及模型部署笔记；学习路线为 `ai-dsp-algorithms-roadmap.md`。统一使用此目录名称，不创建或引用旧的单数目录。
- `linux/`、`agents/`、`lang/`：对应主题的 Markdown 文档。
- `kubernetes/`：现有 HTML 文档及 Markdown 资料；构建时直接复制，当前不自动转换其中的 Markdown。
- `Embodied-AI/`：已有 I2S 原始笔记，当前未加入发布范围；引用时使用有效的仓库链接，发布此目录需同步调整构建配置。
- `hack/build-pages.py`：复制发布内容、将支持目录内的 Markdown 转为同路径 HTML。
- `.github/workflows/pages.yml`：main 推送及手动触发的 GitHub Pages 构建部署。
- `requirements.txt`：Python Markdown 依赖。
- `_site/`：生成的发布产物，已忽略，不手动编辑或提交。

## 笔记规范

- 新增 AI、DSP 和算法笔记放在 `models/`，采用有意义的小写连字符文件名；系列文章可带序号。
- 每篇保留一个一级标题，按需要组织问题、先修知识、解释与公式、小实验、误区、自测和参考资料。
- 解释符号、单位、公式成立的条件与工程限制。区分预期结果、已运行结果和未验证结论。
- 数学公式目前没有专门的渲染器，优先使用可直接阅读的文本或代码表示。
- 示例用标明语言的 fenced code block；示意图可使用 Mermaid，页面通过外部 ESM 模块加载 Mermaid 11。
- 每次完成新文章，更新学习路线的链接与状态。未完成的主题标为待写，不创建空文章。
- 保持既有内容、布局与主题结构，按任务范围修改。

## 链接与首页

- 站内阅读链接指向发布后的 `.html`；Markdown 源文件由构建器保留供下载。
- 同目录使用相对链接，跨目录链接需确认目标会被发布。
- 新增首页卡片时沿用已有结构，并同步入口数量；首页入口数与文章总数可能不同。
- 新增发布目录时同时修改 `CONTENT_DIRS` 和 `PUBLISH_ENTRIES`，区分 Markdown 转换与直接复制。
- 修改目录或文件名后，搜索全仓库的旧路径并更新相关链接。

## 构建与验证

在完整仓库根目录运行：

```bash
python -m pip install -r requirements.txt
python hack/build-pages.py
python -m http.server 8000 --directory _site
```

构建会删除并重建 `_site/`。预览访问 `http://localhost:8000/`。

- 文档修改：检查技术准确性、标题、相对链接及路线状态；对新增或修改的可运行示例，检查依赖并运行验证。
- 构建或路径修改：运行完整构建，确认目标 HTML、Markdown 下载文件及首页链接存在；涉及外观时查看桌面和移动端页面。
- Mermaid 图需要浏览器及外部模块可用，Python 构建通过不代表图已渲染成功。
- 仓库当前没有独立测试套件，不为简单文案改动添加无关测试或依赖。
- main 上的提交会触发自动发布。报告中明确区分提交成功、构建部署成功与线上页面已实际检查；无法执行的验证如实说明。

## 提交习惯

使用明确的提交说明，例如 `docs: add sampling notes` 或 `build: update published directories`。目录迁移尽量将文件、引用和构建配置放在同一次提交中。遵循用户本次指令，不扩展到无关内容。
