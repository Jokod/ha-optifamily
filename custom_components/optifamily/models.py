"""Modèles et helpers pour les données OptiFamily (multi-enfants)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class Enfant:
    """Représentation normalisée d'un enfant."""

    id: int
    libelle: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Enfant | None:
        """Construit un Enfant depuis un dict API ou config entry."""
        if not isinstance(data, dict) or data.get("id") is None:
            return None
        try:
            enfant_id = int(data["id"])
        except (TypeError, ValueError):
            return None
        libelle = str(data.get("libelle") or f"Enfant {enfant_id}")
        return cls(id=enfant_id, libelle=libelle)


def iter_enfants(
    live_enfants: list[dict[str, Any]],
    persisted_enfants: list[dict[str, Any]] | None = None,
) -> list[Enfant]:
    """Fusionne enfants API et config entry (API prioritaire, IDs uniques)."""
    merged: dict[int, Enfant] = {}
    for source in (persisted_enfants or [], live_enfants):
        for raw in source:
            enfant = Enfant.from_dict(raw)
            if enfant:
                merged[enfant.id] = enfant
    return list(merged.values())


def get_today_creneaux(
    planning: dict[str, Any] | None, day: date | None = None
) -> list[dict[str, Any]]:
    """Retourne les créneaux du jour pour un planning mensuel."""
    if not planning:
        return []
    today_str = (day or date.today()).isoformat()
    for semaine in planning.get("semaines", []):
        for journee in semaine.get("journees", []):
            if journee.get("date") == today_str:
                return list(journee.get("creneaux", []))
    return []


def get_presence(planning: dict[str, Any] | None, day: date | None = None) -> str:
    """Indique si l'enfant est présent aujourd'hui (`présent` / `absent` / `inconnu`)."""
    if not planning:
        return "inconnu"
    today_str = (day or date.today()).isoformat()
    day_found = any(
        journee.get("date") == today_str
        for semaine in planning.get("semaines", [])
        for journee in semaine.get("journees", [])
    )
    if not day_found:
        return "inconnu"
    creneaux = get_today_creneaux(planning, day)
    reguliers = [c for c in creneaux if c.get("type") == "regulier"]
    return "présent" if reguliers else "absent"


def build_enfant_status(
    enfant: Enfant,
    planning: dict[str, Any] | None,
    transmissions: list[dict[str, Any]] | None,
    albums: list[dict[str, Any]] | None,
    day: date | None = None,
) -> dict[str, Any]:
    """Construit le résumé d'un enfant pour capteurs agrégés et tableaux de bord."""
    creneaux = get_today_creneaux(planning, day)
    reguliers = [c for c in creneaux if c.get("type") == "regulier"]
    return {
        "id": enfant.id,
        "libelle": enfant.libelle,
        "presence": get_presence(planning, day),
        "creneaux": [c.get("label") for c in reguliers if c.get("label")],
        "creneaux_detail": [
            {
                "type": c.get("type"),
                "label": c.get("label"),
                "details": c.get("details"),
            }
            for c in creneaux
        ],
        "transmissions": len(transmissions or []),
        "albums": len(albums or []),
        "creneaux_mois": _count_monthly_slots(planning),
    }


def build_enfants_summary(data: Any, day: date | None = None) -> dict[str, Any]:
    """Résumé multi-enfants pour capteurs globaux et templates Lovelace."""
    enfants = iter_enfants(data.enfants, getattr(data, "persisted_enfants", None))
    liste: list[dict[str, Any]] = []
    presents: list[str] = []

    for enfant in enfants:
        status = build_enfant_status(
            enfant,
            data.plannings.get(enfant.id),
            data.transmissions.get(enfant.id),
            data.albums.get(enfant.id) if hasattr(data, "albums") else None,
            day,
        )
        liste.append(status)
        if status["presence"] == "présent":
            presents.append(enfant.libelle)

    return {
        "count": len(liste),
        "liste": liste,
        "presents_aujourdhui": len(presents),
        "noms_presents": presents,
    }


def _count_monthly_slots(planning: dict[str, Any] | None) -> int:
    if not planning:
        return 0
    count = 0
    for semaine in planning.get("semaines", []):
        for journee in semaine.get("journees", []):
            count += len([c for c in journee.get("creneaux", []) if c.get("type") == "regulier"])
    return count
