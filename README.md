# Lesia
[![DOI](https://zenodo.org/badge/991174305.svg)](https://doi.org/10.5281/zenodo.20610934)
[![Tests](https://github.com/DobbiKov/lesia/actions/workflows/tests.yml/badge.svg)](https://github.com/DobbiKov/lesia/actions/workflows/tests.yml)
[![GitHub Release](https://img.shields.io/github/release/DobbiKov/lesia.svg?style=flat)]()  

## About
**Lesia** is a tool to help you maintain your multilingual documents that
integrates easily into your workflow.

## Features
- Translate documents easily
- Preserves syntax (LaTeX/Markdown/MyST/Typst)
- Learns from your post-edits
- Preserves terminology (you may provide your vocabulary)
- Good quality translation
- Integrates easily in any workflow
- Easy to use for collaborative use (e.g. git)
- Supports any LLM of your choice

## Documentation
- [Library API reference](./docs/main.md)
- [CLI documentation](./docs/cli.md)
- [Architecture and algorithms](./docs/tool-profound-explanation.md)

## Installation
1. Make sure you have **uv** installed
2. Install it via uv `uv tool install lesia`
3. Verify that it works `lesia --help`

## Usage
1. Create a directory dedicated for the project: `mkdir my-dir`
2. `cd my-dir`
3. Initialize the project `lesia init`
4. Create a directory for the documents you want to translate `mkdir -p src/fr`
    - In this example our source language is French
5. Move your files to the created source directory `src/fr`
6. Create directories for target languages `mkdir -p tgt/en`, `mkdir -p tgt/ua`
7. Associate source and target directories with desired languages
    ```sh
    lesia set-source srs/fr french
    lesia set-target tgt/en english
    lesia set-target tgt/ua ukrainian
    ```
8. Mark files that should be translated `lesia add src/fr/main.md`
9. Synchronize directories `lesia sync`
10. Set a model you want to use for translation `lesia set-llm google gemini-3.0-flash`
11. Set a token (if needed) `export LLM_API_KEY=your-key`
12. Translate 
    ```sh
    lesia translate all english
    lesia translate all ukrainian
    ```
13. Learn more in [the docs](./docs/cli.md)

## Development
1. Ensure you have [uv](https://docs.astral.sh/uv/#__tabbed_1_1) tool installed
   (visit their site for the installation guide)
2. Clone the repo: `git clone https://github.com/DobbiKov/lesia`
3. Enter `cd lesia`
4. Install dependencies `uv sync`
5. Install tool from your directory and make it editable `uv tool install -e .`
5. Enjoy

## Contributing
The suggestions and pull requests are welcome. 

## Citation
If you use this software in your research or writing, please cite it as
follows:

```bib
@software{korotenko_lesia_2026,
  author       = {Korotenko, Yehor},
  title        = {lesia},
  month        = jun,
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v0.1.7},
  doi          = {10.5281/zenodo.20610935},
  url          = {https://doi.org/10.5281/zenodo.20610935}
}
```

## French University Support
Free access to open-source models via [ILaaS](https://www.ilaas.fr/); no API
key required for [Paris-Saclay](https://www.universite-paris-saclay.fr/)
members if running your translations from [MyDocker](https://mydocker.universite-paris-saclay.fr/login).

## Credits
- **Nicolas M. Thiéry** - for supervising this project.
- **LISN (Université Paris-Saclay)** - for financing the internship and
  providing workspace.
- **CMA SaclAI-School** - for financing the project.
