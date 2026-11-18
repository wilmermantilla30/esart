"""Esquemas del panel de Parámetros (contrato de API §6)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ValoresRegla(BaseModel):
    """Los cuatro valores de la regla APTO / NO APTO."""

    model_config = ConfigDict(extra="forbid")

    cursos_habilitantes: list[str] = Field(max_length=50)
    meses_vigencia_reentrenamiento: int
    dias_alerta_vencimiento: int
    exige_apto_para_disparar: bool


class CursoDisponible(BaseModel):
    codigo: str
    nombre: str


class ResumenRegla(BaseModel):
    total: int
    aptos: int
    no_aptos: int
    reentrenamiento_por_vencer: int


class ReglaHabilitacion(BaseModel):
    """Lo que muestra la pestaña Cursos y Capacitaciones."""

    valores: ValoresRegla
    actualizado_en: datetime | None
    actualizado_por: str | None
    cursos_disponibles: list[CursoDisponible]
    resumen: ResumenRegla


class SimulacionRegla(BaseModel):
    actual: ResumenRegla
    propuesto: ResumenRegla
    pasan_a_no_apto: int
    pasan_a_apto: int


class SolicitudGuardarRegla(ValoresRegla):
    """Guardar exige la versión que se editó (concurrencia) y, si aplica, el código TOTP."""

    version: datetime | None
    codigo_totp: str = Field(default="", max_length=6, repr=False)


class Plantilla(BaseModel):
    id: int
    nombre_oficial: str
    nombre_archivo: str
    formato: str
    version: str
    descripcion: str
    tamano_bytes: int
    sha256: str
    subido_en: datetime
    subido_por: str | None


class PoliticaSeguridad(BaseModel):
    codigo: str
    nombre: str
    modulo: str
    requiere_totp: bool
    activa: bool


class ParametrosSeguridad(BaseModel):
    """Pestaña Parámetros de Seguridad: solo consulta (las políticas no se editan desde la web)."""

    totp_habilitado: bool
    usuarios_activos: int
    usuarios_con_autenticador: int
    minutos_inactividad_sesion: int
    intento_captcha: int
    intento_bloqueo: int
    horas_bloqueo: int
    politicas: list[PoliticaSeguridad]
