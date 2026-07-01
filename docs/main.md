# Library API Reference

`lesia` is a Python library for managing and automating the
translation of markup document projects (LaTeX, Markdown, Jupyter, MyST,
Typst). It preserves file structure and formatting, uses LLM services for
translation, and maintains a persistent translation cache.

For a conceptual overview of how the tool works, see the [profound explanation](./tool-profound-explanation.md).

> **Note:** The library is in early development. Expect bugs and incomplete features.

## Table of Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Language](#language)
- [CustomLanguage](#customlanguage)
- [VocabList](#vocablist)
- [Module-level functions](#module-level-functions)
  - [init_project](#init_project)
  - [load_project](#load_project)
- [Project class](#project-class)
  - [Project setup](#project-setup)
  - [Custom language management](#custom-language-management)
  - [File management](#file-management)
  - [Translation](#translation)
  - [Cache management](#cache-management)
  - [LLM configuration](#llm-configuration)
  - [Typst configuration](#typst-configuration)
- [LaTeX configuration](#latex-configuration)
- [Error reference](#error-reference)

---

## Installation

### As a dependency

```sh
pip install <path_to_lesia>
```

Or with `uv`:

```sh
uv add <path_to_lesia>
```

### For development

```sh
git clone https://github.com/DobbiKov/lesia
cd lesia
uv sync
```

---

## Quick start

```python
import asyncio
from lesia.project_manager import init_project, load_project
from lesia.enums import Language

# Initialize a new project in an existing directory
project = init_project("my_project", "/path/to/project/root")

# Set the source directory and its language
project.set_source_directory("analysis_notes_fr", Language.FRENCH)

# Add a target language (creates the output directory automatically)
project.add_target_language(Language.ENGLISH)

# Mark a file for translation
project.set_file_translatability("analysis_notes_fr/main.tex", True)

# Copy untranslatable files (images, bibliography, etc.) to the target directory
project.sync_untranslatable_files()

# Translate (async)
asyncio.run(project.translate_single_file("analysis_notes_fr/main.tex", Language.ENGLISH, None))
```

To use a custom language not in the predefined list:

```python
# Register the custom language (optional short alias)
project.add_custom_language("American English", "_ae", short="AmEng")

# Resolve it using either the full name or the short alias
american_english = project.config.resolve_language("AmEng")  # or "American English"

# Use it just like a predefined language
project.add_target_language(american_english)
asyncio.run(project.translate_all_for_language(american_english, None))
```

To work with an existing project, load it from the current directory (searched upward, like `git`):

```python
from lesia.project_manager import load_project

project = load_project(".")
```

---

## Language

```python
from lesia.enums import Language
```

`Language` is a `str` enum of supported languages.

| Member | Value | Directory suffix |
|---|---|---|
| `Language.FRENCH` | `"French"` | `_fr` |
| `Language.ENGLISH` | `"English"` | `_en` |
| `Language.GERMAN` | `"German"` | `_de` |
| `Language.SPANISH` | `"Spanish"` | `_es` |
| `Language.UKRAINIAN` | `"Ukrainian"` | `_ua` |
| `Language.ARMENIAN` | `"Armenian"` | `_hy` |

**`Language.from_str(s: str) -> Language`**

Case-insensitive parse from a string. Raises `ValueError` if the string does not match any language.

```python
lang = Language.from_str("french")  # Language.FRENCH
lang = Language.from_str("ENGLISH") # Language.ENGLISH
```

> **Note:** All `Project` methods accept both `Language` and `CustomLanguage`. For new code, prefer obtaining languages via `project.config.resolve_language(name)` which returns a `CustomLanguage` and works for both predefined and custom languages uniformly.

---

## CustomLanguage

```python
from lesia.enums import CustomLanguage
```

`CustomLanguage` is the runtime representation of a language — both predefined and custom. All `Project` methods that accept a language argument accept either a `Language` enum member or a `CustomLanguage` instance.

### Constructor

```python
CustomLanguage(lang: str, suffix: str)
```

| Parameter | Description |
|---|---|
| `lang` | Display name, e.g. `"Catalan"`. Used as the language identifier in cache files and config. |
| `suffix` | Directory suffix, e.g. `"_ca"`. Used when auto-creating target directories. |

### Class method

**`CustomLanguage.from_language(lang: Language) -> CustomLanguage`**

Converts a predefined `Language` enum member to a `CustomLanguage` instance.

```python
cl = CustomLanguage.from_language(Language.FRENCH)
# cl.get_lang()       == "French"
# cl.get_dir_suffix() == "_fr"
```

### Instance methods

```python
cl.get_lang() -> str         # Returns the display name
cl.get_dir_suffix() -> str   # Returns the directory suffix
str(cl)                      # Same as get_lang()
```

### Equality and hashing

Two `CustomLanguage` instances are equal if their names match case-insensitively. `CustomLanguage` is also equal to a plain `str` with the same name (case-insensitive). It is hashable and safe to use as a dict key.

```python
CustomLanguage("Catalan", "_ca") == CustomLanguage("catalan", "_ca")  # True
CustomLanguage("Catalan", "_ca") == "catalan"                          # True
```

### Obtaining a `CustomLanguage` from the project

The recommended way to get a `CustomLanguage` for a registered language (predefined or custom) is via `ProjectConfig.resolve_language`:

```python
catalan = project.config.resolve_language("Catalan")
english = project.config.resolve_language("English")
```

---

## VocabList

```python
from lesia.vocab_list import VocabList, vocab_list_from_vocab_db
```

Holds a custom glossary that is passed to the LLM during translation to improve term consistency.

### Constructor

```python
VocabList(source_lang_terms: list[str], target_lang_terms: list[str])
```

Both lists must have the same length. Each pair `(source_lang_terms[i], target_lang_terms[i])` is one vocabulary entry.

```python
vocab = VocabList(
    source_lang_terms=["pomme", "ordinateur"],
    target_lang_terms=["apple", "computer"],
)
```

### `vocab_list_from_vocab_db`

```python
vocab_list_from_vocab_db(
    db: list[dict],
    source_lang: Language | CustomLanguage,
    target_lang: Language | CustomLanguage,
) -> VocabList
```

Extracts a `VocabList` from a multi-language vocabulary database. The `db` argument is a list of dicts where each key is a language name and each value is the term in that language — the format produced by reading a CSV file with `csv.DictReader`.

```python
import csv
from lesia.vocab_list import vocab_list_from_vocab_db
from lesia.enums import Language

with open("vocab.csv") as f:
    db = list(csv.DictReader(f))

# vocab.csv must have language names as column headers:
# French, English
# pomme,  apple
# voiture,car

vocab = vocab_list_from_vocab_db(db, Language.FRENCH, Language.ENGLISH)
```

If the source or target language is not found as a column header, a warning is logged and an empty `VocabList` is returned.

---

## Module-level functions

```python
from lesia.project_manager import init_project, load_project
```

### `init_project`

```python
init_project(project_name: str, root_dir_str: str) -> Project
```

Creates a new translation project by writing a `.lesia/config.json` file inside `root_dir_str`. The directory must already exist and must not already contain a `.lesia` directory.

**Raises:** `InitProjectError` — if the path is invalid, does not exist, is not a directory, or a project is already initialized there.

### `load_project`

```python
load_project(path_str: str) -> Project
```

Loads an existing project. Searches upward from `path_str` for a `.lesia` directory (the same strategy `git` uses to find `.git`). Can be called with `"."` from anywhere inside a project tree.

**Raises:** `LoadProjectError` — if no project is found or the config file cannot be parsed.

---

## Project class

```python
from lesia.project_manager import Project
```

`Project` is the central object for all operations. Always obtain an instance via `init_project` or `load_project`; do not instantiate directly.

```python
project.root_path  # Path  — absolute path to the project root
project.config     # ProjectConfig — the loaded configuration model
```

---

### Project setup

#### `set_source_directory`

```python
project.set_source_directory(dir_name: str, lang: Language | CustomLanguage) -> None
```

Sets (or changes) the source directory and its language. `dir_name` is relative to `project.root_path`. The directory must already exist. Calling this again with a different directory replaces the previous source.

**Raises:** `SetSourceDirError` — if the directory does not exist, is not a directory, or the language is already in use as source or target.

#### `add_target_language`

```python
project.add_target_language(lang: Language | CustomLanguage, tgt_dir: Path | None = None) -> Path
```

Adds a target language. Returns the absolute path of the target directory.

- If `tgt_dir` is `None`, a new directory is created automatically inside the project root using the naming convention `<project_name><lang_suffix>` (e.g. `analysis_notes_en`).
- If `tgt_dir` is provided, it must already exist and be located inside the project root.

**Raises:** `AddLanguageError` — if no source language is set, the language is already present, or the auto-generated directory already exists.

#### `remove_target_language`

```python
project.remove_target_language(lang: Language | CustomLanguage) -> None
```

Removes a target language from the configuration and deletes its directory from disk.

**Raises:** `RemoveLanguageError` — if the language is not a configured target.

#### `get_source_langugage`

```python
project.get_source_langugage() -> CustomLanguage
```

Returns the source language as a `CustomLanguage` instance (works for both predefined and custom languages).

**Raises:** `NoSourceLanguageError` — if no source language is set.

---

### Custom language management

Custom languages extend the fixed predefined set. Once registered, they are stored in the project config and can be used everywhere a language is accepted.

#### `add_custom_language`

```python
project.add_custom_language(name: str, suffix: str, short: str | None = None) -> None
```

Registers a new custom language. `name` is the display name (e.g. `"American English"`); `suffix` is the directory suffix (e.g. `"_ae"`). The optional `short` parameter registers a short alias (e.g. `"AmEng"`) that can be used in place of the full name in any call that accepts a language name string.

```python
project.add_custom_language("Catalan", "_ca")
project.add_custom_language("American English", "_ae", short="AmEng")
```

The short alias is looked up case-insensitively, so `"ameng"` resolves the same as `"AmEng"`.

**Raises:** `AddCustomLanguageError` — if:
- `name` matches a predefined language.
- `name` is already registered as a custom language.
- `short` is already used by another custom language.
- `short` matches a predefined language name (case-insensitive) — this would make the predefined language unreachable via `resolve_language`.
- `short` matches an existing custom language's full name (case-insensitive) — this would create an ambiguous alias.

#### `remove_custom_language`

```python
project.remove_custom_language(name: str) -> None
```

Removes a custom language from the project config. Accepts either the full name or the registered short alias. Removing a language also removes its short alias.

```python
project.remove_custom_language("Catalan")
project.remove_custom_language("AmEng")  # same as remove_custom_language("American English")
```

**Raises:** `RemoveCustomLanguageError` — if the name/alias matches a predefined language, is not registered, or still has an associated target directory (remove the target first with `remove_target_language`).

#### `ProjectConfig.resolve_language`

```python
project.config.resolve_language(name: str) -> CustomLanguage
```

Resolves a language name or short alias to a `CustomLanguage` instance. Resolution order: predefined languages first, then the custom registry by full name, then by short alias (case-insensitive). Because predefined languages are checked first, a short alias can never shadow a predefined language — `add_custom_language` rejects such aliases upfront.

```python
french          = project.config.resolve_language("French")           # predefined
catalan         = project.config.resolve_language("Catalan")          # custom full name
american_en     = project.config.resolve_language("American English") # custom full name
american_en     = project.config.resolve_language("AmEng")           # custom short alias
```

**Raises:** `ValueError` — if the name is not found in either the predefined list or the custom registry (by full name or short alias).

#### `ProjectConfig.custom_languages`

```python
project.config.custom_languages       # dict[str, str]  — full name → suffix
project.config.custom_language_shorts # dict[str, str]  — short alias → full name
```

`custom_languages` maps each registered custom language's full name to its directory suffix. `custom_language_shorts` maps each registered short alias to its corresponding full name. Both are persisted to `config.json`.

---

### File management

#### `set_file_translatability`

```python
project.set_file_translatability(file_path_str: str, translatable: bool) -> None
```

Marks a file in the source directory as translatable (`True`) or untranslatable (`False`).

- **Translatable files** are processed by translation commands and ignored by `sync_untranslatable_files`.
- **Untranslatable files** are copied as-is by `sync_untranslatable_files` and ignored by translation commands.

**Raises:** `AddTranslatableFileError` — if the file does not exist or no source directory is set.

#### `get_translatable_files`

```python
project.get_translatable_files() -> list[Path]
```

Returns absolute paths of all files currently marked as translatable.

**Raises:** `GetTranslatableFilesError` — if no source language is set.

#### `sync_untranslatable_files`

```python
project.sync_untranslatable_files() -> None
```

Copies all untranslatable files from the source directory into every configured target directory, mirroring the subdirectory structure. This makes the target directories self-contained (e.g. buildable with LaTeX).

**Raises:** `SyncFilesError` — if no source or target directories are configured, or a copy fails.

---

### Translation

Translation methods are `async` and require the `LLM_API_KEY` environment variable to be set for the configured service.

#### Setting the API key

`LLM_API_KEY` is read from the environment **at import time**, so it must be set before `lesia` is imported.

**Option 1 — set it in the shell before running your script:**
```sh
export LLM_API_KEY=<your_api_key>
python your_script.py
```

**Option 2 — set it in Python before importing lesia:**
```python
import os
os.environ["LLM_API_KEY"] = "<your_api_key>"

import lesia  # import AFTER setting the key
```

If you set `os.environ["LLM_API_KEY"]` after lesia is already imported, it will have no effect.

#### `translate_single_file`

```python
await project.translate_single_file(
    file_path_str: str,
    target_lang: Language | CustomLanguage,
    vocab_list: VocabList | None,
) -> None
```

Translates one file into `target_lang`. The file must be marked as translatable. Optionally accepts a `VocabList` to guide terminology.

```python
import asyncio
asyncio.run(project.translate_single_file("notes_fr/main.tex", Language.ENGLISH, None))

# With a custom language:
catalan = project.config.resolve_language("Catalan")
asyncio.run(project.translate_single_file("notes_fr/main.tex", catalan, None))
```

**Raises:** `TranslateFileError` — if the file is not marked as translatable, the language is not configured, or translation fails unrecoverably.

#### `translate_all_for_language`

```python
await project.translate_all_for_language(
    target_lang: Language | CustomLanguage,
    vocab_list: VocabList | None,
) -> None
```

Translates all translatable files into `target_lang`. Files are processed sequentially. Individual chunk failures are logged and the chunk is left untranslated, but the run continues.

**Raises:** `TranslateFileError` — for unrecoverable errors.

---

### Cache management

The translation cache stores source-to-translation pairs on disk to avoid redundant LLM calls. See the [Translation Cache section](./tool-profound-explanation.md#the-translation-cache) of the profound explanation for a full description of the on-disk structure and algorithms.

#### `sync_translation_cache`

```python
project.sync_translation_cache(target_lang: Language | CustomLanguage | None = None) -> None
```

Rebuilds the translation cache by scanning on-disk source and target file pairs. Run this after manually editing translated files so that future translations reuse your corrected text instead of regenerating from the LLM.

If `target_lang` is `None`, all configured target languages are synced.

**Raises:** `TranslationCacheSyncError`.

#### `correct_translation_for_lang`

```python
project.correct_translation_for_lang(target_lang: Language | CustomLanguage) -> None
```

Reads translated files on disk for the given language and updates the cache to reflect any manual corrections.

**Raises:** `CorrectTranslationError`.

#### `correct_translation_single_file`

```python
project.correct_translation_single_file(file_path_str: str) -> None
```

Same as `correct_translation_for_lang` but limited to a single file.

**Raises:** `CorrectTranslationError`.

#### `clear_translation_cache_missing_chunks`

```python
project.clear_translation_cache_missing_chunks()
```

Removes cache entries that reference chunk files no longer present on disk. Also removes orphaned chunk files with no corresponding cache row. See the [cache maintenance section](./tool-profound-explanation.md#cache-maintenance) of the profound explanation for the full algorithm.

#### `clear_translation_cache_all`

```python
project.clear_translation_cache_all(
    lang: Language | CustomLanguage | None,
    file_path_str: str | None,
    keyword: str | None,
)
```

Deletes cache entries, optionally scoped to a language, a file, or a keyword substring match. Passing all three as `None` clears the entire cache. See the [cache maintenance section](./tool-profound-explanation.md#cache-maintenance) of the profound explanation for details on each combination.

---

### LLM configuration

The default LLM is `google` / `gemini-2.0-flash`.

Supported services: `google`, `openai`, `anthropic`, `xai`, `aristote`, `ilaas`.

#### `set_llm_service_and_model`

```python
project.set_llm_service_and_model(service: str, model: str) -> None
```

Sets the primary LLM service and model used for translation.

```python
project.set_llm_service_and_model("google", "gemini-2.0-flash")
project.set_llm_service_and_model("openai", "gpt-4o")
project.set_llm_service_and_model("anthropic", "claude-sonnet-4-5-20251001")
```

**Raises:** `SetLLMServiceError`.

#### `set_llm_reasoning_service_and_model`

```python
project.set_llm_reasoning_service_and_model(service: str, model: str) -> None
```

Sets an optional reasoning model for harder translation decisions. When set, the tool may use this model for chunks that require more careful handling.

**Raises:** `SetLLMServiceError`.

#### Getters

```python
project.get_llm_service() -> str
project.get_llm_model() -> str
project.get_llm_reasoning_service() -> str | None
project.get_llm_reasoning_model() -> str | None
```

---

### Typst configuration

By default, string arguments of Typst functions (e.g. captions, labels) are not translated. These methods let you register specific argument names of specific functions as translatable.

#### `set_typst_translatable_string_args_for_function`

```python
project.set_typst_translatable_string_args_for_function(
    function_name: str,
    arg_names: list[str],
) -> None
```

Registers `arg_names` as the translatable string arguments of the Typst function `function_name`.

```python
project.set_typst_translatable_string_args_for_function("figure", ["caption"])
project.set_typst_translatable_string_args_for_function("ex", ["info", "caption"])
```

**Raises:** `SetTypstConfigError`.

#### `remove_typst_translatable_string_args_for_function`

```python
project.remove_typst_translatable_string_args_for_function(function_name: str) -> None
```

Removes the translatable-arg configuration for `function_name`.

**Raises:** `SetTypstConfigError`.

#### `get_typst_translatable_string_args_by_function`

```python
project.get_typst_translatable_string_args_by_function() -> dict[str, list[str]]
```

Returns the current mapping of function names to their registered translatable argument names.

---

### LaTeX configuration

The LaTeX parser has a set of hardcoded defaults — environments like `verbatim` and `lstlisting` are treated as opaque placeholders, commands like `\cite` and `\ref` are never translated, and all unrecognised environments and commands have their body/arguments walked as translatable text. These methods let you extend and fine-tune that behaviour without modifying source code.

All settings are persisted in `.lesia/config.json` and applied automatically before every translation run.

> **Two layers:** Every project method below simply stores the setting and calls `save_config()`. The actual parsing logic lives in `configure_latex_settings()` in `lesia.xml_manipulator_mod.latex`, which can also be called directly without a project (see [Standalone usage](#standalone-usage) below).

#### `add_latex_placeholder_env` / `remove_latex_placeholder_env`

```python
project.add_latex_placeholder_env(env_name: str) -> None
project.remove_latex_placeholder_env(env_name: str) -> None
```

Mark an environment as non-translatable — the entire `\begin{env}…\end{env}` block is emitted as a single opaque placeholder and its content is never sent to the LLM.

```python
project.add_latex_placeholder_env("myverbatim")
project.add_latex_placeholder_env("algorithm")
project.remove_latex_placeholder_env("myverbatim")
```

**Raises:** `SetLatexConfigError` — if the name is empty or (for remove) the environment is not in the list.

#### `add_latex_math_env` / `remove_latex_math_env`

```python
project.add_latex_math_env(env_name: str) -> None
project.remove_latex_math_env(env_name: str) -> None
```

Mark an environment as a math environment. Its body is walked in math mode: plain text inside is treated as a placeholder and only `\text{…}`-style macros (known to pylatexenc) expose translatable content.

```python
project.add_latex_math_env("myequation")
project.remove_latex_math_env("myequation")
```

**Raises:** `SetLatexConfigError` — if the name is empty or (for remove) the environment is not in the list.

#### `add_latex_placeholder_command` / `remove_latex_placeholder_command`

```python
project.add_latex_placeholder_command(cmd_name: str) -> None
project.remove_latex_placeholder_command(cmd_name: str) -> None
```

Mark a command as fully non-translatable.

For **commands that pylatexenc knows** (standard LaTeX commands), the command together with all its arguments becomes a single placeholder.

For **unknown custom commands**, only the command token itself becomes a placeholder; the `{…}` groups that follow are sibling nodes in the parse tree and are still walked as text. To make an unknown command's arguments non-translatable as well, register its argument structure first with `set_latex_custom_command_spec` — once pylatexenc knows the spec, `node.latex_verbatim()` includes all arguments and the entire expression is suppressed.

```python
# Standard usage (command is fully suppressed):
project.add_latex_placeholder_command("myref")

# Custom command — register spec first, then suppress:
project.set_latex_custom_command_spec("myfig", mandatory=2)
project.add_latex_placeholder_command("myfig")
# Now \myfig{label}{caption} becomes a single placeholder.
```

**Raises:** `SetLatexConfigError` — if the name is empty or (for remove) the command is not in the list.

#### `set_latex_command_translatable_args` / `remove_latex_command_translatable_args`

```python
project.set_latex_command_translatable_args(
    cmd_name: str,
    mandatory: list[int] | None = None,
    optional: list[int] | None = None,
) -> None

project.remove_latex_command_translatable_args(cmd_name: str) -> None
```

Specify which arguments of a command are translatable. Arguments use **1-based indexing**, counting `{…}` (mandatory) and `[…]` (optional) separately.

- `mandatory`: 1-based indices of `{…}` arguments that should be translated. Arguments not listed become placeholders.
- `optional`: 1-based indices of `[…]` arguments that should be translated. Arguments not listed become placeholders.
- At least one of `mandatory` or `optional` must be provided.

> **Prerequisite for custom commands:** this setting only takes effect when pylatexenc can parse the command's arguments into `node.nodeargs`. For commands pylatexenc does not know, register the argument structure with `set_latex_custom_command_spec` first.

```python
# \textcolor{color}{text} — translate only the text argument
project.set_latex_custom_command_spec("textcolor", mandatory=2)
project.set_latex_command_translatable_args("textcolor", mandatory=[2])

# \mybox[label]{title}{body} — translate only the body
project.set_latex_custom_command_spec("mybox", mandatory=2, optional=1)
project.set_latex_command_translatable_args("mybox", mandatory=[2], optional=[])

# \section[short title]{full title} — translate both
project.set_latex_command_translatable_args("section", mandatory=[1], optional=[1])
```

**Raises:** `SetLatexConfigError` — if the name is empty, any index is < 1, or neither `mandatory` nor `optional` is provided. For remove: if the command has no config.

#### `set_latex_custom_command_spec` / `remove_latex_custom_command_spec`

```python
project.set_latex_custom_command_spec(
    cmd_name: str,
    mandatory: int,
    optional: int = 0,
) -> None

project.remove_latex_custom_command_spec(cmd_name: str) -> None
```

Register the argument structure of a custom command with pylatexenc. This is required before `set_latex_command_translatable_args` or `add_latex_placeholder_command` can work correctly on commands not built into pylatexenc.

- `mandatory`: total number of mandatory `{…}` arguments.
- `optional`: total number of optional `[…]` arguments (default `0`). Optional arguments are assumed to come **before** mandatory ones — the most common LaTeX pattern.

```python
# \myfig{label}{caption}
project.set_latex_custom_command_spec("myfig", mandatory=2)

# \mybox[label]{title}{body}
project.set_latex_custom_command_spec("mybox", mandatory=2, optional=1)

# Remove a spec
project.remove_latex_custom_command_spec("myfig")
```

**Raises:** `SetLatexConfigError` — if the name is empty, either count is negative, or both counts are zero.

#### `get_latex_settings`

```python
project.get_latex_settings() -> dict
```

Returns the current LaTeX configuration as a plain dict:

```python
{
    "extra_placeholder_envs":   ["myverbatim", "algorithm"],
    "extra_math_envs":          ["myequation"],
    "extra_placeholder_commands": ["myref"],
    "command_translatable_args": {
        "myfig": {"mandatory": [2]},
        "mybox": {"mandatory": [2], "optional": []},
    },
    "custom_command_specs": {
        "myfig": {"mandatory": 2, "optional": 0},
        "mybox": {"mandatory": 2, "optional": 1},
    },
}
```

---

#### Standalone usage

All of the above can be used without a `Project` by calling `configure_latex_settings` directly in the `lesia.xml_manipulator_mod.latex` module. This is useful when you call `parse_latex` from your own code without managing a project.

```python
from lesia.xml_manipulator_mod.latex import (
    configure_latex_settings,
    reset_latex_settings,
    parse_latex,
)

configure_latex_settings(
    extra_placeholder_envs=["myverbatim", "algorithm"],
    extra_math_envs=["myequation"],
    # \myfig and \mybox are custom commands — their argument structure must
    # be declared in custom_command_specs so pylatexenc associates the {…}
    # groups with the command node.  Without that, extra_placeholder_commands
    # would only suppress the bare command token and the arguments would
    # still be walked as translatable text.
    extra_placeholder_commands=["myfig", "mybox"],
    custom_command_specs={
        "myfig": {"mandatory": 2, "optional": 0},
        "mybox": {"mandatory": 2, "optional": 1},
    },
    command_translatable_args={
        "myfig": {"mandatory": [2]},
        "mybox": {"mandatory": [2], "optional": []},
        "section": {"mandatory": [1], "optional": [1]},
    },
)

segments = parse_latex(r"\myfig{fig:label}{My caption} \section[Short]{Full title}")
# [('placeholder', '\\myfig{fig:label}{My caption}'),
#  ('placeholder', '\\section[Short]'), ('text', 'Full title'), ('placeholder', '}'), ...]

reset_latex_settings()  # restore defaults
```

Settings are **process-wide and additive** on top of the hardcoded defaults — you cannot accidentally remove built-in entries such as `\cite` or `verbatim`. Calling `configure_latex_settings` again replaces the previous call entirely; call `reset_latex_settings` to return to defaults.

---

## Error reference

All exceptions inherit from `DirectoryTranslationError`.

Import path: `from lesia import errors`.

```
DirectoryTranslationError
├── ProjectConfigError
│   ├── LoadConfigError
│   └── WriteConfigError
└── ProjectError
    ├── InitProjectError
    │   ├── InvalidPathError
    │   └── ProjectAlreadyInitializedError
    ├── LoadProjectError
    │   └── NoConfigFoundError
    ├── SetLLMServiceError
    ├── SetTypstConfigError
    ├── SetLatexConfigError
    ├── SetSourceDirError
    │   ├── DirectoryDoesNotExistError
    │   ├── NotADirectoryError
    │   └── AnalyzeDirError
    ├── LangAlreadyInProjectError
    ├── AddLanguageError
    │   └── LangDirExistsError
    ├── AddCustomLanguageError
    ├── RemoveCustomLanguageError
    ├── NoSourceLanguageError
    ├── RemoveLanguageError
    │   └── TargetLanguageNotInProjectError
    ├── SyncFilesError
    │   └── NoTargetLanguagesError
    ├── CopyFileDirError
    ├── AddTranslatableFileError
    │   └── FileDoesNotExistError
    ├── GetTranslatableFilesError
    ├── TranslateFileError
    │   ├── UntranslatableFileError
    │   ├── TranslationProcessError
    │   └── ChunkTranslationFailed
    ├── CorrectTranslationError
    │   ├── CorrectingTranslationError
    │   ├── ChecksumNotFoundError
    │   └── NoSourceFileError
    ├── TranslationCacheSyncError
    └── TranslationCacheClearError
```

`ChunkTranslationFailed` carries the untranslated chunk text in its `.chunk` attribute and the original exception in `.original_exception`. Most error classes that wrap a cause expose it as `.original_exception` as well.
