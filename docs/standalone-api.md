# Standalone API Reference

The functions on this page work on plain strings (or file paths) and never
touch a `Project`. Use them when you want to chunk a document, split markup
into translatable text vs. syntax, or tag/reconstruct XML yourself — for
example, to build your own translation pipeline, or to identify the
syntax and non-syntax parts of a document for some other purpose entirely.

For the higher-level, `Project`-based workflow (source/target directories,
translation cache, LLM configuration, ...), see the
[Library API Reference](./main.md).

> **Note:** The library is in early development. Expect bugs and incomplete features.

## Table of Contents

- [Overview](#overview)
- [Chunking](#chunking)
  - [split_latex_document_into_chunks](#split_latex_document_into_chunks)
  - [split_myst_document_into_chunks](#split_myst_document_into_chunks)
  - [split_typst_document_into_chunks](#split_typst_document_into_chunks)
- [Parsing](#parsing)
  - [parse_latex](#parse_latex)
    - [LaTeX parsing configuration](#latex-parsing-configuration)
  - [parse_myst](#parse_myst)
  - [parse_typst](#parse_typst)
    - [Typst parsing configuration](#typst-parsing-configuration)
  - [CodeParser](#codeparser)
- [XML tagging and reconstruction](#xml-tagging-and-reconstruction)
  - [create_translation_xml](#create_translation_xml)
  - [reconstruct_from_xml](#reconstruct_from_xml)
  - [verify_placeholders](#verify_placeholders)
  - [Convenience wrappers](#convenience-wrappers)

---

## Overview

Two independent concerns live here:

- **Chunking** splits a whole document into cell-sized pieces (roughly:
  sections/paragraphs), so a large file can be translated piece by piece
  instead of in one shot.
- **Parsing + XML tagging** takes a single piece of markup (a whole document
  or a single chunk) and separates it into **translatable text** and
  **syntax that must be preserved verbatim** (commands, delimiters, code,
  labels, ...). Parsing produces a plain list of `(kind, content)` segments;
  XML tagging wraps those segments into an XML string with `<PH>`
  placeholder tags around the non-text parts, which is the format the
  library's translation prompts expect. `reconstruct_from_xml` reverses
  that step.

A typical standalone pipeline looks like:

```
raw document
  → split_*_document_into_chunks   (chunking)
  → parse_* / CodeParser.parse     (segmentation: text vs. placeholder)
  → create_translation_xml         (XML tagging)
  → ... translate the <TEXT> content however you like ...
  → reconstruct_from_xml           (rebuild the document)
```

You can also stop after the parsing step if all you need is the list of
`(kind, content)` segments — the XML tagging step is only necessary if you
want the same LLM-facing format `lesia` uses internally.

---

## Chunking

```python
from lesia.doc_translator_mod.latex_chunker import split_latex_document_into_chunks
from lesia.doc_translator_mod.myst_chunker import split_myst_document_into_chunks
from lesia.doc_translator_mod.typst_chunker import split_typst_document_into_chunks
```

### `split_latex_document_into_chunks`

```python
split_latex_document_into_chunks(latex_document_string: str) -> list[dict]
```

Splits a full LaTeX document into structured chunks, separating the
preamble from the body. Each chunk is a dict:

```python
{"id": str, "content": str, "chunk_type": "preamble" | "macro_declaration" | "content"}
```

`chunk_type` is `"preamble"` for everything before `\begin{document}`,
`"macro_declaration"` for the bare `\begin{document}` / `\end{document}`
lines, and `"content"` for the document body, itself split into several
chunks by paragraph/section.

### `split_myst_document_into_chunks`

```python
split_myst_document_into_chunks(source_text: str) -> list[dict]
```

Splits a MyST/Markdown document into heading-aware section chunks, then
further splits any section chunk larger than ~2000 characters back into its
block-level elements. A `myst_target` label (e.g. `(label)=`) immediately
preceding a heading travels with the heading it labels, rather than staying
attached to the previous section. Each chunk is a dict:

```python
{"type": str, "lines": (start_line, end_line), "content": str}
```

`type` is `"section"` for a merged section, or the original markdown-it
token type (e.g. `"heading_open"`) when a section was too large to merge
and was left as individual elements.

### `split_typst_document_into_chunks`

```python
split_typst_document_into_chunks(source: str) -> list[dict]
```

Same idea as the MyST chunker (heading-aware sections with a soft size
limit), but for Typst source. Each chunk is a dict:

```python
{"id": str, "content": str, "chunk_type": "content"}
```

---

## Parsing

Parsing turns a single piece of markup into a flat list of
`(kind, content)` tuples. `kind` is `"text"` for translatable content and
`"placeholder"` for syntax that must be copied through unchanged (Typst
parsing also emits a transient `"math"` kind — see below).

### `parse_latex`

```python
from lesia.xml_manipulator_mod.latex import parse_latex

parse_latex(latex_content: str) -> list[tuple[str, str]]
```

```python
>>> parse_latex(r"\section*{Intro} Hello \ref{sec:intro}.")
[('placeholder', '\\section'), ('text', '*'), ('placeholder', '{'), ('text', 'Intro'),
 ('placeholder', '}'), ('text', ' Hello '), ('placeholder', '\\ref{sec:intro}'), ('text', '.')]
```

Commands whose argument structure `pylatexenc` already knows (`\cite`,
`\ref`, `\label`, `\verb`, math environments, ...) are handled out of the
box. See [LaTeX parsing configuration](#latex-parsing-configuration) below
to teach it about custom commands and environments.

#### LaTeX parsing configuration

```python
from lesia.xml_manipulator_mod.latex import (
    configure_latex_settings,
    reset_latex_settings,
)
```

```python
configure_latex_settings(
    extra_placeholder_envs: list[str] | set[str] = (),
    extra_math_envs: list[str] | set[str] = (),
    extra_placeholder_commands: list[str] | set[str] = (),
    command_translatable_args: dict[str, dict[str, list[int]]] | None = None,
    custom_command_specs: dict[str, dict[str, int]] | None = None,
) -> None
```

Configures module-level, process-wide parsing behaviour for `parse_latex`
(and anything built on top of it, including the `Project`-level
`project.add_latex_placeholder_env`-style helpers — see
[LaTeX configuration](./main.md#latex-configuration) in the main reference
if you're working through a `Project`). All arguments are **additive** on
top of the hardcoded defaults — you cannot accidentally remove built-in
entries such as `\cite` or `verbatim`.

```python
configure_latex_settings(
    extra_placeholder_envs=["myverbatim", "algorithm"],
    extra_math_envs=["myequation"],
    # \myfig is a custom command — its argument structure must be declared
    # in custom_command_specs so pylatexenc associates the {...} groups
    # with the command node. Without that, extra_placeholder_commands would
    # only suppress the bare command token and the arguments would still be
    # walked as translatable text.
    extra_placeholder_commands=["myfig"],
    custom_command_specs={
        "myfig": {"mandatory": 2, "optional": 0},
    },
    command_translatable_args={
        "myfig": {"mandatory": [2]},
        "section": {"mandatory": [1], "optional": [1]},
    },
)

segments = parse_latex(r"\myfig{fig:label}{My caption} \section[Short]{Full title}")

reset_latex_settings()  # restore defaults
```

`reset_latex_settings()` takes no arguments and clears all runtime settings
back to defaults. Calling `configure_latex_settings` again **replaces** the
previous call entirely rather than merging with it.

### `parse_myst`

```python
from lesia.xml_manipulator_mod.myst import parse_myst

parse_myst(source: str) -> list[tuple[str, str]]
```

```python
>>> parse_myst("# Title\n\nSome **bold** text.\n")
[('placeholder', '# '), ('text', 'Title'), ('placeholder', '\n'), ('placeholder', '\n'),
 ('text', 'Some '), ('placeholder', '**'), ('text', 'bold'),
 ('placeholder', '**'), ('text', ' text.'), ('placeholder', '\n')]
```

Handles headings, lists, tables, definition lists, field lists, fenced
directives/roles, and footnotes. Math (`$...$`, `{math}` blocks) is
returned as a `"math"` segment rather than `"text"` or `"placeholder"` —
callers that don't special-case math (like `create_translation_xml`) should
treat it as a placeholder; `myst_to_xml` in the
[convenience wrappers](#convenience-wrappers) does this remapping for you.

### `parse_typst`

```python
from lesia.xml_manipulator_mod.typst import parse_typst

parse_typst(source: str) -> list[tuple[str, str]]
```

Walks the Typst syntax tree and yields `(kind, content)` segments. Raw
blocks, code blocks, labels, refs, links, imports, and `let`/`set`/`show`
rules are emitted as `"placeholder"`; free text is `"text"`; and content
inside recognized math text-functions (`text`, `upright`, `bold`,
`italic`) is emitted as `"math"` (treat it like a placeholder unless you
handle math translation yourself — `typst_to_xml` does this remapping for
you, see [convenience wrappers](#convenience-wrappers)).

By default, string arguments named `caption`, `description`, `info`,
`subtitle`, `summary`, or `title` are treated as translatable text; args
named `file`, `id`, `key`, `label`, `lang`, `language`, `path`, `ref`,
`target`, or `url` never are. See below to customize this per function.

#### Typst parsing configuration

```python
from lesia.xml_manipulator_mod.typst import (
    configure_typst_translatable_string_args_by_function,
    reset_typst_translatable_string_args_by_function,
)
```

```python
configure_typst_translatable_string_args_by_function(
    function_arg_map: dict[str, list[str] | set[str] | tuple[str, ...]],
) -> None
```

Overrides, per Typst function name, which named string arguments should be
treated as translatable text instead of the default
caption/description/info/subtitle/summary/title set. This call **replaces**
the previous configuration rather than merging with it.

```python
configure_typst_translatable_string_args_by_function({
    "mybox": ["heading", "note"],
})

reset_typst_translatable_string_args_by_function()  # restore defaults
```

### `CodeParser`

```python
from lesia.xml_manipulator_mod.code import CodeParser
```

```python
parser = CodeParser(language: str)
parser.parse(source_code: str) -> list[tuple[str, str]]
```

Uses `tree-sitter` (via `tree-sitter-language-pack`) to separate code from
the natural-language content embedded in it — comments and string
literals. `language` is any language name supported by
`tree-sitter-language-pack` (e.g. `"python"`, `"rust"`, `"java"`); an
unsupported name raises `ValueError` at construction time.

Conceptually, `parse` walks the syntax tree for comment/string nodes and
splits each one into its syntax markers (`#`, `//`, quotes, ...) as
`"placeholder"` segments and its natural-language content as `"text"`
segments; everything else in the source is a single surrounding
`"placeholder"`. Fine-grained dissection is currently only configured for
**Python, Rust, and Java** comments/strings — for any other language
supported by `tree-sitter-language-pack`, `parse` returns the entire source
as one `"placeholder"` segment, with nothing extracted as translatable
text.

> **Known issue:** as of `tree-sitter==0.25.2`, `CodeParser.parse` (and
> therefore `code_to_xml`) raises `TypeError: 'bytes' object is not an
> instance of 'str'` on every call — `code.py` still passes
> `bytes(source_code, "utf8")` into `Parser.parse`, but that API now expects
> a `str`. This is not exercised by the test suite. Until it's fixed
> upstream, treat `CodeParser` and `code_to_xml` as non-functional.

---

## XML tagging and reconstruction

```python
from lesia.xml_manipulator_mod.xml import (
    create_translation_xml,
    reconstruct_from_xml,
    verify_placeholders,
)
```

### `create_translation_xml`

```python
create_translation_xml(segments: list[tuple[str, str]]) -> tuple[str, dict, bool]
```

Converts a list of `(kind, content)` segments (as produced by `parse_latex`,
`parse_myst`, `parse_typst`, or `CodeParser.parse`) into a single
`<document><TEXT>...</TEXT></document>` XML string. Text segments become
plain XML text nodes; consecutive non-text segments are merged into a
single `<PH id="...">` tag each (bare `"\n"` placeholders are kept
separate so structural line breaks are never silently absorbed). Only
segments literally typed `"text"` are treated as translatable — any other
type (`"placeholder"`, `"math"`, ...) is folded into a `<PH>`.

Returns `(xml_string, placeholders, ph_only)`:

- `xml_string` — the tagged XML, ready to hand to a translator.
- `placeholders` — `dict[str, str]` mapping each `<PH>` `id` to its original
  content, needed later by `reconstruct_from_xml`.
- `ph_only` — `True` if there was no translatable text at all (every
  segment was a placeholder).

```python
>>> xml, phs, ph_only = create_translation_xml([
...     ("placeholder", "\\section*{"), ("text", "Intro"), ("placeholder", "}"),
... ])
>>> xml
'<document><TEXT><PH id="1">\\section*{</PH>Intro<PH id="2">}</PH></TEXT></document>'
>>> phs
{'1': '\\section*{', '2': '}'}
>>> ph_only
False
```

### `reconstruct_from_xml`

```python
reconstruct_from_xml(translated_xml: str, phs: dict[str, str] | None = None) -> str
```

Reverses `create_translation_xml`: rebuilds the document from a translated
`<document><TEXT>...</TEXT></document>` XML string, substituting each
`<PH id="...">` with the original content from `phs` (falling back to the
`<PH>` tag's own text if its id isn't in `phs`). Raises `xml.etree.ElementTree.ParseError` if `translated_xml` isn't
well-formed.

```python
>>> reconstruct_from_xml(xml, phs)
'\\section*{Intro}'
```

### `verify_placeholders`

```python
verify_placeholders(translated_xml: str, expected_phs: dict[str, str]) -> tuple[list[str], list[str]]
```

Sanity-checks a translated XML string before reconstructing it: returns
`(missing_ids, extra_ids)`, the `<PH>` ids that were expected but absent,
and the ones present but unexpected. Both empty means the translation
didn't drop or invent any placeholders. Returns `([], [])` (rather than
raising) if `translated_xml` fails to parse — that failure mode is expected
to be handled separately by the caller.

### Convenience wrappers

```python
from lesia.xml_manipulator_mod.mod import (
    chunk_to_xml,
    chunk_to_xml_with_placeholders,
    chunk_contains_ph_only,
    latex_to_xml,
    myst_to_xml,
    typst_to_xml_mod,
    code_to_xml,
)
```

`mod.py` chains parsing and XML tagging together so you don't have to call
`parse_*` and `create_translation_xml` yourself:

- `latex_to_xml(source: str) -> tuple[str, dict, bool]` — `parse_latex` + `create_translation_xml`.
- `myst_to_xml(source: str) -> tuple[str, dict, bool]` — `parse_myst` + `create_translation_xml`, remapping `"math"` segments to placeholders.
- `typst_to_xml_mod(source: str) -> tuple[str, dict, bool]` — `parse_typst` + `create_translation_xml`, remapping `"math"` segments to placeholders.
- `code_to_xml(source: str, language: str) -> tuple[str, dict, bool]` — `CodeParser(language).parse` + `create_translation_xml`; falls back to a single placeholder segment (the whole source untranslated) if `language` isn't supported. Currently non-functional — see the [known issue](#codeparser) under `CodeParser`.

```python
chunk_to_xml_bis(source: str, chunk_type: ChunkType) -> tuple[str, dict, bool]
chunk_to_xml(source: str, chunk_type: ChunkType) -> str
chunk_to_xml_with_placeholders(source: str, chunk_type: ChunkType) -> tuple[str, dict]
chunk_contains_ph_only(source: str, chunk_type: ChunkType) -> bool
```

Dispatch over the format-specific functions above by `ChunkType`
(`from lesia.enums import ChunkType`). Only `ChunkType.LaTeX`,
`ChunkType.Myst`, and `ChunkType.Typst` are implemented — any other value
raises `RuntimeError`. `chunk_to_xml` and `chunk_to_xml_with_placeholders`
return a subset of `chunk_to_xml_bis`'s `(xml, placeholders, ph_only)`
tuple; `chunk_contains_ph_only` returns just the `ph_only` flag.
