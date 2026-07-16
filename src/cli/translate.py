import asyncio
import csv
from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from lesia.project_manager import Project
from lesia.translator_retrieval import TranslationStats
from lesia.vocab_list import vocab_list_from_vocab_db
from ._common import get_project_from_context


def _read_vocab_from_file(path: Path) -> list[dict]:
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _print_translation_stats(stats: TranslationStats) -> None:
    lines = [
        f"  chunks from cache:        {stats.chunks_from_cache}",
        f"  chunks translated:        {stats.chunks_translated}",
    ]
    if stats.chunks_passed_to_reasoning > 0:
        lines.append(f"  chunks sent to reasoning: {stats.chunks_passed_to_reasoning}")
    if stats.chunks_failed > 0:
        lines.append(f"  chunks failed:            {stats.chunks_failed}")
    typer.echo("\n".join(lines))
    _print_chunk_failures(stats)


def _print_chunk_failures(stats: TranslationStats) -> None:
    for failure in stats.failures:
        header, *locations = failure.format_lines()
        typer.secho(f"  - {header}", fg=typer.colors.RED, err=True)
        for location in locations:
            typer.secho(f"    {location}", fg=typer.colors.RED, err=True)


def _resolve_paths_to_files(paths: list[Path], project: Project) -> list[str]:
    """Expand a mix of file and directory paths into a flat list of file path strings."""
    translatable = project.get_translatable_files()  # absolute Path objects
    result: list[str] = []

    for path in paths:
        resolved = path.resolve()
        if resolved.is_file():
            result.append(str(path))
        elif resolved.is_dir():
            dir_files = [f for f in translatable if f.is_relative_to(resolved)]
            if not dir_files:
                typer.secho(
                    f"Warning: no translatable files found under '{path}'.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            result.extend(str(f) for f in dir_files)
        else:
            typer.secho(f"Error: '{path}' is not a file or directory.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    return result


async def _do_translate(
    project: Project,
    lang: str,
    paths: list[Path] | None,
    all_files: bool,
    vocab_path: Path | None,
    use_reasoning_model: bool,
) -> None:
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    vocabulary = None
    if vocab_path is not None:
        vocabulary = vocab_list_from_vocab_db(
            _read_vocab_from_file(vocab_path), project.get_source_langugage(), resolved_lang
        )

    try:
        if all_files:
            def on_file_translated(file_path, file_stats):
                _print_translation_stats(file_stats)

            total_stats = await project.translate_all_for_language(
                resolved_lang, vocabulary,
                use_reasoning_model=use_reasoning_model,
                on_file_translated=on_file_translated,
            )
            typer.echo("--- Total statistics ---")
            _print_translation_stats(total_stats)
            typer.secho(f"All translatable files processed for language {resolved_lang}.", fg=typer.colors.GREEN)

        else:
            files = _resolve_paths_to_files(paths, project)
            if not files:
                typer.secho("No files to translate.", fg=typer.colors.YELLOW)
                return

            total_stats = TranslationStats()
            for file_path_str in files:
                stats = await project.translate_single_file(
                    file_path_str, resolved_lang, vocabulary, use_reasoning_model=use_reasoning_model
                )
                _print_translation_stats(stats)
                typer.secho(f"File '{file_path_str}' translated to {resolved_lang} successfully.", fg=typer.colors.GREEN)
                total_stats = total_stats + stats

            if len(files) > 1:
                typer.echo("--- Total statistics ---")
                _print_translation_stats(total_stats)

    except errors.TranslateFileError as e:
        typer.secho(f"Error during translation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during translation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def translate_cli(
    ctx: typer.Context,
    to: Annotated[str, typer.Option("--to", help="Target language (predefined or custom).", case_sensitive=False)],
    paths: Annotated[list[Path] | None, typer.Argument(help="Files or directories to translate. Omit when using --all.")] = None,
    all_files: Annotated[bool, typer.Option("--all", help="Translate all translatable files in the project.")] = False,
    vocabulary: Annotated[Path | None, typer.Option(help="Path to a CSV vocabulary file.", case_sensitive=False)] = None,
    use_reasoning_model: Annotated[bool, typer.Option("--use-reasoning-model", help="Use the configured reasoning model instead of the regular model.")] = False,
):
    """Translate files to a target language.

    Provide one or more files or directories, or use --all to translate everything.

    Examples:

      lesia translate --to French doc.md

      lesia translate --to French src_en/

      lesia translate --to French foo.md bar.md

      lesia translate --to French --all
    """
    if all_files and paths:
        typer.secho("Cannot combine --all with explicit file paths.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not all_files and not paths:
        typer.secho("Provide at least one file/directory, or use --all.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    project = get_project_from_context(ctx)
    asyncio.run(_do_translate(project, to, paths, all_files, vocabulary, use_reasoning_model))
