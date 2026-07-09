import typer
from typing_extensions import Annotated
from pathlib import Path

from lesia import errors
from ._common import get_project_from_context

config_app = typer.Typer(name="config", help="Configure project source and target directories.", no_args_is_help=True)

source_app = typer.Typer(name="source", help="Manage the source directory.", no_args_is_help=True)
target_app = typer.Typer(name="target", help="Manage target directories.", no_args_is_help=True)

config_app.add_typer(source_app)
config_app.add_typer(target_app)


@source_app.command("set")
def set_source_dir(
    ctx: typer.Context,
    dir_name: Annotated[str, typer.Argument(help="Name of the source directory (relative to project root).")],
    lang: Annotated[str, typer.Argument(help="Source language (predefined or custom).", case_sensitive=False)],
):
    """Sets or changes the source directory and its language."""
    project = get_project_from_context(ctx)
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error setting source directory: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        project.set_source_directory(dir_name, resolved_lang)
        typer.secho(f"Source directory set to '{dir_name}' with language {resolved_lang}", fg=typer.colors.GREEN)
    except errors.SetSourceDirError as e:
        typer.secho(f"Error setting source directory: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@source_app.command("info")
def source_info(ctx: typer.Context):
    """Shows the current source directory and its language."""
    project = get_project_from_context(ctx)
    src_dir = project.config.get_src_dir()
    if src_dir is None:
        typer.secho("Source directory: not set", fg=typer.colors.YELLOW)
        return
    src_dir_name = src_dir.get_path().name
    src_lang = src_dir.get_lang()
    typer.secho("Source directory:", fg=typer.colors.BLUE)
    typer.echo(f"  language:  {src_lang}")
    typer.echo(f"  directory: {src_dir_name}/")


@target_app.command("set")
def set_target_dir(
    ctx: typer.Context,
    dir_name: Annotated[Path, typer.Argument(help="Target directory name (relative to project root).", case_sensitive=True)],
    lang: Annotated[str, typer.Argument(help="Target language (predefined or custom).", case_sensitive=False)],
):
    """Adds or updates a target language directory."""
    project = get_project_from_context(ctx)
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error adding language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        new_path = project.add_target_language(resolved_lang, dir_name)
        lang_display = f'"{resolved_lang} ({resolved_lang.get_dir_suffix().lstrip("_")})"'
        typer.secho(f'Set target language {lang_display} for directory "{new_path}".', fg=typer.colors.GREEN)
    except errors.AddLanguageError as e:
        typer.secho(f"Error adding language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@target_app.command("remove")
def remove_target_dir(
    ctx: typer.Context,
    lang: Annotated[str, typer.Argument(help="Target language to remove (predefined or custom).", case_sensitive=False)],
):
    """Removes a target language and its directory from the project."""
    project = get_project_from_context(ctx)
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error removing language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        project.remove_target_language(resolved_lang)
        typer.secho(f"Target language {resolved_lang} and its directory removed.", fg=typer.colors.GREEN)
    except errors.RemoveLanguageError as e:
        typer.secho(f"Error removing language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@target_app.command("list")
def list_targets(ctx: typer.Context):
    """Lists all configured target languages and their directories."""
    project = get_project_from_context(ctx)
    target_langs = project._get_target_languages()
    if not target_langs:
        typer.secho("No target languages configured.", fg=typer.colors.YELLOW)
        return
    typer.secho("Target directories:", fg=typer.colors.BLUE)
    for lang in target_langs:
        tgt_path = project.config.get_target_dir_path_by_lang(lang)
        tgt_name = tgt_path.name if tgt_path else "unknown"
        typer.echo(f"  {lang}  ({tgt_name}/)")
