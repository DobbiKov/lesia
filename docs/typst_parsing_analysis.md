# Typst Parsing Analysis: Text vs Placeholder Segmentation

## Background

This library translates documents by splitting content into `('text', ...)` and
`('placeholder', ...)` segments. Text segments are sent to the LLM for
translation; placeholders are preserved verbatim. This report analyses how that
segmentation works in LaTeX and MyST, and what is possible for Typst.

---

## How Text vs Placeholder Is Marked

### Segment Types

Both existing parsers produce `list[tuple[str, str]]` where each tuple is `(type, content)` with types:

- **`'text'`** — human-readable content that should be translated
- **`'placeholder'`** — syntax/markup that must be preserved verbatim
- **`'math'`** — math blocks (treated as untranslatable by the translator)

---

### LaTeX (`xml_manipulator_mod/latex.py`)

Uses **`pylatexenc`** to walk a proper AST.

**Key rules:**

| Node type | Segment type |
|-----------|-------------|
| `LatexCharsNode` (non-empty, non-whitespace) | `'text'` |
| `LatexCharsNode` (whitespace only) | `'placeholder'` |
| `LatexMacroNode` in `placeholder_commands` (`\ref`, `\cite`, `\frac`, …) | `'placeholder'` (whole macro) |
| Other macros | `'placeholder'` for command, **recurse** into args |
| Math environments | `'placeholder'` unless arg of `math_text_macros` (`\text{}`, `\mathrm{}`, …) |
| Verbatim environments (`verbatim`, `lstlisting`, …) | `'placeholder'` (whole block) |
| `LatexCommentNode` | `% ` → `'placeholder'`, comment text → `'text'` |

Two configuration sets drive the logic:
- `placeholder_commands` — always a placeholder, never recurse into
- `math_text_macros` — inside math mode, recurse into argument to find translatable text

Pre-processing extracts `\verb|...|` and custom pipe-delimited commands before AST walking, then restores them after.

---

### MyST (`xml_manipulator_mod/myst.py`)

Uses **`myst-parser`** / **`markdown-it`** token stream. Each token handler decides the segment type:

| Token type | Segment type |
|-----------|-------------|
| `"text"` | `('text', content)` |
| `"heading_open"`, `"em_open"`, `"strong_open"`, `"paragraph_close"`, etc. | `('placeholder', markup)` |
| `"math_inline"`, `"math_block"`, `"amsmath"` | `('math', ...)` |
| `"fence"` / `"colon_fence"` with `{code-block}`, `{eval-rst}` | `('placeholder', ...)` |
| `"fence"` with `{note}`, `{warning}`, admonitions, etc. | Recurse into content for text |
| `"myst_role"`, `"code_inline"`, `"html_block"` | `('placeholder', ...)` |
| `"myst_line_comment"` | `% ` → placeholder, comment text → `'text'` |

---

## Typst: What Is Possible

### Language Structure

Typst has three clearly separated modes that interleave in documents:

- **Markup mode** — prose and document structure (headings, emphasis, lists)
- **Code mode** — scripting (variables, functions, loops, conditionals)
- **Math mode** — mathematical expressions

This separation maps directly onto the `text`/`placeholder` distinction.

### Target Segmentation

| Typst construct | Segment type |
|----------------|-------------|
| Markup plain text | `'text'` |
| Heading content (`= Title`) | `'text'` (recurse) |
| Emphasis (`_text_`), strong (`*text*`) content | `'text'` (recurse) |
| List item content | `'text'` (recurse) |
| Raw inline (`` `code` ``) | `'placeholder'` |
| Raw block (` ```lang ... ``` `) | `'placeholder'` |
| Math expressions (`$ ... $`) | `'math'` |
| `text(...)` inside math | `'text'` (recurse, analogous to `\text{}`) |
| Labels (`<label>`), references (`@ref`) | `'placeholder'` |
| Code blocks `{ ... }` | `'placeholder'` |
| Function calls, `let`, `for`, `if`, `show`, `set` | `'placeholder'` |
| Comments `// ...` and `/* ... */` | `'placeholder'` for syntax, `'text'` for comment body |

---

## Available Parsing Libraries

### Option 1: `tree-sitter` + `tree-sitter-language-pack` ✅ Recommended

**`tree-sitter-language-pack`** bundles a Typst grammar (from [uben0/tree-sitter-typst](https://github.com/uben0/tree-sitter-typst)) and is installable today with no extra build steps.

```bash
pip install tree-sitter tree-sitter-language-pack
```

```python
from tree_sitter_language_pack import get_parser

parser = get_parser("typst")
tree = parser.parse(bytes(source, "utf8"))
root = tree.root_node

def walk(node):
    if node.type == "text":
        yield ("text", node.text.decode())
    elif node.type in ("raw_span", "raw_blck", "label", "ref",
                        "math", "code", "block"):
        yield ("placeholder", node.text.decode())
    elif node.type in ("emph", "strong", "heading",
                        "list_item", "enum_item", "term_item", "content"):
        # Emit surrounding syntax as placeholder, recurse into children for text
        for child in node.children:
            yield from walk(child)
    else:
        yield ("placeholder", node.text.decode())
```

**Key node types:**

| Node type | Description |
|-----------|-------------|
| `text` | Plain markup text — primary source of `'text'` segments |
| `emph` | `_emphasized_` content |
| `strong` | `*bold*` content |
| `heading` | `= Heading` |
| `raw_span` | Inline raw `` `code` `` |
| `raw_blck` | Raw block ` ```...``` ` |
| `math` | Math expression `$...$` |
| `label` | `<label>` |
| `ref` | `@reference` |
| `code` / `block` | Code expressions |
| `let`, `for`, `branch`, `import` | Code mode constructs |

Tree-sitter gives a **Concrete Syntax Tree** (CST) with source byte offsets, so reconstruction of the original document from segments is lossless — the same guarantee `pylatexenc` provides for LaTeX.

---

### Option 2: `typst-syntax` Rust crate (via subprocess/FFI)

The official [typst-syntax](https://crates.io/crates/typst-syntax) crate is the ground-truth parser — it is what Typst itself uses internally. It exposes rich AST types: `Text`, `Emph`, `Strong`, `Heading`, `Raw`, `Math`, `CodeBlock`, `FuncCall`, `SetRule`, `ShowRule`, etc.

**Pros:** Perfect language parity, handles every edge case correctly.
**Cons:** No Python bindings exist yet. Would require either:
- A small Rust CLI that parses and outputs JSON, called as a subprocess
- PyO3 bindings (significant effort)

---

### Option 3: Regex / Manual Parser

Typst markup is simpler than LaTeX — there is no arbitrary macro redefinition. A regex/state-machine approach could cover most practical markup cases. Similar to how `_extract_verb_commands` pre-processes LaTeX before AST walking.

**Pros:** Zero dependencies, full control.
**Cons:** Fragile for nested structures, will fail on complex code-in-markup interleaving.

---

## Key Differences from LaTeX/MyST to Plan For

1. **No fixed macro dictionary.** Typst functions are first-class and user-definable. Heuristic: any `funcname(content: [...])` call → check if argument is a content block and recurse for text. Known text-in-math functions: `text()`, `upright()`, `bold()`, `italic()`.

2. **Three modes interleave.** Code blocks can appear inline in markup (`#let x = 1`), and content blocks appear in code (`[markup here]`). Tree-sitter handles this naturally through its grammar rules.

3. **Raw blocks are always placeholders.** Both `` `inline` `` and ` ```block``` ` → `'placeholder'`, analogous to `\verb` and `verbatim` in LaTeX.

4. **`text()` in math.** Analogous to `\text{}` in LaTeX — the argument should be recursed into to produce `'text'` segments, not treated as a monolithic placeholder.

5. **Comments are `//` and `/* */`.** Unlike LaTeX's `%` comments, but the same pattern applies: syntax → placeholder, comment body → text.

---

## Recommended Implementation Path

1. Install `tree-sitter` and `tree-sitter-language-pack`
2. Create `src/trans_lib/xml_manipulator_mod/typst.py` mirroring `latex.py` / `myst.py`
3. Walk the CST recursively: `text` nodes → `'text'`; structural wrappers (`emph`, `strong`, `heading`) → emit delimiter nodes as `'placeholder'` and recurse into content children; code/math/raw → `'placeholder'`
4. Handle `text()` calls inside math analogously to `math_text_macros` in the LaTeX parser
5. Add `DocumentType.Typst` and `ChunkType.Typst` to `enums.py`
6. Create a `typst_file_translator.py` and `typst_chunker.py` modelled on the LaTeX equivalents

---

## Current Implementation

The Typst parser and chunker described above have been implemented. This section documents how they actually work, including the chunking pipeline and how oversized chunks are handled at translation time.

Relevant source files:
- `src/trans_lib/xml_manipulator_mod/typst.py` — segment parser (`parse_typst`)
- `src/trans_lib/doc_translator_mod/typst_chunker.py` — file-level chunker
- `src/trans_lib/translator_retrieval.py` — translation-time subchunking

### File-level chunking

`split_typst_document_into_chunks(source)` splits a Typst source file into
chunks before translation:

- Parses the Typst AST using `typst_syntax`.
- Builds `simple_chunks` from AST-aware units.
- Groups simple chunks into section groups.
- Completes or splits large sections **by AST element boundaries**, not by raw
  text slicing.

Key property: commands and syntax units are treated as atomic units during
repacking. A command head and body are never split across chunk boundaries. If a
single AST unit exceeds the soft maximum of 2000 characters, it is emitted as
one oversized chunk rather than cut in the middle.

### Translation-time subchunking

For Typst chunks longer than 2000 characters, the translator attempts to split
them internally before sending to the LLM. This keeps individual LLM calls
within a manageable size without re-running file-level chunking.

**Step 1 — segment classification.** The whole chunk is parsed with `parse_typst`,
producing an ordered list of `('text', ...)`, `('placeholder', ...)`, and
`('math', ...)` segments. Classification happens before any boundaries are
chosen, so no segment is ever cut by the splitting logic.

**Step 2 — packing.** Segments are packed left-to-right into subchunks up to
2000 characters. Placeholder and math segments are kept atomic — they are never
split internally. A placeholder larger than 2000 characters becomes one oversized
subchunk on its own. Text segments may be split if a single text run itself
exceeds 2000 characters, using a boundary heuristic that prioritises paragraph
breaks, then newlines, then sentence boundaries, then spaces.

**Step 3 — lossless reconstruction guard.** After splitting, the algorithm
verifies that concatenating all subchunks reproduces the original exactly. If
not, subchunking is abandoned and the full chunk is passed to the LLM as-is.

Each subchunk is then translated via the normal `translate_or_fetch` path
(including its own cache lookup). Placeholder-only subchunks bypass the LLM
entirely. After all subchunks are translated, the results are concatenated and
the original full chunk → combined translation pair is persisted as one cache
entry. If any subchunk fails, the entire operation raises
`ChunkTranslationFailed` with the original full chunk unchanged.

### Typst function string arguments

By default, string arguments of user-defined Typst functions are not translated.
The project configuration allows registering specific argument names of specific
functions as translatable:

```
lesia set-typst-func-args figure caption
lesia set-typst-func-args ex info caption
```

This maps onto `parse_typst` behaviour: when the parser encounters a call to a
registered function, it recurses into the listed string arguments and yields
their content as `'text'` segments rather than treating the whole call as a
`'placeholder'`.

### Edge cases

| Case | Behaviour |
|---|---|
| Command near a size boundary | File-level chunker keeps command head and body together; subchunker classifies the command as a placeholder and does not split it |
| `#show` / `#set` / `#let` | Classified as placeholder via parse segmentation; syntax-safe |
| Inline math (`$...$`) | Classified as non-translatable segment; not split across subchunk boundaries |
| Large raw/code block inside a command body | Becomes a single placeholder subchunk (possibly >2000); bypasses LLM |
| Very large single text run | Split by boundary heuristics (paragraph → newline → sentence → space → hard cut) |
| Parse/reconstruction mismatch | Subchunking abandoned; full chunk sent to LLM |
| Partial subchunk failure | Whole chunk fails as `ChunkTranslationFailed`; original left unchanged |

---

## References

- [frozolotl/tree-sitter-typst](https://github.com/frozolotl/tree-sitter-typst) — correctness-focused grammar
- [uben0/tree-sitter-typst](https://github.com/uben0/tree-sitter-typst) — grammar bundled in tree-sitter-language-pack
- [tree-sitter-language-pack · PyPI](https://pypi.org/project/tree-sitter-language-pack/)
- [typst-syntax crate docs](https://docs.rs/typst-syntax/latest/typst_syntax/ast/index.html)
- [py-tree-sitter](https://github.com/tree-sitter/py-tree-sitter)
- [Typst documentation](https://typst.app/docs/)
