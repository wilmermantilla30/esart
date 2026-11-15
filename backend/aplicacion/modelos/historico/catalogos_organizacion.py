"""Propuesta HU-04 fase 3: clasificación institucional de unidades."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModelo


class TipoUnidad(BaseModelo):
    """Catálogo independiente del superior jerárquico de una unidad."""

    __tablename__ = "tipos_unidad"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'", name="codigo"),
        CheckConstraint("length(btrim(nombre)) > 0", name="nombre"),
    )
