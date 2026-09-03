"""Constantes pour l'intégration OptiFamily."""

from __future__ import annotations

DOMAIN = "optifamily"

# Configuration
CONF_CRECHE_ID = "creche_id"
CONF_CRECHE_NAME = "creche_name"
CONF_ENFANTS = "enfants"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

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
API_FACTURATION = "/api/auth/v3/opti-family/facturation"

# Durées (secondes) — polling volontairement prudent pour ne pas spammer l'API
DEFAULT_SCAN_INTERVAL = 1800  # 30 minutes
MIN_SCAN_INTERVAL = 300  # minimum 5 minutes
MAX_SCAN_INTERVAL = 7200  # maximum 2 heures
TOKEN_REFRESH_MARGIN = 60  # renouveler 60 s avant expiration


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


# Stockage sécurisé dans le store HA (suffixé par entry_id)
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}.tokens"

# Timeouts HTTP
HTTP_TIMEOUT = 15

# Platforms
PLATFORMS = ["sensor"]
