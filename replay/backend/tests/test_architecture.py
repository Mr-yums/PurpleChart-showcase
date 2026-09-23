"""Garde-fous sur le sens des dépendances et l'isolation du runtime."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = ROOT / "app"


def imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_dependency_direction():
    for layer, forbidden in {
        "domain": (
            "app.services",
            "app.repositories",
            "app.infra",
            "app.api",
            "app.bootstrap",
            "fastapi",
            "pydantic",
            "sqlite3",
            "httpx",
        ),
        "services": ("app.api", "app.bootstrap", "app.main", "app.visitor_workspaces"),
        "repositories": ("app.services", "app.api", "app.bootstrap", "app.main"),
        "api": ("app.repositories", "app.services", "app.infra"),
    }.items():
        for path in (APP / layer).rglob("*.py"):
            for name in imports(path):
                assert not name.startswith(forbidden), f"{path.relative_to(APP)} -> {name}"
    assert not any(name.startswith("fastapi") for name in imports(APP / "bootstrap.py"))


def test_internal_module_graph_is_acyclic():
    graph = {
        "app." + ".".join(p.relative_to(APP).with_suffix("").parts): set(imports(p))
        for p in APP.rglob("*.py")
    }
    visited = set()

    def visit(name, stack):
        assert name not in stack, " -> ".join((*stack, name))
        if name in visited:
            return
        for target in graph.get(name, ()):
            if target in graph:
                visit(target, (*stack, name))
        visited.add(name)

    for name in graph:
        visit(name, ())


def test_runtime_has_no_test_or_outbound_http_client_packages():
    packages = {
        line.split("==")[0]
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert not packages & {"pytest", "pytest-asyncio", "httpx", "httpcore", "ruff", "watchfiles"}


def test_services_do_not_access_another_objects_private_attributes():
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Attribute)
                and node.attr.startswith("_")
                and not node.attr.startswith("__")
            ):
                assert isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"), (
                    f"{path.relative_to(APP)}:{node.lineno} {ast.unparse(node)}"
                )
