# Translate dir CLI

This is a CLI tool that aims to automate the translation of large documents written using markup languages such as:
- LaTeX
- Markdown
- Jupyter
- MyST
- Typst

This CLI tool is an implementation of [this library](https://github.com/DobbiKov/lesia).

Learn more about the project: [main repository](https://github.com/DobbiKov/sci-trans-git).

Extended abstract about the project: [link](https://dobbikov.github.io/sci-trans-git/jdse-paper.pdf)

⚠️ This tool is in early development. Expect bugs and incomplete features.

## Table of Contents

- [Why lesia?](#why-lesia)
- [Features](#features)
- [Citation](#citation)
- [Getting started](#getting-started)
    - [Installation](#installation)
    - [First steps](#first-steps)
        - [Project setup](#project-setup)
        - [Sync & Translate](#sync--translate)
        - [Correction](#correction)
- [Getting started for developers](#getting-started-for-developers)
- [Command reference](#command-reference)
    - [Global options](#global-options)
    - [Project management](#project-management)
    - [Custom languages](#custom-languages)
    - [File management](#file-management)
    - [Translation](#translation)
        - [--use-reasoning-model](#--use-reasoning-model)
    - [Cache management](#cache-management)
    - [LLM configuration](#llm-configuration)
        - [Custom LLM services](#custom-llm-services)
    - [Typst configuration](#typst-configuration)
- [Documentation](#documentation)
- [Contributing](#contributing)

## Why lesia?

Manually translating large projects with scientific notation, Markdown, or
LaTeX is slow and error-prone. This library automates this process while
preserving file structure and formatting, so you can focus on refining the
content rather than wrestling with markup.

## Features

- [x] **Project creation** – Set up a new translation workspace in seconds
- [x] **Source & target language management** – Easily define languages for translation
- [x] **File syncing** – Synchronize translatable and non-translatable files across languages
- [x] **Translation cache** – Keep track of all translated content and corrections
- [x] **AI-based translations** – Leverage Google Gemini and other LLM services for high-quality translations
- [x] **Vocabulary support** – Fine-tune translations with custom glossaries
- [x] **Cache-aware corrections** – Preserve manual fixes by syncing the cache from files on disk
- [x] **Typst support** – Full support for Typst documents including configurable function argument translation

## Citation

If you use this software in your research or for writing, please cite it as follows:

```bib
@software{korotenko-sci-trans-git,
    author = {Yehor Korotenko},
    title = {sci-trans-git},
    year = {2025},
    publisher = {GitHub},
    version = {0.2.0-alpha},
    url = {https://github.com/DobbiKov/sci-trans-git},
    doi = {10.5281/zenodo.15775111}
}
```

## Getting started

For developers: follow [here](#getting-started-for-developers)

### Installation

Requirements:
- Python 3.11+
- [uv](https://docs.astral.sh/uv/#__tabbed_1_1) (dependency manager)

1. Ensure you have [uv](https://docs.astral.sh/uv/#__tabbed_1_1) installed.
4. Install CLI
    ```sh
    uv tool install lesia
    ```
5. Run the CLI:
    ```
    lesia --help
    ```

### First steps

This section is a guide to start using this tool as quickly as possible. The profound
explanation can be found [here](https://github.com/DobbiKov/lesia/blob/master/docs/tool-profound-explanation.md).
It is strongly recommended to read it to understand how the tool manages files and what
the overall project structure looks like.

#### Project Setup

1. Create a root directory for your translation project and place your writing project inside it.

2. Initialize the translation project:
    ```
    lesia init [--name <my_project>]
    ```

3. Set the source directory and its language:
    ```
    lesia set-source <dir_name> <language>
    ```

    Example:
    ```
    lesia set-source analysis_notes french
    ```

4. Add target language(s):
    ```
    lesia set-target <dir_name> <language>
    ```

    Example:
    ```
    lesia set-target tgt/en english
    ```

#### Sync & Translate

5. Mark files for translation:
    ```
    lesia add <path_to_file>
    ```

    Example:
    ```
    lesia add analysis_notes/main.tex
    ```

    To see all translatable files: `lesia list`

6. Sync files between source and target directories:
    ```
    lesia sync
    ```

For translation, the `LLM_API_KEY` of the service you use is required for
certain providers.

Follow these instructions to obtain a key for `gemini` models from Google:
1. Visit [this link](https://aistudio.google.com/app/apikey)
2.
    - If it is your first time getting a Gemini API key:
        1. Click on `Get API Key`, then accept the Terms of Service.
        2. Click on `Create API Key`
        3. Copy the generated key from the popup
    - If you already have an API key:
        1. Click on `Create API Key`
        2. Create a new project or choose an existing one
        3. Click on `Create API KEY in existing project`
        4. Copy the generated key from the popup

Set the key as an environment variable:
- On Linux/macOS:
    ```sh
    export LLM_API_KEY=<your_key>
    ```
- On Windows (cmd):
    ```sh
    set LLM_API_KEY=<your_key>
    ```
- On Windows (PowerShell):
    ```sh
    $env:LLM_API_KEY="<your_key>"
    ```

7. Translate one file:
    ```
    lesia translate file <file_path> <target_language>
    ```

    Example:
    ```
    lesia translate file analysis_notes/main.tex english
    ```

8. Translate all files:
    ```
    lesia translate all <target_language>
    ```

    Example:
    ```
    lesia translate all english
    ```

##### Vocabulary

You can use the `--vocabulary` flag with any translation command to provide a custom translation vocabulary. This flag expects the path to a CSV file containing your glossary.

The CSV file should be structured as a table where:

* Each column header is a language name (matching the project's configured language names, e.g. `English`, `French`).
* Each row lists a term and its translations.

Example `vocab.csv`:
```csv
English,    French,     German
apple,      pomme,      Apfel
computer,   ordinateur, Computer
```

```sh
lesia translate all english --vocabulary vocab.csv
```

This helps the translation tool choose more accurate terms and maintain consistency across your project.

#### Correction

After automated translation, you will typically review the output and make manual edits directly in the translated files. The cache can be updated to reflect your corrections so that future translations reuse them instead of regenerating from the LLM.

9. Rebuild the translation cache from the files on disk:
    ```
    lesia cache sync
    ```

    Run this after manually editing translated files. The tool reads all source and target files, computes their checksums, and updates the correspondence cache accordingly.

See the [Translation Cache section](./tool-profound-explanation.md#the-translation-cache) of the profound explanation for a detailed description of the cache structure and how `cache sync` works.

---

## Getting started for developers

1. Ensure you have [uv](https://docs.astral.sh/uv/#__tabbed_1_1) installed.
2. Clone the library first; the installation guide is [here](https://github.com/DobbiKov/lesia?tab=readme-ov-file#installation).
3. Get the path to the library directory on your local machine (e.g. `realpath <your_dir>` on macOS).
4. Clone this repo:
    ```sh
    git clone https://github.com/DobbiKov/lesia
    ```
5. Enter the directory:
    ```sh
    cd lesia
    ```
6. Remove the current library dependency:
    ```sh
    uv remove lesia
    ```
7. Add the local one:
    ```sh
    uv add --editable <path_to_local_lib_dir>
    ```
8. Install the dependencies:
    ```sh
    uv sync
    ```
9. Install the CLI globally in editable mode:
    ```sh
    uv tool install -e .
    ```

---

## Command reference

All commands are run as `lesia <command> [options]`. Commands that operate on a project search upward from the current directory for a `.lesia/` folder (like `git` searches for `.git/`).

### Global options

| Option | Short | Description |
|---|---|---|
| `--verbose` | `-v` | Show diagnostic (TRACE-level) logs on stderr |
| `--help` | | Show help for a command |

### Project management

#### `init`

```
lesia init [--name <name>] [--path <path>]
```

Initializes a new translation project in the given directory (default: current directory). Creates a `.lesia/config.json` file.

| Option | Default | Description |
|---|---|---|
| `--name` | `MyTranslationProject` | Project name |
| `--path` | `.` | Directory to initialize the project in |

#### `set-source`

```
lesia set-source <dir_name> <language>
```

Sets (or changes) the source directory and its language. `dir_name` is relative to the project root. `language` can be a predefined language name (e.g. `French`), a custom language name, or a short alias previously registered with `add-lang`.

```
lesia set-source analysis_notes_fr french
lesia set-source analysis_notes_ca catalan
lesia set-source analysis_notes_ae AmEng
```

#### `set-target`

```
lesia set-target <dir_name> <language>
```

Registers an existing directory as the target for a language. `language` can be a predefined language name, a custom language name, or a short alias previously registered with `add-lang`.

```
lesia set-target analysis_notes_en english
lesia set-target analysis_notes_ca catalan
lesia set-target analysis_notes_ae AmEng
```

#### `remove-target`

```
lesia remove-target <language>
```

Removes a target language from the project configuration and deletes its directory from disk. Accepts predefined language names, custom language names, and short aliases.

```
lesia remove-target english
lesia remove-target catalan
lesia remove-target AmEng
```

#### `info`

```
lesia info
```

Displays a summary of the current project: name, root path, source language and directory, configured LLM, reasoning model, Typst function arg settings, and all target languages with their directories.

#### `sync`

```
lesia sync
```

Copies all untranslatable files from the source directory to every target directory, mirroring the subdirectory structure. Run this before building the translated project (e.g. with LaTeX) to ensure all assets are present.

#### `status`

```
lesia status [--files]
```

Shows translation and proofreading progress for every configured target language.

For each language the output includes:
- how many chunks have been translated out of the total (`translated/total`)
- how many of those translated chunks have been proofread (i.e. do **not** carry the `needs_review` tag) out of the total translated (`proofread/translated`)

A chunk is marked `needs_review` automatically when it is translated by the LLM for the first time. The tag is cleared when you manually edit the chunk and run `lesia cache sync`, which rebuilds the cache from the corrected files on disk.

| Option | Description |
|---|---|
| `--files` | Break down the statistics per source file in addition to the per-language totals |

**Example output (no flag):**
```
Source language: French
  English: 42/42 chunks translated (100%), 0 untranslated | 38/42 proofread (90%), 4 need review
  German: 30/42 chunks translated (71%), 12 untranslated | 25/30 proofread (83%), 5 need review
```

**Example output (with `--files`):**
```
Source language: French
  English: 42/42 chunks translated (100%), 0 untranslated | 38/42 proofread (90%), 4 need review
    main.tex: 20/20 (100%), 0 untranslated | 18/20 proofread (90%), 2 need review
    intro.tex: 22/22 (100%), 0 untranslated | 20/22 proofread (90%), 2 need review
```

Lines are printed in green when all chunks are translated **and** none need review, and yellow otherwise.

---

### Custom languages

By default, lesia supports a fixed set of predefined languages (`French`, `English`, `German`, `Spanish`, `Ukrainian`, `Armenian`). Custom languages let you work with any language not in this list — you register them in the project config with a name and a directory suffix, and then use them everywhere a language name is accepted (`set-source`, `set-target`, `remove-target`, `translate file`, `translate all`, `cache clear --lang`).

You can optionally assign a **short alias** to a custom language. Once registered, the short alias is interchangeable with the full name in every command.

Custom languages are stored in the project config and are therefore shared with anyone who clones the repository.

#### `add-lang`

```
lesia add-lang <name> <suffix> [--short <alias>]
```

Registers a new custom language in the project. `name` is the display name used in all other commands; `suffix` is the directory suffix used when creating target directories automatically (e.g. `_ae` produces `<project_name>_ae`). The optional `--short` flag registers a short alias that can be used in place of the full name in any subsequent command.

```
lesia add-lang Catalan _ca
lesia add-lang "American English" _ae --short AmEng
```

After the second command, both `"American English"` and `AmEng` are accepted anywhere a language name is expected.

**Errors:**
- The name matches a predefined language → error.
- The name is already registered as a custom language → error.
- The short alias is already used by another custom language → error.

#### `remove-lang`

```
lesia remove-lang <name>
lesia remove-lang <alias>
```

Removes a custom language from the project config. Both the full name and the short alias (if one was registered) are accepted. Removing a language also removes its short alias.

```
lesia remove-lang Catalan
lesia remove-lang AmEng        # same as: lesia remove-lang "American English"
```

**Errors:**
- The name matches a predefined language → error (predefined languages cannot be removed).
- The name/alias is not in the config → error.
- The language still has an associated target directory configured → error. Remove the target first with `remove-target <name>`.

---

### File management

#### `add`

```
lesia add <file_path> [<file_path> ...]
```

Marks one or more files in the source directory as translatable. Translatable files are processed by translation commands and skipped by `sync`.

```
lesia add analysis_notes_fr/main.tex analysis_notes_fr/lec1.tex
```

#### `remove`

```
lesia remove <file_path> [<file_path> ...]
```

Marks one or more files as untranslatable (the reverse of `add`). Untranslatable files are copied as-is by `sync` and ignored by translation commands.

```
lesia remove analysis_notes_fr/figures/logo.pdf
```

#### `list`

```
lesia list
```

Lists all files currently marked as translatable in the source directory, with paths relative to the project root.

---

### Translation

Translation commands require `LLM_API_KEY` to be set in the environment.

#### `translate file`

```
lesia translate file <file_path> <language> [--vocabulary <csv_path>] [--use-reasoning-model]
```

Translates a single file to the specified target language. The file must be marked as translatable. `language` accepts predefined language names, custom language names, and short aliases.

```
lesia translate file analysis_notes_fr/main.tex english
lesia translate file analysis_notes_fr/main.tex catalan --vocabulary vocab.csv
lesia translate file analysis_notes_fr/main.tex AmEng --use-reasoning-model
```

#### `translate all`

```
lesia translate all <language> [--vocabulary <csv_path>] [--use-reasoning-model]
```

Translates all translatable files to the specified language. `language` accepts predefined language names, custom language names, and short aliases.

```
lesia translate all english
lesia translate all catalan --vocabulary vocab.csv
lesia translate all AmEng --use-reasoning-model
```

#### `--use-reasoning-model`

Both `translate file` and `translate all` accept the `--use-reasoning-model` flag. When passed, the reasoning model configured via `set-reasoning-model` is used **instead of** the regular model for the entire translation run — the regular model is not called at all.

This requires `LLM_REASONING_API_KEY` to be set (falls back to `LLM_API_KEY` if the reasoning key is not set separately).

If no reasoning model has been configured, the flag falls back to the regular model.

```
lesia translate all english --use-reasoning-model
lesia translate file analysis_notes_fr/main.tex english --use-reasoning-model
```

---

### Cache management

The translation cache stores source-to-translated-text pairs on disk to avoid re-calling the LLM for content that has already been translated. See the [Translation Cache section](./tool-profound-explanation.md#the-translation-cache) of the profound explanation for details on the on-disk structure and algorithms.

#### `cache sync`

```
lesia cache sync
```

Rebuilds the translation cache from on-disk source and target files. Run this after manually editing translated files to ensure the cache matches the current contents.

#### `cache clear`

```
lesia cache clear --missing-chunks
lesia cache clear --all [--lang <language>] [--file <path>] [--keyword <string>]
```

Cleans up cache entries. Exactly one action flag is required: `--missing-chunks` or `--all`.

**Rules and constraints:**
- `--lang`, `--file`, and `--keyword` only work with `--all`.
- `--keyword` cannot be combined with `--missing-chunks`.
- Language names are case-insensitive and accept predefined language names, custom language names, and short aliases.
- `--file` expects a project file path (the same path used with `translate file`).

**What `--missing-chunks` does:**
- Removes correspondence rows whose source chunk file is missing.
- Removes correspondence rows where no target chunk files exist.
- Clears target checksum fields for missing target chunk files (keeps the row if at least one target exists).
- Deletes orphaned chunk files not referenced by any remaining correspondence row.
- If the correspondence CSV is missing, all cache chunk files are deleted.

**What `--all` does (no keyword):**
- With `--lang`: clears only that language's checksum fields and deletes its chunk files in scope.
- With `--file`: limits deletion to that file's path hash across all languages (or only `--lang` if set).
- With no `--lang`/`--file`: deletes all cache chunk files and removes all correspondence rows.
- Rows are removed only when all language fields are empty; otherwise the row is kept with cleared fields.

**What `--all --keyword <string>` does:**
- Deletes chunk files whose contents contain the keyword (literal substring, case-sensitive).
- Clears the matching checksum fields in the correspondence CSV.
- Rows are removed only if all language fields are cleared by the keyword deletion.
- If the keyword matches nothing, the cache is unchanged.

**Examples:**
```
lesia cache clear --missing-chunks
lesia cache clear --all --lang English
lesia cache clear --all --lang AmEng
lesia cache clear --all --file analysis_notes_fr/doc.md
lesia cache clear --all --lang French --file analysis_notes_fr/doc.md
lesia cache clear --all
lesia cache clear --all --keyword glossary
lesia cache clear --all --file analysis_notes_fr/doc.md --keyword glossary
```

---

### LLM configuration

The default LLM is `google` / `gemini-2.0-flash`. Use `list-llms` to see all available services.

#### `set-llm`

```
lesia set-llm <service> <model>
```

Sets the primary LLM service and model used for translation. The setting is saved to the project config.

```
lesia set-llm google gemini-2.0-flash
lesia set-llm openai gpt-4o
lesia set-llm anthropic claude-sonnet-4-5-20251001
```

#### `set-reasoning-model`

```
lesia set-reasoning-model <service> <model>
```

Sets an optional reasoning model. By default it is used alongside the regular model for more challenging translation decisions. Pass `--use-reasoning-model` to `translate file` or `translate all` to use it as the sole model instead.

```
lesia set-reasoning-model google gemini-2.0-flash-thinking-exp
```

Reasoning models require the `LLM_REASONING_API_KEY` environment variable (falls back to `LLM_API_KEY` if not set separately).

#### `list-llms`

```
lesia list-llms
```

Lists all available LLM service names (built-in and custom) that can be used with `set-llm` and `set-reasoning-model`.

---

### Custom LLM services

You can add your own LLM service by placing a Python file in `.lesia/services/`. Every `.py` file in that directory (except the template) is loaded automatically whenever a project command runs.

After `lesia init`, a ready-to-copy template is placed at:

```
.lesia/services/custom_service_example.py
```

You can also create a new file from scratch. The only requirement is that it contains a class that inherits from `BaseService` and implements four methods:

```python
from unified_model_caller import BaseService


class MyService(BaseService):
    def get_name(self) -> str:
        # The name used in `set-llm` and `set-reasoning-model`.
        return "my-service"

    def requires_token(self) -> bool:
        # Return True if the service needs an API key.
        # The key is read from the LLM_API_KEY environment variable by the caller.
        return True

    def service_cooldown(self) -> int:
        # Milliseconds to wait between calls to respect rate limits. Use 0 for no delay.
        return 0

    def call(self, model: str, prompt: str) -> str:
        # Call the remote API and return the plain-text response.
        raise NotImplementedError
```

Once the file is saved, run `lesia list-llms` to confirm the service appears, then use it like any built-in service:

```
lesia set-llm my-service my-model-name
```

The services directory is part of the project (inside `.lesia/`), so committing it makes the custom service available to everyone who clones the repository.

#### External dependencies

If your custom service requires a third-party package (e.g. `boto3`, `mistralai`), you need to inject it into the `lesia` tool environment:

```sh
uv tool inject lesia <package-name>
```

Example:

```sh
uv tool inject lesia boto3
```

If the package is not installed, the service file will fail to load and a warning will be printed — no other commands are affected.

---

### Typst configuration

By default, string arguments of Typst functions (e.g. captions, labels, custom function parameters) are not translated. These commands let you mark specific argument names of specific functions as translatable.

See the [Current Implementation section](./typst_parsing_analysis.md#current-implementation) of the Typst parsing analysis for a detailed explanation of how Typst translation works internally.

#### `set-typst-func-args`

```
lesia set-typst-func-args <function_name> <arg_name> [<arg_name> ...]
```

Registers the listed argument names of a Typst function as translatable. Calling this again for the same function name replaces the previous setting.

```
lesia set-typst-func-args figure caption
lesia set-typst-func-args ex info caption
```

#### `unset-typst-func-args`

```
lesia unset-typst-func-args <function_name>
```

Removes the translatable-arg configuration for a function.

```
lesia unset-typst-func-args ex
```

---

## Documentation

- Library API reference: [docs/main.md](./main.md)
- Architecture and algorithms: [docs/tool-profound-explanation.md](./tool-profound-explanation.md)
- Typst parsing and implementation: [docs/typst_parsing_analysis.md](./typst_parsing_analysis.md)

## Contributing

Suggestions and pull requests are welcome. Visit the issues pages as well as the project's [main page](https://github.com/DobbiKov/sci-trans-git) and the [shared document](https://codimd.math.cnrs.fr/sUW9PQ1tTLWcR98UjLHLpw) to know the current direction and plans.
