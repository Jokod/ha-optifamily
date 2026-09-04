"""Constantes pour l'intégration OptiFamily."""

from __future__ import annotations

DOMAIN = "optifamily"

# Configuration
CONF_CRECHE_ID = "creche_id"
CONF_CRECHE_NAME = "creche_name"
CONF_ENFANTS = "enfants"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PAUSE_UPDATES = "pause_updates"
CONF_PAUSE_UPDATES_START = "pause_updates_start"
CONF_PAUSE_UPDATES_END = "pause_updates_end"
CONF_PAUSE_WHEN_CLOSED = "pause_when_closed"
CONF_ENABLED_ENFANTS = "enabled_enfants"
CONF_DOCUMENTS_SCOPE = "documents_scope"

# DayContext / phase famille
PHASE_LEAD_MINUTES = 90
DAY_TICK_SECONDS = 60

# Documents select (dashboard)
DOCUMENTS_SCOPE_CRECHE = "creche"
DOCUMENTS_SCOPE_FAMILLE = "famille"
DOCUMENTS_SCOPE_ENFANT = "enfant"
DOCUMENTS_SCOPES = (
    DOCUMENTS_SCOPE_CRECHE,
    DOCUMENTS_SCOPE_FAMILLE,
    DOCUMENTS_SCOPE_ENFANT,
)

# API
API_BASE_URL = "https://back.opticreche.fr"
API_PRE_LOGIN = "/auth/pre-login"
API_LOGIN = "/auth/login"
API_REFRESH = "/auth/refresh"
API_LOGOUT = "/api/auth/v3/logout"
API_ME = "/api/auth/v3/me"
API_ENFANTS = "/api/auth/v3/opti-family/enfants"
API_PLANNING = "/api/auth/v3/opti-family/enfant/{enfant_id}/planning/{year}/{month}"
API_TRANSMISSIONS = "/api/auth/v3/opti-family/enfant/{enfant_id}/transmissions/{date}"
API_ALBUMS = "/api/auth/v3/opti-family/enfant/{enfant_id}/albums"
API_ACTUALITES = "/api/auth/v3/opti-family/actualites/from/{from_}/to/{to}"
API_MESSAGES = "/api/auth/v3/opti-family/messages"
API_DOCUMENTS = "/api/auth/v3/opti-family/documents/creche/{creche_id}"
API_DOCUMENTS_FAMILLE = "/api/auth/v3/opti-family/documents/famille/{famille_id}"
API_DOCUMENTS_ENFANT = "/api/auth/v3/opti-family/documents/enfant/{enfant_id}"
API_FACTURATION = "/api/auth/v3/opti-family/facturation"

# Durées (secondes) — polling volontairement prudent pour ne pas spammer l'API
DEFAULT_SCAN_INTERVAL = 1800  # 30 minutes
MIN_SCAN_INTERVAL = 300  # minimum 5 minutes
MAX_SCAN_INTERVAL = 7200  # maximum 2 heures
DEFAULT_PAUSE_UPDATES = True
DEFAULT_PAUSE_UPDATES_START = "21:00:00"
DEFAULT_PAUSE_UPDATES_END = "06:00:00"
DEFAULT_PAUSE_WHEN_CLOSED = True
TOKEN_REFRESH_MARGIN = 60  # renouveler 60 s avant expiration
# Planning calendrier : un appel API par mois/enfant, puis cache
PLANNING_CACHE_TTL = DEFAULT_SCAN_INTERVAL  # 30 min (aligné polling)
PLANNING_ERROR_RETRY = 300  # 5 min avant de réessayer un mois en échec


def clamp_scan_interval(seconds: int | float | None) -> int:
    """Borne l'intervalle de rafraîchissement dans [MIN, MAX]."""
    try:
        value = int(seconds) if seconds is not None else DEFAULT_SCAN_INTERVAL
    except (TypeError, ValueError):
        value = DEFAULT_SCAN_INTERVAL
    return max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, value))


def scan_interval_from_minutes(minutes: int | float | None) -> int:
    """Convertit des minutes UI en secondes bornées pour le coordinator."""
    try:
        value = int(minutes) if minutes is not None else (DEFAULT_SCAN_INTERVAL // 60)
    except (TypeError, ValueError):
        value = DEFAULT_SCAN_INTERVAL // 60
    return clamp_scan_interval(value * 60)


def parse_clock(value: str | None, default: str) -> tuple[int, int, int]:
    """Parse `HH:MM` / `HH:MM:SS` → (h, m, s)."""
    raw = (value or default or "").strip()
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
    except (TypeError, ValueError, IndexError):
        return parse_clock(default, "00:00:00")
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return parse_clock(default, "00:00:00")
    return hour, minute, second


def clock_to_seconds(value: str | None, default: str) -> int:
    """Secondes depuis minuit pour comparer des horaires."""
    hour, minute, second = parse_clock(value, default)
    return hour * 3600 + minute * 60 + second


def is_update_paused(
    now_seconds: int,
    *,
    enabled: bool,
    start: str | None,
    end: str | None,
) -> bool:
    """True si `now` est dans [start, end) — gère les plages qui passent minuit."""
    if not enabled:
        return False
    start_s = clock_to_seconds(start, DEFAULT_PAUSE_UPDATES_START)
    end_s = clock_to_seconds(end, DEFAULT_PAUSE_UPDATES_END)
    now_s = int(now_seconds) % (24 * 3600)
    if start_s == end_s:
        return False
    if start_s < end_s:
        return start_s <= now_s < end_s
    return now_s >= start_s or now_s < end_s


# Stockage sécurisé dans le store HA (suffixé par entry_id)
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}.tokens"

# Timeouts HTTP
HTTP_TIMEOUT = 15

# Platforms
PLATFORMS = ["sensor", "binary_sensor", "calendar"]
