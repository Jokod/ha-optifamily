"""Modèles et helpers pour les données OptiFamily (multi-enfants)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any

_CRENEAU_BOUNDS = re.compile(r"(\d{1,2})[:hH](\d{2})\s*[-–]\s*(\d{1,2})[:hH](\d{2})")
_CLOSED_TYPE_RE = re.compile(r"ferm|cong[eé]|absence|closed|f[eé]ri[eé]", re.IGNORECASE)
_CLOSED_LABEL_RE = re.compile(
    r"(fermeture|ferm[eé]|closed|cong[eé]s?|absence|f[eé]ri[eé])",
    re.IGNORECASE,
)


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


def enabled_enfant_ids(
    all_enfants: list[Enfant],
    enabled_option: list[Any] | None,
) -> set[int] | None:
    """IDs suivis depuis les options ; None = tous."""
    if enabled_option is None:
        return None
    if not isinstance(enabled_option, list | tuple | set):
        return None
    ids: set[int] = set()
    for raw in enabled_option:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    known = {e.id for e in all_enfants}
    return ids & known if known else ids


def iter_enfants_enabled(
    live_enfants: list[dict[str, Any]],
    persisted_enfants: list[dict[str, Any]] | None = None,
    *,
    enabled_ids: list[Any] | set[int] | None = None,
) -> list[Enfant]:
    """Enfants fusionnés filtrés par la liste « enfants suivis »."""
    enfants = iter_enfants(live_enfants, persisted_enfants)
    if enabled_ids is None or not isinstance(enabled_ids, list | tuple | set):
        return enfants
    allowed = enabled_enfant_ids(enfants, list(enabled_ids))
    if allowed is None:
        return enfants
    return [e for e in enfants if e.id in allowed]


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


def is_closed_creneau(creneau: Any) -> bool:
    """True si le créneau représente une fermeture / absence / jour férié."""
    if not isinstance(creneau, dict):
        return False
    ctype = str(creneau.get("type") or "").strip()
    if ctype and _CLOSED_TYPE_RE.search(ctype):
        return True
    blob = f"{creneau.get('label') or ''} {creneau.get('details') or ''}"
    return bool(_CLOSED_LABEL_RE.search(blob))


def is_jour_fermeture(planning: dict[str, Any] | None, day: date | None = None) -> bool:
    """True si le jour contient au moins un créneau de fermeture."""
    return any(is_closed_creneau(c) for c in get_today_creneaux(planning, day))


def get_attendance_creneaux(
    planning: dict[str, Any] | None, day: date | None = None
) -> list[dict[str, Any]]:
    """Créneaux de présence réelle (réguliers), vide si jour de fermeture."""
    creneaux = get_today_creneaux(planning, day)
    if any(is_closed_creneau(c) for c in creneaux):
        return []
    return [c for c in creneaux if str(c.get("type") or "").strip().lower() == "regulier"]


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
    return "présent" if get_attendance_creneaux(planning, day) else "absent"


def is_creche_closed_for_family(
    plannings: dict[int, dict[str, Any]] | None,
    day: date | None = None,
) -> bool:
    """True si le jour est connu et qu'aucun enfant n'a de créneau régulier.

    Couvre week-ends, fermetures et jours sans inscription — à partir du
    planning déjà en cache (pas d'appel API).
    """
    if not plannings:
        return False
    day = day or date.today()
    known = False
    for planning in plannings.values():
        presence = get_presence(planning, day)
        if presence == "présent":
            return False
        if presence == "absent":
            known = True
    return known


def build_enfant_status(
    enfant: Enfant,
    planning: dict[str, Any] | None,
    transmissions: list[dict[str, Any]] | None,
    albums: list[dict[str, Any]] | None,
    day: date | None = None,
) -> dict[str, Any]:
    """Construit le résumé d'un enfant pour capteurs agrégés et tableaux de bord."""
    creneaux = get_today_creneaux(planning, day)
    attendance = get_attendance_creneaux(planning, day)
    return {
        "id": enfant.id,
        "libelle": enfant.libelle,
        "presence": get_presence(planning, day),
        "jour_fermeture": is_jour_fermeture(planning, day),
        "creneaux": [c.get("label") for c in attendance if c.get("label")],
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


def build_enfants_summary(
    data: Any,
    day: date | None = None,
    *,
    enabled_ids: list[Any] | set[int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Résumé multi-enfants pour capteurs globaux et templates Lovelace."""
    from .day_context import compute_enfant_day, enrich_enfant_status

    enfants = iter_enfants_enabled(
        data.enfants,
        getattr(data, "persisted_enfants", None),
        enabled_ids=enabled_ids,
    )
    liste: list[dict[str, Any]] = []
    presents: list[str] = []
    now = now or datetime.now()
    day = day or now.date()

    for enfant in enfants:
        status = build_enfant_status(
            enfant,
            data.plannings.get(enfant.id),
            data.transmissions.get(enfant.id),
            data.albums.get(enfant.id) if hasattr(data, "albums") else None,
            day,
        )
        ctx = compute_enfant_day(enfant, data.plannings.get(enfant.id), now=now)
        status = enrich_enfant_status(status, ctx)
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


# ─── Transmissions ───────────────────────────────────────────────

_TRANSMISSION_TYPE_LABELS: dict[str, str] = {
    "sieste": "Sieste",
    "change": "Change",
    "repas": "Repas",
    "arrivee": "Arrivée",
    "depart": "Départ",
    "activite": "Activité",
    "sante": "Santé",
    "humeur": "Humeur",
    "hygiene": "Hygiène",
    "note": "Note",
}

_TRANSMISSION_ICON_MDI: dict[str, str] = {
    "sieste": "mdi:sleep",
    "sieste2": "mdi:sleep",
    "couche": "mdi:human-baby-changing-table",
    "biberon": "mdi:baby-bottle-outline",
    "repas": "mdi:food-apple-outline",
    "arrivee": "mdi:login",
    "depart": "mdi:logout",
    "activite": "mdi:palette-outline",
    "sante": "mdi:medical-bag",
    "humeur": "mdi:emoticon-outline",
    "note": "mdi:note-text-outline",
}

_TRANSMISSION_EMOJI: dict[str, str] = {
    "sieste": "💤",
    "change": "🧷",
    "repas": "🍼",
    "arrivee": "🚪",
    "depart": "🏠",
    "activite": "🎨",
    "sante": "💊",
    "humeur": "😊",
    "note": "📝",
}

_TRANSMISSION_COLOR: dict[str, str] = {
    "sieste": "indigo",
    "change": "amber",
    "repas": "cyan",
    "arrivee": "green",
    "depart": "deep-orange",
    "activite": "purple",
    "sante": "red",
    "humeur": "pink",
    "hygiene": "teal",
    "note": "blue-grey",
}

_SIESTE_QUALITE: dict[str, str] = {
    "0": "Pas dormi",
    "1": "Peu",
    "2": "Bien",
    "3": "Très bien",
}

_CHANGE_PROPRETE: dict[str, str] = {
    "couche": "Couche",
    "pot": "Sur le pot",
    "toilettes": "Aux toilettes",
    "toilette": "Aux toilettes",
    "": "Aucun",
}

_CHANGE_CONTENU: dict[str, str] = {
    "pipi": "Urine",
    "caca": "Selles",
}


def format_minutes_clock(value: Any) -> str | None:
    """Convertit des minutes depuis minuit (`585` → `09:45`)."""
    try:
        total = int(value)
    except (TypeError, ValueError):
        return None
    if total < 0 or total >= 24 * 60:
        return None
    return f"{total // 60:02d}:{total % 60:02d}"


def _transmission_display_time(raw: dict[str, Any]) -> str | None:
    """Heure affichée selon le type (arrivée/départ/sieste ≠ durée dans detail)."""
    kind = str(raw.get("type") or "").lower()
    detail = str(raw.get("detail") or "").strip()
    if kind in {"arrivee", "depart"}:
        if detail and re.fullmatch(r"\d{1,2}:\d{2}", detail):
            parts = detail.split(":")
            return f"{int(parts[0]):02d}:{parts[1]}"
        return format_minutes_clock(raw.get("valeur1")) or format_minutes_clock(raw.get("heure"))
    if kind == "sieste":
        # `heure` = début, `valeur1` = fin (minutes), `detail` = durée
        return format_minutes_clock(raw.get("heure")) or format_minutes_clock(raw.get("valeur1"))
    return format_minutes_clock(raw.get("heure"))


def _transmission_title(raw: dict[str, Any]) -> str:
    kind = str(raw.get("type") or "").strip().lower()
    sous = str(raw.get("sousType") or raw.get("sous_type") or "").strip()
    base = _TRANSMISSION_TYPE_LABELS.get(kind, kind.capitalize() if kind else "Transmission")
    if kind == "change" and sous:
        return base
    if kind == "repas" and sous:
        return sous.capitalize()
    if sous and sous.lower() not in {kind, "couche"}:
        return f"{base} · {sous}"
    return base


def _transmission_detail_text(raw: dict[str, Any]) -> str:
    """Complément lisible (durée, volume, pipi/caca, etc.)."""
    kind = str(raw.get("type") or "").lower()
    detail = str(raw.get("detail") or "").strip()
    v1 = str(raw.get("valeur1") or "").strip()
    if kind == "change":
        return v1 if v1 and v1.lower() != "non défini" else detail
    if kind == "repas":
        return detail or (f"{v1} ml" if v1.isdigit() else v1)
    if kind == "sieste":
        return detail
    if kind in {"arrivee", "depart"}:
        clock = _transmission_display_time(raw)
        if detail and detail != clock and not re.fullmatch(r"\d{1,2}:\d{2}", detail):
            return detail
        return ""
    return detail or v1


def _transmission_rows(
    raw: dict[str, Any], *, debut: str | None, fin: str | None
) -> list[dict[str, str]]:
    """Lignes label/valeur pour l'UI type portail (badges)."""
    kind = str(raw.get("type") or "").lower()
    sous = str(raw.get("sousType") or raw.get("sous_type") or "").strip().lower()
    v1 = str(raw.get("valeur1") or "").strip()
    v2 = str(raw.get("valeur2") or "").strip()
    detail = str(raw.get("detail") or "").strip()
    complements = str(raw.get("complements") or "").strip()
    rows: list[dict[str, str]] = []

    if kind == "sieste":
        if debut:
            rows.append({"label": "Début", "value": debut, "kind": "badge"})
        if fin:
            rows.append({"label": "Fin", "value": fin, "kind": "badge"})
        if detail:
            rows.append({"label": "Durée", "value": detail, "kind": "badge"})
        qualite = _SIESTE_QUALITE.get(v2)
        if qualite:
            rows.append({"label": "Qualité du sommeil", "value": qualite, "kind": "chip"})
    elif kind == "change":
        heure = format_minutes_clock(raw.get("heure"))
        if heure:
            rows.append({"label": "Heure", "value": heure, "kind": "badge"})
        proprete = _CHANGE_PROPRETE.get(sous, sous.capitalize() if sous else "Aucun")
        rows.append({"label": "Propreté", "value": proprete, "kind": "chip"})
        contenu = _CHANGE_CONTENU.get(v1.lower(), v1.capitalize() if v1 else "")
        if contenu:
            rows.append({"label": "Contenu", "value": contenu, "kind": "chip"})
        if v2:
            rows.append({"label": "Type de selles", "value": v2, "kind": "badge"})
    elif kind == "repas":
        heure = format_minutes_clock(raw.get("heure"))
        if heure:
            rows.append({"label": "Heure", "value": heure, "kind": "badge"})
        volume = detail or (f"{v1} ml" if v1.isdigit() else v1)
        if volume:
            rows.append({"label": "Quantité", "value": volume, "kind": "badge"})
    elif kind in {"arrivee", "depart"}:
        heure = _transmission_display_time(raw)
        if heure:
            rows.append({"label": "Heure", "value": heure, "kind": "badge"})
    else:
        heure = format_minutes_clock(raw.get("heure"))
        if heure:
            rows.append({"label": "Heure", "value": heure, "kind": "badge"})
        if detail:
            rows.append({"label": "Détail", "value": detail, "kind": "text"})

    if complements:
        rows.append({"label": "Note", "value": complements, "kind": "note"})
    return rows


def _transmission_bloc(rows: list[dict[str, str]]) -> str:
    """Texte multi-lignes pour secondary mushroom."""
    lines: list[str] = []
    for row in rows:
        label = str(row.get("label") or "")
        value = str(row.get("value") or "")
        kind = str(row.get("kind") or "badge")
        if kind == "note":
            lines.append(f"💬 {value}")
        else:
            lines.append(f"{label}  ·  {value}")
    return "\n".join(lines)


def _transmission_chips(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Chips Lovelace (badges bleus / chips verts)."""
    chips: list[dict[str, str]] = []
    for row in rows:
        kind = str(row.get("kind") or "badge")
        if kind == "note":
            continue
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        label = str(row.get("label") or "").strip()
        content = f"{label} {value}" if kind == "badge" and label else value
        chips.append(
            {
                "content": content,
                "tone": "success" if kind == "chip" else "info",
            }
        )
    return chips


def normalize_transmission(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise une transmission API pour capteurs / Lovelace."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "").strip().lower()
    icon_key = str(raw.get("icon") or kind or "").strip().lower()
    titre = _transmission_title(raw)
    detail = _transmission_detail_text(raw)
    complements = str(raw.get("complements") or "").strip()
    debut = fin = None
    if kind == "sieste":
        debut = format_minutes_clock(raw.get("heure"))
        fin = format_minutes_clock(raw.get("valeur1"))
    heure = _transmission_display_time(raw)
    rows = _transmission_rows(raw, debut=debut, fin=fin)
    sort_key = 0
    try:
        sort_key = int(raw.get("heure") or 0)
    except (TypeError, ValueError):
        sort_key = 0
    return {
        "id": raw.get("id"),
        "type": kind,
        "sous_type": str(raw.get("sousType") or raw.get("sous_type") or "").strip(),
        "icon": _TRANSMISSION_ICON_MDI.get(icon_key)
        or _TRANSMISSION_ICON_MDI.get(kind)
        or "mdi:clipboard-text-outline",
        "emoji": _TRANSMISSION_EMOJI.get(kind, "📋"),
        "color": _TRANSMISSION_COLOR.get(kind, "teal"),
        "heure": heure,
        "debut": debut,
        "fin": fin,
        "titre": titre,
        "detail": detail,
        "complements": complements,
        "marquant": bool(raw.get("marquant")),
        "rows": rows,
        "chips": _transmission_chips(rows),
        "bloc": _transmission_bloc(rows),
        "sort_key": sort_key,
        "ligne": format_transmission_ligne(
            {"heure": heure, "titre": titre, "detail": detail, "complements": complements}
        ),
    }


def format_transmission_ligne(item: dict[str, Any]) -> str:
    """Une ligne texte : `09:45 · Sieste · 01:00 — note`."""
    parts: list[str] = []
    if item.get("heure"):
        parts.append(str(item["heure"]))
    if item.get("titre"):
        parts.append(str(item["titre"]))
    if item.get("detail"):
        parts.append(str(item["detail"]))
    line = " · ".join(parts) if parts else "Transmission"
    if item.get("complements"):
        line = f"{line} — {item['complements']}"
    return line


def normalize_transmissions(raw_list: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Liste normalisée triée chronologiquement."""
    items: list[dict[str, Any]] = []
    for raw in raw_list or []:
        item = normalize_transmission(raw)
        if item:
            items.append(item)
    items.sort(key=lambda i: (i.get("sort_key") or 0, str(i.get("heure") or "")))
    return items


def transmissions_markdown(
    raw_list: list[dict[str, Any]] | None,
    *,
    enfant_libelle: str | None = None,
    jour: str | None = None,
    limit: int | None = None,
) -> str:
    """Markdown natif HA (titres + badges `code`) — sans HTML (DOMPurify)."""
    items = normalize_transmissions(raw_list)
    truncated = False
    if limit is not None and len(items) > limit:
        items = items[:limit]
        truncated = True

    lines: list[str] = []
    header_bits = [str(b) for b in (enfant_libelle, jour) if b]
    if header_bits:
        lines.append(f"### {' · '.join(header_bits)}")
        lines.append("")
    if not items:
        lines.append("_Aucune transmission_")
        return "\n".join(lines)

    for item in items:
        star = " ★" if item.get("marquant") else ""
        lines.append(f"**{item.get('emoji') or '📋'} {item.get('titre') or 'Transmission'}{star}**")
        for row in item.get("rows") or []:
            label = str(row.get("label") or "")
            value = str(row.get("value") or "")
            kind = str(row.get("kind") or "badge")
            if kind == "note":
                lines.append(f"  _{value}_")
            elif kind == "chip":
                lines.append(f"- {label} → **{value}**")
            elif kind == "text":
                lines.append(f"- {label} — {value}")
            else:
                lines.append(f"- {label} `{value}`")
        lines.append("")
    if truncated:
        lines.append("_Voir le journal pour la suite…_")
    return "\n".join(lines).rstrip() + "\n"


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


def _pick_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def _pick_id(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = data.get(key)
        if raw is None or isinstance(raw, dict | list):
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def normalize_downloadable_item(
    raw: Any,
    *,
    kind: str,
    limit_photos: int | None = None,
) -> dict[str, Any] | None:
    """Normalise un item API en entrée riche UI (+ métadonnées téléchargement)."""
    if not isinstance(raw, dict):
        return None
    item_id = _pick_id(raw, "id", "photoId", "documentId", "factureId", "mediaId", "uuid")
    titre = _pick_str(
        raw,
        "titre",
        "title",
        "label",
        "libelle",
        "nom",
        "name",
        "filename",
        "fileName",
    )
    download_url = _pick_str(
        raw,
        "download_url",
        "downloadUrl",
        "url",
        "mediaUrl",
        "media_url",
        "fichierUrl",
        "fileUrl",
        "path",
    )
    media_id = _pick_id(raw, "mediaId", "media_id", "fichierId", "fileId") or item_id
    downloadable = bool(download_url or media_id)
    item: dict[str, Any] = {
        "id": item_id,
        "titre": titre or (f"{kind} {item_id}" if item_id else kind),
        "label": titre or "",
        "kind": kind,
        "downloadable": downloadable,
        "download_url": download_url,
        "media_id": media_id if downloadable else None,
        "date": _pick_str(raw, "date", "createdAt", "created_at", "dateCreation"),
    }
    if kind == "album":
        photos_raw = raw.get("photos") or raw.get("medias") or raw.get("images") or []
        photos: list[dict[str, Any]] = []
        if isinstance(photos_raw, list):
            for photo in photos_raw:
                normalized = normalize_downloadable_item(photo, kind="photo")
                if normalized:
                    photos.append(normalized)
                if limit_photos is not None and len(photos) >= limit_photos:
                    break
        item["photos"] = photos
        item["photos_count"] = len(photos_raw) if isinstance(photos_raw, list) else len(photos)
    if kind == "message":
        item["corps"] = (
            _pick_str(raw, "corps", "body", "contenu", "content", "message", "texte") or ""
        )
        item["vu"] = bool(raw.get("vu", True))
        item["sender"] = bool(raw.get("sender", False))
        item["downloadable"] = False
        item["download_url"] = None
        item["media_id"] = None
    return item


def normalize_album_items(albums: list[Any] | None, *, limit: int = 20) -> list[dict[str, Any]]:
    """Albums + photos imbriquées pour attributs capteur."""
    items: list[dict[str, Any]] = []
    for raw in albums or []:
        item = normalize_downloadable_item(raw, kind="album", limit_photos=10)
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_document_items(
    documents: list[Any] | None, *, limit: int = 20
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in documents or []:
        item = normalize_downloadable_item(raw, kind="document")
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_facture_items(factures: list[Any] | None, *, limit: int = 20) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in factures or []:
        item = normalize_downloadable_item(raw, kind="facture")
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_actualite_items(actualites: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    raw_list: list[Any]
    if isinstance(actualites, dict):
        raw_list = list(actualites.get("actualites") or actualites.get("items") or [])
    elif isinstance(actualites, list):
        raw_list = actualites
    else:
        raw_list = []
    items: list[dict[str, Any]] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        item = {
            "id": _pick_id(raw, "id"),
            "titre": _pick_str(raw, "titre", "title", "libelle", "label") or "Actualité",
            "date": _pick_str(raw, "date", "createdAt", "created_at"),
            "resume": _pick_str(raw, "resume", "summary", "contenu", "content", "texte") or "",
            "downloadable": False,
        }
        items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_message_items(messages: list[Any] | None, *, limit: int = 20) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in messages or []:
        item = normalize_downloadable_item(raw, kind="message")
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


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
