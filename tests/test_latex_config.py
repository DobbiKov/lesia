"""Tests for the configurable LaTeX parsing system.

Covers:
- configure_latex_settings / reset_latex_settings (module-level API)
- extra_placeholder_envs
- extra_math_envs
- extra_placeholder_commands
- command_translatable_args (known macros via pylatexenc)
- custom_command_specs + command_translatable_args (unknown/custom macros)
- ProjectConfig field validation and get/set/remove methods
- Interaction between settings (e.g. placeholder_commands takes priority)
- reset clears all runtime state
"""

import pytest

from lesia.xml_manipulator_mod.latex import (
    configure_latex_settings,
    parse_latex,
    reset_latex_settings,
)
from lesia.project_config_models import ProjectConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _texts(segments):
    """Return only the text-type segments' content."""
    return [content for seg_type, content in segments if seg_type == "text"]


def _placeholders(segments):
    """Return only the placeholder-type segments' content."""
    return [content for seg_type, content in segments if seg_type == "placeholder"]


def _types(segments):
    return [seg_type for seg_type, _ in segments]


def _joined_placeholders(segments):
    return "".join(_placeholders(segments))


def _has_text(segments, substring: str) -> bool:
    """Return True if any text segment contains the given substring."""
    return any(substring in content for content in _texts(segments))


@pytest.fixture(autouse=True)
def reset_after_each_test():
    """Guarantee a clean module state before and after every test."""
    reset_latex_settings()
    yield
    reset_latex_settings()


# ===========================================================================
# configure_latex_settings / reset_latex_settings
# ===========================================================================

class TestConfigureAndReset:
    def test_default_state_parses_text_normally(self):
        result = parse_latex(r"Hello world")
        assert "Hello world" in _texts(result)

    def test_reset_clears_extra_placeholder_envs(self):
        configure_latex_settings(extra_placeholder_envs=["myenv"])
        reset_latex_settings()
        # After reset, \begin{myenv} body should be translatable again
        result = parse_latex(r"\begin{myenv}some text\end{myenv}")
        assert "some text" in _texts(result)

    def test_reset_clears_extra_placeholder_commands(self):
        configure_latex_settings(extra_placeholder_commands=["mycmd"])
        reset_latex_settings()
        result = parse_latex(r"\mycmd{translatable}")
        assert "translatable" in _texts(result)

    def test_reset_clears_command_translatable_args(self):
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 2}},
            command_translatable_args={"myfig": {"mandatory": [2]}},
        )
        reset_latex_settings()
        # After reset, no spec → both args walked as text (default)
        result = parse_latex(r"\myfig{label}{caption}")
        assert "label" in _texts(result)
        assert "caption" in _texts(result)

    def test_configure_strips_whitespace_from_names(self):
        configure_latex_settings(extra_placeholder_envs=["  myenv  "])
        result = parse_latex(r"\begin{myenv}code here\end{myenv}")
        assert "code here" not in _texts(result)

    def test_configure_ignores_empty_strings(self):
        # Should not raise; empty entries are silently skipped
        configure_latex_settings(
            extra_placeholder_envs=["", "  "],
            extra_placeholder_commands=[""],
        )
        result = parse_latex(r"Hello")
        assert "Hello" in _texts(result)

    def test_multiple_configure_calls_overwrite_previous(self):
        configure_latex_settings(extra_placeholder_envs=["envA"])
        configure_latex_settings(extra_placeholder_envs=["envB"])
        # envA is no longer registered; envB is
        result_a = parse_latex(r"\begin{envA}text\end{envA}")
        result_b = parse_latex(r"\begin{envB}text\end{envB}")
        assert "text" in _texts(result_a)   # envA now translatable
        assert "text" not in _texts(result_b)  # envB is placeholder


# ===========================================================================
# extra_placeholder_envs
# ===========================================================================

class TestExtraPlaceholderEnvs:
    def test_unknown_env_body_is_translatable_by_default(self):
        result = parse_latex(r"\begin{myenv}some text\end{myenv}")
        assert "some text" in _texts(result)

    def test_configured_env_becomes_full_placeholder(self):
        configure_latex_settings(extra_placeholder_envs=["myenv"])
        result = parse_latex(r"\begin{myenv}some text\end{myenv}")
        assert "some text" not in _texts(result)
        joined = _joined_placeholders(result)
        assert "myenv" in joined

    def test_configured_env_does_not_affect_other_envs(self):
        configure_latex_settings(extra_placeholder_envs=["mycode"])
        result = parse_latex(r"\begin{mytext}readable text\end{mytext}")
        assert "readable text" in _texts(result)

    def test_multiple_placeholder_envs(self):
        configure_latex_settings(extra_placeholder_envs=["envA", "envB"])
        result_a = parse_latex(r"\begin{envA}secret\end{envA}")
        result_b = parse_latex(r"\begin{envB}hidden\end{envB}")
        assert "secret" not in _texts(result_a)
        assert "hidden" not in _texts(result_b)

    def test_hardcoded_verbatim_still_placeholder(self):
        # verbatim is hardcoded; configure_latex_settings should not remove it
        result = parse_latex(r"\begin{verbatim}printf(x)\end{verbatim}")
        assert "printf(x)" not in _texts(result)

    def test_env_with_surrounding_text(self):
        configure_latex_settings(extra_placeholder_envs=["code"])
        result = parse_latex(r"Before \begin{code}x = 1\end{code} after")
        assert _has_text(result, "Before")
        assert _has_text(result, "after")
        assert not _has_text(result, "x = 1")


# ===========================================================================
# extra_math_envs
# ===========================================================================

class TestExtraMathEnvs:
    def test_unknown_env_body_is_translatable_by_default(self):
        result = parse_latex(r"\begin{mymath}x + y\end{mymath}")
        assert "x + y" in _texts(result)

    def test_configured_math_env_body_is_not_translatable(self):
        configure_latex_settings(extra_math_envs=["mymath"])
        result = parse_latex(r"\begin{mymath}x + y\end{mymath}")
        assert "x + y" not in _texts(result)

    def test_hardcoded_equation_env_stays_math(self):
        result = parse_latex(r"\begin{equation}E = mc^2\end{equation}")
        assert "E = mc^2" not in _texts(result)

    def test_math_env_begin_end_are_placeholders(self):
        configure_latex_settings(extra_math_envs=["mymath"])
        result = parse_latex(r"\begin{mymath}x\end{mymath}")
        joined = _joined_placeholders(result)
        assert "\\begin{mymath}" in joined
        assert "\\end{mymath}" in joined

    def test_custom_math_env_body_is_treated_as_math_not_text(self):
        # Custom math env body is walked as math — arbitrary text inside is not translated
        configure_latex_settings(extra_math_envs=["myeq"])
        result = parse_latex(r"\begin{myeq}x + y\end{myeq}")
        assert not _has_text(result, "x + y")


# ===========================================================================
# extra_placeholder_commands
# ===========================================================================

class TestExtraPlaceholderCommands:
    def test_unknown_command_args_are_translatable_by_default(self):
        result = parse_latex(r"\mycmd{translatable content}")
        assert "translatable content" in _texts(result)

    def test_configured_command_name_becomes_placeholder(self):
        # For unknown macros (no spec), only the command NAME becomes a placeholder;
        # the {..} args are sibling group nodes and still get walked as text.
        configure_latex_settings(extra_placeholder_commands=["myref"])
        result = parse_latex(r"See \myref{fig:1} for details")
        joined = _joined_placeholders(result)
        assert "\\myref" in joined

    def test_configured_command_surrounding_text_still_translatable(self):
        configure_latex_settings(extra_placeholder_commands=["myref"])
        result = parse_latex(r"Before \myref{x} after")
        assert _has_text(result, "Before")
        assert _has_text(result, "after")

    def test_placeholder_command_with_spec_makes_whole_command_placeholder(self):
        # Combining custom_command_specs + extra_placeholder_commands is the correct
        # way to make an unknown macro (including its args) fully non-translatable.
        configure_latex_settings(
            custom_command_specs={"myref": {"mandatory": 1}},
            extra_placeholder_commands=["myref"],
        )
        result = parse_latex(r"See \myref{fig:1} for details")
        assert "fig:1" not in _texts(result)
        joined = _joined_placeholders(result)
        assert "\\myref{fig:1}" in joined

    def test_multiple_placeholder_commands_names_are_placeholders(self):
        configure_latex_settings(extra_placeholder_commands=["cmdA", "cmdB"])
        result = parse_latex(r"\cmdA{x} and \cmdB{y}")
        joined = _joined_placeholders(result)
        assert "\\cmdA" in joined
        assert "\\cmdB" in joined


# ===========================================================================
# command_translatable_args — known macros (no custom spec needed)
# ===========================================================================

class TestCommandTranslatableArgsKnownMacros:
    def test_custom_macro_with_spec_only_second_mandatory_arg_translatable(self):
        # command_translatable_args only works when pylatexenc knows the macro spec.
        # For unknown macros, register them with custom_command_specs first.
        configure_latex_settings(
            custom_command_specs={"mycolor": {"mandatory": 2}},
            command_translatable_args={"mycolor": {"mandatory": [2]}},
        )
        result = parse_latex(r"\mycolor{red}{Hello world}")
        assert "Hello world" in _texts(result)
        assert "red" not in _texts(result)

    def test_custom_macro_with_spec_first_arg_is_placeholder(self):
        configure_latex_settings(
            custom_command_specs={"mycolor": {"mandatory": 2}},
            command_translatable_args={"mycolor": {"mandatory": [2]}},
        )
        result = parse_latex(r"\mycolor{blue}{Some text}")
        joined = _joined_placeholders(result)
        assert "blue" in joined

    def test_custom_macro_with_spec_footnote_style(self):
        configure_latex_settings(
            custom_command_specs={"myfootnote": {"mandatory": 1}},
            command_translatable_args={"myfootnote": {"mandatory": [1]}},
        )
        result = parse_latex(r"\myfootnote{This is a footnote.}")
        assert "This is a footnote." in _texts(result)

    def test_unknown_macro_both_args_translatable_by_default(self):
        # Without spec or config, unknown macro args are sibling groups → walked as text
        result = parse_latex(r"\textcolor{red}{Hello}")
        assert "Hello" in _texts(result)
        assert "red" in _texts(result)

    def test_custom_macro_empty_mandatory_list_makes_all_args_placeholders(self):
        configure_latex_settings(
            custom_command_specs={"mycolor": {"mandatory": 2}},
            command_translatable_args={"mycolor": {"mandatory": []}},
        )
        result = parse_latex(r"\mycolor{red}{Hello}")
        assert "Hello" not in _texts(result)
        assert "red" not in _texts(result)


# ===========================================================================
# custom_command_specs + command_translatable_args
# ===========================================================================

class TestCustomCommandSpecs:
    def test_custom_macro_all_args_translatable_without_config(self):
        # Without spec, unknown macro args are sibling nodes — all walked as text
        result = parse_latex(r"\myfig{label}{caption}")
        assert "label" in _texts(result)
        assert "caption" in _texts(result)

    def test_custom_spec_registers_macro_with_pylatexenc(self):
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 2}},
            command_translatable_args={"myfig": {"mandatory": [2]}},
        )
        result = parse_latex(r"\myfig{fig:label}{My caption here}")
        assert "My caption here" in _texts(result)
        assert "fig:label" not in _texts(result)

    def test_custom_spec_mandatory_only_first_arg_translatable(self):
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 2}},
            command_translatable_args={"myfig": {"mandatory": [1]}},
        )
        result = parse_latex(r"\myfig{First arg}{Second arg}")
        assert "First arg" in _texts(result)
        assert "Second arg" not in _texts(result)

    def test_custom_spec_with_optional_arg_not_translatable(self):
        configure_latex_settings(
            custom_command_specs={"mybox": {"mandatory": 2, "optional": 1}},
            command_translatable_args={"mybox": {"mandatory": [2], "optional": []}},
        )
        result = parse_latex(r"\mybox[fig:1]{My Title}{Body text here}")
        assert "Body text here" in _texts(result)
        assert "My Title" not in _texts(result)
        assert "fig:1" not in _texts(result)

    def test_custom_spec_with_optional_arg_translatable(self):
        configure_latex_settings(
            custom_command_specs={"mybox": {"mandatory": 1, "optional": 1}},
            command_translatable_args={"mybox": {"mandatory": [1], "optional": [1]}},
        )
        result = parse_latex(r"\mybox[Short desc]{Body text}")
        assert "Short desc" in _texts(result)
        assert "Body text" in _texts(result)

    def test_custom_spec_all_mandatory_args_translatable(self):
        configure_latex_settings(
            custom_command_specs={"mybox": {"mandatory": 2, "optional": 1}},
            command_translatable_args={"mybox": {"mandatory": [1, 2], "optional": []}},
        )
        result = parse_latex(r"\mybox[label]{Title here}{Body here}")
        assert "Title here" in _texts(result)
        assert "Body here" in _texts(result)
        assert "label" not in _texts(result)

    def test_custom_spec_without_translatable_args_config(self):
        # Spec registered but no command_translatable_args → default (all args walked)
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 2}},
        )
        result = parse_latex(r"\myfig{label}{caption}")
        assert "label" in _texts(result)
        assert "caption" in _texts(result)

    def test_custom_spec_zero_optional(self):
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 3, "optional": 0}},
            command_translatable_args={"myfig": {"mandatory": [3]}},
        )
        result = parse_latex(r"\myfig{a}{b}{translatable}")
        assert "translatable" in _texts(result)
        assert "a" not in _texts(result)
        assert "b" not in _texts(result)

    def test_command_spec_does_not_affect_unrelated_commands(self):
        configure_latex_settings(
            custom_command_specs={"myfig": {"mandatory": 2}},
            command_translatable_args={"myfig": {"mandatory": [2]}},
        )
        result = parse_latex(r"\other{always translatable}")
        assert "always translatable" in _texts(result)


# ===========================================================================
# Interaction / priority
# ===========================================================================

class TestInteractions:
    def test_placeholder_command_with_spec_takes_priority_over_translatable_args(self):
        # If a command is in both placeholder_commands and command_translatable_args,
        # placeholder wins. With a spec registered, the whole command is a placeholder.
        configure_latex_settings(
            custom_command_specs={"mycmd": {"mandatory": 1}},
            extra_placeholder_commands=["mycmd"],
            command_translatable_args={"mycmd": {"mandatory": [1]}},
        )
        result = parse_latex(r"\mycmd{should not translate}")
        assert "should not translate" not in _texts(result)

    def test_placeholder_env_takes_priority_over_default_env_behavior(self):
        configure_latex_settings(extra_placeholder_envs=["myenv"])
        result = parse_latex(r"\begin{myenv}hidden\end{myenv}")
        assert "hidden" not in _texts(result)

    def test_extra_math_env_body_is_not_translated(self):
        # Custom math env body is walked as math — plain text inside is not translated
        configure_latex_settings(extra_math_envs=["myeq"])
        result = parse_latex(r"\begin{myeq}x + y\end{myeq}")
        assert "x + y" not in _texts(result)

    def test_settings_persist_across_multiple_parse_calls(self):
        # Module-level settings stay active until reset; two consecutive calls both apply them
        configure_latex_settings(
            custom_command_specs={"myref": {"mandatory": 1}},
            extra_placeholder_commands=["myref"],
        )
        parse_latex(r"\myref{x}")  # first call
        result = parse_latex(r"\myref{y}")  # second call — settings still active
        assert "y" not in _texts(result)

    def test_hardcoded_placeholder_command_names_are_always_placeholders(self):
        # Even without custom specs, hardcoded placeholder command names are placeholders
        configure_latex_settings(extra_placeholder_commands=["newcmd"])
        result_ref = parse_latex(r"\ref{fig:1}")
        result_cite = parse_latex(r"\cite{smith2020}")
        joined_ref = _joined_placeholders(result_ref)
        joined_cite = _joined_placeholders(result_cite)
        assert "\\ref" in joined_ref
        assert "\\cite" in joined_cite


# ===========================================================================
# Predefined placeholder commands — arguments must NOT be translatable text
# ===========================================================================

class TestPredefinedPlaceholderCommands:
    """Ensure that every built-in placeholder command is treated as a single
    placeholder including its arguments — not just the command name."""

    def test_label_is_full_placeholder(self):
        result = parse_latex(r"\label{fig:myfig}")
        assert "fig:myfig" not in _texts(result)
        assert r"\label{fig:myfig}" in _joined_placeholders(result)

    def test_input_is_full_placeholder(self):
        result = parse_latex(r"\input{chapter1}")
        assert "chapter1" not in _texts(result)
        assert r"\input{chapter1}" in _joined_placeholders(result)

    def test_include_is_full_placeholder(self):
        result = parse_latex(r"\include{appendix}")
        assert "appendix" not in _texts(result)
        assert r"\include{appendix}" in _joined_placeholders(result)

    def test_ref_is_full_placeholder(self):
        result = parse_latex(r"\ref{eq:1}")
        assert "eq:1" not in _texts(result)
        assert r"\ref{eq:1}" in _joined_placeholders(result)

    def test_autoref_is_full_placeholder(self):
        result = parse_latex(r"\autoref{sec:intro}")
        assert "sec:intro" not in _texts(result)
        assert r"\autoref{sec:intro}" in _joined_placeholders(result)

    def test_cite_is_full_placeholder(self):
        result = parse_latex(r"\cite{smith2020}")
        assert "smith2020" not in _texts(result)
        assert r"\cite{smith2020}" in _joined_placeholders(result)

    def test_cite_with_optional_note_is_full_placeholder(self):
        result = parse_latex(r"\cite[p.~5]{smith2020}")
        assert "smith2020" not in _texts(result)
        assert "p.~5" not in _texts(result)

    def test_includegraphics_is_full_placeholder(self):
        result = parse_latex(r"\includegraphics{figure.png}")
        assert "figure.png" not in _texts(result)
        assert r"\includegraphics{figure.png}" in _joined_placeholders(result)

    def test_includegraphics_with_options_is_full_placeholder(self):
        result = parse_latex(r"\includegraphics[width=0.5\textwidth]{figure.png}")
        assert "figure.png" not in _texts(result)

    def test_href_is_full_placeholder(self):
        result = parse_latex(r"\href{https://example.com}{click here}")
        assert "https://example.com" not in _texts(result)
        assert "click here" not in _texts(result)
        assert r"\href{https://example.com}{click here}" in _joined_placeholders(result)

    def test_url_is_full_placeholder(self):
        result = parse_latex(r"\url{https://example.com}")
        assert "https://example.com" not in _texts(result)
        assert r"\url{https://example.com}" in _joined_placeholders(result)

    def test_path_is_full_placeholder(self):
        result = parse_latex(r"\path{/usr/local/bin}")
        assert "/usr/local/bin" not in _texts(result)
        assert r"\path{/usr/local/bin}" in _joined_placeholders(result)

    def test_frac_is_full_placeholder(self):
        result = parse_latex(r"\frac{1}{2}")
        assert "1" not in _texts(result)
        assert "2" not in _texts(result)
        assert r"\frac{1}{2}" in _joined_placeholders(result)

    def test_sqrt_is_full_placeholder(self):
        result = parse_latex(r"\sqrt{x}")
        assert "x" not in _texts(result)
        assert r"\sqrt{x}" in _joined_placeholders(result)

    def test_placeholder_commands_with_surrounding_text(self):
        # Surrounding text must remain translatable
        result = parse_latex(r"See \ref{fig:1} for details.")
        assert _has_text(result, "See")
        assert _has_text(result, "for details.")
        assert "fig:1" not in _texts(result)


# ===========================================================================
# ProjectConfig — field validation
# ===========================================================================

class TestProjectConfigLatexFields:

    def _make_config(self):
        return ProjectConfig.new("test")

    # --- placeholder envs ---

    def test_add_placeholder_env(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        assert "myenv" in cfg.latex_extra_placeholder_envs

    def test_add_placeholder_env_idempotent(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        cfg.add_latex_placeholder_env("myenv")
        assert cfg.latex_extra_placeholder_envs.count("myenv") == 1

    def test_add_placeholder_env_empty_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.add_latex_placeholder_env("")

    def test_remove_placeholder_env(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        cfg.remove_latex_placeholder_env("myenv")
        assert "myenv" not in cfg.latex_extra_placeholder_envs

    def test_remove_placeholder_env_not_present_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.remove_latex_placeholder_env("nonexistent")

    # --- math envs ---

    def test_add_math_env(self):
        cfg = self._make_config()
        cfg.add_latex_math_env("mymath")
        assert "mymath" in cfg.latex_extra_math_envs

    def test_add_math_env_idempotent(self):
        cfg = self._make_config()
        cfg.add_latex_math_env("mymath")
        cfg.add_latex_math_env("mymath")
        assert cfg.latex_extra_math_envs.count("mymath") == 1

    def test_add_math_env_empty_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.add_latex_math_env("")

    def test_remove_math_env(self):
        cfg = self._make_config()
        cfg.add_latex_math_env("mymath")
        cfg.remove_latex_math_env("mymath")
        assert "mymath" not in cfg.latex_extra_math_envs

    def test_remove_math_env_not_present_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.remove_latex_math_env("nonexistent")

    # --- placeholder commands ---

    def test_add_placeholder_command(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_command("myref")
        assert "myref" in cfg.latex_extra_placeholder_commands

    def test_add_placeholder_command_idempotent(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_command("myref")
        cfg.add_latex_placeholder_command("myref")
        assert cfg.latex_extra_placeholder_commands.count("myref") == 1

    def test_add_placeholder_command_empty_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.add_latex_placeholder_command("")

    def test_remove_placeholder_command(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_command("myref")
        cfg.remove_latex_placeholder_command("myref")
        assert "myref" not in cfg.latex_extra_placeholder_commands

    def test_remove_placeholder_command_not_present_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.remove_latex_placeholder_command("nonexistent")

    # --- command_translatable_args ---

    def test_set_command_translatable_args_mandatory_only(self):
        cfg = self._make_config()
        cfg.set_latex_command_translatable_args("myfig", mandatory=[2])
        assert cfg.latex_command_translatable_args["myfig"]["mandatory"] == [2]

    def test_set_command_translatable_args_both(self):
        cfg = self._make_config()
        cfg.set_latex_command_translatable_args("mybox", mandatory=[2], optional=[1])
        assert cfg.latex_command_translatable_args["mybox"]["mandatory"] == [2]
        assert cfg.latex_command_translatable_args["mybox"]["optional"] == [1]

    def test_set_command_translatable_args_deduplicates_and_sorts(self):
        cfg = self._make_config()
        cfg.set_latex_command_translatable_args("cmd", mandatory=[3, 1, 2, 1])
        assert cfg.latex_command_translatable_args["cmd"]["mandatory"] == [1, 2, 3]

    def test_set_command_translatable_args_empty_name_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_command_translatable_args("", mandatory=[1])

    def test_set_command_translatable_args_zero_index_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_command_translatable_args("cmd", mandatory=[0])

    def test_set_command_translatable_args_negative_index_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_command_translatable_args("cmd", mandatory=[-1])

    def test_set_command_translatable_args_neither_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_command_translatable_args("cmd")

    def test_remove_command_translatable_args(self):
        cfg = self._make_config()
        cfg.set_latex_command_translatable_args("myfig", mandatory=[2])
        cfg.remove_latex_command_translatable_args("myfig")
        assert "myfig" not in cfg.latex_command_translatable_args

    def test_remove_command_translatable_args_not_present_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.remove_latex_command_translatable_args("nonexistent")

    # --- custom_command_specs ---

    def test_set_custom_command_spec_mandatory_only(self):
        cfg = self._make_config()
        cfg.set_latex_custom_command_spec("myfig", mandatory=2)
        assert cfg.latex_custom_command_specs["myfig"]["mandatory"] == 2
        assert cfg.latex_custom_command_specs["myfig"]["optional"] == 0

    def test_set_custom_command_spec_with_optional(self):
        cfg = self._make_config()
        cfg.set_latex_custom_command_spec("mybox", mandatory=2, optional=1)
        assert cfg.latex_custom_command_specs["mybox"]["mandatory"] == 2
        assert cfg.latex_custom_command_specs["mybox"]["optional"] == 1

    def test_set_custom_command_spec_empty_name_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_custom_command_spec("", mandatory=1)

    def test_set_custom_command_spec_negative_mandatory_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_custom_command_spec("cmd", mandatory=-1)

    def test_set_custom_command_spec_negative_optional_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_custom_command_spec("cmd", mandatory=1, optional=-1)

    def test_set_custom_command_spec_all_zero_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.set_latex_custom_command_spec("cmd", mandatory=0, optional=0)

    def test_remove_custom_command_spec(self):
        cfg = self._make_config()
        cfg.set_latex_custom_command_spec("myfig", mandatory=2)
        cfg.remove_latex_custom_command_spec("myfig")
        assert "myfig" not in cfg.latex_custom_command_specs

    def test_remove_custom_command_spec_not_present_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError):
            cfg.remove_latex_custom_command_spec("nonexistent")

    # --- get_latex_settings ---

    def test_get_latex_settings_returns_all_fields(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        cfg.add_latex_math_env("mymath")
        cfg.add_latex_placeholder_command("myref")
        cfg.set_latex_command_translatable_args("myfig", mandatory=[2])
        cfg.set_latex_custom_command_spec("myfig", mandatory=2)

        settings = cfg.get_latex_settings()

        assert "myenv" in settings["extra_placeholder_envs"]
        assert "mymath" in settings["extra_math_envs"]
        assert "myref" in settings["extra_placeholder_commands"]
        assert settings["command_translatable_args"]["myfig"]["mandatory"] == [2]
        assert settings["custom_command_specs"]["myfig"]["mandatory"] == 2

    def test_get_latex_settings_returns_empty_defaults(self):
        cfg = self._make_config()
        settings = cfg.get_latex_settings()
        assert settings["extra_placeholder_envs"] == []
        assert settings["extra_math_envs"] == []
        assert settings["extra_placeholder_commands"] == []
        assert settings["command_translatable_args"] == {}
        assert settings["custom_command_specs"] == {}

    def test_get_latex_settings_returns_copies_not_references(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        settings = cfg.get_latex_settings()
        settings["extra_placeholder_envs"].append("other")
        # Original should be unaffected
        assert "other" not in cfg.latex_extra_placeholder_envs

    # --- JSON round-trip ---

    def test_config_serialises_and_deserialises_latex_fields(self):
        cfg = self._make_config()
        cfg.add_latex_placeholder_env("myenv")
        cfg.add_latex_math_env("mymath")
        cfg.add_latex_placeholder_command("myref")
        cfg.set_latex_command_translatable_args("myfig", mandatory=[2])
        cfg.set_latex_custom_command_spec("myfig", mandatory=2, optional=1)

        json_str = cfg.model_dump_json()
        cfg2 = ProjectConfig.model_validate_json(json_str)

        assert "myenv" in cfg2.latex_extra_placeholder_envs
        assert "mymath" in cfg2.latex_extra_math_envs
        assert "myref" in cfg2.latex_extra_placeholder_commands
        assert cfg2.latex_command_translatable_args["myfig"]["mandatory"] == [2]
        assert cfg2.latex_custom_command_specs["myfig"]["mandatory"] == 2
        assert cfg2.latex_custom_command_specs["myfig"]["optional"] == 1
