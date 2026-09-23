"""
PurpleReplay v2 — Exceptions de domaine
— hiérarchie métier mappée sur des codes HTTP par les handlers de main.py.
Les services lèvent ; les routes ne gèrent pas les erreurs à la main.
"""

from __future__ import annotations


class DomainError(Exception):
    status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    """État incompatible (ex : pas de session chargée, pas de position)."""

    status_code = 409


class ValidationError(DomainError):
    status_code = 422


class ExternalServiceError(DomainError):
    """Feed live ou API PurpleChart injoignable."""

    status_code = 502
