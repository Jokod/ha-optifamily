"""Tests unitaires — modèles et helpers multi-enfants."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from custom_components.optifamily.models import (
    Enfant,
    build_enfants_summary,
    enabled_enfant_ids,
    flatten_planning_jours,
    format_creneau_labels,
    get_attendance_creneaux,
    get_presence,
    get_today_creneaux,
    is_closed_creneau,
    is_creche_closed_for_family,
    is_jour_fermeture,
    iter_enfants,
    iter_enfants_enabled,
    iter_year_months,
    normalize_actualite_items,
    normalize_album_items,
    normalize_document_items,
    normalize_downloadable_item,
    normalize_facture_items,
    normalize_message_items,
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


def test_get_presence_fermeture_overrides_regulier() -> None:
    today = date.today()
    assert is_closed_creneau("x") is False
    assert is_closed_creneau({"type": "regulier", "label": "08:00 - 18:00"}) is False
    planning = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "creneaux": [
                            {"type": "regulier", "label": "07:45 - 18:45"},
                            {"type": "fermeture", "label": "Fermé"},
                        ],
                    }
                ]
            }
        ]
    }
    assert get_presence(planning, today) == "absent"
    assert is_jour_fermeture(planning, today) is True
    assert get_attendance_creneaux(planning, today) == []


def test_get_presence_regulier_with_fermeture_label() -> None:
    today = date.today()
    planning = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "creneaux": [
                            {
                                "type": "regulier",
                                "label": "07:45 - 18:45",
                                "details": "fermeture",
                            }
                        ],
                    }
                ]
            }
        ]
    }
    assert get_presence(planning, today) == "absent"
    assert is_jour_fermeture(planning, today) is True


def test_get_presence_inconnu() -> None:
    assert get_presence(None) == "inconnu"
    assert get_presence({"semaines": []}, date(2026, 9, 3)) == "inconnu"


def test_is_creche_closed_for_family() -> None:
    today = date.today()
    assert is_creche_closed_for_family(None) is False
    assert is_creche_closed_for_family({}) is False
    assert is_creche_closed_for_family({1: {"semaines": []}}) is False
    closed = {
        1: {
            "semaines": [
                {"journees": [{"date": today.isoformat(), "creneaux": [{"type": "fermeture"}]}]}
            ]
        }
    }
    assert is_creche_closed_for_family(closed) is True
    open_day = {
        1: {
            "semaines": [
                {
                    "journees": [
                        {
                            "date": today.isoformat(),
                            "creneaux": [{"type": "regulier", "label": "08-18"}],
                        }
                    ]
                }
            ]
        },
        2: {
            "semaines": [
                {"journees": [{"date": today.isoformat(), "creneaux": [{"type": "fermeture"}]}]}
            ]
        },
    }
    assert is_creche_closed_for_family(open_day) is False


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
    assert "### Léa · 2026-09-04" in md
    assert "Sieste" in md
    assert "`09:45`" in md
    assert "**Bien**" in md
    assert "★" in md
    preview = transmissions_markdown(raw, limit=2)
    assert "Voir le journal" in preview
    empty = transmissions_markdown([])
    assert "Aucune transmission" in empty
    assert items[0]["chips"]
    assert items[0]["color"] == "indigo"
    assert "Début" in items[0]["bloc"]


# --- suite ---


def test_enabled_enfant_ids_and_iter() -> None:
    enfants = [Enfant(1, "A"), Enfant(2, "B")]
    assert enabled_enfant_ids(enfants, None) is None
    assert enabled_enfant_ids(enfants, "nope") is None  # type: ignore[arg-type]
    assert enabled_enfant_ids(enfants, [1, "2", "x", None]) == {1, 2}
    assert enabled_enfant_ids([], [1, 2]) == {1, 2}

    live = [{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}]
    assert [e.id for e in iter_enfants_enabled(live, enabled_ids=None)] == [1, 2]
    assert [e.id for e in iter_enfants_enabled(live, enabled_ids="bad")] == [1, 2]  # type: ignore[arg-type]
    assert [e.id for e in iter_enfants_enabled(live, enabled_ids=[1])] == [1]
    assert [e.id for e in iter_enfants_enabled(live, enabled_ids=[99])] == []
    with patch("custom_components.optifamily.models.enabled_enfant_ids", return_value=None):
        assert [e.id for e in iter_enfants_enabled(live, enabled_ids=[1])] == [1, 2]


def test_normalize_downloadable_and_lists() -> None:
    assert normalize_downloadable_item("x", kind="document") is None
    nested = normalize_downloadable_item({"id": {"nested": 1}}, kind="document")
    assert nested is not None and nested["id"] is None
    assert _pick_via_normalize_id_skip()

    doc = normalize_downloadable_item(
        {
            "documentId": 9,
            "titre": "Doc",
            "downloadUrl": "https://ex/f.pdf",
            "date": "2026-01-01",
        },
        kind="document",
    )
    assert doc and doc["downloadable"] is True and doc["id"] == "9"

    album = normalize_downloadable_item(
        {
            "id": 1,
            "label": "Album",
            "photos": [
                {"id": 10, "url": "https://ex/a.jpg"},
                "skip",
                {"id": 11, "mediaUrl": "https://ex/b.jpg"},
                {"id": 12, "path": "/c.jpg"},
            ],
        },
        kind="album",
        limit_photos=2,
    )
    assert album and len(album["photos"]) == 2
    assert album["photos_count"] == 4

    album_bad_photos = normalize_downloadable_item({"id": 2, "medias": "not-a-list"}, kind="album")
    assert album_bad_photos and album_bad_photos["photos"] == []

    msg = normalize_downloadable_item(
        {"id": 3, "corps": "bonjour", "vu": False, "sender": True}, kind="message"
    )
    assert msg and msg["downloadable"] is False and msg["corps"] == "bonjour"

    albums = [{"id": i, "photos": []} for i in range(25)]
    assert len(normalize_album_items(albums, limit=3)) == 3
    assert normalize_album_items(None) == []

    docs = [{"id": i} for i in range(5)] + ["bad"]
    assert len(normalize_document_items(docs, limit=2)) == 2
    assert len(normalize_facture_items([{"factureId": 1}], limit=1)) == 1
    assert normalize_facture_items([None], limit=1) == []  # type: ignore[list-item]

    assert normalize_actualite_items(None) == []
    assert normalize_actualite_items("x") == []
    assert len(normalize_actualite_items([{"id": 1}, "x", {"titre": "T"}], limit=10)) == 2
    assert (
        len(
            normalize_actualite_items(
                {"items": [{"id": i, "resume": "r"} for i in range(30)]}, limit=5
            )
        )
        == 5
    )
    assert normalize_actualite_items({"actualites": [{"libelle": "A"}]})[0]["titre"] == "A"

    msgs = [{"id": i, "message": "m"} for i in range(10)]
    assert len(normalize_message_items(msgs, limit=3)) == 3
    assert normalize_message_items(None) == []


def _pick_via_normalize_id_skip() -> bool:
    """Force _pick_id to skip dict/list values then find a scalar."""
    item = normalize_downloadable_item({"id": [1, 2], "uuid": "u-1", "name": "x"}, kind="document")
    return item is not None and item["id"] == "u-1"
