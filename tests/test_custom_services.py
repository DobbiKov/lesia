import pytest
from pathlib import Path

from unified_model_caller import LLMCaller
import unified_model_caller.core as _umc_core

from lesia.constants import CONF_DIR, CUSTOM_SERVICES_DIR_NAME, CUSTOM_SERVICES_TEMPLATE_FILENAME
from lesia.project_manager import load_custom_services, init_project


_VALID_SERVICE = """\
from unified_model_caller import BaseService

class MyTestService(BaseService):
    def get_name(self) -> str:
        return "my-test-service"
    def requires_token(self) -> bool:
        return False
    def service_cooldown(self) -> int:
        return 0
    def call(self, model: str, prompt: str) -> str:
        return "ok"
"""


@pytest.fixture(autouse=True)
def restore_services():
    """Restore the LLMCaller service registry after each test."""
    original = dict(_umc_core._SERVICES)
    yield
    _umc_core._SERVICES.clear()
    _umc_core._SERVICES.update(original)


def _make_services_dir(tmp_path: Path) -> Path:
    conf_dir = tmp_path / CONF_DIR
    services_dir = conf_dir / CUSTOM_SERVICES_DIR_NAME
    services_dir.mkdir(parents=True)
    return conf_dir


def test_load_custom_services_no_dir(tmp_path: Path) -> None:
    conf_dir = tmp_path / CONF_DIR
    conf_dir.mkdir()
    before = set(LLMCaller.get_services())
    load_custom_services(conf_dir)
    assert set(LLMCaller.get_services()) == before


def test_load_custom_services_loads_valid_service(tmp_path: Path) -> None:
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "my_service.py").write_text(_VALID_SERVICE)

    load_custom_services(conf_dir)

    assert "my-test-service" in LLMCaller.get_services()


def test_load_custom_services_skips_template(tmp_path: Path) -> None:
    conf_dir = _make_services_dir(tmp_path)
    # Write the template content (which registers "my-service") under the template filename
    from lesia.project_manager import _CUSTOM_SERVICE_TEMPLATE
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / CUSTOM_SERVICES_TEMPLATE_FILENAME).write_text(_CUSTOM_SERVICE_TEMPLATE)

    before = set(LLMCaller.get_services())
    load_custom_services(conf_dir)
    assert set(LLMCaller.get_services()) == before


def test_load_custom_services_invalid_file_does_not_crash(tmp_path: Path) -> None:
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "bad_service.py").write_text("this is not valid python !!!@#")
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "good_service.py").write_text(_VALID_SERVICE)

    load_custom_services(conf_dir)  # must not raise

    assert "my-test-service" in LLMCaller.get_services()  # valid service still loaded


def test_init_project_creates_template(tmp_path: Path) -> None:
    init_project("test-proj", str(tmp_path))

    template_path = tmp_path / CONF_DIR / CUSTOM_SERVICES_DIR_NAME / CUSTOM_SERVICES_TEMPLATE_FILENAME
    assert template_path.exists()
    assert "BaseService" in template_path.read_text()


def _make_service_with_name(service_name: str) -> str:
    return f"""\
from unified_model_caller import BaseService

class ConflictService(BaseService):
    def get_name(self) -> str:
        return "{service_name}"
    def requires_token(self) -> bool:
        return False
    def service_cooldown(self) -> int:
        return 0
    def call(self, model: str, prompt: str) -> str:
        return "conflict"
"""


def test_load_custom_services_warns_but_loads_service_shadowing_builtin(tmp_path: Path) -> None:
    """A custom service that shadows a built-in is loaded (with a warning), not skipped."""
    conf_dir = _make_services_dir(tmp_path)
    builtin_name = LLMCaller.get_services()[0]  # grab any existing built-in name
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "shadow.py").write_text(
        _make_service_with_name(builtin_name)
    )

    load_custom_services(conf_dir)

    # The built-in service must have been replaced by the custom one
    assert _umc_core._SERVICES[builtin_name].__name__ == "ConflictService"


def test_load_custom_services_errors_on_conflicting_custom_services(tmp_path: Path) -> None:
    """Two custom services with the same name must raise ValueError."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "a_first.py").write_text(_VALID_SERVICE)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "b_shadow.py").write_text(
        _make_service_with_name("my-test-service")
    )

    with pytest.raises(ValueError, match="conflicts with another custom service"):
        load_custom_services(conf_dir)


# ---------------------------------------------------------------------------
# Multiple valid services
# ---------------------------------------------------------------------------

_VALID_SERVICE_2 = """\
from unified_model_caller import BaseService

class AnotherTestService(BaseService):
    def get_name(self) -> str:
        return "another-test-service"
    def requires_token(self) -> bool:
        return False
    def service_cooldown(self) -> int:
        return 0
    def call(self, model: str, prompt: str) -> str:
        return "ok2"
"""


def test_load_custom_services_multiple_valid_services(tmp_path: Path) -> None:
    """All valid service files in the directory are registered."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "a_service.py").write_text(_VALID_SERVICE)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "b_service.py").write_text(_VALID_SERVICE_2)

    load_custom_services(conf_dir)

    assert "my-test-service" in LLMCaller.get_services()
    assert "another-test-service" in LLMCaller.get_services()


# ---------------------------------------------------------------------------
# Files that fail to load
# ---------------------------------------------------------------------------

def test_load_custom_services_no_subclass_does_not_crash(tmp_path: Path) -> None:
    """A valid Python file with no BaseService subclass is skipped with a warning."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "no_subclass.py").write_text("x = 1 + 1\n")
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "good_service.py").write_text(_VALID_SERVICE)

    load_custom_services(conf_dir)  # must not raise

    assert "my-test-service" in LLMCaller.get_services()


def test_load_custom_services_runtime_error_in_file_does_not_crash(tmp_path: Path) -> None:
    """A file that raises at import time is skipped; other services still load."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "crash.py").write_text(
        "raise RuntimeError('intentional crash')\n"
    )
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "good_service.py").write_text(_VALID_SERVICE)

    load_custom_services(conf_dir)  # must not raise

    assert "my-test-service" in LLMCaller.get_services()


# ---------------------------------------------------------------------------
# Builtin shadow doesn't block subsequent services
# ---------------------------------------------------------------------------

def test_load_custom_services_builtin_shadow_does_not_block_others(tmp_path: Path) -> None:
    """After a builtin-shadowing file is loaded (with a warning), subsequent files still load."""
    conf_dir = _make_services_dir(tmp_path)
    builtin_name = LLMCaller.get_services()[0]
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "a_shadow.py").write_text(
        _make_service_with_name(builtin_name)
    )
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "b_new.py").write_text(_VALID_SERVICE)

    load_custom_services(conf_dir)

    assert _umc_core._SERVICES[builtin_name].__name__ == "ConflictService"
    assert "my-test-service" in LLMCaller.get_services()


# ---------------------------------------------------------------------------
# Custom conflict: first custom is still registered after error
# ---------------------------------------------------------------------------

def test_load_custom_services_first_custom_registered_before_conflict_error(tmp_path: Path) -> None:
    """When a custom-vs-custom conflict is detected, the first service is already registered."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "a_first.py").write_text(_VALID_SERVICE)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "b_conflict.py").write_text(
        _make_service_with_name("my-test-service")
    )

    with pytest.raises(ValueError, match="conflicts with another custom service"):
        load_custom_services(conf_dir)

    assert "my-test-service" in LLMCaller.get_services()
    assert _umc_core._SERVICES["my-test-service"].__name__ == "MyTestService"


# ---------------------------------------------------------------------------
# File with multiple subclasses
# ---------------------------------------------------------------------------

def _make_two_subclass_service(name_a: str, name_b: str) -> str:
    return f"""\
from unified_model_caller import BaseService

class ServiceA(BaseService):
    def get_name(self) -> str:
        return "{name_a}"
    def requires_token(self) -> bool:
        return False
    def service_cooldown(self) -> int:
        return 0
    def call(self, model: str, prompt: str) -> str:
        return "a"

class ServiceB(BaseService):
    def get_name(self) -> str:
        return "{name_b}"
    def requires_token(self) -> bool:
        return False
    def service_cooldown(self) -> int:
        return 0
    def call(self, model: str, prompt: str) -> str:
        return "b"
"""


def test_load_custom_services_file_with_two_subclasses_one_shadows_builtin(tmp_path: Path) -> None:
    """File with two subclasses where one shadows a builtin: both load, warning for the builtin."""
    conf_dir = _make_services_dir(tmp_path)
    builtin_name = LLMCaller.get_services()[0]
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "multi.py").write_text(
        _make_two_subclass_service(builtin_name, "brand-new-service")
    )

    load_custom_services(conf_dir)

    assert _umc_core._SERVICES[builtin_name].__name__ == "ServiceA"
    assert "brand-new-service" in LLMCaller.get_services()


def test_load_custom_services_file_with_two_subclasses_one_conflicts_with_custom(tmp_path: Path) -> None:
    """File with two subclasses where one conflicts with an already-loaded custom raises ValueError."""
    conf_dir = _make_services_dir(tmp_path)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "a_first.py").write_text(_VALID_SERVICE)
    (conf_dir / CUSTOM_SERVICES_DIR_NAME / "b_multi.py").write_text(
        _make_two_subclass_service("my-test-service", "brand-new-service")
    )

    with pytest.raises(ValueError, match="conflicts with another custom service"):
        load_custom_services(conf_dir)
