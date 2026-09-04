"""Tests DayContext — matrice statut_jour / phase / messages FR."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

from custom_components.optifamily.day_context import (
    PHASE_CHERCHER,
    PHASE_CRECHE,
    PHASE_DEPOSER,
    PHASE_FERME,
    PHASE_INCONNU,
    PHASE_MAISON,
    PHASE_RENTRE,
    STATUT_AUCUN,
    STATUT_FERME,
    STATUT_INCONNU,
    STATUT_MULTI,
    STATUT_UN,
    Plage,
    _message_enfant,
    _phase_from_plages,
    _plages_from_attendance,
    compute_enfant_day,
    compute_family_day,
    enrich_enfant_status,
)
from custom_components.optifamily.models import Enfant


def _planning_day(day: date, creneaux: list[dict]) -> dict:
    return {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "visible": True,
                        "creneaux": creneaux,
                    }
                ]
            }
        ]
    }


def test_inconnu_sans_planning() -> None:
    enfant = Enfant(1, "Léa")
    ctx = compute_enfant_day(enfant, None, now=datetime(2026, 3, 10, 8, 0))
    assert ctx.statut_jour == STATUT_INCONNU
    assert ctx.phase_enfant == PHASE_INCONNU
    assert "non confirmée" in ctx.message.lower() or "Présence" in ctx.message


def test_fermeture_prioritaire() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(
        day,
        [
            {"type": "fermeture", "label": "Fermé"},
            {"type": "regulier", "label": "08:00 - 18:00"},
        ],
    )
    ctx = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 9, 0))
    assert ctx.statut_jour == STATUT_FERME
    assert ctx.phase_enfant == PHASE_FERME
    assert ctx.jour_fermeture is True


def test_aucun_creneau() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(day, [])
    ctx = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 9, 0))
    assert ctx.statut_jour == STATUT_AUCUN
    assert ctx.phase_enfant == PHASE_MAISON
    assert "pas de créneau" in ctx.message


def test_un_creneau_phases() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(day, [{"type": "regulier", "label": "08:00 - 17:00"}])
    enfant = Enfant(1, "Léa")

    early = compute_enfant_day(enfant, planning, now=datetime(2026, 3, 10, 6, 0))
    assert early.statut_jour == STATUT_UN
    assert early.phase_enfant == PHASE_MAISON

    drop = compute_enfant_day(enfant, planning, now=datetime(2026, 3, 10, 7, 0))
    assert drop.phase_enfant == PHASE_DEPOSER
    assert drop.minutes == 60

    mid = compute_enfant_day(enfant, planning, now=datetime(2026, 3, 10, 12, 0))
    assert mid.phase_enfant == PHASE_CRECHE

    pick = compute_enfant_day(enfant, planning, now=datetime(2026, 3, 10, 16, 0))
    assert pick.phase_enfant == PHASE_CHERCHER

    done = compute_enfant_day(enfant, planning, now=datetime(2026, 3, 10, 18, 0))
    assert done.phase_enfant == PHASE_RENTRE


def test_multi_creneaux_prochain() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(
        day,
        [
            {"type": "regulier", "label": "08:00 - 12:00"},
            {"type": "regulier", "label": "14:00 - 18:00"},
        ],
    )
    ctx = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 13, 0))
    assert ctx.statut_jour == STATUT_MULTI
    assert ctx.creneaux_count == 2
    assert ctx.phase_enfant == PHASE_DEPOSER
    assert ctx.minutes == 60


def test_family_ferme_et_attention() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(day, [{"type": "fermeture", "label": "Férié"}])
    family = compute_family_day(
        [Enfant(1, "Léa")],
        {1: planning},
        now=datetime(2026, 3, 10, 9, 0),
        unread_creche=2,
    )
    assert family.phase == PHASE_FERME
    assert family.tous_fermes is True
    assert family.attention is True
    assert "message" in family.attention_raison


def test_family_priorite_deposer() -> None:
    day = date(2026, 3, 10)
    p1 = _planning_day(day, [{"type": "regulier", "label": "08:00 - 17:00"}])
    p2 = _planning_day(day, [{"type": "regulier", "label": "09:00 - 17:00"}])
    family = compute_family_day(
        [Enfant(1, "Léa"), Enfant(2, "Tom")],
        {1: p1, 2: p2},
        now=datetime(2026, 3, 10, 7, 30),
    )
    assert family.phase == PHASE_DEPOSER
    assert family.cible == "Léa"
    assert family.attention is True


def test_enrich_enfant_status() -> None:
    day = date(2026, 3, 10)
    planning = _planning_day(day, [{"type": "regulier", "label": "08:00 - 17:00"}])
    ctx = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 10, 0))
    merged = enrich_enfant_status({"id": 1, "libelle": "Léa", "presence": "présent"}, ctx)
    assert merged["statut_jour"] == STATUT_UN
    assert merged["phase_enfant"] == PHASE_CRECHE
    assert merged["plages"]
    assert "message" in merged


# --- suite ---


def test_day_context_as_dict_and_edge_messages() -> None:
    day = date(2026, 3, 10)
    planning = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "creneaux": [{"type": "regulier", "label": "08:00 - 17:00"}],
                    }
                ]
            }
        ]
    }
    ctx = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 7, 0))
    d = ctx.as_dict()
    assert d["phase_enfant"] == PHASE_DEPOSER
    assert d["plages"]

    family = compute_family_day([], {}, now=datetime(2026, 3, 10, 9, 0))
    assert family.as_dict()["phase"]
    assert "aucun enfant" in family.message.lower() or "introuvable" in family.message.lower()

    # plage sans bornes parsables
    assert _plages_from_attendance([{"label": "Fermé"}], day, datetime(2026, 3, 10, 9, 0)) == []

    # phase edges: done, creche without pick, empty plages
    assert _phase_from_plages([], lead=90) == (PHASE_MAISON, None, None)
    done_plage = Plage("08:00", "17:00", "08:00 - 17:00", -600, -60)
    assert _phase_from_plages([done_plage], lead=90)[0] == PHASE_RENTRE

    # branche défensive : liste « non vide » mais itération vide
    class _TruthyEmpty(list):
        def __bool__(self) -> bool:
            return True

    assert _phase_from_plages(_TruthyEmpty(), lead=90) == (PHASE_CRECHE, None, None)

    # message branches
    assert "non confirmée" in _message_enfant(
        libelle="L", statut="inconnu", phase=PHASE_MAISON, plages=[], minutes=None, at=None
    )
    assert "à 10:00" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_DEPOSER,
        plages=[],
        minutes=120,
        at="10:00",
    )
    assert "dans 1 h 30 min" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_DEPOSER,
        plages=[],
        minutes=90,
        at="10:00",
    )
    assert "dans 1 h" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_DEPOSER,
        plages=[],
        minutes=60,
        at="10:00",
    )
    assert "dans 1 h 5 min" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_CHERCHER,
        plages=[],
        minutes=65,
        at=None,
    )
    assert "dans 20 min" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_CHERCHER,
        plages=[],
        minutes=20,
        at=None,
    )
    assert "récupération" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_CRECHE,
        plages=[],
        minutes=30,
        at="17:00",
    )
    assert _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_CRECHE,
        plages=[],
        minutes=None,
        at=None,
    ).endswith("en crèche")
    assert "rentré" in _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_RENTRE,
        plages=[],
        minutes=None,
        at=None,
    )
    plages = [Plage("08:00", "12:00", "08:00 - 12:00", 60, 300)]
    assert (
        "maison"
        in _message_enfant(
            libelle="L",
            statut=STATUT_UN,
            phase=PHASE_MAISON,
            plages=plages,
            minutes=60,
            at="08:00",
        ).lower()
    )
    assert _message_enfant(
        libelle="L",
        statut=STATUT_UN,
        phase=PHASE_MAISON,
        plages=[],
        minutes=None,
        at=None,
    ).endswith("à la maison")


def test_day_context_unparsable_regulier_and_family_maison() -> None:
    day = date(2026, 3, 10)
    planning = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "creneaux": [{"type": "regulier", "label": "journée"}],
                    }
                ]
            }
        ]
    }
    present = compute_enfant_day(Enfant(1, "Léa"), planning, now=datetime(2026, 3, 10, 10, 0))
    assert present.statut_jour == STATUT_UN
    assert present.phase_enfant == PHASE_CRECHE

    # Plusieurs créneaux réguliers sans horaires parsables → plages vides, phase creche
    planning_multi = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "creneaux": [
                            {"type": "regulier", "label": "matin"},
                            {"type": "regulier", "label": "soir"},
                        ],
                    }
                ]
            }
        ]
    }
    multi = compute_enfant_day(Enfant(1, "Léa"), planning_multi, now=datetime(2026, 3, 10, 10, 0))
    assert multi.statut_jour == STATUT_UN  # len(plages)==0 → pas MULTI
    assert multi.phase_enfant == PHASE_CRECHE
    assert multi.creneaux_count == 2

    with patch("custom_components.optifamily.day_context.get_presence", return_value="absent"):
        maison = compute_enfant_day(
            Enfant(1, "Léa"), planning_multi, now=datetime(2026, 3, 10, 10, 0)
        )
    assert maison.phase_enfant == PHASE_MAISON

    # Family: several enfants all at home (absent)
    p_none = {"semaines": [{"journees": [{"date": day.isoformat(), "creneaux": []}]}]}
    fam = compute_family_day(
        [Enfant(1, "A"), Enfant(2, "B")],
        {1: p_none, 2: p_none},
        now=datetime(2026, 3, 10, 9, 0),
    )
    assert fam.phase == PHASE_MAISON
    assert "maison" in fam.message.lower()

    # Single enfant maison
    fam1 = compute_family_day(
        [Enfant(1, "A")],
        {1: p_none},
        now=datetime(2026, 3, 10, 9, 0),
    )
    assert fam1.phase == PHASE_MAISON

    # Family with present but only rentre/maison (no active deposit/pick/creche)
    p_done = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "creneaux": [{"type": "regulier", "label": "08:00 - 09:00"}],
                    }
                ]
            }
        ]
    }
    fam_rentre = compute_family_day(
        [Enfant(1, "Léa")],
        {1: p_done},
        now=datetime(2026, 3, 10, 18, 0),
        unread_creche=0,
    )
    assert fam_rentre.phase == PHASE_RENTRE
    assert "récupérer" not in fam_rentre.attention_raison

    # Phase chercher → attention « récupérer »
    p_pick = {
        "semaines": [
            {
                "journees": [
                    {
                        "date": day.isoformat(),
                        "creneaux": [{"type": "regulier", "label": "08:00 - 17:00"}],
                    }
                ]
            }
        ]
    }
    fam_pick = compute_family_day(
        [Enfant(1, "Léa")],
        {1: p_pick},
        now=datetime(2026, 3, 10, 16, 0),
        unread_creche=0,
    )
    assert fam_pick.phase == PHASE_CHERCHER
    assert "récupérer" in fam_pick.attention_raison
