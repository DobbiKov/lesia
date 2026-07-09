import asyncio
import csv
from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from lesia.project_manager import Project
from lesia.vocab_list import vocab_list_from_vocab_db
from ._common import get_project_from_context

translate_app = typer.Typer(name="translate", help="Translate files.", no_args_is_help=True)


def _read_vocab_from_file(path: Path) -> list[dict]:
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _print_translation_stats(stats) -> None:
    lines = [
        f"  chunks from cache:        {stats.chunks_from_cache}",
        f"  chunks translated:        {stats.chunks_translated}",
    ]
    if stats.chunks_passed_to_reasoning > 0:
        lines.append(f"  chunks sent to reasoning: {stats.chunks_passed_to_reasoning}")
    if stats.chunks_failed > 0:
        lines.append(f"  chunks failed:            {stats.chunks_failed}")
    typer.echo("\n".join(lines))


async def _translate_file_command(
    project: Project,
    file_path_str: str,
    lang: str,
    vocab: Path | None,
    use_reasoning_model: bool = False,
):
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        vocabulary = None
        if vocab is not None:
            vocabulary = vocab_list_from_vocab_db(
                _read_vocab_from_file(vocab), project.get_source_langugage(), resolved_lang
            )
        stats = await project.translate_single_file(
            file_path_str, resolved_lang, vocabulary, use_reasoning_model=use_reasoning_model
        )
        _print_translation_stats(stats)
        typer.secho(f"File '{file_path_str}' translated to {resolved_lang} successfully.", fg=typer.colors.GREEN)
    except errors.TranslateFileError as e:
        typer.secho(f"Error translating file '{file_path_str}': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during translation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@translate_app.command("file")
def translate_file_cli(
    ctx: typer.Context,
    file_path: Annotated[str, typer.Argument(help="Path to the translatable file.")],
    lang: Annotated[str, typer.Argument(help="Target language for translation (predefined or custom).", case_sensitive=False)],
    vocabulary: Annotated[Path | None, typer.Option(help="A path to the csv file with the vocabulary.", case_sensitive=False)] = None,
    use_reasoning_model: Annotated[bool, typer.Option("--use-reasoning-model", help="Use the configured reasoning model instead of the regular model.")] = False,
):
    """Translates a single specified translatable file."""
    project = get_project_from_context(ctx)
    asyncio.run(_translate_file_command(project, file_path, lang, vocabulary, use_reasoning_model=use_reasoning_model))


async def _translate_all_command(
    project: Project,
    lang: str,
    vocab: Path | None,
    use_reasoning_model: bool = False,
):
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        vocabulary = None
        if vocab is not None:
            vocabulary = vocab_list_from_vocab_db(
                _read_vocab_from_file(vocab), project.get_source_langugage(), resolved_lang
            )

        def on_file_translated(file_path, file_stats):
            _print_translation_stats(file_stats)

        total_stats = await project.translate_all_for_language(
            resolved_lang, vocabulary, use_reasoning_model=use_reasoning_model, on_file_translated=on_file_translated
        )
        typer.echo("--- Total statistics ---")
        _print_translation_stats(total_stats)
        typer.secho(f"All translatable files processed for language {resolved_lang}.", fg=typer.colors.GREEN)
    except errors.TranslateFileError as e:
        typer.secho(f"Error during 'translate all' for {resolved_lang}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during 'translate all': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@translate_app.command("all")
def translate_all_cli(
    ctx: typer.Context,
    lang: Annotated[str, typer.Argument(help="Target language for translation (predefined or custom).", case_sensitive=False)],
    vocabulary: Annotated[Path | None, typer.Option(help="A path to the csv file with the vocabulary.", case_sensitive=False)] = None,
    use_reasoning_model: Annotated[bool, typer.Option("--use-reasoning-model", help="Use the configured reasoning model instead of the regular model.")] = False,
):
    """Translates all translatable files to the specified language."""
    project = get_project_from_context(ctx)
    asyncio.run(_translate_all_command(project, lang, vocabulary, use_reasoning_model=use_reasoning_model))
