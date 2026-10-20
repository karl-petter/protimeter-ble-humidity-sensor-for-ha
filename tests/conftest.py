"""
Shared pytest fixtures for the Protimeter BLE test suite.

Parser tests (test_parser.py) exercise pure functions and happen to pull in
the whole custom_components.protimeter_ble package on import (importing a
submodule always runs the package's __init__.py first), which is why the
real `homeassistant`/`bleak` packages below are needed even for those.

Integration tests (test_init.py and friends) exercise config-entry
setup/unload/reload against a real, test-mode Home Assistant core, provided
by the pytest-homeassistant-custom-component plugin (auto-registered via its
pytest11 entry point - no explicit pytest_plugins line needed).
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ during tests."""
    yield
