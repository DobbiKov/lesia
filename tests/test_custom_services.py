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
