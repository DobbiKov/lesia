# Lesia CLI

⚠️ This tool is in early development. Expect bugs and incomplete features.

## Table of Contents

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
    - [Language management](#language-management)
    - [Project configuration](#project-configuration)
    - [File management](#file-management)
    - [Translation](#translation)
        - [--use-reasoning-model](#--use-reasoning-model)
    - [Vocabulary configuration](#vocabulary-configuration)
    - [Cache management](#cache-management)
    - [LLM configuration](#llm-configuration)
        - [API key configuration](#api-key-configuration)
        - [Custom LLM services](#custom-llm-services)
    - [Typst configuration](#typst-configuration)
    - [LaTeX configuration](#latex-configuration)
    - [Migration](#migration)
- [Documentation](#documentation)

## Getting started

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
    lesia config source set <dir_name> <language>
    ```

    Example:
    ```
    lesia config source set analysis_notes french
    ```

4. Add target language(s):
    ```
    lesia config target set <dir_name> <language>
    ```

    Example:
    ```
    lesia config target set tgt/en english
    ```

#### Sync & Translate

5. Mark files for translation:
    ```
    lesia file add <path_to_file>
    ```

    Example:
    ```
    lesia file add analysis_notes/main.tex
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

There are two ways to supply the key:

**Option A — shell environment variable** (set once per terminal session):
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

**Option B — `.env` file** (persisted in the project, read automatically):

Create a file (e.g. `.env`) containing your keys:
```
LLM_API_KEY=<your_key>
LLM_REASONING_API_KEY=<your_reasoning_key>
```

Then tell lesia where to find it:
```sh
lesia llm env-file set .env
```

The path is saved in `.lesia/config.toml` and resolved automatically on every translation run. Shell environment variables always take precedence over the file, so you can still override individual keys in CI or on the command line without touching the file.

> **Security note:** treat your `.env` file like a password. Add it to `.gitignore` so it is never committed.

7. Translate specific files:
    ```
    lesia translate --to <language> <file_path> [<file_path> ...]
    ```

    Example:
    ```
    lesia translate --to english analysis_notes/main.tex
    ```

8. Translate all files:
    ```
    lesia translate --to <language> --all
    ```

    Example:
    ```
    lesia translate --to english --all
    ```

##### Vocabulary

A vocabulary file is a CSV glossary that guides the LLM to use your preferred terminology. Column headers must be language names (e.g. `French`, `English`); each row contains one term and its translations.

Example `vocab.csv`:
```csv
French,     English,    German
pomme,      apple,      Apfel
ordinateur, computer,   Computer
```

There are two ways to supply a vocabulary:

**Per-run flag** — pass it directly to the translate command:
```sh
lesia translate --to english --all --vocabulary vocab.csv
```

**Project default** — store it once in the config so it is used automatically on every translation run:
```sh
lesia vocab set vocab.csv
```

When both are provided the flag always takes precedence over the project default. See [Vocabulary configuration](#vocabulary-configuration) for the full command reference.

#### Correction

After automated translation, you will typically review the output and make manual edits directly in the translated files. The cache can be updated to reflect your corrections so that future translations reuse them instead of regenerating from the LLM.

9. Rebuild the translation cache from the files on disk:
    ```
    lesia cache sync
    ```

    Run this after manually editing translated files. The tool reads all source and target files, computes their checksums, and updates the correspondence cache accordingly.

See the [Translation Cache section](./tool-profound-explanation.md#the-translation-cache) of the profound explanation for a detailed description of the cache structure and how `cache sync` works.

### Getting started for developers

1. Ensure you have [uv](https://docs.astral.sh/uv/#__tabbed_1_1) installed.
2. Clone this repo:
    ```sh
    git clone https://github.com/DobbiKov/lesia
    ```
3. Enter the directory:
    ```sh
    cd lesia
    ```
4. Install the dependencies:
    ```sh
    uv sync
    ```
5. Install the CLI globally in editable mode:
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

Initializes a new translation project in the given directory (default: current directory). Creates a `.lesia/config.toml` file.

| Option | Default | Description |
|---|---|---|
| `--name` | `MyTranslationProject` | Project name |
| `--path` | `.` | Directory to initialize the project in |

#### `info`

```
lesia info
```

Displays a summary of the current project: name, root path, source language and directory, configured LLM, reasoning model, env file path (or "Not set" if none is configured), Typst function arg settings, LaTeX configuration, and all target languages with their directories.

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

### Language management

By default, lesia supports a fixed set of predefined languages (`French`, `English`, `German`, `Spanish`, `Ukrainian`, `Armenian`). Custom languages let you work with any language not in this list — you register them in the project config with a name and a directory suffix, and then use them everywhere a language name is accepted (`config source set`, `config target set`, `config target remove`, `translate --to`, `cache clear --lang`).

You can optionally assign a **short alias** to a custom language. Once registered, the short alias is interchangeable with the full name in every command.

Custom languages are stored in the project config and are therefore shared with anyone who clones the repository.

#### `lang add`

```
lesia lang add <name> <suffix> [--short <alias>]
```

Registers a new custom language in the project. `name` is the display name used in all other commands; `suffix` is the directory suffix used when creating target directories automatically (e.g. `_ae` produces `<project_name>_ae`). The optional `--short` flag registers a short alias that can be used in place of the full name in any subsequent command.

```
lesia lang add Catalan _ca
lesia lang add "American English" _ae --short AmEng
```

After the second command, both `"American English"` and `AmEng` are accepted anywhere a language name is expected. Short aliases are resolved case-insensitively.

**Errors:**
- The name matches a predefined language → error.
- The name is already registered as a custom language → error.
- The short alias is already used by another custom language → error.
- The short alias matches a predefined language name (case-insensitive) → error (would make the predefined language unreachable).
- The short alias matches an existing custom language's full name (case-insensitive) → error (would create an ambiguous alias).

#### `lang remove`

```
lesia lang remove <name>
lesia lang remove <alias>
```

Removes a custom language from the project config. Both the full name and the short alias (if one was registered) are accepted. Removing a language also removes its short alias.

```
lesia lang remove Catalan
lesia lang remove AmEng        # same as: lesia lang remove "American English"
```

**Errors:**
- The name matches a predefined language → error (predefined languages cannot be removed).
- The name/alias is not in the config → error.
- The language still has an associated target directory configured → error. Remove the target first with `lesia config target remove <name>`.

#### `lang list`

```
lesia lang list
```

Lists all languages, grouped by their assignment status:

- **Assigned to directories** — languages currently set as the source or a target, with their directory names.
- **Custom (registered, not assigned)** — custom languages that exist in the config but are not yet assigned to any directory.
- **Predefined (available, not assigned)** — built-in languages that are not currently in use.

```
Assigned to directories:
  source:  French  (analysis_notes_fr/)
  target:  English  (analysis_notes_en/)

Custom (registered, not assigned):
  Catalan  (_ca)
  American English  (_ae, short: AmEng)

Predefined (available, not assigned):
  German, Spanish, Ukrainian, Armenian
```

---

### Project configuration

These commands manage which directories are assigned as the source and targets for translation.

#### `config source set`

```
lesia config source set <dir_name> <language>
```

Sets (or changes) the source directory and its language. `dir_name` is relative to the project root. `language` can be a predefined language name (e.g. `French`), a custom language name, or a short alias previously registered with `lang add`.

```
lesia config source set analysis_notes_fr french
lesia config source set analysis_notes_ca catalan
lesia config source set analysis_notes_ae AmEng
```

#### `config source info`

```
lesia config source info
```

Shows the current source directory name and its language.

```
Source directory:
  language:  French
  directory: analysis_notes_fr/
```

#### `config target set`

```
lesia config target set <dir_name> <language>
```

Registers an existing directory as the target for a language. `language` can be a predefined language name, a custom language name, or a short alias previously registered with `lang add`.

```
lesia config target set analysis_notes_en english
lesia config target set analysis_notes_ca catalan
lesia config target set analysis_notes_ae AmEng
```

#### `config target remove`

```
lesia config target remove <language>
```

Removes a target language from the project configuration and deletes its directory from disk. Accepts predefined language names, custom language names, and short aliases.

```
lesia config target remove english
lesia config target remove catalan
lesia config target remove AmEng
```

#### `config target list`

```
lesia config target list
```

Lists all configured target languages and their directories.

```
Target directories:
  English  (analysis_notes_en/)
  German   (analysis_notes_de/)
```

---

### File management

#### `file add`

```
lesia file add <file_path> [<file_path> ...]
```

Marks one or more files in the source directory as translatable. Translatable files are processed by translation commands and skipped by `sync`.

```
lesia file add analysis_notes_fr/main.tex analysis_notes_fr/lec1.tex
```

#### `file remove`

```
lesia file remove <file_path> [<file_path> ...]
```

Marks one or more files as untranslatable (the reverse of `file add`). Untranslatable files are copied as-is by `sync` and ignored by translation commands.

```
lesia file remove analysis_notes_fr/figures/logo.pdf
```

#### `list`

```
lesia list
```

Lists all files currently marked as translatable in the source directory, with paths relative to the project root.

---

### Translation

Translation requires `LLM_API_KEY` to be set — either as a shell environment variable or via a `.env` file configured with `lesia llm env-file set`. See [API key configuration](#api-key-configuration) for details.

#### `translate`

```
lesia translate --to <language> [<path> ...] [--vocabulary <csv_path>] [--use-reasoning-model]
lesia translate --to <language> --all       [--vocabulary <csv_path>] [--use-reasoning-model]
```

Translates files to the specified target language. `--to` is required. You must provide either one or more file/directory paths, or the `--all` flag — not both.

`language` accepts predefined language names, custom language names, and short aliases registered with `lang add`.

**Translating specific files:**

Pass one or more file paths. Shell glob patterns are expanded by the shell before the CLI receives them.

```
lesia translate --to english analysis_notes_fr/main.tex
lesia translate --to english analysis_notes_fr/main.tex analysis_notes_fr/lec1.tex
lesia translate --to english analysis_notes_fr/*.tex
```

**Translating a directory:**

Pass a directory path to translate all translatable files under it.

```
lesia translate --to english analysis_notes_fr/
lesia translate --to english notes.tex analysis_notes_fr/appendix/
```

**Translating all files:**

Use `--all` to translate every file marked as translatable in the project.

```
lesia translate --to english --all
lesia translate --to catalan --all --vocabulary vocab.csv
lesia translate --to AmEng --all --use-reasoning-model
```

If `--vocabulary` is omitted and a default vocabulary file is configured via `lesia vocab set`, that file is used automatically. Passing `--vocabulary` always overrides the project default.

**Output:**

After each file is translated, a per-file statistics summary is printed. When more than one file is translated, a total summary is shown at the end:

```
  chunks from cache:        4
  chunks translated:        18
  chunks sent to reasoning: 2
  chunks failed:            1
--- Total statistics ---
  chunks from cache:        10
  chunks translated:        42
  chunks sent to reasoning: 3
  chunks failed:            1
```

`chunks sent to reasoning` is only shown when the reasoning model was used for at least one chunk. `chunks failed` is only shown when at least one chunk failed after all retries.

#### `--use-reasoning-model`

The `--use-reasoning-model` flag makes the translate command use the reasoning model configured via `lesia llm set-reasoning` **instead of** the regular model for the entire translation run — the regular model is not called at all.

This requires `LLM_REASONING_API_KEY` to be available — either as a shell environment variable or in the configured `.env` file — and falls back to `LLM_API_KEY` if the reasoning key is not set separately.

If no reasoning model has been configured, the flag falls back to the regular model.

```
lesia translate --to english --all --use-reasoning-model
lesia translate --to english analysis_notes_fr/main.tex --use-reasoning-model
```

---

### Vocabulary configuration

A vocabulary file is a CSV glossary that guides the LLM towards your preferred terminology. It is applied at the prompt level — each chunk is translated with the vocabulary list injected so the model can reference it.

**Precedence: `--vocabulary` flag > project default > no vocabulary.**

The `--vocabulary` flag passed to `translate` always wins. If no flag is given, the project default configured here is used. If neither is set, translation proceeds without a glossary.

**Expected CSV format:**

Column headers must exactly match the language names used in the project (predefined names like `French`, `English`, or custom names registered with `lang add`). Each row is one term entry.

```csv
French,     English,    German
pomme,      apple,      Apfel
ordinateur, computer,   Computer
```

#### `vocab set`

```
lesia vocab set <path>
```

Sets a default vocabulary CSV file for the project. The path is saved to `.lesia/config.toml` relative to the project root when possible, making the config portable.

```sh
lesia vocab set vocab.csv
lesia vocab set /shared/team-glossary.csv
```

If the file does not exist yet a warning is printed but the path is still saved — the file can be created later.

#### `vocab unset`

```
lesia vocab unset
```

Removes the default vocabulary file from the project config. After this, only an explicit `--vocabulary` flag supplies a glossary.

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
lesia cache clear --checksum <checksum> [--lang <language>]
```

Cleans up cache entries. Exactly one action flag is required: `--missing-chunks`, `--all`, or `--checksum`.

**Rules and constraints:**
- `--lang`, `--file`, and `--keyword` only work with `--all` (except `--lang`, which also works with `--checksum`).
- `--file` cannot be combined with `--checksum`.
- `--keyword` cannot be combined with `--missing-chunks` or `--checksum`.
- Language names are case-insensitive and accept predefined language names, custom language names, and short aliases.
- `--file` expects a project file path (the same path used with `translate`).

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

**What `--checksum <checksum>` does:**

The behaviour depends on whether the checksum belongs to a source or target chunk (determined by looking it up in the correspondence CSV):

- **Source checksum, no `--lang`**: deletes the source chunk file and all associated target chunk files for that row, then removes the row from the CSV entirely.
- **Source checksum, `--lang <language>`**: deletes only the target chunk file for the specified language that is associated with the given source chunk. The source chunk and all other target chunks are preserved; the row is kept with that language's field cleared.
- **Target checksum** (no `--lang`, or with `--lang`): deletes just the specific target chunk file and clears its field in the CSV. The source chunk and any other target chunks are unaffected.

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
lesia cache clear --checksum abc123def456
lesia cache clear --checksum abc123def456 --lang French
```

---

### LLM configuration

The default LLM is `google` / `gemini-2.0-flash`. Use `lesia llm list` to see all available services.

#### `llm set`

```
lesia llm set <service> <model>
```

Sets the primary LLM service and model used for translation. The setting is saved to the project config.

```
lesia llm set google gemini-2.0-flash
lesia llm set openai gpt-4o
lesia llm set anthropic claude-sonnet-4-5-20251001
```

#### `llm set-reasoning`

```
lesia llm set-reasoning <service> <model>
```

Sets an optional reasoning model. By default it is used alongside the regular model for more challenging translation decisions. Pass `--use-reasoning-model` to `translate` to use it as the sole model instead.

```
lesia llm set-reasoning google gemini-2.0-flash-thinking-exp
```

Reasoning models require `LLM_REASONING_API_KEY` to be available — either as a shell environment variable or in the configured `.env` file — and fall back to `LLM_API_KEY` if not set separately.

#### `llm list`

```
lesia llm list
```

Lists all available LLM service names (built-in and custom) that can be used with `llm set` and `llm set-reasoning`.

#### `llm set-xml-retries`

```
lesia llm set-xml-retries <n>
```

Sets how many times the standard model is retried on XML parse errors before the reasoning model is used as a fallback for that chunk. `0` means the reasoning model is always used (never the standard model). Requires a reasoning model to be configured via `llm set-reasoning`.

```
lesia llm set-xml-retries 3
lesia llm set-xml-retries 0
```

---

### API key configuration

API keys can be supplied in two ways. Shell environment variables always take precedence; the `.env` file is the fallback.

| Variable | Used for |
|---|---|
| `LLM_API_KEY` | Primary key for the standard LLM service |
| `LLM_REASONING_API_KEY` | Key for the reasoning model service; falls back to `LLM_API_KEY` if not set |

#### `llm env-file set`

```
lesia llm env-file set <path>
```

Saves the path to a `.env` file in the project config. On every translation run lesia reads `LLM_API_KEY` and `LLM_REASONING_API_KEY` from this file when they are not already set in the shell environment.

The path can be absolute or relative to the current directory; it is stored relative to the project root when possible, making the config portable across machines (as long as the file exists at the same relative location).

```sh
lesia llm env-file set .env
lesia llm env-file set /home/user/secrets/lesia.env
```

If the file does not exist yet a warning is printed but the path is still saved — the file can be created later.

**Expected file format:**

```
# Lines starting with # are ignored, as are blank lines.
LLM_API_KEY=your_key_here
LLM_REASONING_API_KEY=your_reasoning_key_here
```

Values may optionally be surrounded by single or double quotes. Only `LLM_API_KEY` and `LLM_REASONING_API_KEY` are read; all other lines are ignored.

> **Security note:** add your `.env` file to `.gitignore` so keys are never committed to version control.

#### `llm env-file unset`

```
lesia llm env-file unset
```

Removes the configured `.env` file path from the project config. After this command, only shell environment variables are used for API key resolution.

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
        # The name used in `llm set` and `llm set-reasoning`.
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

Once the file is saved, run `lesia llm list` to confirm the service appears, then use it like any built-in service:

```
lesia llm set my-service my-model-name
```

The services directory is part of the project (inside `.lesia/`), so committing it makes the custom service available to everyone who clones the repository.

#### Name conflicts

When a project is loaded, all custom service files are inspected before any of them are registered. Two conflict rules apply:

- **Custom service shadows a built-in** — the custom service is still loaded and replaces the built-in, but a warning is printed to stderr. This is allowed because overriding a built-in with a drop-in replacement can be intentional (e.g. routing calls through a local proxy).
- **Two custom services share the same name** — loading is aborted with an error and the project command exits with a non-zero code. Remove or rename one of the conflicting files before running any `lesia` command.

```
WARNING - Custom service 'my_google.py' defines name 'google' which overshadows a built-in service. Is this intended?
```

```
Error loading project: Custom service 'b_service.py' defines name 'my-service'
which conflicts with another custom service already loaded.
Remove or rename one of the conflicting service files.
```

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

#### `typst set-func-args`

```
lesia typst set-func-args <function_name> <arg_name> [<arg_name> ...]
```

Registers the listed argument names of a Typst function as translatable. Calling this again for the same function name replaces the previous setting.

```
lesia typst set-func-args figure caption
lesia typst set-func-args ex info caption
```

#### `typst unset-func-args`

```
lesia typst unset-func-args <function_name>
```

Removes the translatable-arg configuration for a function.

```
lesia typst unset-func-args ex
```

---

### LaTeX configuration

The LaTeX parser has hardcoded defaults for common environments and commands. These commands let you extend that behaviour on a per-project basis. All settings are stored in `.lesia/config.toml` and applied automatically before every translation run.

> **Two layers of control:** these CLI commands are a thin wrapper around the library API. The same settings can be set programmatically via `Project` methods — see the [LaTeX configuration section](./main.md#latex-configuration) of the library reference.

#### Understanding how unknown commands work

For **commands that pylatexenc knows** (standard LaTeX: `\section`, `\textbf`, etc.), arguments are parsed into `node.nodeargs` and every setting below works as expected.

For **custom or unknown commands**, pylatexenc does not parse the `{…}` groups as arguments — they become sibling nodes walked as text. To get full control over a custom command, register its argument structure first with `latex cmd-spec set`, then use the other commands to configure translatability.

#### `latex placeholder-env add`

```
lesia latex placeholder-env add <env_name>
```

Mark an environment as non-translatable. The entire `\begin{env}…\end{env}` block becomes an opaque placeholder — its content is never sent to the LLM.

```
lesia latex placeholder-env add algorithm
lesia latex placeholder-env add myverbatim
```

#### `latex placeholder-env remove`

```
lesia latex placeholder-env remove <env_name>
```

Remove an environment from the non-translatable list.

```
lesia latex placeholder-env remove myverbatim
```

#### `latex math-env add`

```
lesia latex math-env add <env_name>
```

Mark an environment as a math environment. Its body is walked in math mode: only `\text{…}` and similar macros (known to pylatexenc) expose translatable content; everything else is a placeholder.

```
lesia latex math-env add myequation
lesia latex math-env add myalign
```

#### `latex math-env remove`

```
lesia latex math-env remove <env_name>
```

Remove an environment from the math list.

```
lesia latex math-env remove myequation
```

#### `latex placeholder-cmd add`

```
lesia latex placeholder-cmd add <cmd_name>
```

Mark a command as non-translatable. For standard commands (known to pylatexenc), the command together with all its arguments becomes a single placeholder. For custom commands, register the argument structure first with `latex cmd-spec set`.

```
# Suppress a standard command
lesia latex placeholder-cmd add myref

# Suppress a custom command including its arguments
lesia latex cmd-spec set myfig --mandatory 2
lesia latex placeholder-cmd add myfig
```

#### `latex placeholder-cmd remove`

```
lesia latex placeholder-cmd remove <cmd_name>
```

Remove a command from the non-translatable list.

```
lesia latex placeholder-cmd remove myref
```

#### `latex cmd-spec set`

```
lesia latex cmd-spec set <cmd_name> --mandatory <N> [--optional <M>]
```

Register the argument structure of a custom command with pylatexenc, so its arguments appear in `node.nodeargs` and can be controlled by `latex cmd-args set` or `latex placeholder-cmd add`.

| Option | Short | Description |
|---|---|---|
| `--mandatory` | `-m` | Number of mandatory `{…}` arguments |
| `--optional` | `-o` | Number of optional `[…]` arguments (default `0`) |

Optional arguments are assumed to come **before** mandatory ones.

```
# \myfig{label}{caption}
lesia latex cmd-spec set myfig --mandatory 2

# \mybox[label]{title}{body}
lesia latex cmd-spec set mybox --mandatory 2 --optional 1
```

#### `latex cmd-spec unset`

```
lesia latex cmd-spec unset <cmd_name>
```

Remove the custom argument structure definition for a command.

```
lesia latex cmd-spec unset myfig
```

#### `latex cmd-args set`

```
lesia latex cmd-args set <cmd_name> [--mandatory <i> [<i> ...]] [--optional <j> [<j> ...]]
```

Specify which arguments of a command are translatable using **1-based indices**, counting mandatory `{…}` and optional `[…]` arguments separately. Arguments not listed become placeholders.

> Requires the command's argument structure to be known to pylatexenc. For custom commands, run `latex cmd-spec set` first.

| Option | Short | Description |
|---|---|---|
| `--mandatory` | `-m` | 1-based indices of `{…}` args that are translatable |
| `--optional` | `-o` | 1-based indices of `[…]` args that are translatable |

At least one option is required.

```
# \myfig{label}{caption} — translate only the caption (arg 2)
lesia latex cmd-spec set myfig --mandatory 2
lesia latex cmd-args set myfig --mandatory 2

# \mybox[label]{title}{body} — translate only the body (mandatory arg 2)
lesia latex cmd-spec set mybox --mandatory 2 --optional 1
lesia latex cmd-args set mybox --mandatory 2

# \section[short title]{full title} — translate both
lesia latex cmd-args set section --mandatory 1 --optional 1
```

#### `latex cmd-args unset`

```
lesia latex cmd-args unset <cmd_name>
```

Remove the per-argument translation configuration for a command (reverts to default: all arguments translatable).

```
lesia latex cmd-args unset myfig
```

---

## Migration

### `lesia migrate toml`

```sh
lesia migrate toml
```

Migrates an existing project from the legacy `config.json` format to `config.toml`. Reads `.lesia/config.json`, writes `.lesia/config.toml`, and deletes the JSON file. Run this once per project after upgrading from an older version of lesia.

```sh
lesia migrate toml
# Migrated config.json to config.toml in /path/to/project/.lesia
```

---

## Documentation

- Library API reference: [docs/main.md](./main.md)
- Architecture and algorithms: [docs/tool-profound-explanation.md](./tool-profound-explanation.md)
- Typst parsing and implementation: [docs/typst_parsing_analysis.md](./typst_parsing_analysis.md)
