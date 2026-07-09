import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

file_app = typer.Typer(name="file", help="Manage translatable files.", no_args_is_help=True)


@file_app.command("add")
def mark_translatable(
    ctx: typer.Context,
    file_paths: Annotated[list[str], typer.Argument(help="Path(s) to the file (relative to project root or absolute).")],
):
    """Marks file(s) in the source directory as translatable."""
    project = get_project_from_context(ctx)
    try:
        for file_path in file_paths:
            project.set_file_translatability(file_path, True)
            typer.secho(f"File '{file_path}' marked as translatable.", fg=typer.colors.GREEN)
    except errors.AddTranslatableFileError as e:
        typer.secho(f"Error marking file as translatable: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@file_app.command("remove")
def mark_untranslatable(
    ctx: typer.Context,
    file_paths: Annotated[list[str], typer.Argument(help="Path(s) to the file (relative to project root or absolute).")],
):
    """Marks file(s) in the source directory as untranslatable."""
    project = get_project_from_context(ctx)
    try:
        for file_path in file_paths:
            project.set_file_translatability(file_path, False)
            typer.secho(f"File '{file_path}' marked as untranslatable.", fg=typer.colors.GREEN)
    except errors.AddTranslatableFileError as e:
        typer.secho(f"Error marking file as untranslatable: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
