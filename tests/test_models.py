"""Tests unitaires — modèles et helpers multi-enfants."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from custom_components.optifamily.models import (
    Enfant,
    build_enfants_summary,
    flatten_planning_jours,
    format_creneau_labels,
    get_presence,
    get_today_creneaux,
    iter_enfants,
    iter_year_months,
    parse_creneau_bounds,
    planning_to_events,
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


def test_format_and_flatten_creneaux(planning_present: dict, today: date) -> None:
    assert format_creneau_labels(None) == []
    assert format_creneau_labels(["x"]) == []
    assert format_creneau_labels([{"type": "regulier"}]) == ["regulier"]
    assert format_creneau_labels([{"label": "08:00 - 18:00", "details": "repas"}]) == [
        "08:00 - 18:00 (repas)"
    ]
    jours = flatten_planning_jours(planning_present)
    assert jours[0]["date"] == today.isoformat()
    assert jours[0]["creneaux"] == ["07:45 - 18:45"]
    hidden = {"semaines": [{"journees": [{"visible": False, "creneaux": [{"label": "x"}]}]}]}
    assert flatten_planning_jours(hidden) == []
    assert flatten_planning_jours(None) == []
    assert flatten_planning_jours({}) == []
    empty_day = {"semaines": [{"journees": [{"date": "2026-09-01", "creneaux": []}]}]}
    assert flatten_planning_jours(empty_day) == []


def test_parse_creneau_bounds_and_months() -> None:
    day = date(2026, 9, 3)
    bounds = parse_creneau_bounds("07:45 - 18:45", day)
    assert bounds is not None
    assert bounds[0].hour == 7
    assert bounds[1].hour == 18
    overnight = parse_creneau_bounds("18:00 - 08:00", day)
    assert overnight is not None
    assert overnight[1].hour == 19
    assert parse_creneau_bounds("Fermé", day) is None
    assert parse_creneau_bounds("25:00 - 26:00", day) is None
    start = datetime(2026, 12, 20)
    end = datetime(2027, 1, 5)
    assert iter_year_months(start, end) == [(2026, 12), (2027, 1)]


def test_planning_to_events(planning_present: dict, planning_absent: dict, today: date) -> None:
    timed = planning_to_events(planning_present, "Alice")
    assert timed[0].summary.startswith("Alice")
    assert timed[0].start.hour == 7
    closed = planning_to_events(planning_absent, "Bob")
    assert closed[0].start == today
    assert planning_to_events(None, "X") == []
    bad = {
        "semaines": [
            {
                "journees": [
                    {"date": "not-a-date", "creneaux": [{"label": "a"}]},
                    {"creneaux": [{"label": "b"}]},
                    {"date": today.isoformat(), "creneaux": ["skip", {"label": "Fermeture"}]},
                ]
            }
        ]
    }
    events = planning_to_events(bad, "Z")
    assert any(e.summary.endswith("Fermeture") for e in events)

    overlap = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "visible": True,
                        "creneaux": [{"id": 9, "type": "regulier", "label": "07:45 - 18:45"}],
                    }
                ]
            },
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "visible": True,
                        "creneaux": [{"id": 9, "type": "regulier", "label": "07:45 - 18:45"}],
                    }
                ]
            },
        ]
    }
    assert len(planning_to_events(overlap, "Alice")) == 1
    other_month = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": "2026-08-31",
                        "visible": True,
                        "creneaux": [{"id": 3, "label": "08:00 - 18:00"}],
                    }
                ]
            }
        ]
    }
    assert planning_to_events(other_month, "A", year=2026, month=9) == []
    assert planning_to_events(other_month, "A", year=2025, month=8) == []
    hidden = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "visible": False,
                        "creneaux": [{"id": 4, "label": "08:00 - 18:00"}],
                    }
                ]
            }
        ]
    }
    assert planning_to_events(hidden, "A") == []


def test_normalize_transmissions_sample() -> None:
    raw = [
        {
            "id": 1,
            "heure": "585",
            "type": "sieste",
            "sousType": "",
            "valeur1": "645",
            "valeur2": "2",
            "detail": "01:00",
            "complements": "dodo",
            "icon": "sieste2",
            "marquant": False,
        },
        {
            "id": 2,
            "heure": "690",
            "type": "repas",
            "sousType": "biberon",
            "valeur1": "210",
            "detail": "210 ml",
            "complements": "",
            "icon": "biberon",
            "marquant": False,
        },
        {
            "id": 3,
            "heure": "779",
            "type": "arrivee",
            "sousType": "",
            "valeur1": "480",
            "detail": "08:00",
            "complements": "repas 12h",
            "icon": "arrivee",
            "marquant": False,
        },
        {
            "id": 4,
            "heure": "825",
            "type": "change",
            "sousType": "couche",
            "valeur1": "caca",
            "valeur2": "Non défini",
            "detail": "",
            "complements": "",
            "icon": "couche",
            "marquant": True,
        },
    ]
    from custom_components.optifamily.models import (
        normalize_transmissions,
        transmissions_markdown,
    )

    items = normalize_transmissions(raw)
    assert len(items) == 4
    assert items[0]["type"] == "sieste"
    assert items[0]["heure"] == "09:45"
    assert items[0]["debut"] == "09:45"
    assert items[0]["fin"] == "10:45"
    assert any(r["value"] == "Bien" for r in items[0]["rows"])
    assert "01:00" in items[0]["ligne"]
    assert items[0]["complements"] == "dodo"
    biberon = next(i for i in items if i["type"] == "repas")
    assert biberon["titre"] == "Biberon"
    assert "210 ml" in biberon["ligne"]
    arrivee = next(i for i in items if i["type"] == "arrivee")
    assert arrivee["heure"] == "08:00"
    change = next(i for i in items if i["type"] == "change")
    assert any(r["value"] == "Couche" for r in change["rows"])
    assert any(r["value"] == "Selles" for r in change["rows"])
    md = transmissions_markdown(raw, enfant_libelle="Léa", jour="2026-09-04")
    assert "Léa" in md
    assert 'class="of-tx"' in md
    assert "Sieste" in md
    assert "of-tx-badge" in md
    assert "of-tx-chip" in md
    assert "of-tx-card--hot" in md
    preview = transmissions_markdown(raw, limit=2)
    assert "Voir le journal" in preview
    assert transmissions_markdown([]) == (
        '<div class="of-tx"><div class="of-tx-empty">Aucune transmission</div></div>'
    )
