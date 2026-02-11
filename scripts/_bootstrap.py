"""脚本启动引导：统一设置项目导入路径与根目录。"""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent


def setup_project_path() -> tuple[Path, Path]:
    """确保脚本可稳定导入 `movies_recommend` 包。

    Returns:
        tuple[Path, Path]: (PACKAGE_ROOT, PROJECT_ROOT)
    """
    project_root_str = str(PROJECT_ROOT)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    return PACKAGE_ROOT, PROJECT_ROOT

