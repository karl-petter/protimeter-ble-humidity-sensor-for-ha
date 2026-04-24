"""
Stub out all Home Assistant and BLE dependencies so parser.py can be imported
in a plain Python / pytest environment without a running HA instance.
"""

import sys
from unittest.mock import MagicMock

_HA_STUBS = [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.bluetooth",
    "homeassistant.components.sensor",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.util",
    "homeassistant.util.dt",
    "bleak",
    "bleak_retry_connector",
]

for _mod in _HA_STUBS:
    sys.modules.setdefault(_mod, MagicMock())
