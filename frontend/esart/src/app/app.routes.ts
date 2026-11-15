import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'unidades', pathMatch: 'full' },
  { path: 'unidades', loadComponent: () => import('./unidades').then(m => m.Unidades) },
];
