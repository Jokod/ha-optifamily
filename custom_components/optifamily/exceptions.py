"""Exceptions pour l'intégration OptiFamily."""

from __future__ import annotations


class OptieFamilyError(Exception):
    """Erreur de base de l'intégration."""


class OptieFamilyAuthError(OptieFamilyError):
    """Erreur d'authentification (identifiants invalides, token expiré…)."""


class OptieFamilyConnectionError(OptieFamilyError):
    """Erreur de connexion réseau ou timeout."""


class OptieFamilyApiError(OptieFamilyError):
    """Erreur renvoyée par l'API (statut HTTP inattendu)."""

    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class OptieFamilyMultipleCrechesError(OptieFamilyError):
    """Plusieurs crèches disponibles — sélection requise."""

    def __init__(self, creches: list[dict]) -> None:
        self.creches = creches
        super().__init__(f"{len(creches)} crèches disponibles pour ce compte")


class OptieFamilySetupError(OptieFamilyError):
    """Erreur lors de la découverte automatique du compte."""
