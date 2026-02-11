"""检查项目文本文件编码一致性（UTF-8 / UTF-8 BOM）。"""

from __future__ import annotations

from pathlib import Path


TEXT_SUFFIXES = {
    '.py', '.md', '.txt', '.json', '.yml', '.yaml', '.html', '.css', '.js', '.sql', '.ini', '.toml'
}

TEXT_NAMES = {
    '.env.example', '.gitignore', '.gitattributes'
}

SKIP_DIRS = {
    '.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.venv', 'venv', 'env'
}


def should_check(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.name.startswith('.pyright') and path.suffix.lower() == '.json':
        return False
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    if path.name in TEXT_NAMES:
        return True
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    utf8_bom_files: list[str] = []
    non_utf8_files: list[str] = []

    for path in root.rglob('*'):
        if not should_check(path):
            continue
        raw = path.read_bytes()
        if raw.startswith(b'\xef\xbb\xbf'):
            utf8_bom_files.append(str(path.relative_to(root)))
            continue
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError:
            non_utf8_files.append(str(path.relative_to(root)))

    if utf8_bom_files:
        print('发现 UTF-8 BOM 文件（建议去除 BOM）:')
        for file in utf8_bom_files:
            print(f'  - {file}')

    if non_utf8_files:
        print('发现非 UTF-8 文件:')
        for file in non_utf8_files:
            print(f'  - {file}')

    if utf8_bom_files or non_utf8_files:
        return 1

    print('编码检查通过：所有文本文件均为 UTF-8（无 BOM）。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
