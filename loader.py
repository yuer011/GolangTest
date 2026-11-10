"""只加载 ``cases/regression`` 的独立回归 case loader。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .spec import RegressionCaseSpec, clear_registry, get_registry


class RegressionLoader:
    def load(self, src: str | Path = "cases/regression") -> list[RegressionCaseSpec]:
        path = Path(src).resolve()
        if not path.exists():
            raise FileNotFoundError(f"回归 case 路径不存在：{path}")
        parts = path.parts
        if not any(
            parts[index : index + 2] == ("cases", "regression") for index in range(len(parts) - 1)
        ):
            raise ValueError(f"回归入口只允许加载 cases/regression：{path}")

        clear_registry()
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for py in files:
            if py.name == "__init__.py":
                continue
            self._import_by_path(py)
        return get_registry()

    @staticmethod
    def _import_by_path(py: Path) -> None:
        module_name = "dlp_auto_regression_case_" + "_".join(py.with_suffix("").parts[-5:])
        spec = importlib.util.spec_from_file_location(module_name, py)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载回归 case：{py}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
