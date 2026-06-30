# ChangeLog
Unfortunately it starts from the vesion v0.1.9

## Changelog - v0.1.10

### Features

- **LaTeX parsing settings**: Added the ability to choose which LaTeX environments and commands (and their parameters) are translatable or not.

### Bug Fixes

- **Language overshadowing**: Fixed an issue where a custom language could overshadow a predefined or another custom language. An error is now raised when two custom languages share the same name.
- **Service overshadowing**: Added a warning when a custom service overshadows a predefined one, and an error is raised when two custom services share the same name.
- **Project encapsulation**: Fixed an encapsulation problem with project and project config.

### CI/CD

- Added MyST site deployment workflow.
- Fixed path to `_build` directory in CI.
- Fixed missing `working-directory` for the build command in CI.

### Docs

- Added MyST configuration for the documentation site.
- Made the MyST site include README, CONTRIBUTING, and CHANGELOG pages.
- Added links to the website and documentation on GitHub Pages to the README.
- Added a landing page to the MyST site configuration.
- Updated CONTRIBUTING to point to the issues page instead of the TODO section.
- Styled the landing page for lesia.
- Covered LaTeX parsing settings with documentation.
- Updated docs to reflect new checks for language and service overshadowing.

### Tests

- Covered LaTeX parsing settings feature with tests.
- Covered the language overshadowing fix with tests.
- Covered the service overshadowing checks with tests.

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

