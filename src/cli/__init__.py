import sys
from importlib.metadata import version, PackageNotFoundError

import typer
from typing_extensions import Annotated

from .project import init, info_on_project, translation_status, list_translatable_files, sync_files
from .lang import lang_app
from .config import source_app, target_app
from .file import file_app
from .llm import llm_app
from .vocab import vocab_app
from .typst import typst_app
from .latex import latex_app
from .translate import translate_cli
from .cache import cache_app
from .migrate import migrate_app

try:
    _version = version("lesia")
except PackageNotFoundError:
    _version = "unknown"

app = typer.Typer(
    name="lesia",
    help="A tool for managing and translating directory structures.",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show diagnostic logs.")] = False,
    ver: Annotated[bool, typer.Option("--version", help="Show the version and exit.", is_eager=True)] = False,
) -> None:
    from loguru import logger
    if ver:
        typer.echo(f"lesia {_version}")
        raise typer.Exit()
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="TRACE")
    else:
        logger.add(sys.stderr, level="WARNING")
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# --- Top-level project commands ---
app.command("init")(init)
app.command("info")(info_on_project)
app.command("status")(translation_status)
app.command("list")(list_translatable_files)
app.command("sync")(sync_files)

# --- Sub-apps ---
app.add_typer(lang_app)
app.add_typer(source_app)
app.add_typer(target_app)
app.add_typer(file_app)
app.add_typer(llm_app)
app.add_typer(vocab_app)
app.add_typer(typst_app)
app.add_typer(latex_app)
app.command("translate")(translate_cli)
app.add_typer(cache_app)
app.add_typer(migrate_app)


if __name__ == "__main__":
    app()
