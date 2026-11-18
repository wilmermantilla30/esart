import { ComponentFixture, TestBed } from '@angular/core/testing';
import { VentanaBloqueo } from './ventana-bloqueo';

describe('VentanaBloqueo', () => {
  let component: VentanaBloqueo;
  let fixture: ComponentFixture<VentanaBloqueo>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VentanaBloqueo],
    }).compileComponents();

    fixture = TestBed.createComponent(VentanaBloqueo);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('no inventa cero intentos ni expone detalles en la ventana pública', () => {
    fixture.componentRef.setInput('intentosFallidos', 7);
    fixture.componentRef.setInput('direccionIp', '192.0.2.4');
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent;
    expect(texto).toContain('Este comprobante no incluye datos del envío');
    expect(texto).not.toContain('0 registrados');
    expect(texto).not.toContain('7 registrados');
    expect(texto).not.toContain('192.0.2.4');
  });

  it('muestra el dato administrativo y usa exclusivamente el reloj del padre', () => {
    fixture.componentRef.setInput('detallesAdministrativos', true);
    fixture.componentRef.setInput('intentosFallidos', 7);
    fixture.componentRef.setInput('segundosRestantes', 3601);
    fixture.componentRef.setInput('desbloqueoEstimado', '2026-11-16T15:00:00Z');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('7 registrados');
    expect(fixture.nativeElement.textContent).toContain('01:01');
    fixture.componentRef.setInput('segundosRestantes', 3600);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('01:00');
  });
});
