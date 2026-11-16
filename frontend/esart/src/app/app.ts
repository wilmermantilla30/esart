import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AvisoInactividad } from './compartido/aviso-inactividad/aviso-inactividad';

@Component({
  imports: [RouterOutlet, AvisoInactividad],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  protected readonly title = signal('esart');
}
