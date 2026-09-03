"""Tests unitaires — modèles et helpers multi-enfants."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from custom_components.optifamily.models import (
    Enfant,
    build_enfants_summary,
    get_presence,
    get_today_creneaux,
    iter_enfants,
)


def test_enfant_from_dict_ok() -> None:
    enfant = Enfant.from_dict({"id": "2001", "libelle": "Alice"})
    assert enfant == Enfant(id=2001, libelle="Alice")


def test_enfant_from_dict_invalid() -> None:
    assert Enfant.from_dict({}) is None
    assert Enfant.from_dict({"id": "abc"}) is None


def test_iter_enfants_merges_and_deduplicates() -> None:
    persisted = [{"id": 1, "libelle": "Ancien"}]
    live = [{"id": 1, "libelle": "Alice"}, {"id": 2, "libelle": "Bob"}]
    result = iter_enfants(live, persisted)
    assert {e.id: e.libelle for e in result} == {1: "Alice", 2: "Bob"}


def test_get_presence_present(planning_present: dict, today: date) -> None:
    assert get_presence(planning_present, today) == "présent"


def test_get_presence_absent(planning_absent: dict, today: date) -> None:
    assert get_presence(planning_absent, today) == "absent"


def test_get_presence_inconnu() -> None:
    assert get_presence(None) == "inconnu"
    assert get_presence({"semaines": []}, date(2026, 9, 3)) == "inconnu"


def test_get_today_creneaux(planning_present: dict, today: date) -> None:
    creneaux = get_today_creneaux(planning_present, today)
    assert len(creneaux) == 1
    assert creneaux[0]["label"] == "07:45 - 18:45"


def test_build_enfants_summary_multi(planning_present: dict, today: date) -> None:
    data = SimpleNamespace(
        enfants=[{"id": 1, "libelle": "Alice"}, {"id": 2, "libelle": "Bob"}],
        persisted_enfants=[],
        plannings={1: planning_present, 2: None},
        transmissions={1: [{}], 2: []},
        albums={1: [], 2: [{}, {}]},
    )
    summary = build_enfants_summary(data, today)
    assert summary["count"] == 2
    assert summary["presents_aujourdhui"] == 1
    assert summary["noms_presents"] == ["Alice"]
    assert summary["liste"][0]["transmissions"] == 1
    assert summary["liste"][1]["albums"] == 2
