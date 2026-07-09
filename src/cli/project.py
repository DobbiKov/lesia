from pathlib import Path

import typer
from typing_extensions import Annotated

from lesia import errors
from ._common import get_project_from_context


def init(
    name: Annotated[str, typer.Option(help="Name for the new project.")] = "MyTranslationProject",
    path: Annotated[Path, typer.Option(help="Directory to initialize the project in. Defaults to current directory.")] = Path("."),
):
    """Initializes a new translation project."""
    from lesia.project_manager import init_project
    try:
        project = init_project(name, str(path.resolve()))
        typer.secho(f"Project '{project.config.name}' initialized successfully at {project.root_path}", fg=typer.colors.GREEN)
    except errors.InitProjectError as e:
        typer.secho(f"Error initializing project: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def info_on_project(ctx: typer.Context):
    """Provides an info about the project."""
    from lesia.constants import CUSTOM_SERVICES_DIR_NAME, CUSTOM_SERVICES_TEMPLATE_FILENAME
    from lesia.project_manager import _get_service_names_from_file

    project = get_project_from_context(ctx)

    print("Project name: {}".format(project.config.get_name()))
    try:
        rel_root = project.root_path.relative_to(Path.cwd())
        display_root = str(rel_root)
    except ValueError:
        display_root = str(project.root_path)
    print("Root Path: {}".format(display_root))

    src_dir = project.config.get_src_dir()
    if src_dir is None:
        print("Source language: Not set")
    else:
        src_dir_name = src_dir.get_path().name
        src_dir_lang = src_dir.get_lang()
        print("Source language:")
        print("- {}, directory: {}".format(src_dir_lang, src_dir_name))

    target_langs = project._get_target_languages()
    if len(target_langs) == 0:
        print("Target language(s): None")
    else:
        print("Target language(s):")
        for lang in target_langs:
            tgt_dir = project.config.get_target_dir_path_by_lang(lang)
            tgt_dir_name = None if tgt_dir is None else tgt_dir.name
            print("- {}, directory: {}".format(lang, tgt_dir_name))

    vocab_file_path = project.config.get_vocab_file_path()
    if vocab_file_path:
        print("Ontology: {}".format(vocab_file_path))
    else:
        print("Ontology: Not set")

    env_file_path = project.config.get_env_file_path()
    if env_file_path:
        print("Env file: {}".format(env_file_path))
    else:
        print("Env file: Not set (using shell environment variables)")

    llm_service = project.get_llm_service()
    llm_model = project.get_llm_model()
    llm_reasoning_service = project.get_llm_reasoning_service()
    llm_reasoning_model = project.get_llm_reasoning_model()
    print("Default models:")
    print("- lightweight: {} {}".format(llm_service, llm_model))
    if llm_reasoning_model:
        print("- heavyweight: {} {}".format(llm_reasoning_service, llm_reasoning_model))
    else:
        print("- heavyweight: Not set")

    print("XML retries before reasoning: {}".format(project.get_xml_retries_before_reasoning()))

    typst_string_args = project.get_typst_translatable_string_args_by_function()
    if typst_string_args:
        print("Typst translatable string args:")
        for func, args in sorted(typst_string_args.items()):
            print("- {}: {}".format(func, ", ".join(args)))
    else:
        print("Typst translatable string args: Not set")

    latex_settings = project.get_latex_settings()
    placeholder_envs = latex_settings["extra_placeholder_envs"]
    math_envs = latex_settings["extra_math_envs"]
    placeholder_cmds = latex_settings["extra_placeholder_commands"]
    cmd_args = latex_settings["command_translatable_args"]
    cmd_specs = latex_settings["custom_command_specs"]
    if placeholder_envs or math_envs or placeholder_cmds or cmd_args or cmd_specs:
        print("LaTeX settings:")
        if placeholder_envs:
            print("  Placeholder envs: {}".format(", ".join(sorted(placeholder_envs))))
        if math_envs:
            print("  Math envs: {}".format(", ".join(sorted(math_envs))))
        if placeholder_cmds:
            print("  Placeholder commands: {}".format(", ".join(sorted(placeholder_cmds))))
        if cmd_specs:
            print("  Custom command specs:")
            for cmd, spec in sorted(cmd_specs.items()):
                print("    {}: mandatory={}, optional={}".format(
                    cmd, spec.get("mandatory", 0), spec.get("optional", 0)
                ))
        if cmd_args:
            print("  Command translatable args:")
            for cmd, spec in sorted(cmd_args.items()):
                parts = []
                if "mandatory" in spec:
                    parts.append("mandatory={}".format(spec["mandatory"]))
                if "optional" in spec:
                    parts.append("optional={}".format(spec["optional"]))
                print("    {}: {}".format(cmd, ", ".join(parts)))
    else:
        print("LaTeX settings: Not set")

    custom_languages = project.config.custom_languages
    custom_shorts = project.config.custom_language_shorts
    shorts_by_name = {full: short for short, full in custom_shorts.items()}
    if custom_languages:
        print("Custom languages:")
        for lang_name, suffix in sorted(custom_languages.items()):
            short = shorts_by_name.get(lang_name)
            short_str = f" (short: {short})" if short else ""
            print("- {}, suffix: {}{}".format(lang_name, suffix, short_str))
    else:
        print("Custom languages: None")

    services_dir = project.config_dir_path / CUSTOM_SERVICES_DIR_NAME
    custom_service_names = []
    if services_dir.is_dir():
        for service_file in sorted(services_dir.glob("*.py")):
            if service_file.name == CUSTOM_SERVICES_TEMPLATE_FILENAME:
                continue
            custom_service_names.extend(_get_service_names_from_file(service_file))
    if custom_service_names:
        print("Custom llm services:")
        for name in custom_service_names:
            print("- {}".format(name))
    else:
        print("Custom llm services: None")

    print("Custom llm models: None")


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
            try:
                display_path = f_path.relative_to(project.root_path)
            except ValueError:
                display_path = f_path
            typer.echo(f"  {display_path}")
    except errors.GetTranslatableFilesError as e:
        typer.secho(f"Error listing translatable files: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def sync_files(ctx: typer.Context):
    """Synchronizes untranslatable files from the source to all target directories."""
    project = get_project_from_context(ctx)
    try:
        project.sync_untranslatable_files()
        typer.secho("Untranslatable files synchronized successfully.", fg=typer.colors.GREEN)
    except errors.SyncFilesError as e:
        typer.secho(f"Error synchronizing files: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
