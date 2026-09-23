"""Sélection des deux générations d’archives, lecture seule."""


class ArchiveSources:
    """Repository facade: select once before starting a reader, not during its execution."""

    def __init__(self, legacy, modern):
        self.legacy = legacy
        self.modern = modern
        self.active = legacy
        self.kind = "legacy"

    def select(self, kind):
        if kind not in ("legacy", "v2"):
            raise ValueError("Source de séance invalide")
        self.active = self.modern if kind == "v2" else self.legacy
        self.kind = kind

    @property
    def path(self):
        return self.active.path

    def __getattr__(self, key):
        return getattr(self.active, key)


class GammaSources:
    # [Sol] No legacy gamma/vanna fallback when the selected session comes from V2.
    def __init__(self, archives, legacy, modern):
        self.archives = archives
        self.legacy = legacy
        self.modern = modern

    @property
    def is_modern(self):
        return self.archives.kind == "v2"

    def __getattr__(self, key):
        return getattr(self.modern if self.is_modern else self.legacy, key)
