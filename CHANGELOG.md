# ChangeLog
Unfortunately it starts from the vesion v0.1.9

## Changelog - v0.1.9

### Features

- **Performance improvement**: CSV database is now stored in memory, making translation lookup O(1) instead of reading from disk on each lookup.
- **Custom language shortened version**: Added the possibility to set a shortened version of a custom language.
- **LaTeX comments untranslatable**: LaTeX comments are now marked as untranslatable and will be skipped during translation.
- **Renamed internal directory**: `translation_cache` has been renamed to `cache` inside the `.lesia` directory.
- **Renamed library**: Internal library renamed from `trans_lib` to `lesia`.
- **`--version` flag**: Added `--version` flag to the `lesia` CLI.
- **Status command improvement**: `lesia status` now also shows information about files that have the `needs_review` tag.
- **Aristote service support**: Updated to `unified-model-caller` v0.2.5, adding support for the Aristote service.

### Bug Fixes

- Fixed the message shown when the target language setting is applied.
- Improved lazy imports for `project_manager`, `project_runtime`, `cache_rebuilder`, `doc_corrector`, `enums`, `helpers`, `project_config_model`, and `translator` to reduce startup time.

### Docs

- Added documentation for the `status` command.
- Added info about the shortened version of custom languages in the library docs.
- Added a link to the Saclai school in the README.

### Tests

- Covered in-memory CSV storage with tests.
- Covered shortened version functionality with tests.
- Covered `status` command with tests.

