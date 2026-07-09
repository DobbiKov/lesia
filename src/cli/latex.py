import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

latex_app = typer.Typer(name="latex", help="Configure LaTeX translation settings.", no_args_is_help=True)

_placeholder_env_app = typer.Typer(name="placeholder-env", help="Manage non-translatable LaTeX environments.", no_args_is_help=True)
_math_env_app = typer.Typer(name="math-env", help="Manage LaTeX math environments.", no_args_is_help=True)
_placeholder_cmd_app = typer.Typer(name="placeholder-cmd", help="Manage non-translatable LaTeX commands.", no_args_is_help=True)
_cmd_spec_app = typer.Typer(name="cmd-spec", help="Define custom LaTeX command argument structures.", no_args_is_help=True)
_cmd_args_app = typer.Typer(name="cmd-args", help="Set which LaTeX command arguments are translatable.", no_args_is_help=True)

latex_app.add_typer(_placeholder_env_app)
latex_app.add_typer(_math_env_app)
latex_app.add_typer(_placeholder_cmd_app)
latex_app.add_typer(_cmd_spec_app)
latex_app.add_typer(_cmd_args_app)


# --- placeholder-env ---

@_placeholder_env_app.command("add")
def add_latex_placeholder_env(
    ctx: typer.Context,
    env_name: Annotated[str, typer.Argument(help="LaTeX environment name to treat as a placeholder (not translated)")],
):
    """Marks a LaTeX environment as non-translatable (whole env becomes a placeholder)."""
    project = get_project_from_context(ctx)
    try:
        project.add_latex_placeholder_env(env_name)
        typer.secho(f"LaTeX environment '{env_name}' added to placeholder list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_placeholder_env_app.command("remove")
def remove_latex_placeholder_env(
    ctx: typer.Context,
    env_name: Annotated[str, typer.Argument(help="LaTeX environment name to remove from placeholder list")],
):
    """Removes a LaTeX environment from the non-translatable list."""
    project = get_project_from_context(ctx)
    try:
        project.remove_latex_placeholder_env(env_name)
        typer.secho(f"LaTeX environment '{env_name}' removed from placeholder list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- math-env ---

@_math_env_app.command("add")
def add_latex_math_env(
    ctx: typer.Context,
    env_name: Annotated[str, typer.Argument(help="LaTeX environment name to treat as math")],
):
    """Marks a LaTeX environment as a math environment (body walked as math, not text)."""
    project = get_project_from_context(ctx)
    try:
        project.add_latex_math_env(env_name)
        typer.secho(f"LaTeX environment '{env_name}' added to math list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_math_env_app.command("remove")
def remove_latex_math_env(
    ctx: typer.Context,
    env_name: Annotated[str, typer.Argument(help="LaTeX environment name to remove from math list")],
):
    """Removes a LaTeX environment from the math list."""
    project = get_project_from_context(ctx)
    try:
        project.remove_latex_math_env(env_name)
        typer.secho(f"LaTeX environment '{env_name}' removed from math list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- placeholder-cmd ---

@_placeholder_cmd_app.command("add")
def add_latex_placeholder_command(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name to treat as a placeholder (not translated)")],
):
    """Marks a LaTeX command as non-translatable (whole command becomes a placeholder)."""
    project = get_project_from_context(ctx)
    try:
        project.add_latex_placeholder_command(cmd_name)
        typer.secho(f"LaTeX command '{cmd_name}' added to placeholder list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_placeholder_cmd_app.command("remove")
def remove_latex_placeholder_command(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name to remove from placeholder list")],
):
    """Removes a LaTeX command from the non-translatable list."""
    project = get_project_from_context(ctx)
    try:
        project.remove_latex_placeholder_command(cmd_name)
        typer.secho(f"LaTeX command '{cmd_name}' removed from placeholder list.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- cmd-spec ---

@_cmd_spec_app.command("set")
def set_latex_custom_command_spec(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name, e.g. myfig")],
    mandatory: Annotated[int, typer.Option("--mandatory", "-m", help="Number of mandatory {..} arguments")],
    optional: Annotated[int, typer.Option("--optional", "-o", help="Number of optional [..] arguments")] = 0,
):
    """Defines the argument structure of a custom LaTeX command for correct parsing.

    Use this for commands unknown to pylatexenc so their arguments are parsed
    correctly and 'latex cmd-args set' can control which are translated.

    Optional args are assumed to come before mandatory args.

    Examples:

      lesia latex cmd-spec set myfig --mandatory 2

      lesia latex cmd-spec set mybox --mandatory 2 --optional 1
    """
    project = get_project_from_context(ctx)
    try:
        project.set_latex_custom_command_spec(cmd_name, mandatory=mandatory, optional=optional)
        typer.secho(
            f"LaTeX command '{cmd_name}' spec set — mandatory: {mandatory}, optional: {optional}.",
            fg=typer.colors.GREEN,
        )
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_cmd_spec_app.command("unset")
def unset_latex_custom_command_spec(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name to remove the spec for")],
):
    """Removes the custom argument structure definition for a LaTeX command."""
    project = get_project_from_context(ctx)
    try:
        project.remove_latex_custom_command_spec(cmd_name)
        typer.secho(f"LaTeX command '{cmd_name}' spec removed.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- cmd-args ---

@_cmd_args_app.command("set")
def set_latex_command_translatable_args(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name, e.g. href")],
    mandatory: Annotated[list[int] | None, typer.Option("--mandatory", "-m", help="1-based indices of mandatory {..} args that are translatable")] = None,
    optional: Annotated[list[int] | None, typer.Option("--optional", "-o", help="1-based indices of optional [..] args that are translatable")] = None,
):
    """Sets which arguments of a LaTeX command are translatable (1-based indices).

    Examples:

      lesia latex cmd-args set href --mandatory 2

      lesia latex cmd-args set section --mandatory 1 --optional 1
    """
    project = get_project_from_context(ctx)
    if not mandatory and not optional:
        typer.secho("Provide at least --mandatory or --optional.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        project.set_latex_command_translatable_args(cmd_name, mandatory=mandatory, optional=optional)
        parts = []
        if mandatory:
            parts.append(f"mandatory: {mandatory}")
        if optional:
            parts.append(f"optional: {optional}")
        typer.secho(
            f"LaTeX command '{cmd_name}' translatable args set — {', '.join(parts)}.",
            fg=typer.colors.GREEN,
        )
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_cmd_args_app.command("unset")
def unset_latex_command_translatable_args(
    ctx: typer.Context,
    cmd_name: Annotated[str, typer.Argument(help="LaTeX command name to remove translatable-arg config for")],
):
    """Removes per-argument translation config for a LaTeX command."""
    project = get_project_from_context(ctx)
    try:
        project.remove_latex_command_translatable_args(cmd_name)
        typer.secho(f"LaTeX command '{cmd_name}' arg config removed.", fg=typer.colors.GREEN)
    except errors.SetLatexConfigError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
