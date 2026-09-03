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

# Durées (secondes)
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
TOKEN_REFRESH_MARGIN = 60  # renouveler 60 s avant expiration

# Stockage sécurisé dans le store HA (suffixé par entry_id)
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}.tokens"

# Timeouts HTTP
HTTP_TIMEOUT = 15

# Platforms
PLATFORMS = ["sensor"]
