"""Tests for the amplifierd package skeleton structure."""

from pathlib import Path

import pytest

# Root of the amplifierd project (two levels up from tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "amplifierd"


# --- Package import tests ---


@pytest.mark.unit
class TestPackageImports:
    """Verify all packages are importable."""

    def test_import_amplifierd(self):
        import amplifierd

        assert amplifierd is not None

    def test_version(self):
        import amplifierd

        assert amplifierd.__version__ == "0.1.0"

    def test_import_state(self):
        import amplifierd.state

        assert amplifierd.state is not None

    def test_import_models(self):
        import amplifierd.models

        assert amplifierd.models is not None

    def test_import_routes(self):
        import amplifierd.routes

        assert amplifierd.routes is not None


# --- Directory structure tests ---


@pytest.mark.unit
class TestDirectoryStructure:
    """Verify all expected directories and files exist."""

    def test_src_amplifierd_init(self):
        assert (SRC_ROOT / "__init__.py").is_file()

    def test_src_amplifierd_main(self):
        assert (SRC_ROOT / "__main__.py").is_file()

    def test_state_package(self):
        assert (SRC_ROOT / "state" / "__init__.py").is_file()

    def test_models_package(self):
        assert (SRC_ROOT / "models" / "__init__.py").is_file()

    def test_routes_package(self):
        assert (SRC_ROOT / "routes" / "__init__.py").is_file()


# --- pyproject.toml tests ---


@pytest.mark.unit
class TestPyprojectToml:
    """Verify pyproject.toml exists and has key fields."""

    @pytest.fixture(autouse=True)
    def _read_pyproject(self):
        self.content = (PROJECT_ROOT / "pyproject.toml").read_text()

    def test_pyproject_exists(self):
        assert (PROJECT_ROOT / "pyproject.toml").is_file()

    def test_pyproject_has_project_name(self):
        assert 'name = "amplifierd"' in self.content

    def test_pyproject_has_version(self):
        assert 'version = "0.1.0"' in self.content

    def test_pyproject_has_cli_script(self):
        assert 'amplifierd = "amplifierd.cli:main"' in self.content
