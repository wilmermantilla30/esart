/**
 * Ícono (Material Symbols) de cada componente del menú. La malla en la base guarda qué ve
 * cada usuario; el ícono es decisión visual del front. Un componente nuevo sin ícono
 * asignado usa ICONO_POR_DEFECTO, así agregar módulos no rompe el sidebar.
 */
export const ICONOS_MENU: Readonly<Record<string, string>> = {
  DASHBOARD: 'dashboard',
  PERSONAL_MILITAR: 'badge',
  PERSONAL_VERIFICAR: 'person_search',
  PERSONAL_HABILITADOS: 'military_tech',
  PERSONAL_CARGUE_EXCEL: 'upload_file',
  PERSONAL_CARGUE_MANUAL: 'person_add',
  HOJAS_VIDA: 'contact_page',
  CURSOS: 'school',
  NOTAS: 'grading',
  NOTAS_CARGA: 'edit_note',
  REENTRENAMIENTOS: 'target',
  CERTIFICACIONES: 'workspace_premium',
  DOCTRINA: 'menu_book',
  INSTRUCTORES: 'co_present',
  USUARIOS: 'manage_accounts',
  PARAMETROS_HABILITACION: 'tune',
  PERMISOS: 'admin_panel_settings',
  AUDITORIA: 'fact_check',
};

export const ICONO_POR_DEFECTO = 'widgets';

export function iconoDeComponente(codigo: string): string {
  return ICONOS_MENU[codigo] ?? ICONO_POR_DEFECTO;
}
