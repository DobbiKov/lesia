import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

typst_app = typer.Typer(name="typst", help="Configure Typst translation settings.", no_args_is_help=True)


@typst_app.command("set-func-args")
def set_typst_function_args(
    ctx: typer.Context,
    function_name: Annotated[str, typer.Argument(help="Typst function name, e.g. ex")],
    arg_names: Annotated[list[str], typer.Argument(help="Translatable string argument names, e.g. info caption")],
):
    """Sets translatable Typst string argument names for a function."""
    project = get_project_from_context(ctx)
    try:
        project.set_typst_translatable_string_args_for_function(function_name, arg_names)
        typer.secho(
            f"Typst function '{function_name}' translatable string args set to: {', '.join(arg_names)}",
            fg=typer.colors.GREEN,
        )
    except errors.SetTypstConfigError as e:
        typer.secho(f"Error setting Typst function args: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@typst_app.command("unset-func-args")
def unset_typst_function_args(
    ctx: typer.Context,
    function_name: Annotated[str, typer.Argument(help="Typst function name to remove from config")],
):
    """Removes Typst function string-arg translation settings for a function."""
    project = get_project_from_context(ctx)
    try:
        project.remove_typst_translatable_string_args_for_function(function_name)
        typer.secho(
            f"Typst function '{function_name}' settings removed.",
            fg=typer.colors.GREEN,
        )
    except errors.SetTypstConfigError as e:
        typer.secho(f"Error removing Typst function args: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
