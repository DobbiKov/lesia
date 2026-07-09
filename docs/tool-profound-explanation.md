# The profound explanation of the tool

This page contains an overview and explanation of the architecture, algorithms
and ideology of the library, and explains its features.

## Table of Contents

- [The profound explanation of the tool](#the-profound-explanation-of-the-tool)
  - [Table of Contents](#table-of-contents)
  - [Main Unit: Project](#main-unit-project)
  - [Project initialization and required settings](#project-initialization-and-required-settings)
    - [Important notes](#important-notes)
  - [Two types of files](#two-types-of-files)
  - [Syncing vs Translating](#syncing-vs-translating)
    - [Syncing](#syncing)
    - [Translating](#translating)
    - [Difference](#difference)
  - [Translation algorithm](#translation-algorithm)
  - [Correcting](#correcting)
  - [Translation Cache](#the-translation-cache)
    - [Structure](#structure)
    - [Checksum-to-text cache](#checksum-to-text-cache)
    - [Correspondence cache](#correspondence-cache)
    - [Cache sync](#cache-sync)
    - [Cache maintenance](#cache-maintenance)

## Main Unit: Project

The main unit of the library is called a **translation project**. A translation
project contains all the information about your file structure, languages and
translation cache.

Translation projects behaves similarly to, e.g., `git` projects. There is always
a root directory that you must be in, where you'll initialize the translation
project. The root directory contains the project configuration in a dedicated
_dot_ directory, a translation cache, and the files that are "tracked": in
our case the files that are synced and translated across the languages.

> Note: don't confuse your writing project, for example: LaTeX project and
> translation project. Your "writing project's" root directory must be placed in
> the root directory of the translation project.

For example: let's assume that we have a French LaTeX project in a directory
having the following structure:
```
analysis_notes_fr/
├── main.tex
├── lec1.tex
├── authors.tex
├── figues/
│   └── ...
└── bib/
    └── bib.tex
```

Creating a translation project requires a dedicated directory holding
`analysis_notes_fr` as subdirectory. For example:

```
analysis_notes/
└── analysis_notes_fr/
    ├── main.tex
    ├── lec1.tex
    ├── authors.tex
    ├── figues/
    │   └── ...
    └── bib/
        └── bib.tex
```

Once initialized, the translation project has the following structure:
```
analysis_notes/
├── analysis_notes_fr/
│   ├── main.tex
│   ├── lec1.tex
│   ├── authors.tex
│   ├── figues/
│   │   └── ...
│   └── bib/
│       └── bib.tex
├── .lesia/
    ├── config.toml
    └── translate_cache/
        └── ...
```

And after translation into Ukrainian it becomes:

```
analysis_notes/
├── analysis_notes_fr/
│   ├── main.tex
│   ├── lec1.tex
│   ├── authors.tex
│   ├── figues/
│   │   └── ...
│   └── bib/
│       └── bib.tex
├── analysis_notes_ua/
│   ├── main.tex
│   ├── lec1.tex
│   ├── authors.tex
│   ├── figues/
│   │   └── ...
│   └── bib/
│       └── bib.tex
├── .lesia/
    ├── config.toml
    └── translate_cache/
        └── ...
```

## Project initialization and required settings

When you initialize a project, a `.lesia` directory is created that
stores a `config.toml` configuration file. This file will store:

- the project's name
- the source and target languages
- the directories that correspond to the source and target languages
- the files that must be translated
- additional settings

You must then set a **source directory** together with its language. Only files
within that source directory can be translated. You must then set at least one
**target directory** together with its language. The target directory will be
created if needed and will eventually hold the translation of the source
directory.

### Important notes

- The source directory can be reset, i.e you can set another directory as a
  source one using the same `lesia config source set` command.
- The target languages can be removed using `lesia config target remove` command (in CLI), or
  `remove_target_language` method in the library.

## Translatable and untranslatable files.

You can mark any file in the source directory as _translatable_; a translatable
file is ignored by the `sync` command, and translated by the translation
commands.

All other files in the source directory are considered as _untranslatable_. An
untranslatable file is copied over as is by the `sync` command and ignored by
the translation commands. Typical untranslatable files are assets such as media
or bibliography files.

With this, once translated and synced, the target directory should be ready for
use (e.g. for building with latex).

## Translation algorithm

The algorithm reads a file, divides it into _chunks_ (sometimes called _cells_
here) and pass them to a Large Language Model (by default the _gemini_ models
from google) together with a big prompt that asks the model to translate a chunk
and explains how to preserve the structure, syntax and layout. Then the
translation is extracted, added as a translation pair with the source of the
chunk in the translation cache (see below) and written to the output file.

After the translation, some metadata is set for each chunk in the output file.
Such metadata may be:

- the source checksum that serves to identify the source text that has been
  translated
- a _needs_review_ tag that alerts the user that a particular chunk has been
  translated by machine and needs review by a human.

The translation command may also take a vocabulary list as optional parameter.
That list contains pairs of a word or phrase on a source language and its
translation on the target one. That vocabulary is passed to the LLM in order to
improve its translation quality.

The current version of the library supports the next services:

- OpenAI
- Anthropic
- Google
- Aristote
- xAI

Each service can be set as well as a model supported by each service using an
appropriate interface. The google's `gemini-2.0-flash` is a model set by
default.

When translating, an environment variable `LLM_API_KEY` must be set accordingly
to the service you use.

## The Translation Cache

The translation cache stores translation pairs for later fast retrieval and
reuse.

### Structure

The cache is stored in the `translate_cache` directory located at the project
root. This folder has the following structure:

```
translate_cache/
├── correspondence_cache.csv
├── <lang_1>/
│   └── <path_hash>/
│       └── <chunk_checksum>
└── <lang_2>/
    └── <path_hash>/
        └── <chunk_checksum>
```

and consists of two parts:

- a checksum-to-text cache
- a correspondence cache

### Checksum-to-text cache

This part of the cache is stored in the `<lang_*>` folders. Each file in these
folders holds a chunk of text and is named after the checksum of that chunk.
Chunks are organised into subdirectories named after a **path hash** — a
deterministic hash of the source file's project-relative path — so that all
chunks belonging to a particular source file are grouped together.

This system allows the storage of the chunk contents, source retrieval and
updates comparison.

Example of such structure:

```
translate_cache/
├── English/
│   └── a3f7c1/
│       ├── <checksum1_en>
│       └── <checksum2_en>
├── French/
│   └── a3f7c1/
│       ├── <checksum1_fr>
│       └── <checksum2_fr>
└── correspondence_cache.csv
```

### Correspondence cache

The correspondence cache is stored in the `correspondence_cache.csv` file. Each
row of that file stores the checksums of chunks of text in two languages or
more, and states that they are the current reference translations of each other.

For example, the following rows:
```
path_hash,French,English
a3f7c1,<checksum1_fr>,<checksum1_en>
a3f7c1,<checksum2_fr>,<checksum2_en>
```
states that the chunks stored in the files `French/a3f7c1/<checksum1_fr>` and
`English/a3f7c1/<checksum1_en>` respectively are the current reference
translations of each other.

A row is removed only when all language fields in it are empty. A row with some
missing target fields is kept — it indicates that some translations are pending
or have been selectively cleared.

### Cache sync

After manually editing translated files, the correspondence cache can become
stale — it still points to the old translated chunks even though the files on
disk have changed. Running `cache sync` (CLI) or `sync_translation_cache`
(library) rebuilds the correspondence cache from the current on-disk source and
target files:

1. For each translatable source file, compute the checksum of each chunk.
2. For each target language, read the translated file and compute the checksum
   of each chunk.
3. Write or update correspondence rows to link each source chunk to its
   translated counterpart.

This ensures future translations reuse your manual corrections rather than
regenerating them from the LLM.

### Cache maintenance

Over time the cache can accumulate stale entries — for example, when source
files are edited and chunks change, the old chunk files and their correspondence
rows become orphans. The `cache clear` command (CLI) or
`clear_translation_cache_*` methods (library) handle cleanup.

**Removing missing chunks** (`--missing-chunks`):

Removes correspondence rows whose source chunk file is missing, rows where no
target chunk files exist, and orphaned chunk files that are not referenced by any
remaining correspondence row. If a row has some missing targets but at least one
present target, it is kept with the missing fields cleared. This is the safe,
targeted cleanup to run after editing or deleting source files.

**Clearing by scope** (`--all`):

Deletes cache entries for a specific language (`--lang`), a specific file
(`--file`), or both. Without any scope, clears the entire cache. Rows are
removed only when all their language fields are empty after the clear; otherwise
the row is kept with the cleared fields set to empty.

**Clearing by keyword** (`--all --keyword`):

Deletes chunk files whose text contains the keyword as a literal substring
(case-sensitive) and clears the corresponding fields. Useful for removing a
specific passage from the cache without clearing everything.

## Correcting

After the automated translation, authors will typically review the translated
chunks and do some postedits. These postedits are precious. Calling the
`correction` command updates accordingly the translation cache to ensure that
future translations exploit them.
