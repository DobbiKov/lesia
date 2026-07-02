---
title: Lesia — Translate your scientific documents
site:
  hide_outline: true
  hide_toc: true
  hide_title_block: true
---

+++ {"kind": "centered"}

v0.1.7 — Early Beta

## Translate scientific documents with AI

Lesia is an open-source Python library and CLI that automates the translation of
LaTeX, Markdown, Typst, MyST, and Jupyter documents — preserving
structure, formatting, and syntax while you stay in control.

{button}`Get started <#install>`
[View on GitHub](https://github.com/DobbiKov/lesia)

+++

## Everything you need for document translation

Built for researchers, scientists, and technical writers who need accurate, structure-preserving translations at scale.

::::{grid} 2 2 3 3

:::{card} 🔒 Format Preservation
The system protects LaTeX commands, Typst syntax, Markdown fences, and code blocks from being altered during translation.
:::

:::{card} ✏️ Postedits
Your postedits are precious. Cache-aware correction system lets you override specific translations. Your corrections survive subsequent retranslations.
:::

:::{card} 🧑‍💻 Ease of Use
Integrates easily into any workflow and allows you to collaborate with anyone.
:::

:::{card} 📖 Terminology Preservation
Define domain-specific glossaries to ensure consistent translation of technical terms across your entire project.
:::

:::{card} 🗂️ Project Management
Initialize and manage translation projects with a `.lesia` config file. Track source and target directories per language.
:::

:::{card} ⚡ Smart Translation Cache
Persistent on-disk cache with checksum-based deduplication. Never pay for the same translation twice — only changed chunks are re-translated.
:::

:::{card} 🔄 File Syncing
Automatically sync non-translatable assets (images, bibliography, fonts) between language directories. Only text changes where it should.
:::

:::{card} 🤖 Multiple LLM Backends
Switch between Google Gemini, OpenAI, Anthropic, xAI, and others. Use a secondary reasoning model for complex passages.
:::

:::{card} 🇫🇷 French University Support
Free access to open-source models via ILaaS; no API key required for Paris-Saclay members if running your translations from MyDocker.
:::

:::{card} 🧪 Python Library API
Embed Lesia into your own scripts and pipelines. Full async support for concurrent translation of multiple files.
:::

::::

+++ {"kind": "logo-cloud"}

## Supported Formats

Works with your documents — from academic papers to data science notebooks, Lesia handles the most popular scientific markup languages.

::::{grid} 2 3 5 5

:::{card}
🔶 **LaTeX**
:::

:::{card}
📝 **Markdown**
:::

:::{card}
📓 **Jupyter Notebooks**
:::

:::{card}
⚡ **MyST**
:::

:::{card}
🔷 **Typst**
:::

::::

+++ 
## Open and Secure
Lesia is completely free and open-source, you may download it, change it,
redistribute as you wish. Moreover, the data is yours, you may choose any LLM
model provider even the models you run locally.

+++ {"kind": "logo-cloud"}

## Your choice of AI model

Lesia supports major commercial providers as well as self-hosted and institutional deployments.

::::{grid} 2 3 3 6

:::{card}
♊ **Google Gemini**
:::

:::{card}
🤖 **OpenAI**
:::

:::{card}
🔬 **Anthropic**
:::

:::{card}
✖️ **xAI / Grok**
:::

:::{card}
🇫🇷 **iLaaS**
:::

:::{card}
🐳 **MyDocker**
:::

::::

+++

(install)=
## Get up and running

Install as a standalone CLI tool or embed the library in your own Python project.

`````{tab-set}

````{tab-item} CLI Tool
```bash
# Requires uv (https://docs.astral.sh/uv/)
uv tool install lesia

# Verify installation
lesia --help
```
````

````{tab-item} Python Library
```bash
# pip
pip install lesia

# uv
uv add lesia
```
````

````{tab-item} Development
```bash
git clone https://github.com/DobbiKov/lesia
cd lesia
uv sync

# Run tests
uv run pytest
```
````

````{tab-item} Quick Start
```python
import asyncio
from lesia.project_manager import init_project
from lesia.enums import Language

# Initialize project
project = init_project("my_project", "/path/to/root")

# Configure source
project.set_source_directory("docs_fr", Language.FRENCH)
project.add_target_language(Language.ENGLISH)
project.set_file_translatability("docs_fr/main.tex", True)

# Sync static assets and translate
project.sync_untranslatable_files()
asyncio.run(project.translate_single_file(
    "docs_fr/main.tex", Language.ENGLISH, None
))
```
````

`````

+++ {"kind": "logo-cloud"}

## Supported Languages

Translate between any combination of the supported natural languages.

::::{grid} 2 2 4 4

:::{card}
🇬🇧 **English**
:::

:::{card}
🇫🇷 **French**
:::

:::{card}
🇩🇪 **German**
:::

:::{card}
🇪🇸 **Spanish**
:::

:::{card}
🇺🇦 **Ukrainian**
:::

:::{card}
🇦🇲 **Armenian**
:::

:::{card}
🌐 **Add your own**
:::

::::

+++

## Projects that use Lesia

Open-source projects and tools that actively use Lesia in their workflow.

::::{grid} 1 1 3 3

:::{card} 📚 Linear Algebra Lecture Notes
Linear Algebra Lecture Notes in English, French and Ukrainian.

- [GitHub Source](https://github.com/DobbiKov/semester4-lecture-notes/tree/main/linalg_translation)
- [🇫🇷 French](https://dobbikov.github.io/semester4-lecture-notes/linalg.pdf) 
- [🇺🇦 Ukrainian](https://dobbikov.github.io/semester4-lecture-notes/linalg_ua.pdf) 
- [🇬🇧 English](https://dobbikov.github.io/semester4-lecture-notes/linalg_en.pdf)
:::

:::{card} 📚 Topology Lecture Notes
Topology Lecture Notes in English, French and Ukrainian.

- [GitHub Source](https://github.com/DobbiKov/semester4-lecture-notes/tree/main/analyse) 
- [🇫🇷 French](https://dobbikov.github.io/semester4-lecture-notes/analyse.pdf)
- [🇺🇦 Ukrainian](https://dobbikov.github.io/semester4-lecture-notes/analyse_ua.pdf)
- [🇬🇧 English](https://dobbikov.github.io/semester4-lecture-notes/analyse_en.pdf)
:::

:::{card} 📚 Statistics Lecture Notes
Statistics Lecture Notes in English, French and Ukrainian.

- [GitHub Source](https://github.com/DobbiKov/semester6-lecture-notes/tree/main/stats)
- [🇫🇷 French](https://dobbikov.github.io/semester6-lecture-notes/stats.pdf)
- [🇺🇦 Ukrainian](https://dobbikov.github.io/semester6-lecture-notes/stats_ua.pdf)
- [🇬🇧 English](https://dobbikov.github.io/semester6-lecture-notes/stats_en.pdf)
:::

:::{card} 📄 MyDocker Documentation
Documentation for [MyDocker](https://mydocker.universite-paris-saclay.fr) service of Université Paris-Saclay.

- [GitLab Source](https://gitlab.dsi.universite-paris-saclay.fr/mydocker/mydocker.gitlab.dsi.universite-paris-saclay.fr)
- [🇫🇷 French](https://mydocker.gitlab.dsi.universite-paris-saclay.fr/)
- [🇬🇧 English](https://mydocker.gitlab.dsi.universite-paris-saclay.fr/en/)
:::

::::

## Cite Lesia

Using Lesia in your research? Please cite it as follows.

```bib
@software{korotenko_lesia_2026,
    author    = {Korotenko, Yehor},
    title     = {lesia},
    month     = {jun},
    year      = {2026},
    publisher = {Zenodo},
    version   = {v0.1.7},
    doi       = {10.5281/zenodo.20610935},
    url       = {https://doi.org/10.5281/zenodo.20610935}
}
```
