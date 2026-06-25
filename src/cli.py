import asyncio
import csv
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import typer
from lesia.project_manager import Project
from loguru import logger
from typing_extensions import Annotated # For Typer < 0.7 or for more complex annotations


from lesia.enums import Language
from lesia import errors
from lesia.errors import AddCustomLanguageError, RemoveCustomLanguageError
from lesia.vocab_list import vocab_list_from_vocab_db # Import the errors module

try:
    _version = version("lesia")
except PackageNotFoundError:
    _version = "unknown"

# Create the Typer app
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

# Shared callback to load project (or handle not being in one)
def get_project_from_context(ctx: typer.Context) -> Project:
    """Loads project based on current directory or explicit path."""
    from lesia.project_manager import load_project
    try:
        # Typer passes the command-specific options.
        # We need a way to get a global --project-path or use CWD.
        # Let's assume `load_project` can take PWD.
        project_path_str = "." # Default to current directory
        
        # If a global option --project-dir is added to app, it can be accessed via ctx.params
        # if ctx.parent and ctx.parent.params.get("project_dir"):
        #    project_path_str = ctx.parent.params["project_dir"]
            
        return load_project(project_path_str)
    except errors.LoadProjectError as e:
        typer.secho(f"Error loading project: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e: # Catch any other unexpected error during load
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- Project Initialization and Loading Commands ---
@app.command()
def init(
    name: Annotated[str, typer.Option(help="Name for the new project.")] = "MyTranslationProject",
    path: Annotated[Path, typer.Option(help="Directory to initialize the project in. Defaults to current directory.")] = Path(".")
):
    """Initializes a new translation project."""
    from lesia.project_manager import init_project
    try:
        project = init_project(name, str(path.resolve()))
        typer.secho(f"Project '{project.config.name}' initialized successfully at {project.root_path}", fg=typer.colors.GREEN)
    except errors.InitProjectError as e:
        typer.secho(f"Error initializing project: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("add-lang")
def add_custom_language(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Custom language name, e.g. 'Catalan'.")],
    suffix: Annotated[str, typer.Argument(help="Directory suffix for the language, e.g. '_ca'.")],
):
    """Registers a new custom language in the project."""
    project = get_project_from_context(ctx)
    try:
        project.add_custom_language(name, suffix)
        typer.secho(f"Custom language '{name}' with suffix '{suffix}' added.", fg=typer.colors.GREEN)
    except AddCustomLanguageError as e:
        typer.secho(f"Error adding custom language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("remove-lang")
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


@app.command("set-source")
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

@app.command("set-target")
def add_language(
    ctx: typer.Context,
    dir_name: Annotated[Path, typer.Argument(help="Set particular directory.", case_sensitive=True)],
    lang: Annotated[str, typer.Argument(help="Target language to add (predefined or custom).", case_sensitive=False)],
):
    """Adds a new target language to the project."""
    project = get_project_from_context(ctx)
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error adding language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        new_path = project.add_target_language(resolved_lang, dir_name)
        typer.secho(f"Target language {resolved_lang} added. Directory created at {new_path}", fg=typer.colors.GREEN)
    except errors.AddLanguageError as e:
        typer.secho(f"Error adding language: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("remove-target")
def remove_language(
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

@app.command("sync")
def sync_files(ctx: typer.Context):
    """Synchronizes untranslatable files from the source to all target directories."""
    project = get_project_from_context(ctx)
    try:
        project.sync_untranslatable_files()
        typer.secho("Untranslatable files synchronized successfully.", fg=typer.colors.GREEN)
    except errors.SyncFilesError as e:
        typer.secho(f"Error synchronizing files: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("add")
def mark_translatable(
    ctx: typer.Context,
    file_paths: Annotated[list[str], typer.Argument(help="Path to the file (relative to project root or absolute).")]
):
    """Marks a file in the source directory as translatable."""
    project = get_project_from_context(ctx)
    try:
        for file_path in file_paths:
            project.set_file_translatability(file_path, True)
            typer.secho(f"File '{file_path}' marked as translatable.", fg=typer.colors.GREEN)
    except errors.AddTranslatableFileError as e:
        typer.secho(f"Error marking file as translatable: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("remove")
def mark_untranslatable(
    ctx: typer.Context,
    file_paths: Annotated[list[str], typer.Argument(help="Path to the file (relative to project root or absolute).")]
):
    """Marks a file in the source directory as untranslatable."""
    project = get_project_from_context(ctx)
    try:
        for file_path in file_paths:
            project.set_file_translatability(file_path, False)
            typer.secho(f"File '{file_path}' marked as untranslatable.", fg=typer.colors.GREEN)
    except errors.AddTranslatableFileError as e:
        typer.secho(f"Error marking file as untranslatable: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("set-llm")
def set_llm(
    ctx: typer.Context, # For getting loaded project
    service: Annotated[str, typer.Argument(help="Name of the service providing a model")],
    model: Annotated[str, typer.Argument(help="Name of the model", case_sensitive=True)] # Typer handles Enum conversion
):
    """Sets or changes the standard LLM and the service providing the model."""
    project = get_project_from_context(ctx)
    try:
        project.set_llm_service_and_model(service, model)
        typer.secho(f"The service set to '{service}' with the model {model}", fg=typer.colors.GREEN)
    except errors.SetSourceDirError as e:
        typer.secho(f"Error setting service and model: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("set-reasoning-model")
def set_reasoning_model(
    ctx: typer.Context,
    service: Annotated[str, typer.Argument(help="Name of the service providing the reasoning model")],
    model: Annotated[str, typer.Argument(help="Name of the reasoning model", case_sensitive=True)],
):
    """Sets or changes the reasoning LLM and the service providing the model."""
    project = get_project_from_context(ctx)
    try:
        project.set_llm_reasoning_service_and_model(service, model)
        typer.secho(f"Reasoning model set to '{model}' on service '{service}'", fg=typer.colors.GREEN)
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error setting reasoning model: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("set-typst-func-args")
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
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error setting Typst function args: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("unset-typst-func-args")
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
    except errors.SetLLMServiceError as e:
        typer.secho(f"Error removing Typst function args: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("list")
def list_translatable_files(ctx: typer.Context):
    """Lists all files marked as translatable in the source directory."""
    project = get_project_from_context(ctx)
    try:
        files = project.get_translatable_files()
        if not files:
            typer.secho("No translatable files found.", fg=typer.colors.YELLOW)
            return
        typer.secho("Translatable files:", fg=typer.colors.BLUE)
        for f_path in files:
            # Try to make path relative to project root for cleaner display
            try:
                display_path = f_path.relative_to(project.root_path)
            except ValueError:
                display_path = f_path # If not under root_path (should not happen)
            typer.echo(f"  {display_path}")
    except errors.GetTranslatableFilesError as e:
        typer.secho(f"Error listing translatable files: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("info")
def info_on_project(ctx: typer.Context):
    """
    Provides an info about the project
    """
    project = get_project_from_context(ctx)
    print("Project Information:")
    print("\tProject Name: {}".format(project.config.get_name()) )
    print("\tRoot Path: {}".format(project.root_path))

    src_dir = project.config.get_src_dir()
    if src_dir is None:
        print("\tSource directory: Is not set")
    else:
        src_dir_name = src_dir.get_path().name
        src_dir_lang = src_dir.get_lang()
        llm_service = project.get_llm_service()
        llm_model = project.get_llm_model()
        llm_reasoning_service = project.get_llm_reasoning_service()
        llm_reasoning_model = project.get_llm_reasoning_model()
        print("\tSource language: {}".format(src_dir_lang))
        print("\tSource directory: {}".format(src_dir_name))
        print("\tStandard model: {} {}".format(llm_service, llm_model))
        if llm_reasoning_model:
            print("\tReasoning model: {} {}".format(llm_reasoning_service, llm_reasoning_model))
        else:
            print("\tReasoning model: Not set")
        typst_string_args = project.get_typst_translatable_string_args_by_function()
        if typst_string_args:
            print("\tTypst translatable string args:")
            for func, args in sorted(typst_string_args.items()):
                print("\t  {}: {}".format(func, ", ".join(args)))
        else:
            print("\tTypst translatable string args: Not set")


    custom_languages = project.config.custom_languages
    if custom_languages:
        print("Custom languages:")
        for name, suffix in sorted(custom_languages.items()):
            print("\t{:<20} suffix: {}".format(name, suffix))
    else:
        print("Custom languages: None")

    target_langs = project._get_target_languages()
    if len( target_langs ) == 0:
        print("\tTarget langauges: There is no target languages")
    else:
        print("Target languages:")
        for lang in target_langs:
            tgt_dir = project.config.get_target_dir_path_by_lang(lang)
            tgt_dir_name = None if tgt_dir is None else tgt_dir.name
            print("\tLanguage: {:<10} | Directory: {}".format(lang, tgt_dir_name))

@app.command("status")
def translation_status(
    ctx: typer.Context,
    files: Annotated[bool, typer.Option("--files", help="Show per-file chunk statistics.")] = False,
):
    """Shows translation progress: how many chunks are untranslated per language."""
    project = get_project_from_context(ctx)
    try:
        status = project.get_translation_status(include_files=files)
    except Exception as e:
        typer.secho(f"Error getting translation status: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"Source language: {status.source_lang}", fg=typer.colors.BLUE)

    if not status.target_langs:
        typer.secho("No target languages configured.", fg=typer.colors.YELLOW)
        return

    for lang_status in status.target_langs:
        total = lang_status.total_chunks
        translated = lang_status.translated_chunks
        untranslated = lang_status.untranslated_chunks
        proofread = lang_status.proofread_chunks
        needs_review = lang_status.needs_review_chunks
        if total == 0:
            line = f"  {lang_status.lang}: no cached chunks"
        else:
            pct = int(translated / total * 100)
            line = f"  {lang_status.lang}: {translated}/{total} chunks translated ({pct}%), {untranslated} untranslated"
            if translated > 0:
                pr_pct = int(proofread / translated * 100)
                line += f" | {proofread}/{translated} proofread ({pr_pct}%), {needs_review} need review"
        color = typer.colors.GREEN if untranslated == 0 and needs_review == 0 and total > 0 else typer.colors.YELLOW
        typer.secho(line, fg=color)

        if files and lang_status.files:
            for file_status in lang_status.files:
                f_total = file_status.total_chunks
                f_translated = file_status.translated_chunks
                f_untranslated = file_status.untranslated_chunks
                f_proofread = file_status.proofread_chunks
                f_needs_review = file_status.needs_review_chunks
                f_pct = int(f_translated / f_total * 100) if f_total else 0
                f_color = typer.colors.GREEN if f_untranslated == 0 and f_needs_review == 0 else typer.colors.YELLOW
                f_line = f"    {file_status.relative_path}: {f_translated}/{f_total} ({f_pct}%), {f_untranslated} untranslated"
                if f_translated > 0:
                    f_pr_pct = int(f_proofread / f_translated * 100)
                    f_line += f" | {f_proofread}/{f_translated} proofread ({f_pr_pct}%), {f_needs_review} need review"
                typer.secho(f_line, fg=f_color)

    if status.never_processed_files:
        typer.secho("\nFiles with no cached translations yet:", fg=typer.colors.YELLOW)
        for rel_path in status.never_processed_files:
            typer.echo(f"  {rel_path}")


@app.command("list-llms")
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

# --- Translation Commands ---
translate_app = typer.Typer(name="translate", help="Translate files", no_args_is_help=True)
app.add_typer(translate_app) # Sub-command of project

def _read_vocab_from_file(path: Path) -> list[dict]:
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)

async def _translate_file_command(project: Project, file_path_str: str, lang: str, vocab: Path | None, use_reasoning_model: bool = False):
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        vocabulary = None
        if vocab is not None:
            vocabulary = vocab_list_from_vocab_db(_read_vocab_from_file(vocab), project.get_source_langugage(), resolved_lang)

        await project.translate_single_file(file_path_str, resolved_lang, vocabulary, use_reasoning_model=use_reasoning_model)
        typer.secho(f"File '{file_path_str}' translated to {resolved_lang} successfully.", fg=typer.colors.GREEN)
    except errors.TranslateFileError as e:
        typer.secho(f"Error translating file '{file_path_str}': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during translation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@translate_app.command("file")
def translate_file_cli(
    ctx: typer.Context,
    file_path: Annotated[str, typer.Argument(help="Path to the translatable file.")],
    lang: Annotated[str, typer.Argument(help="Target language for translation (predefined or custom).", case_sensitive=False)],
    vocabulary: Annotated[Path | None, typer.Option(help="A path to the csv file with the vocabulary.", case_sensitive=False)] = None,
    use_reasoning_model: Annotated[bool, typer.Option("--use-reasoning-model", help="Use the configured reasoning model instead of the regular model.")] = False,
):
    """Translates a single specified translatable file."""
    project = get_project_from_context(ctx)
    asyncio.run(_translate_file_command(project, file_path, lang, vocabulary, use_reasoning_model=use_reasoning_model))


async def _translate_all_command(project: Project, lang: str, vocab: Path | None, use_reasoning_model: bool = False):
    try:
        resolved_lang = project.config.resolve_language(lang)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        vocabulary = None
        if vocab is not None:
            vocabulary = vocab_list_from_vocab_db(_read_vocab_from_file(vocab), project.get_source_langugage(), resolved_lang)

        await project.translate_all_for_language(resolved_lang, vocabulary, use_reasoning_model=use_reasoning_model)
        typer.secho(f"All translatable files processed for language {resolved_lang}.", fg=typer.colors.GREEN)
    except errors.TranslateFileError as e:
        typer.secho(f"Error during 'translate all' for {resolved_lang}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during 'translate all': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@translate_app.command("all")
def translate_all_cli(
    ctx: typer.Context,
    lang: Annotated[str, typer.Argument(help="Target language for translation (predefined or custom).", case_sensitive=False)],
    vocabulary: Annotated[Path | None, typer.Option(help="A path to the csv file with the vocabulary.", case_sensitive=False)] = None,
    use_reasoning_model: Annotated[bool, typer.Option("--use-reasoning-model", help="Use the configured reasoning model instead of the regular model.")] = False,
):
    """Translates all translatable files to the specified language."""
    project = get_project_from_context(ctx)
    asyncio.run(_translate_all_command(project, lang, vocabulary, use_reasoning_model=use_reasoning_model))


# ============ cache app =============
cache_app = typer.Typer(name="cache", help="Translation cache utilities", no_args_is_help=True)
app.add_typer(cache_app)

@cache_app.command("sync")
def sync_cache_cli(ctx: typer.Context):
    """Synchronizes the translation cache for all target languages using on-disk files."""
    project = get_project_from_context(ctx)
    try:
        project.sync_translation_cache()
        typer.secho("Translation cache synced for all target languages.", fg=typer.colors.GREEN)
    except errors.TranslationCacheSyncError as e:
        typer.secho(f"Error syncing translation cache: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during cache sync: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@cache_app.command("clear")
def clear_cache_cli(
    ctx: typer.Context,
    missing_chunks: Annotated[
        bool,
        typer.Option(
            "--missing-chunks",
            help="Remove cache entries that reference missing chunk files.",
        ),
    ] = False,
    all_cache: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Delete all cache entries for a language and/or file.",
        ),
    ] = False,
    lang: Annotated[
        str | None,
        typer.Option(
            "--lang",
            help="Limit cache deletion to a specific language (predefined or custom).",
            case_sensitive=False,
        ),
    ] = None,
    file_path: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help="Limit cache deletion to a specific project file path.",
        ),
    ] = None,
    keyword: Annotated[
        str | None,
        typer.Option(
            "--keyword",
            help="Limit cache deletion to chunks containing the keyword.",
        ),
    ] = None,
):
    """Clears translation cache entries based on cleanup flags."""
    if missing_chunks and all_cache:
        typer.secho(
            "Use only one cache clear action flag at a time (--missing-chunks or --all).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if (lang is not None or file_path is not None) and missing_chunks:
        typer.secho(
            "--lang and --file can only be used with --all.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if keyword is not None and not all_cache:
        typer.secho(
            "--keyword can only be used with --all.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if not missing_chunks and not all_cache:
        typer.secho(
            "No cache clear flags provided. Use --missing-chunks or --all.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    project = get_project_from_context(ctx)
    resolved_lang = None
    if lang is not None:
        try:
            resolved_lang = project.config.resolve_language(lang)
        except ValueError as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    try:
        if missing_chunks:
            stats = project.clear_translation_cache_missing_chunks()
            typer.secho(
                (
                    "Cache cleanup complete: "
                    f"{stats.removed_rows} row(s) removed, "
                    f"{stats.cleared_fields} field(s) cleared, "
                    f"{stats.removed_source_chunks} source chunk(s) removed, "
                    f"{stats.removed_target_chunks} target chunk(s) removed."
                ),
                fg=typer.colors.GREEN,
            )
        else:
            stats = project.clear_translation_cache_all(
                resolved_lang,
                str(file_path) if file_path else None,
                keyword,
            )
            if (
                file_path is not None
                and stats.removed_rows == 0
                and stats.cleared_fields == 0
                and stats.removed_chunk_files == 0
            ):
                typer.secho(
                    f"Warning: no cache entries found for '{file_path}'. "
                    "Make sure the path is relative to the source directory "
                    "or points to the file directly.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            typer.secho(
                (
                    "Cache deletion complete: "
                    f"{stats.removed_rows} row(s) removed, "
                    f"{stats.cleared_fields} field(s) cleared, "
                    f"{stats.removed_chunk_files} chunk file(s) removed."
                ),
                fg=typer.colors.GREEN,
            )
    except errors.TranslationCacheClearError as e:
        typer.secho(f"Error clearing translation cache: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during cache clear: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

# --- Main execution for CLI ---
# This callback is for global options like --project-dir if you add them
# For now, it's not strictly needed as get_project_from_context handles loading
# @app.callback()
# def main_global_options(
#    project_dir: Annotated[Optional[Path], typer.Option(help="Path to the project directory (if not current).")] = None
# ):
#    """
#    Directory Translation Tool
#    """
#    # Store project_dir in ctx.obj if needed by subcommands,
#    # or handle it directly in get_project_from_context.
#    pass


if __name__ == "__main__": 
    app()
