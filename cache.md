# Cache Clear Technical Report

## Overview
This change adds cache clear behaviors:
- `lesia cache clear --missing-chunks` cleans the cache by removing or fixing correspondence entries that point to missing chunk files. It also removes orphaned source chunks that have no correspondence rows.
- `lesia cache clear --all --lang <language>` and/or `--file <path>` deletes cached data scoped to a specific language and/or file.
- `lesia cache clear --all --keyword <string>` deletes cached chunks whose contents include the keyword, with optional `--lang`/`--file` scoping.

## Files and Components
- `src/trans_lib/translation_cache/cache_cleaner.py`
  - Cleanup implementations.
  - Exposes `clear_missing_chunks(root_path, source_lang)` and `clear_all(root_path, lang, relative_path)`.
- `src/trans_lib/project_runtime.py`
  - Adds cache clear wrappers with error handling.
- `src/trans_lib/project_manager.py`
  - Adds convenience methods for cache clear actions.
- `src/cli.py`
  - Adds `lesia cache clear --missing-chunks` and `--all` CLI entry points.
- `src/trans_lib/errors.py`
  - Adds `TranslationCacheClearError`.
- `tests/test_cache_clear.py`
  - New coverage for row removal, field clearing, and orphan source deletion.

## Cache Layout (used by cleanup)
The cleanup logic directly scans the on-disk cache and ignores `path_checksums.csv`.
- Cache root: `<project>/.translate_dir/translate_cache`
- Chunk files are stored by language and path checksum:
  - `<lang>/<path_hash>/<chunk_checksum>`

## Cleanup Algorithm (missing-chunks)
Inputs:
- Source language from project config.
- Correspondence CSV (`correspondence_cache.csv`) if present.
- On-disk chunk files.

Steps:
1. Load cache root. If it does not exist, exit with zero changes.
2. Enumerate all source language chunk files (including any that are stored directly under `<lang>/`).
3. Load correspondence rows:
   - If CSV does not exist: treat all source chunks as orphaned and delete them.
4. For each row:
   - Resolve `path_hash` and source checksum.
   - If source checksum is missing or its chunk file is missing: remove the row.
   - Otherwise, validate all target language checksum files:
     - If at least one target chunk file exists, clear only missing target fields.
     - If no target chunk files exist, remove the row.
5. Write a new correspondence CSV if any row was removed or fields were cleared.
6. Remove any source chunk files that are not referenced by a kept correspondence row.

## Behavior Summary
- Rows with missing source files are removed.
- Rows with no existing target chunk files are removed.
- Rows with some missing targets are kept and the missing checksum fields are cleared.
- Orphaned source chunks (no correspondence row) are deleted.
- Target chunk files are deleted when they are not referenced by any remaining correspondence row.
- Keyword deletes only the matching chunk files and clears corresponding fields; rows are removed only when all language fields are empty.

## CLI Usage
```
lesia cache clear --missing-chunks
```
```
lesia cache clear --all --lang English
lesia cache clear --all --file src_en/doc.md
lesia cache clear --all --lang French --file src_en/doc.md
lesia cache clear --all
lesia cache clear --all --keyword glossary
lesia cache clear --all --file src_en/doc.md --keyword glossary
```
The command requires at least one action flag. `--lang` and `--file` only work with `--all`. `--all` without scopes clears all cache and correspondence rows. It reports:
- removed rows
- cleared fields
- removed chunk files

## Tests Added
- `test_clear_missing_chunks_removes_row_and_source`
- `test_clear_missing_chunks_clears_missing_target_fields`
- `test_clear_missing_chunks_removes_row_when_source_missing`
- `test_clear_missing_chunks_removes_orphan_source_chunks`

These tests validate row removal, field clearing, orphan removal, and the non-deletion of target chunk files.
