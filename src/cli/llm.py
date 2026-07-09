from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context

llm_app = typer.Typer(name="llm", help="Configure LLM services and models.", no_args_is_help=True)

_env_file_app = typer.Typer(name="env-file", help="Manage the API keys .env file.", no_args_is_help=True)
llm_app.add_typer(_env_file_app)


@llm_app.command("set")
def set_llm(
    ctx: typer.Context,
    service: Annotated[str, typer.Argument(help="Name of the service providing the model.")],
    model: Annotated[str, typer.Argument(help="Name of the model.", case_sensitive=True)],
):
    """Sets or changes the standard LLM service and model."""
    project = get_project_from_context(ctx)
    try:
        project.set_llm_service_and_model(service, model)
        typer.secho(f"The service set to '{service}' with the model {model}", fg=typer.colors.GREEN)
    except errors.SetSourceDirError as e:
        typer.secho(f"Error setting service and model: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@llm_app.command("set-reasoning")
def set_reasoning_model(
    ctx: typer.Context,
    service: Annotated[str, typer.Argument(help="Name of the service providing the reasoning model.")],
    model: Annotated[str, typer.Argument(help="Name of the reasoning model.", case_sensitive=True)],
):
    """Sets or changes the reasoning LLM service and model."""
    project = get_project_from_context(ctx)
    try:
        project.set_llm_reasoning_service_and_model(service, model)
        typer.secho(f"Reasoning model set to '{model}' on service '{service}'", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error setting reasoning model: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@llm_app.command("list")
def list_llm_services(ctx: typer.Context):
    """Lists all available LLM services."""
    try:
        from lesia.project_manager import load_project
        load_project(".")
    except errors.NoConfigFoundError:
        pass  # Not in a project — only built-in services will be listed
    try:
        from unified_model_caller import LLMCaller
        services = LLMCaller.get_services()
        if not services:
            typer.secho("No LLM services found.", fg=typer.colors.YELLOW)
            return
        typer.secho("Available LLM services:", fg=typer.colors.BLUE)
        for service in services:
            typer.echo(f"  {service}")
    except Exception as e:
        typer.secho(f"Error listing LLM services: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@llm_app.command("set-xml-retries")
def set_xml_retries_before_reasoning(
    ctx: typer.Context,
    retries: Annotated[int, typer.Argument(help="Number of failed XML attempts with the standard model before switching to the reasoning model (0 = always use reasoning model).")],
):
    """Sets how many times the standard model is retried on XML errors before falling back to the reasoning model."""
    project = get_project_from_context(ctx)
    try:
        project.set_xml_retries_before_reasoning(retries)
        typer.secho(f"xml_retries_before_reasoning set to {retries}", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_env_file_app.command("set")
def set_env_file(
    ctx: typer.Context,
    env_file_path: Annotated[Path, typer.Argument(help="Path to the .env file containing LLM_API_KEY and/or LLM_REASONING_API_KEY.")],
):
    """Sets the path to a .env file from which API keys are read.

    Shell environment variables always take precedence over the file.
    The path is stored in the project config.
    """
    project = get_project_from_context(ctx)
    resolved = env_file_path.resolve()
    if not resolved.exists():
        typer.secho(
            f"Warning: '{resolved}' does not exist. The path will be stored but keys cannot be read from a missing file.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    try:
        project.set_env_file(resolved)
        typer.secho(f"Env file set to '{resolved}'.", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error setting env file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@_env_file_app.command("unset")
def unset_env_file(ctx: typer.Context):
    """Removes the configured .env file path from the project config."""
    project = get_project_from_context(ctx)
    try:
        project.unset_env_file()
        typer.secho("Env file path removed from config.", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error unsetting env file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
