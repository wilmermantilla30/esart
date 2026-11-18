import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CargueManual } from './cargue-manual';

describe('CargueManual', () => {
  let component: CargueManual;
  let fixture: ComponentFixture<CargueManual>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CargueManual],
    }).compileComponents();

    fixture = TestBed.createComponent(CargueManual);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
