from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

vocab_app = typer.Typer(name="vocab", help="Configure the default vocabulary file.", no_args_is_help=True)


@vocab_app.command("set")
def set_vocab_file(
    ctx: typer.Context,
    vocab_file_path: Annotated[Path, typer.Argument(help="Path to the CSV vocabulary file to use by default for all translations.")],
):
    """Sets a default vocabulary file for the project.

    The file is used automatically when no --vocabulary flag is passed to a
    translate command. Passing --vocabulary explicitly always takes precedence
    over this default.
    """
    project = get_project_from_context(ctx)
    resolved = vocab_file_path.resolve()
    if not resolved.exists():
        typer.secho(
            f"Warning: '{resolved}' does not exist. The path will be stored but the file cannot be read until it exists.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    try:
        project.set_vocab_file(resolved)
        typer.secho(f"Default vocab file set to '{resolved}'.", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error setting vocab file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@vocab_app.command("unset")
def unset_vocab_file(ctx: typer.Context):
    """Removes the configured default vocabulary file from the project config."""
    project = get_project_from_context(ctx)
    try:
        project.unset_vocab_file()
        typer.secho("Default vocab file removed from config.", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error unsetting vocab file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
