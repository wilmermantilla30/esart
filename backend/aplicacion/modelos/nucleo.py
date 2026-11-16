"""Entidades existentes; los contratos UUID previos se conservan en historico/."""

from .persistencia import (
    ArtilleroCargo,
    ArtilleroCertificacion,
    ArtilleroCurso,
    Componente,
    HojaVidaArtillero,
    PersonalMilitar,
    Rol,
    RolPermiso,
    SistemaArtilleria,
    TipoCargo,
    TipoCurso,
    UnidadMilitar,
    Usuario,
    UsuarioPermiso,
)

__all__ = [
    "UnidadMilitar",
    "PersonalMilitar",
    "HojaVidaArtillero",
    "Rol",
    "Usuario",
    "TipoCurso",
    "ArtilleroCurso",
    "ArtilleroCertificacion",
    "SistemaArtilleria",
    "TipoCargo",
    "ArtilleroCargo",
    "Componente",
    "RolPermiso",
    "UsuarioPermiso",
]
