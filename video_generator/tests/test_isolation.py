from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / 'video_generator'
PROHIBITED = ('application', 'domain', 'infrastructure', 'dealbot')


def iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob('*.py') if '__pycache__' not in path.parts)


def absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def imports_root(module_name: str, root_name: str) -> bool:
    return module_name == root_name or module_name.startswith(f'{root_name}.')


def test_video_generator_package_stays_isolated_from_existing_project_layers() -> None:
    for path in iter_python_files(PACKAGE_ROOT):
        imports = absolute_imports(path)
        offending = sorted(
            module
            for module in imports
            if any(imports_root(module, root_name) for root_name in PROHIBITED)
        )
        assert offending == [], f'{path} unexpectedly imports existing project layers: {offending}'
