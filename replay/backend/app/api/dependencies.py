"""Adaptateur FastAPI : récupérer le conteneur de la requête courante."""

from fastapi import Request

from app.bootstrap import Container


def get_container(request: Request) -> Container:
    return getattr(request.state, "visitor_container", request.app.state.container)
