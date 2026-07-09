from pathlib import Path

import typer

from lesia.errors import MigrateConfigError

migrate_app = typer.Typer(name="migrate", help="Migration utilities.", no_args_is_help=True)


@migrate_app.command("toml")
def migrate_toml(ctx: typer.Context):
    """Migrates an existing config.json to config.toml and removes the JSON file."""
    from lesia.helpers import find_dir_upwards
    from lesia.project_config_io import migrate_config_json_to_toml
    from lesia.constants import JSON_CONFIG_FILENAME, CONFIG_FILENAME, CONF_DIR

    conf_dir = find_dir_upwards(Path(".").resolve(), CONF_DIR)
    if conf_dir is None:
        typer.secho("No lesia project found in the current directory or its parents.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    json_path = conf_dir / JSON_CONFIG_FILENAME
    toml_path = conf_dir / CONFIG_FILENAME

    if not json_path.exists():
        typer.secho(f"Nothing to migrate: {json_path} does not exist.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    try:
        migrate_config_json_to_toml(json_path, toml_path)
        typer.secho(f"Migrated config.json to config.toml in {conf_dir}", fg=typer.colors.GREEN)
    except MigrateConfigError as e:
        typer.secho(f"Migration failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
