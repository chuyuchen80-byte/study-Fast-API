"""
=============================================================================
 markdown_utils.py —— Markdown 转安全 HTML 工具（v2.0 新增文件）
=============================================================================

Django 对比：
   Django 无内置 Markdown 转换，通常用 django-markdownx 或模板过滤器
   FastAPI 也无内置，这里提供简单实现

安全警告（重要！）：
   本模块是 Markdown 转 HTML 的极简实现，仅支持基本语法。
   生产环境强烈建议使用 python-markdown 库 + bleach 白名单消毒：

   import markdown
   import bleach
   def markdown_to_safe_html(text: str) -> str:
       html = markdown.markdown(text, extensions=['fenced_code', 'tables'])
       allowed_tags = ['p', 'strong', 'em', 'code', 'pre', 'a', 'h1', 'h2',
                       'h3', 'ul', 'ol', 'li', 'blockquote', 'img', 'br']
       allowed_attrs = {'a': ['href', 'title'], 'img': ['src', 'alt']}
       return bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)

   当前简单实现的风险：
   - 不阻止 XSS（原始 HTML/JS 标签会直接通过）
   - 不支持表格、列表、标题等高级语法
   - 正则匹配可能误伤非 Markdown 文本中的特殊字符
"""

import re


def markdown_to_safe_html(text: str) -> str:
    """
    将 Markdown 文本转换为安全的 HTML。

    v2.0 新增函数。

    支持的 Markdown 语法：
      **粗体**           → <strong>粗体</strong>
      *斜体*             → <em>斜体</em>
      `代码`             → <code>代码</code>
      [链接文字](URL)   → <a href="URL">链接文字</a>
      ```语言
      代码块
      ```                → <pre><code>代码块</code></pre>
      空行分隔的段落     → <p>段落</p>

    不支持的语法：
      表格、有序/无序列表、标题（# ## ###）、图片、
      引用（>）、分割线（---）、任务列表等。

    处理流程：
      1. 按空行分割段落，每个段落用 <p> 包裹
      2. 在每个段落内应用内联 Markdown 正则替换
      3. 处理代码块（```）

    参数：text — 原始 Markdown 字符串
    返回：HTML 字符串

    注意：返回的 HTML 未经过 bleach 消毒，
      如果前端传入的内容包含 <script> 等标签会直接保留。
      生产环境必须在上层做消毒处理。
    """
    if not text:
        return ""

    # ── 步骤 1：处理代码块（```...```）────────────────────
    # 在段落处理之前提取，避免内部的空行被误分割
    code_blocks = {}
    code_counter = 0

    def _extract_code_block(match: re.Match) -> str:
        nonlocal code_counter
        placeholder = f"%%CODEBLOCK{code_counter}%%"
        lang = match.group(1) or ""
        code = match.group(2).strip()
        code_blocks[placeholder] = (
            f'<pre><code class="language-{lang}">{_escape_html(code)}</code></pre>'
        )
        code_counter += 1
        return placeholder

    text = re.sub(
        r"```(\w+)?\s*\n(.+?)```",
        _extract_code_block,
        text,
        flags=re.DOTALL,
    )

    # ── 步骤 2：按空行分割成段落 ──────────────────────────
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    html_paragraphs = []
    for paragraph in paragraphs:
        # 跳过代码块占位符（已经是 HTML 了）
        if paragraph.startswith("%%CODEBLOCK"):
            html_paragraphs.append(paragraph)
            continue

        # 先转义 HTML（防止 XSS）
        paragraph = _escape_html(paragraph)

        # 应用内联 Markdown 规则
        paragraph = _apply_inline_rules(paragraph)

        html_paragraphs.append(f"<p>{paragraph}</p>")

    result = "\n".join(html_paragraphs)

    # ── 步骤 3：还原代码块占位符 ──────────────────────────
    for placeholder, code_html in code_blocks.items():
        result = result.replace(placeholder, code_html)

    # ── 步骤 4：处理段落内的换行（<br>） ──────────────────
    # 单行换行 → <br>（Markdown 规范：行尾两个空格或单换行）
    result = result.replace("\n", "<br>\n")

    # 清理多余的 <p> 和 <br> 嵌套
    result = re.sub(r"<p><br>\s*</p>", "", result)

    return result


def _escape_html(text: str) -> str:
    """
    转义 HTML 特殊字符，防止 XSS 注入。

    把 < > & " ' 转为对应的 HTML 实体。
    这是防止 XSS 的第一道防线（代码块内的代码不需要转义）。

    html.escape() 的简化内联版（避免额外 import）。
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    # 单引号不转义（HTML5 规范中不是必须的）
    return text


def _apply_inline_rules(text: str) -> str:
    """
    在内联文本上应用 Markdown 格式化规则。

    在 HTML 转义之后应用，因为转义后的文本不含 < > 等特殊字符，
    正则替换生成的 HTML 标签是唯一的不转义标签。

    处理顺序很重要（先后次序影响结果）：
      1. **粗体**    (双星号，先处理避免被单星号误匹配)
      2. *斜体*      (单星号)
      3. `行内代码`  (反引号)
      4. [链接](URL) (方括号+圆括号)
    """
    # 粗体：**text** → <strong>text</strong>
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # 斜体：*text* → <em>text</em>
    # 使用更精确的正则以避免匹配 ** 或 * 前后有其他文本的情况
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)

    # 行内代码：`code` → <code>code</code>
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    # 链接：[text](url) → <a href="url">text</a>
    # rel="nofollow noopener" 是安全最佳实践
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        r'<a href="\2" rel="nofollow noopener noreferrer">\1</a>',
        text,
    )

    return text