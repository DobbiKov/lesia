from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

cache_app = typer.Typer(name="cache", help="Translation cache utilities.", no_args_is_help=True)


@cache_app.command("sync")
def sync_cache_cli(ctx: typer.Context):
    """Synchronizes the translation cache for all target languages using on-disk files."""
    project = get_project_from_context(ctx)
    try:
        project.sync_translation_cache()
        typer.secho("Translation cache synced for all target languages.", fg=typer.colors.GREEN)
    except errors.TranslationCacheSyncError as e:
        typer.secho(f"Error syncing translation cache: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during cache sync: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@cache_app.command("clear")
def clear_cache_cli(
    ctx: typer.Context,
    missing_chunks: Annotated[
        bool,
        typer.Option("--missing-chunks", help="Remove cache entries that reference missing chunk files."),
    ] = False,
    all_cache: Annotated[
        bool,
        typer.Option("--all", help="Delete all cache entries for a language and/or file."),
    ] = False,
    lang: Annotated[
        str | None,
        typer.Option("--lang", help="Limit cache deletion to a specific language (predefined or custom).", case_sensitive=False),
    ] = None,
    file_path: Annotated[
        Path | None,
        typer.Option("--file", help="Limit cache deletion to a specific project file path."),
    ] = None,
    keyword: Annotated[
        str | None,
        typer.Option("--keyword", help="Limit cache deletion to chunks containing the keyword."),
    ] = None,
    checksum: Annotated[
        str | None,
        typer.Option("--checksum", help="Delete cache chunk files matching a specific checksum."),
    ] = None,
):
    """Clears translation cache entries based on cleanup flags."""
    action_flags = [missing_chunks, all_cache, checksum is not None]
    if sum(action_flags) > 1:
        typer.secho(
            "Use only one cache clear action flag at a time (--missing-chunks, --all, or --checksum).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if (lang is not None or file_path is not None) and missing_chunks:
        typer.secho(
            "--lang and --file can only be used with --all or --checksum.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if keyword is not None and not all_cache:
        typer.secho(
            "--keyword can only be used with --all.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if file_path is not None and checksum is not None:
        typer.secho(
            "--file cannot be used with --checksum.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if not missing_chunks and not all_cache and checksum is None:
        typer.secho(
            "No cache clear flags provided. Use --missing-chunks, --all, or --checksum.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    project = get_project_from_context(ctx)
    resolved_lang = None
    if lang is not None:
        try:
            resolved_lang = project.config.resolve_language(lang)
        except ValueError as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    try:
        if missing_chunks:
            stats = project.clear_translation_cache_missing_chunks()
            typer.secho(
                (
                    "Cache cleanup complete: "
                    f"{stats.removed_rows} row(s) removed, "
                    f"{stats.cleared_fields} field(s) cleared, "
                    f"{stats.removed_source_chunks} source chunk(s) removed, "
                    f"{stats.removed_target_chunks} target chunk(s) removed."
                ),
                fg=typer.colors.GREEN,
            )
        elif checksum is not None:
            stats = project.clear_translation_cache_by_checksum(checksum, resolved_lang)
            if stats.removed_chunk_files == 0:
                typer.secho(
                    f"Warning: no cache files found with checksum '{checksum}'.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            typer.secho(
                (
                    "Cache deletion complete: "
                    f"{stats.removed_rows} row(s) removed, "
                    f"{stats.cleared_fields} field(s) cleared, "
                    f"{stats.removed_chunk_files} chunk file(s) removed."
                ),
                fg=typer.colors.GREEN,
            )
        else:
            stats = project.clear_translation_cache_all(
                resolved_lang,
                str(file_path) if file_path else None,
                keyword,
            )
            if (
                file_path is not None
                and stats.removed_rows == 0
                and stats.cleared_fields == 0
                and stats.removed_chunk_files == 0
            ):
                typer.secho(
                    f"Warning: no cache entries found for '{file_path}'. "
                    "Make sure the path is relative to the source directory "
                    "or points to the file directly.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            typer.secho(
                (
                    "Cache deletion complete: "
                    f"{stats.removed_rows} row(s) removed, "
                    f"{stats.cleared_fields} field(s) cleared, "
                    f"{stats.removed_chunk_files} chunk file(s) removed."
                ),
                fg=typer.colors.GREEN,
            )
    except errors.TranslationCacheClearError as e:
        typer.secho(f"Error clearing translation cache: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during cache clear: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
