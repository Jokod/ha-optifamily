"""Modèles et helpers pour les données OptiFamily (multi-enfants)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any

_CRENEAU_BOUNDS = re.compile(r"(\d{1,2})[:hH](\d{2})\s*[-–]\s*(\d{1,2})[:hH](\d{2})")


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


def format_creneau_labels(creneaux: list[dict[str, Any]] | None) -> list[str]:
    """Libellés lisibles (sans dumps YAML) pour cartes Lovelace et notifications."""
    labels: list[str] = []
    for creneau in creneaux or []:
        if not isinstance(creneau, dict):
            continue
        label = str(creneau.get("label") or "").strip()
        details = str(creneau.get("details") or "").strip()
        if label and details:
            labels.append(f"{label} ({details})")
        elif label:
            labels.append(label)
        elif creneau.get("type"):
            labels.append(str(creneau["type"]))
    return labels


def flatten_planning_jours(planning: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Jours visibles du mois avec créneaux formatés (tableau de bord)."""
    if not planning:
        return []
    jours: list[dict[str, Any]] = []
    for semaine in planning.get("semaines", []):
        for journee in semaine.get("journees", []):
            if journee.get("visible") is False:
                continue
            labels = format_creneau_labels(journee.get("creneaux"))
            if not labels:
                continue
            jours.append({"date": journee.get("date"), "creneaux": labels})
    return jours


def parse_creneau_bounds(label: str, day: date) -> tuple[datetime, datetime] | None:
    """Extrait début/fin naïfs depuis un libellé du type `07:45 - 18:45`."""
    match = _CRENEAU_BOUNDS.search(label or "")
    if not match:
        return None
    h1, m1, h2, m2 = (int(g) for g in match.groups())
    try:
        start = datetime.combine(day, time(h1, m1))
        end = datetime.combine(day, time(h2, m2))
    except ValueError:
        return None
    if end <= start:
        end = start + timedelta(hours=1)
    return start, end


def iter_year_months(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """Liste (année, mois) couvrant [start, end)."""
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    months: list[tuple[int, int]] = []
    while cursor <= last:
        months.append((cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


@dataclass(frozen=True, slots=True)
class PlanningEvent:
    """Événement planning pour le calendrier Home Assistant."""

    start: datetime | date
    end: datetime | date
    summary: str
    description: str
    uid: str


def planning_to_events(
    planning: dict[str, Any] | None,
    enfant_libelle: str,
    tzinfo: datetime.tzinfo | None = None,
    *,
    year: int | None = None,
    month: int | None = None,
) -> list[PlanningEvent]:
    """Convertit un planning mensuel API en événements calendrier (sans doublons)."""
    events: list[PlanningEvent] = []
    if not planning:
        return events
    seen: set[str] = set()
    for semaine in planning.get("semaines", []):
        for journee in semaine.get("journees", []):
            if journee.get("visible") is False:
                continue
            raw_date = journee.get("date")
            if not raw_date:
                continue
            try:
                day = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            if year is not None and day.year != year:
                continue
            if month is not None and day.month != month:
                continue
            for index, creneau in enumerate(journee.get("creneaux") or []):
                if not isinstance(creneau, dict):
                    continue
                labels = format_creneau_labels([creneau])
                title = labels[0] if labels else "Créneau"
                summary = f"{enfant_libelle} — {title}"
                description = str(creneau.get("type") or "")
                uid = str(
                    creneau.get("id")
                    or f"{raw_date}-{creneau.get('label')}-{creneau.get('type')}-{index}"
                )
                if uid in seen:
                    continue
                seen.add(uid)
                bounds = parse_creneau_bounds(str(creneau.get("label") or ""), day)
                if bounds:
                    start, end = bounds
                    if tzinfo is not None:
                        start = start.replace(tzinfo=tzinfo)
                        end = end.replace(tzinfo=tzinfo)
                    events.append(
                        PlanningEvent(
                            start=start,
                            end=end,
                            summary=summary,
                            description=description,
                            uid=uid,
                        )
                    )
                    continue
                events.append(
                    PlanningEvent(
                        start=day,
                        end=day + timedelta(days=1),
                        summary=summary,
                        description=description,
                        uid=uid,
                    )
                )
    return events
