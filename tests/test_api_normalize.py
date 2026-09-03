"""Tests unitaires — normalisation API."""

from __future__ import annotations

from custom_components.optifamily.api import (
    _parse_creches_from_response,
    normalize_enfants,
)


def test_parse_creches_list_format_observed() -> None:
    """Format confirmé : [{"id": 1001, "libelle": "..."}]."""
    creches = _parse_creches_from_response([{"id": 1001, "libelle": "Crèche A"}])
    assert creches == [{"id": 1001, "nom": "Crèche A"}]


def test_parse_creches_multiple() -> None:
    creches = _parse_creches_from_response(
        [
            {"id": 1001, "libelle": "A"},
            {"id": 1002, "libelle": "B"},
        ]
    )
    assert len(creches) == 2
    assert {c["id"] for c in creches} == {1001, 1002}


def test_parse_creches_empty() -> None:
    assert _parse_creches_from_response([]) == []
    assert _parse_creches_from_response(None) == []


def test_normalize_enfants() -> None:
    result = normalize_enfants(
        [
            {"id": 2001, "libelle": "Alice"},
            {"id": "bad"},
            {"libelle": "Sans id"},
        ]
    )
    assert result == [{"id": 2001, "libelle": "Alice"}]
