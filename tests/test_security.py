"""Tests de garde-fous sécurité."""

from __future__ import annotations

import ast
from pathlib import Path

from custom_components.optifamily import const

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "optifamily"


def test_no_profil_endpoint_constant() -> None:
    """Le endpoint /profil ne doit pas être exposé dans const."""
    paths = [getattr(const, name) for name in dir(const) if name.startswith("API_")]
    assert all("/profil" not in str(path) for path in paths)


def test_source_never_calls_profil() -> None:
    """Aucun fichier Python ne doit appeler /profil."""
    for path in ROOT.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "/opti-family/profil" not in content
        assert "API_PROFIL" not in content


def test_api_error_truncates_message() -> None:
    """Les erreurs API ne doivent pas remonter de payloads entiers."""
    import inspect

    from custom_components.optifamily.api import OptieFamilyApiClient

    source = inspect.getsource(OptieFamilyApiClient._request)
    assert "text[:200]" in source


def test_no_eval_exec_in_package() -> None:
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec"}
