"""Load integration submodules without homeassistant (real __init__.py imports HA)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_pkg = "custom_components.peak_power_forecast"
_base = _root / "custom_components" / "peak_power_forecast"


def _ensure_package_modules() -> None:
    if (
        _pkg in sys.modules
        and f"{_pkg}.forecast" in sys.modules
        and f"{_pkg}.visual" in sys.modules
    ):
        return

    if "custom_components" not in sys.modules:
        cc = types.ModuleType("custom_components")
        cc.__path__ = [str(_root / "custom_components")]
        sys.modules["custom_components"] = cc

    cc = sys.modules["custom_components"]
    if _pkg not in sys.modules:
        ppf = types.ModuleType(_pkg)
        ppf.__path__ = [str(_base)]
        sys.modules[_pkg] = ppf
        setattr(cc, "peak_power_forecast", ppf)

    def _exec(name: str, path: Path) -> None:
        if name in sys.modules:
            return
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)

    _exec(f"{_pkg}.const", _base / "const.py")
    _exec(f"{_pkg}.forecast", _base / "forecast.py")
    _exec(f"{_pkg}.visual", _base / "visual.py")


_ensure_package_modules()
