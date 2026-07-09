import typer
from typing_extensions import Annotated

from lesia.errors import AddCustomLanguageError, RemoveCustomLanguageError
from lesia.enums import Language
from ._common import get_project_from_context

lang_app = typer.Typer(name="lang", help="Manage languages.", no_args_is_help=True)


@lang_app.command("add")
def add_custom_language(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Custom language name, e.g. 'American English'.")],
    suffix: Annotated[str, typer.Argument(help="Directory suffix for the language, e.g. '_ae'.")],
    short: Annotated[str | None, typer.Option("--short", help="Optional short name alias, e.g. 'AmEng'.")] = None,
):
    """Registers a new custom language in the project."""
    project = get_project_from_context(ctx)
    try:
        project.add_custom_language(name, suffix, short)
        msg = f"Custom language '{name}' with suffix '{suffix}' added."
        if short:
            msg += f" Short alias: '{short}'."
        typer.secho(msg, fg=typer.colors.GREEN)
    except AddCustomLanguageError as e:
        typer.secho(f"Error adding custom language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@lang_app.command("remove")
def remove_custom_language(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Custom language name to remove, e.g. 'Catalan'.")],
):
    """Removes a custom language from the project config."""
    project = get_project_from_context(ctx)
    try:
        project.remove_custom_language(name)
        typer.secho(f"Custom language '{name}' removed.", fg=typer.colors.GREEN)
    except RemoveCustomLanguageError as e:
        typer.secho(f"Error removing custom language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@lang_app.command("list")
def list_languages(ctx: typer.Context):
    """Lists all languages: those assigned to directories and those not yet assigned."""
    project = get_project_from_context(ctx)

    src_dir = project.config.get_src_dir()
    src_lang = src_dir.get_lang() if src_dir is not None else None
    target_langs = project._get_target_languages()  # list of str

    assigned = set()
    if src_lang is not None:
        assigned.add(src_lang)
    assigned.update(target_langs)

    custom_languages = project.config.custom_languages  # name → suffix
    shorts_by_name = {full: short for short, full in project.config.custom_language_shorts.items()}

    # --- Assigned to directories ---
    if src_lang is not None or target_langs:
        typer.secho("Assigned to directories:", fg=typer.colors.BLUE)
        if src_lang is not None:
            src_dir_name = src_dir.get_path().name
            typer.echo(f"  source:  {src_lang}  ({src_dir_name}/)")
        for lang in target_langs:
            tgt_path = project.config.get_target_dir_path_by_lang(lang)
            tgt_name = tgt_path.name if tgt_path else "unknown"
            typer.echo(f"  target:  {lang}  ({tgt_name}/)")
    else:
        typer.secho("Assigned to directories: none", fg=typer.colors.YELLOW)

    # --- Custom languages not assigned ---
    unassigned_custom = {
        name: suffix for name, suffix in custom_languages.items()
        if name not in assigned
    }
    if unassigned_custom:
        typer.secho("\nCustom (registered, not assigned):", fg=typer.colors.BLUE)
        for name, suffix in sorted(unassigned_custom.items()):
            short = shorts_by_name.get(name)
            short_str = f", short: {short}" if short else ""
            typer.echo(f"  {name}  ({suffix}{short_str})")

    # --- Predefined languages not in use ---
    predefined_unused = [lang for lang in Language if lang not in assigned]
    if predefined_unused:
        typer.secho("\nPredefined (available, not assigned):", fg=typer.colors.BLUE)
        typer.echo("  " + ", ".join(str(lang) for lang in predefined_unused))
