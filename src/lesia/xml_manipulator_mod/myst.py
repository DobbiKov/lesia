"""MyST/Markdown source splitter.

parse_myst(source) → Chunk
    Splits MyST source into ('text', ...) and ('placeholder', ...) segments.

    'text'        — translatable content, sent to the translator
    'placeholder' — MyST/Markdown syntax, preserved verbatim
"""

import re

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.amsmath import amsmath_plugin
from mdit_py_plugins.colon_fence import colon_fence_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.myst_role import myst_role_plugin
from mdit_py_plugins.myst_blocks import myst_block_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.field_list import fieldlist_plugin
from mdit_py_plugins.attrs import attrs_plugin, attrs_block_plugin
from mdit_py_plugins.substitution import substitution_plugin
from typing import TypeAlias

Chunk: TypeAlias = list[tuple[str, str]]


# ---------------------------------------------------------------------------
# Parser singleton
# ---------------------------------------------------------------------------

def _make_parser() -> MarkdownIt:
    return (
        MarkdownIt("commonmark", {"sourceMap": True, "typographer": True, "html": True})
        .use(dollarmath_plugin, allow_labels=True, allow_space=True, allow_digits=True, double_inline=True)
        .use(amsmath_plugin)
        .use(colon_fence_plugin)
        .use(front_matter_plugin)
        .use(myst_role_plugin)
        .use(myst_block_plugin)
        .use(footnote_plugin)
        .use(deflist_plugin)
        .use(fieldlist_plugin)
        .use(attrs_plugin)
        .use(attrs_block_plugin)
        .use(substitution_plugin)
    )


_parser = _make_parser()


# ---------------------------------------------------------------------------
# Directive classification
# ---------------------------------------------------------------------------

# Directives whose info/title after the type name is translatable text
_DIRECTIVES_TRANSLATABLE_TITLE = {
    "{admonition}", "{attention}", "{caution}", "{danger}", "{error}",
    "{hint}", "{important}", "{note}", "{seealso}", "{tip}", "{warning}",
    "{aside}", "{sidebar}", "{topic}", "{dropdown}",
}

# Roles whose content is translatable human-readable text.
# All other roles are emitted verbatim as placeholders.
TRANSLATABLE_ROLES = {
    "definiendum",
}

# Directives whose body is MyST and should be parsed recursively.
# Opaque-body directives ({eval-rst}, {math}, {amsmath}, {toctree}, {list-table},
# {versionadded}, etc.) must NOT appear here — their content is RST / LaTeX /
# file paths / structured data, not plain MyST.  They fall through to _src instead.
_DIRECTIVES_RECURSIVE_BODY = {
    "{admonition}", "{attention}", "{caution}", "{danger}", "{error}",
    "{hint}", "{important}", "{note}", "{seealso}", "{tip}", "{warning}",
    "{aside}", "{sidebar}", "{topic}", "{dropdown}",
    "{figure}",
}

# Directives that have opaque arguments (file paths, URLs) but whose specific
# option fields contain translatable human-readable text.
# Maps directive type → set of option key names (without colons) whose values
# should be sent to the translator.
_DIRECTIVES_TRANSLATABLE_OPTIONS: dict[str, set[str]] = {
    "{figure}": {"alt"},
    "{image}": {"alt"},
    "{video}": {"alt"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prefix_each_line(block: str, prefix: str) -> str:
    """Prefix each non-empty line in block with prefix, preserving newlines."""
    if not block or not prefix:
        return block
    return ''.join(
        (prefix + line) if line.strip() else line
        for line in block.splitlines(keepends=True)
    )


def _opening_token(node: SyntaxTreeNode):
    return node.nester_tokens.opening if node.nester_tokens else node.token


def _find_inline(node: SyntaxTreeNode) -> SyntaxTreeNode | None:
    return next((c for c in node.children if c.type == "inline"), None)


def _src(node: SyntaxTreeNode, lines: list[str]) -> Chunk:
    """Return exact source lines for a node as a single placeholder."""
    if node.map:
        start, end = node.map
        return [('placeholder', ''.join(lines[start:end]))]
    return []


def _node_prefix(node: SyntaxTreeNode, lines: list[str]) -> str:
    """Return the leading whitespace of the first source line of *node*."""
    if node.map and node.map[0] < len(lines):
        line = lines[node.map[0]]
        return line[: len(line) - len(line.lstrip())]
    return ''


# ---------------------------------------------------------------------------
# Inline rendering
# ---------------------------------------------------------------------------

def _render_inline(node: SyntaxTreeNode, out: Chunk, softbreak_indent: str = '') -> None:
    """Recursively render an inline (or inline container) node."""
    for child in node.children:
        _render_inline_node(child, out, softbreak_indent)


def _render_inline_node(node: SyntaxTreeNode, out: Chunk, softbreak_indent: str = '') -> None:
    match node.type:
        case "inline":
            _render_inline(node, out, softbreak_indent)

        case "text":
            out.append(('text', node.content))

        case "softbreak":
            if softbreak_indent:
                out.append(('placeholder', '\n' + softbreak_indent))
            else:
                out.append(('text', '\n'))

        case "hardbreak":
            out.append(('placeholder', '\\\n' + softbreak_indent))

        case "code_inline":
            out.append(('placeholder', f'`{node.content}`'))

        case "html_inline":
            content = node.content
            # Continuation lines inside html_inline have their leading indent stripped by
            # the list-item parser; re-add the softbreak indent so the content round-trips.
            if softbreak_indent and '\n' in content:
                content = content.replace('\n', '\n' + softbreak_indent)
            out.append(('placeholder', content))

        case "math_inline":
            out.append(('placeholder', '$' + node.content + '$'))

        case "math_inline_double":
            out.append(('placeholder', '$$' + node.content + '$$'))

        case "em":
            tok = _opening_token(node)
            markup = tok.markup if tok else '*'
            out.append(('placeholder', markup))
            for child in node.children:
                _render_inline_node(child, out, softbreak_indent)
            out.append(('placeholder', markup))

        case "strong":
            tok = _opening_token(node)
            markup = tok.markup if tok else '**'
            out.append(('placeholder', markup))
            for child in node.children:
                _render_inline_node(child, out, softbreak_indent)
            out.append(('placeholder', markup))

        case "link":
            tok = _opening_token(node)
            href = tok.attrs.get('href', '') if tok and tok.attrs else ''
            title = tok.attrs.get('title', '') if tok and tok.attrs else ''
            out.append(('placeholder', '['))
            for child in node.children:
                _render_inline_node(child, out, softbreak_indent)
            suffix = f']({href} "{title}")' if title else f']({href})'
            out.append(('placeholder', suffix))

        case "image":
            tok = _opening_token(node)
            src = tok.attrs.get('src', '') if tok and tok.attrs else ''
            title = tok.attrs.get('title', '') if tok and tok.attrs else ''
            out.append(('placeholder', '!['))
            for child in node.children:
                _render_inline_node(child, out, softbreak_indent)
            suffix = f']({src} "{title}")' if title else f']({src})'
            out.append(('placeholder', suffix))

        case "myst_role":
            name = node.meta.get('name', '') if node.meta else ''
            if name in TRANSLATABLE_ROLES:
                out.append(('placeholder', f'{{{name}}}`'))
                content = node.content
                if content.endswith('>') and ' <' in content:
                    display, _, target = content[:-1].rpartition(' <')
                    out.append(('text', display))
                    out.append(('placeholder', ' <'))
                    out.append(('text', target))
                    out.append(('placeholder', '>`'))
                else:
                    out.append(('text', content))
                    out.append(('placeholder', '`'))
            else:
                out.append(('placeholder', f'{{{name}}}`{node.content}`'))

        case "footnote_ref":
            label = node.meta.get('label', '') if node.meta else ''
            out.append(('placeholder', f'[^{label}]'))

        case "substitution_inline":
            out.append(('placeholder', '{{' + node.content + '}}'))

        case "attrs_inline":
            pass  # attribute metadata, no output

        case _:
            out.append(('placeholder', node.content or ''))


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _get_align(node: SyntaxTreeNode) -> str | None:
    tok = _opening_token(node)
    if tok and tok.attrs:
        style = tok.attrs.get('style', '')
        if 'right' in style:
            return 'right'
        if 'center' in style:
            return 'center'
        if 'left' in style:
            return 'left'
    return None


def _align_marker(align: str | None) -> str:
    return {'left': ':---', 'center': ':---:', 'right': '---:'}.get(align or '', '---')


def _render_table(node: SyntaxTreeNode, out: Chunk) -> None:
    thead = next((c for c in node.children if c.type == "thead"), None)
    tbody = next((c for c in node.children if c.type == "tbody"), None)

    if thead:
        header_row = next((c for c in thead.children if c.type == "tr"), None)
        if header_row:
            out.append(('placeholder', '|'))
            aligns = []
            for th in header_row.children:
                if th.type != "th":
                    continue
                inline = _find_inline(th)
                if inline:
                    _render_inline(inline, out)
                aligns.append(_get_align(th))
                out.append(('placeholder', '|'))
            out.append(('placeholder', '\n|'))
            for align in aligns:
                out.append(('placeholder', _align_marker(align) + '|'))
            out.append(('placeholder', '\n'))

    if tbody:
        for tr in tbody.children:
            if tr.type != "tr":
                continue
            out.append(('placeholder', '|'))
            for td in tr.children:
                if td.type != "td":
                    continue
                inline = _find_inline(td)
                if inline:
                    _render_inline(inline, out)
                out.append(('placeholder', '|'))
            out.append(('placeholder', '\n'))


# ---------------------------------------------------------------------------
# Deflist rendering
# ---------------------------------------------------------------------------

def _render_deflist(node: SyntaxTreeNode, out: Chunk) -> None:
    for child in node.children:
        if child.type == "dt":
            inline = _find_inline(child)
            if inline:
                _render_inline(inline, out)
            out.append(('placeholder', '\n'))
        elif child.type == "dd":
            out.append(('placeholder', ':   '))
            for subchild in child.children:
                if subchild.type == "paragraph":
                    inline = _find_inline(subchild)
                    if inline:
                        _render_inline(inline, out)
            out.append(('placeholder', '\n'))
    out.append(('placeholder', '\n'))


# ---------------------------------------------------------------------------
# Field list rendering
# ---------------------------------------------------------------------------

def _render_field_list(node: SyntaxTreeNode, out: Chunk, indent_prefix: str = '') -> None:
    children = node.children
    i = 0
    while i < len(children):
        child = children[i]
        if child.type == "fieldlist_name":
            inline = _find_inline(child)
            name_text = inline.content if inline else ""
            line = f":{name_text}:"
            i += 1
            if i < len(children) and children[i].type == "fieldlist_body":
                body = children[i]
                para = next((c for c in body.children if c.type == "paragraph"), None)
                if para:
                    inline_body = _find_inline(para)
                    body_text = inline_body.content if inline_body else ""
                else:
                    body_text = ""
                line += f" {body_text}"
                i += 1
            out.append(('placeholder', indent_prefix + line + '\n'))
        else:
            i += 1
    out.append(('placeholder', '\n'))


# ---------------------------------------------------------------------------
# Directive option extraction
# ---------------------------------------------------------------------------

_DIRECTIVE_OPTION_RE = re.compile(r'^:[A-Za-z0-9_-]+:')
_DIRECTIVE_OPTION_PARSE_RE = re.compile(r'^(:[A-Za-z0-9_-]+:)([ \t]?)(.*)')


def _render_directive_options(
    options: str,
    translatable_keys: set[str],
    indent_prefix: str,
    out: Chunk,
) -> None:
    """Render directive option lines, emitting translatable option values as text segments.

    Non-translatable options and blank lines are emitted as placeholders verbatim.
    markdown-it strips the fence-content indent, so ``indent_prefix`` is re-added
    to every non-blank line (matching the behaviour of ``_prefix_each_line``).
    """
    for line in options.splitlines(keepends=True):
        content = line.rstrip('\n').rstrip('\r')
        m = _DIRECTIVE_OPTION_PARSE_RE.match(content)
        if m:
            key_part = m.group(1)    # e.g. ":alt:"
            sep = m.group(2)         # space between key and value (may be empty)
            value_part = m.group(3)  # e.g. "A beautiful sunset"
            key_name = key_part[1:-1]  # strip surrounding colons → "alt"
            if key_name in translatable_keys and value_part:
                out.append(('placeholder', indent_prefix + key_part + sep))
                out.append(('text', value_part))
                out.append(('placeholder', '\n'))
            else:
                out.append(('placeholder', indent_prefix + content + '\n'))
        elif content.strip():
            # Non-empty, non-option line (shouldn't appear in a well-formed options block)
            out.append(('placeholder', indent_prefix + content + '\n'))
        else:
            # Blank separator line — emit as-is (no indent needed)
            out.append(('placeholder', line))


def _split_directive_options(content: str) -> tuple[str, str]:
    """
    Split directive body content into (options_block, body).

    MyST directive options are leading lines of the form ':key: value'.
    Unlike RST field lists, a continuation line that doesn't match the
    option pattern signals the end of the options block — no blank line
    separator is required.  An optional single blank line immediately
    after the options is consumed into the options block so it is
    preserved verbatim on reconstruction.
    """
    lines = content.splitlines(keepends=True)
    i = 0
    while i < len(lines) and _DIRECTIVE_OPTION_RE.match(lines[i]):
        i += 1
    # Include optional blank line separator in the options block
    if i < len(lines) and lines[i].strip() == '':
        i += 1
    return ''.join(lines[:i]), ''.join(lines[i:])


# ---------------------------------------------------------------------------
# Fence rendering
# ---------------------------------------------------------------------------

def _render_fence(node: SyntaxTreeNode, lines: list[str], out: Chunk, list_level: int = 0) -> None:
    tok = node.token
    info = tok.info
    content = tok.content  # already ends with '\n' or is empty
    markup = tok.markup

    # Extract directive type from info string
    table_type = ''
    if info and '{' in info:
        end = info.find('}')
        if end != -1:
            table_type = info[:end + 1]
            info = info[end + 1:]

    # For non-directive and opaque directive fences: use source lines verbatim
    if (table_type not in _DIRECTIVES_TRANSLATABLE_TITLE
            and table_type not in _DIRECTIVES_RECURSIVE_BODY
            and table_type not in _DIRECTIVES_TRANSLATABLE_OPTIONS):
        out.extend(_src(node, lines))
        return

    # Directive fence: extract indentation prefix from source
    indent_prefix = ''
    if node.map and lines:
        first_line = lines[node.map[0]]
        indent_prefix = first_line[:len(first_line) - len(first_line.lstrip())]

    # Opening line: [indent][markup][table_type][info]
    out.append(('placeholder', indent_prefix + markup + table_type))
    if info and table_type in _DIRECTIVES_TRANSLATABLE_TITLE:
        out.append(('text', info))
    else:
        out.append(('placeholder', info))
    out.append(('placeholder', '\n'))

    # Body: directives with translatable options get option-by-option rendering;
    # directives with recursive MyST bodies get parsed recursively;
    # for title-only directives the body is opaque — emit it verbatim as a placeholder.
    if table_type in _DIRECTIVES_TRANSLATABLE_OPTIONS and content:
        translatable_keys = _DIRECTIVES_TRANSLATABLE_OPTIONS[table_type]
        options, body = _split_directive_options(content)
        if options:
            _render_directive_options(options, translatable_keys, indent_prefix, out)
        if body:
            if table_type in _DIRECTIVES_RECURSIVE_BODY:
                # e.g. {figure} caption is plain MyST prose
                inner = _parse_myst(body, list_level, indent_prefix)
                out.extend(inner)
            else:
                out.append(('placeholder', body))
    elif table_type in _DIRECTIVES_RECURSIVE_BODY and content:
        # Strip leading ':key: value' option lines before recursing so that the
        # fieldlist_plugin does not consume the first body paragraph as a field
        # continuation (MyST ends the options block at the first non-option line,
        # no blank line separator required).
        options, body = _split_directive_options(content)
        if options:
            # Prepend indent_prefix to every non-blank line: markdown-it strips
            # the list continuation indent from fence content, so each option
            # line must have it re-added individually.
            out.append(('placeholder', _prefix_each_line(options, indent_prefix)))
        if body:
            inner = _parse_myst(body, list_level, indent_prefix)
            out.extend(inner)
    elif content:
        out.append(('placeholder', content))

    # Closing line: [indent][markup]
    out.append(('placeholder', indent_prefix + markup + '\n'))


# ---------------------------------------------------------------------------
# List rendering
# ---------------------------------------------------------------------------

def _is_loose_list(node: SyntaxTreeNode) -> bool:
    """Return True if any list_item contains a non-hidden paragraph (loose list)."""
    for item in node.children:
        if item.type != "list_item":
            continue
        for child in item.children:
            if child.type == "paragraph":
                tok = _opening_token(child)
                if tok and not tok.hidden:
                    return True
    return False


def _render_list(node: SyntaxTreeNode, lines: list[str], out: Chunk,
                 outer_level: int = 0, local_level: int = 0,
                 indent_prefix: str = '') -> None:
    """
    outer_level: nesting depth inherited from parent contexts (e.g. directive inside a list).
    local_level: nesting depth within the current render context (0 = top of this context).
    indent_prefix: absolute whitespace prepended by the enclosing directive context.
    Trailing \\n is only added when local_level == 0 (top of context).
    """
    items = [c for c in node.children if c.type == "list_item"]
    is_loose = _is_loose_list(node)
    for i, item in enumerate(items):
        _render_list_item(item, lines, out, outer_level, local_level, indent_prefix)
        if i < len(items) - 1:
            # Adjust separator so we don't duplicate a \n already present at the end
            # of the item (e.g. when the last child was a fence block).
            ends_with_nl = bool(out and out[-1][1].endswith('\n'))
            if is_loose:
                sep = '\n' if ends_with_nl else '\n\n'
            else:
                sep = '' if ends_with_nl else '\n'
            if sep:
                out.append(('placeholder', sep))
    if local_level == 0:
        # Add trailing newline only if the last segment doesn't already end with one
        # (avoids a spurious blank line when the last item ended with a fence block).
        if not (out and out[-1][1].endswith('\n')):
            out.append(('placeholder', '\n'))
        # Emit trailing blank lines that fall inside the node's source map but after
        # the last item's content (markdown-it includes the separating blank in the
        # last item's map for tight lists, so the gap calculation in _parse_myst
        # sees gap=0 and skips them).
        if node.map and lines:
            end = node.map[1]
            blanks = 0
            while end > 0 and (end - 1) < len(lines) and lines[end - 1].strip() == '':
                blanks += 1
                end -= 1
            if blanks > 0:
                out.append(('placeholder', '\n' * blanks))


def _child_gap(prev: SyntaxTreeNode, nxt: SyntaxTreeNode) -> int:
    """Return the number of blank lines between two sibling nodes via source maps."""
    if prev.map and nxt.map:
        return max(0, nxt.map[0] - prev.map[1])
    return 0


def _render_list_item(item: SyntaxTreeNode, lines: list[str], out: Chunk,
                      outer_level: int = 0, local_level: int = 0,
                      indent_prefix: str = '') -> None:
    tok = _opening_token(item)
    actual_level = outer_level + local_level
    prefix = indent_prefix + _node_prefix(item, lines)

    # Determine marker from token
    if item.parent and item.parent.type == "ordered_list":
        info = tok.info if tok and tok.info else "1"
        marker = f"{info}. "
    else:
        markup = tok.markup if tok and tok.markup else "-"
        marker = f"{markup} "

    continuation_indent = prefix + ' ' * len(marker)
    out.append(('placeholder', prefix + marker))

    block_children = item.children
    for j, child in enumerate(block_children):
        if j > 0:
            # Use source-map gap to produce correct number of newlines between siblings.
            # gap=0 → one newline (tight), gap=1 → blank line between blocks, etc.
            gap = _child_gap(block_children[j - 1], child)
            out.append(('placeholder', '\n' * (gap + 1)))

        if child.type == "paragraph":
            # Render inline content (no trailing '\n' — list handles separators)
            inline = _find_inline(child)
            if inline:
                _render_inline(inline, out, softbreak_indent=continuation_indent)
        elif child.type in ("bullet_list", "ordered_list"):
            _render_list(child, lines, out, outer_level, local_level + 1, indent_prefix)
        elif child.type in ("fence", "colon_fence"):
            # Directive inside a list item: inner lists start one level deeper
            _render_fence(child, lines, out, actual_level + 1)
        else:
            _render_block(child, lines, out, actual_level, continuation_indent)


# ---------------------------------------------------------------------------
# Footnote reference rendering
# ---------------------------------------------------------------------------

def _render_footnote_reference(node: SyntaxTreeNode, lines: list[str], out: Chunk,
                               list_level: int = 0) -> None:
    label = node.meta.get('label', '') if node.meta else ''
    out.extend([
        ('placeholder', '['),
        ('placeholder', f'^{label}'),
        ('placeholder', ']'),
        ('placeholder', ': '),
    ])
    for child in node.children:
        _render_block(child, lines, out, list_level)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def _render_block(node: SyntaxTreeNode, lines: list[str], out: Chunk,
                  list_level: int = 0, indent_prefix: str = '') -> None:
    match node.type:
        case "paragraph":
            if indent_prefix:
                out.append(('placeholder', indent_prefix))
            inline = _find_inline(node)
            if inline:
                _render_inline(inline, out)
            out.append(('placeholder', '\n'))

        case "heading":
            tok = _opening_token(node)
            markup = tok.markup if tok else '#'
            if markup == '=':
                markup = '#'
            elif markup == '-':
                markup = '##'
            out.append(('placeholder', indent_prefix + markup + ' '))
            inline = _find_inline(node)
            if inline:
                _render_inline(inline, out)
            out.append(('placeholder', '\n'))

        case "fence" | "colon_fence":
            # _render_fence reads indent_prefix from its own source lines
            _render_fence(node, lines, out, list_level)

        case "bullet_list" | "ordered_list":
            _render_list(node, lines, out, outer_level=list_level, local_level=0,
                         indent_prefix=indent_prefix)

        case "table":
            _render_table(node, out)

        case "blockquote":
            bq_prefix = indent_prefix + '> '
            for child in node.children:
                if child.type == "paragraph":
                    out.append(('placeholder', bq_prefix))
                    inline = _find_inline(child)
                    if inline:
                        _render_inline(inline, out, softbreak_indent=bq_prefix)
                    out.append(('placeholder', '\n'))
                else:
                    _render_block(child, lines, out, list_level, bq_prefix)

        case "hr":
            out.extend(_src(node, lines))

        case "html_block" | "html_inline":
            out.append(('placeholder', indent_prefix + node.content))

        case "math_block":
            out.append(('placeholder', indent_prefix + '$$' + node.content + '$$'))

        case "amsmath":
            out.append(('placeholder', indent_prefix + node.content))

        case "myst_target":
            out.append(('placeholder', indent_prefix + f'({node.content})=\n'))

        case "myst_line_comment":
            # Use verbatim source lines — consecutive comment lines collapse into
            # one token by the parser, so reconstructing from content would lose
            # the '% ' prefix on each continuation line.
            out.extend(_src(node, lines))

        case "myst_block_break":
            out.append(('placeholder', indent_prefix + f'+++ {node.content}\n'))

        case "front_matter":
            out.append(('placeholder', f'---\n{node.content}\n---\n'))

        case "footnote_reference":
            _render_footnote_reference(node, lines, out, list_level)

        case "field_list":
            _render_field_list(node, out, indent_prefix)

        case "dl":
            _render_deflist(node, out)

        case "substitution_block":
            out.append(('placeholder', indent_prefix + '{{' + node.content + '}}'))

        case "attrs_block":
            out.extend(_src(node, lines))

        case _:
            out.extend(_src(node, lines))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _parse_myst(source: str, list_level: int = 0, indent_prefix: str = '') -> Chunk:
    """Internal parse that carries outer list nesting depth and indent into recursive calls."""
    lines = source.splitlines(keepends=True)
    tokens = _parser.parse(source)
    tree = SyntaxTreeNode(tokens)

    out: Chunk = []
    children = tree.children
    for i, child in enumerate(children):
        _render_block(child, lines, out, list_level, indent_prefix)
        # Preserve blank lines between top-level blocks using source maps
        if i < len(children) - 1:
            nxt = children[i + 1]
            gap_start = child.map[1] if child.map else 0
            gap_end = nxt.map[0] if nxt.map else gap_start
            blanks = gap_end - gap_start
            if blanks > 0:
                out.append(('placeholder', '\n' * blanks))
    return out


def parse_myst(source: str) -> Chunk:
    """
    Split MyST markdown source into ('text'|'placeholder', content) segments.

    'text' segments contain translatable content.
    'placeholder' segments contain MyST syntax that must be preserved verbatim.
    """
    return _parse_myst(source, 0)
