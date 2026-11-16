import { Component, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Unidad, UnidadesService } from './unidades.service';

@Component({
  selector: 'esart-unidades',
  template: `
    <h1>Unidades militares</h1>
    <p>Organización institucional de ESART</p>
    @if (cargando()) { <p role="status">Consultando unidades…</p> }
    @if (error()) { <p role="alert">{{ error() }}</p><button (click)="cargar()">Reintentar</button> }
    @if (!cargando() && !error()) {
      <p>{{ unidades().length }} unidades · {{ clasificadas() }} clasificadas ·
        {{ unidades().length - clasificadas() }} pendientes</p>
      <label>Buscar por código o nombre
        <input type="search" (input)="busqueda.set($any($event.target).value)" />
      </label>
      <label>Tipo de unidad
        <select (change)="tipo.set($any($event.target).value)">
          <option value="">Todos</option><option value="pendiente">Pendientes de clasificación</option>
          @for (t of tipos(); track t) { <option [value]="t">{{ t }}</option> }
        </select>
      </label>
      <label><input type="checkbox" (change)="activas.set($any($event.target).checked)" /> Solo activas</label>
      <table>
        <caption>Unidades y relaciones jerárquicas</caption>
        <thead><tr><th>Código</th><th>Nombre</th><th>Tipo</th><th>Superior</th><th>Jerarquía</th></tr></thead>
        <tbody>
          @for (u of visibles(); track u.id) {
            <tr><td>{{ u.codigo }}</td><td>{{ u.nombre }}</td>
              <td>{{ u.tipo_nombre ?? 'Pendiente de clasificación' }}</td>
              <td>{{ u.padre_codigo ?? 'Sin superior' }}</td><td>{{ ruta(u) }}</td></tr>
          } @empty { <tr><td colspan="5">No hay unidades que coincidan con los filtros.</td></tr> }
        </tbody>
      </table>
    }
  `,
  styles: [`:host { display:block; padding:2rem; font-family:system-ui; }
    label { display:inline-block; margin:0 1rem 1rem 0; } input, select, button { padding:.5rem; }
    table { width:100%; border-collapse:collapse; } th,td { text-align:left; padding:.75rem; border-bottom:1px solid #ccc; }
    caption { text-align:left; padding:1rem 0; } [role=alert] { color:#9b2226; }`],
})
export class Unidades {
  private readonly servicio = inject(UnidadesService);
  readonly unidades = signal<Unidad[]>([]);
  readonly cargando = signal(true);
  readonly error = signal('');
  readonly busqueda = signal('');
  readonly tipo = signal('');
  readonly activas = signal(false);
  readonly clasificadas = computed(() => this.unidades().filter(u => !u.clasificacion_pendiente).length);
  readonly tipos = computed(() => [...new Set(this.unidades().flatMap(u => u.tipo_nombre ? [u.tipo_nombre] : []))].sort());
  readonly visibles = computed(() => this.unidades().filter(u =>
    `${u.codigo} ${u.nombre}`.toLocaleLowerCase().includes(this.busqueda().toLocaleLowerCase()) &&
    (!this.activas() || u.activo) &&
    (!this.tipo() || (this.tipo() === 'pendiente' ? u.clasificacion_pendiente : u.tipo_nombre === this.tipo()))));

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set('');
    this.servicio.listar().subscribe({
      next: datos => { this.unidades.set(datos); this.cargando.set(false); },
      error: (e: HttpErrorResponse) => {
        this.unidades.set([]);
        this.error.set(e.status === 401 ? 'Inicie sesión para consultar las unidades.' :
          e.status === 403 ? 'No tiene permiso para consultar las unidades.' :
          'No fue posible consultar ESART. Revise la conexión del backend.');
        this.cargando.set(false);
      },
    });
  }

  ruta(unidad: Unidad): string {
    const porId = new Map(this.unidades().map(u => [u.id, u]));
    const vistos = new Set<string>();
    const partes: string[] = [];
    let actual: Unidad | undefined = unidad;
    while (actual) {
      if (vistos.has(actual.id)) return 'Error: ciclo jerárquico';
      vistos.add(actual.id);
      partes.unshift(actual.codigo);
      if (actual.unidad_padre_id && !porId.has(actual.unidad_padre_id)) return 'Error: superior inexistente';
      actual = actual.unidad_padre_id ? porId.get(actual.unidad_padre_id) : undefined;
    }
    return partes.join(' → ');
  }
}
