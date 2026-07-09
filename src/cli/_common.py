import typer
from lesia import errors
from lesia.project_manager import Project


def get_project_from_context(ctx: typer.Context) -> Project:
    """Loads project based on current directory."""
    from lesia.project_manager import load_project
    try:
        return load_project(".")
    except errors.LoadProjectError as e:
        typer.secho(f"Error loading project: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
