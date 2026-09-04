"""Contexte journalier OptiFamily — source de vérité pour phase / présence / messages UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .const import PHASE_LEAD_MINUTES
from .models import (
    Enfant,
    get_attendance_creneaux,
    get_presence,
    is_jour_fermeture,
    parse_creneau_bounds,
)

PHASE_MAISON = "maison"
PHASE_DEPOSER = "deposer"
PHASE_CRECHE = "creche"
PHASE_CHERCHER = "chercher"
PHASE_RENTRE = "rentre"
PHASE_FERME = "ferme"
PHASE_INCONNU = "inconnu"

STATUT_FERME = "ferme"
STATUT_AUCUN = "aucun_creneau"
STATUT_INCONNU = "inconnu"
STATUT_UN = "un_creneau"
STATUT_MULTI = "multi_creneaux"

_PHASE_LIBELLES = {
    PHASE_MAISON: "À la maison",
    PHASE_DEPOSER: "À déposer",
    PHASE_CRECHE: "En crèche",
    PHASE_CHERCHER: "À récupérer",
    PHASE_RENTRE: "Rentré·e",
    PHASE_FERME: "Crèche fermée",
    PHASE_INCONNU: "Inconnu",
}


@dataclass(frozen=True, slots=True)
class Plage:
    """Créneau régulier normalisé."""

    debut: str
    fin: str
    label: str
    minutes_to_start: int
    minutes_to_end: int


@dataclass(frozen=True, slots=True)
class EnfantDayContext:
    """État d'un enfant pour un jour donné."""

    enfant_id: int
    libelle: str
    presence: str
    statut_jour: str
    jour_fermeture: bool
    phase_enfant: str
    plages: tuple[Plage, ...]
    creneaux_count: int
    debut: str | None
    fin: str | None
    minutes: int | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "enfant_id": self.enfant_id,
            "libelle": self.libelle,
            "presence": self.presence,
            "statut_jour": self.statut_jour,
            "jour_fermeture": self.jour_fermeture,
            "phase_enfant": self.phase_enfant,
            "plages": [
                {
                    "debut": p.debut,
                    "fin": p.fin,
                    "label": p.label,
                    "minutes_to_start": p.minutes_to_start,
                    "minutes_to_end": p.minutes_to_end,
                }
                for p in self.plages
            ],
            "creneaux_count": self.creneaux_count,
            "debut": self.debut,
            "fin": self.fin,
            "minutes": self.minutes,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class FamilyDayContext:
    """Agrégat famille pour le jour."""

    phase: str
    libelle: str
    message: str
    minutes: int | None
    cible: str | None
    attention: bool
    attention_raison: str
    jour_fermeture: bool
    tous_fermes: bool
    enfants: tuple[EnfantDayContext, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "libelle": self.libelle,
            "message": self.message,
            "minutes": self.minutes,
            "cible": self.cible,
            "attention": self.attention,
            "attention_raison": self.attention_raison,
            "jour_fermeture": self.jour_fermeture,
            "tous_fermes": self.tous_fermes,
            "enfants": [e.as_dict() for e in self.enfants],
        }


def _clock(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"


def _plages_from_attendance(
    attendance: list[dict[str, Any]], day: date, now: datetime
) -> list[Plage]:
    plages: list[Plage] = []
    for creneau in attendance:
        label = str(creneau.get("label") or "").strip()
        bounds = parse_creneau_bounds(label, day)
        if not bounds:
            continue
        start, end = bounds
        to_start = int((start - now.replace(tzinfo=None)).total_seconds() // 60)
        to_end = int((end - now.replace(tzinfo=None)).total_seconds() // 60)
        plages.append(
            Plage(
                debut=_clock(start),
                fin=_clock(end),
                label=label,
                minutes_to_start=to_start,
                minutes_to_end=to_end,
            )
        )
    plages.sort(key=lambda p: (p.minutes_to_start, p.debut))
    return plages


def _phase_from_plages(plages: list[Plage], *, lead: int) -> tuple[str, int | None, str | None]:
    """Retourne (phase, minutes, at_clock) pour le prochain événement pertinent."""
    if not plages:
        return PHASE_MAISON, None, None

    drop: Plage | None = None
    pick: Plage | None = None
    mid = 0
    done = 0
    for plage in plages:
        if plage.minutes_to_start > 0:
            if drop is None or plage.minutes_to_start < drop.minutes_to_start:
                drop = plage
        elif plage.minutes_to_end > 0:
            mid += 1
            if pick is None or plage.minutes_to_end < pick.minutes_to_end:
                pick = plage
        else:
            done += 1

    if drop is not None and 0 < drop.minutes_to_start <= lead:
        return PHASE_DEPOSER, drop.minutes_to_start, drop.debut
    if drop is not None:
        return PHASE_MAISON, drop.minutes_to_start, drop.debut
    if pick is not None and pick.minutes_to_end <= lead:
        return PHASE_CHERCHER, pick.minutes_to_end, pick.fin
    if mid > 0:
        mins = pick.minutes_to_end if pick else None
        at = pick.fin if pick else None
        return PHASE_CRECHE, mins, at
    if done > 0:
        return PHASE_RENTRE, None, None
    return PHASE_CRECHE, None, None


def _message_enfant(
    *,
    libelle: str,
    statut: str,
    phase: str,
    plages: list[Plage],
    minutes: int | None,
    at: str | None,
) -> str:
    if statut == STATUT_FERME:
        return "Crèche fermée aujourd’hui"
    if statut == STATUT_INCONNU:
        return "Présence non confirmée"
    if statut == STATUT_AUCUN:
        return f"{libelle} — pas de créneau aujourd’hui"
    if phase == PHASE_DEPOSER and minutes is not None and at:
        if minutes > 90:
            return f"Allez déposer {libelle} à {at}"
        if minutes >= 60:
            h, m = divmod(minutes, 60)
            extra = f" {m} min" if m else ""
            return f"Allez déposer {libelle} dans {h} h{extra}"
        return f"Allez déposer {libelle} dans {minutes} min"
    if phase == PHASE_CHERCHER and minutes is not None:
        if minutes >= 60:
            h, m = divmod(minutes, 60)
            extra = f" {m} min" if m else ""
            return f"Allez chercher {libelle} dans {h} h{extra}"
        return f"Allez chercher {libelle} dans {minutes} min"
    if phase == PHASE_CRECHE:
        if at:
            return f"{libelle} est en crèche · récupération à {at}"
        return f"{libelle} est en crèche"
    if phase == PHASE_RENTRE:
        return f"{libelle} est rentré·e"
    if plages:
        labels = " · ".join(p.label for p in plages)
        return f"{libelle} à la maison · {labels}"
    return f"{libelle} est à la maison"


def compute_enfant_day(
    enfant: Enfant,
    planning: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    lead_minutes: int = PHASE_LEAD_MINUTES,
) -> EnfantDayContext:
    """Calcule l'état jour d'un enfant."""
    now = now or datetime.now()
    day = now.date()
    naive_now = now.replace(tzinfo=None) if now.tzinfo else now
    presence = get_presence(planning, day)
    fermeture = is_jour_fermeture(planning, day)
    attendance = get_attendance_creneaux(planning, day)
    plages = _plages_from_attendance(attendance, day, naive_now)

    if presence == "inconnu":
        statut = STATUT_INCONNU
        phase = PHASE_INCONNU
        minutes = None
        at = None
    elif fermeture:
        statut = STATUT_FERME
        phase = PHASE_FERME
        minutes = None
        at = None
    elif not attendance:
        statut = STATUT_AUCUN
        phase = PHASE_MAISON
        minutes = None
        at = None
    else:
        statut = STATUT_MULTI if len(plages) > 1 else STATUT_UN
        if not plages:
            # Régulier sans horaires parsables
            phase = PHASE_CRECHE if presence == "présent" else PHASE_MAISON
            minutes = None
            at = None
        else:
            phase, minutes, at = _phase_from_plages(plages, lead=lead_minutes)

    message = _message_enfant(
        libelle=enfant.libelle,
        statut=statut,
        phase=phase,
        plages=plages,
        minutes=minutes,
        at=at,
    )
    debut = plages[0].debut if plages else None
    fin = plages[-1].fin if plages else None
    return EnfantDayContext(
        enfant_id=enfant.id,
        libelle=enfant.libelle,
        presence=presence,
        statut_jour=statut,
        jour_fermeture=fermeture,
        phase_enfant=phase,
        plages=tuple(plages),
        creneaux_count=len(attendance),
        debut=debut,
        fin=fin,
        minutes=minutes,
        message=message,
    )


def compute_family_day(
    enfants: list[Enfant],
    plannings: dict[int, dict[str, Any]] | None,
    *,
    now: datetime | None = None,
    lead_minutes: int = PHASE_LEAD_MINUTES,
    unread_creche: int = 0,
) -> FamilyDayContext:
    """Agrège les contextes enfants en un état famille."""
    now = now or datetime.now()
    plannings = plannings or {}
    contexts = [
        compute_enfant_day(e, plannings.get(e.id), now=now, lead_minutes=lead_minutes)
        for e in enfants
    ]

    if not contexts:
        return FamilyDayContext(
            phase=PHASE_INCONNU,
            libelle=_PHASE_LIBELLES[PHASE_INCONNU],
            message="Intégration introuvable ou aucun enfant configuré.",
            minutes=None,
            cible=None,
            attention=False,
            attention_raison="RAS",
            jour_fermeture=False,
            tous_fermes=False,
            enfants=(),
        )

    tous_fermes = all(c.statut_jour == STATUT_FERME for c in contexts)
    known = [c for c in contexts if c.statut_jour != STATUT_INCONNU]
    jour_fermeture = (
        bool(known)
        and all(c.statut_jour in {STATUT_FERME, STATUT_AUCUN} for c in known)
        and any(c.statut_jour == STATUT_FERME for c in known)
    )

    if tous_fermes:
        phase = PHASE_FERME
        message = "Crèche fermée aujourd’hui."
        minutes = None
        cible = None
    else:
        # Priorité phase : deposer > chercher > creche > rentre > maison > inconnu
        priority = {
            PHASE_DEPOSER: 0,
            PHASE_CHERCHER: 1,
            PHASE_CRECHE: 2,
            PHASE_RENTRE: 3,
            PHASE_MAISON: 4,
            PHASE_FERME: 5,
            PHASE_INCONNU: 6,
        }
        best = min(contexts, key=lambda c: (priority.get(c.phase_enfant, 9), c.minutes or 10**9))
        # Si personne en deposer/chercher/creche, préférer message maison agrégé
        active = [
            c for c in contexts if c.phase_enfant in {PHASE_DEPOSER, PHASE_CHERCHER, PHASE_CRECHE}
        ]
        if active:
            best = min(active, key=lambda c: (priority.get(c.phase_enfant, 9), c.minutes or 10**9))
            phase = best.phase_enfant
            message = best.message
            minutes = best.minutes
            cible = best.libelle
        else:
            presents = [c for c in contexts if c.presence == "présent"]
            if not presents:
                phase = PHASE_MAISON
                if len(contexts) == 1:
                    message = contexts[0].message
                else:
                    message = "Journée à la maison — personne en crèche."
                minutes = None
                cible = None
            else:
                phase = best.phase_enfant
                message = best.message
                minutes = best.minutes
                cible = best.libelle

    attention_parts: list[str] = []
    if unread_creche > 0:
        attention_parts.append(f"{unread_creche} message(s)")
    if phase == PHASE_DEPOSER:
        attention_parts.append("déposer")
    if phase == PHASE_CHERCHER:
        attention_parts.append("récupérer")
    attention = bool(attention_parts)

    return FamilyDayContext(
        phase=phase,
        libelle=_PHASE_LIBELLES.get(phase, phase),
        message=message,
        minutes=minutes,
        cible=cible,
        attention=attention,
        attention_raison=" · ".join(attention_parts) if attention_parts else "RAS",
        jour_fermeture=jour_fermeture or tous_fermes,
        tous_fermes=tous_fermes,
        enfants=tuple(contexts),
    )


def enrich_enfant_status(
    status: dict[str, Any],
    ctx: EnfantDayContext,
) -> dict[str, Any]:
    """Fusionne un build_enfant_status avec le DayContext."""
    merged = dict(status)
    merged.update(
        {
            "statut_jour": ctx.statut_jour,
            "phase_enfant": ctx.phase_enfant,
            "plages": [
                {
                    "debut": p.debut,
                    "fin": p.fin,
                    "label": p.label,
                    "minutes_to_start": p.minutes_to_start,
                    "minutes_to_end": p.minutes_to_end,
                }
                for p in ctx.plages
            ],
            "creneaux_count": ctx.creneaux_count,
            "debut": ctx.debut,
            "fin": ctx.fin,
            "minutes": ctx.minutes,
            "message": ctx.message,
        }
    )
    return merged
