import { Component, computed, input, output } from '@angular/core';

@Component({
  selector: 'app-ventana-bloqueo',
  standalone: true,
  imports: [],
  templateUrl: './ventana-bloqueo.html',
  styleUrl: './ventana-bloqueo.css',
})
export class VentanaBloqueo {
  readonly usuario = input<string>('');
  readonly intentosFallidos = input<number | null>(null);
  readonly detallesAdministrativos = input(false);
  readonly desbloqueoEstimado = input<string | null>(null);
  readonly codigoBloqueo = input<string>('');
  readonly direccionIp = input<string>('');
  readonly enviosActuales = input<number | null>(null);
  readonly fechaEnvio = input<string | null>(null);
  readonly ipObservacion = input<string | null>(null);
  // Reloj unico del padre, derivado de bloqueado_hasta y la hora del servidor.
  readonly segundosRestantes = input<number | null>(null);
  readonly cerrar = output<void>();
  readonly solicitarDesbloqueo = output<void>();
  protected readonly intentosVisibles = computed(() => {
    const valor = this.intentosFallidos();
    return this.detallesAdministrativos() && valor !== null && Number.isInteger(valor) && valor >= 0
      ? valor
      : null;
  });
  protected readonly tiempoFormateado = computed(() => {
    const total = this.segundosRestantes();
    if (total === null || !Number.isFinite(total) || total < 0) return 'No disponible';
    // HH:MM, redondeado hacia arriba para no anunciar 00:00 antes del vencimiento.
    const minutos = Math.ceil(total / 60);
    return [Math.floor(minutos / 60), minutos % 60]
      .map((valor) => String(valor).padStart(2, '0'))
      .join(':');
  });
  protected readonly fechaBloqueo = computed(() => {
    const fecha = this.desbloqueoEstimado();
    if (!fecha || !Number.isFinite(Date.parse(fecha))) return 'No disponible';
    return new Date(fecha).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' });
  });
  protected volverLogin(): void {
    this.cerrar.emit();
  }
  protected desbloquearToken(): void {
    this.solicitarDesbloqueo.emit();
  }
}
