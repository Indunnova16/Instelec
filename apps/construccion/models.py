"""
Models for construction (línea de transmisión en construcción) project management.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.gis.db import models as gis_models

from apps.core.models import BaseModel
from apps.contratos.models import Contrato


class ProyectoConstruccion(BaseModel):
    """
    A construction project linked to a Construccion contract.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contrato = models.OneToOneField(
        Contrato,
        on_delete=models.CASCADE,
        limit_choices_to={'unidad_negocio': 'CONSTRUCCION'},
        related_name='proyecto_construccion',
    )
    nombre = models.CharField('Nombre del proyecto', max_length=300)
    descripcion = models.TextField('Descripción', blank=True)
    fecha_inicio = models.DateField('Fecha de inicio', null=True, blank=True)
    fecha_fin_estimada = models.DateField('Fecha fin estimada', null=True, blank=True)
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=[
            ('PLANIFICACION', 'Planificación'),
            ('EJECUCION', 'Ejecución'),
            ('CIERRE', 'Cierre'),
            ('FINALIZADO', 'Finalizado'),
        ],
        default='PLANIFICACION',
    )
    observaciones = models.TextField('Observaciones', blank=True)

    # Pesos editables por actividad — para % avance ponderado (#61)
    # Defaults según Gabriel Acevedo (Reunión 7, 00:11:36):
    # excavación 30%, vaciado 40%, relleno 20% — ajustables.
    peso_cerramiento_pct = models.PositiveSmallIntegerField('Peso Cerramiento %', default=5)
    peso_excavacion_pct = models.PositiveSmallIntegerField('Peso Excavación %', default=30)
    peso_solado_pct = models.PositiveSmallIntegerField('Peso Solado %', default=5)
    peso_acero_pct = models.PositiveSmallIntegerField('Peso Acero %', default=15)
    peso_vaciado_pct = models.PositiveSmallIntegerField('Peso Vaciado %', default=30)
    peso_compactacion_pct = models.PositiveSmallIntegerField('Peso Compactación %', default=15)

    # Pesos editables CANT MONTAJE (#76) — defaults del Excel del cliente (suma=100)
    peso_mont_estructura_sitio_pct = models.PositiveSmallIntegerField(
        'Peso Estructura en sitio %', default=10)
    peso_mont_prearamada_pct = models.PositiveSmallIntegerField(
        'Peso Prearmada %', default=20)
    peso_mont_torre_montada_pct = models.PositiveSmallIntegerField(
        'Peso Torre montada %', default=45)
    peso_mont_revisada_pct = models.PositiveSmallIntegerField(
        'Peso Revisada %', default=25)

    # Pesos editables CANT TENDIDO (#79) — Conductor: 6 actividades (suma=100)
    peso_tend_riega_manila_pct = models.PositiveSmallIntegerField(
        'Tend. Riega manila %', default=10)
    peso_tend_riega_guaya_pct = models.PositiveSmallIntegerField(
        'Tend. Riega guaya conductor %', default=30)
    peso_tend_tendido_conductor_pct = models.PositiveSmallIntegerField(
        'Tend. Tendido conductor %', default=30)
    peso_tend_grapado_pct = models.PositiveSmallIntegerField(
        'Tend. Grapado/amarre %', default=10)
    peso_tend_accesorios_pct = models.PositiveSmallIntegerField(
        'Tend. Accesorios/puentes %', default=10)
    peso_tend_balizas_pct = models.PositiveSmallIntegerField(
        'Tend. Balizas/desviadores %', default=10)

    # Pesos editables CANT TENDIDO Fibra (OPGW) — 5 actividades (suma=100)
    peso_tend_riega_manila_fibra_pct = models.PositiveSmallIntegerField(
        'OPGW Riega manila fibra %', default=10)
    peso_tend_riega_guaya_opgw_pct = models.PositiveSmallIntegerField(
        'OPGW Riega guaya %', default=20)
    peso_tend_tendido_opgw_pct = models.PositiveSmallIntegerField(
        'OPGW Tendido %', default=40)
    peso_tend_grapado_fibra_pct = models.PositiveSmallIntegerField(
        'OPGW Grapado/amarre fibra %', default=20)
    peso_tend_empalmes_opgw_pct = models.PositiveSmallIntegerField(
        'OPGW Empalmes %', default=10)

    class Meta:
        db_table = 'construccion_proyectos'
        verbose_name = 'Proyecto de Construcción'
        verbose_name_plural = 'Proyectos de Construcción'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nombre} ({self.contrato.codigo})"

    @property
    def torres_total(self):
        return self.torres.count()

    @property
    def torres_con_obra_civil_completa(self):
        return self.torres.filter(
            pata_obra__liberacion_arqueologica_ok=True,
            pata_obra__replanteo_ok=True,
            pata_obra__excavacion_ok=True,
            pata_obra__solado_ok=True,
            pata_obra__acero_refuerzo_ok=True,
            pata_obra__vaciado_ok=True,
            pata_obra__relleno_compactacion_ok=True,
        ).distinct().count()

    @property
    def porcentaje_avance_civil(self):
        total = self.torres_total
        if total == 0:
            return 0
        completado = self.torres_con_obra_civil_completa
        return round((completado / total) * 100, 2)

    @property
    def porcentaje_avance_montaje(self):
        torres = self.torres.all()
        if not torres.exists():
            return 0
        total_pct = sum(f.porcentaje_montaje for f in self.fases.all())
        return round(total_pct / torres.count(), 2) if torres.exists() else 0

    @property
    def porcentaje_avance_tendido(self):
        torres = self.torres.all()
        if not torres.exists():
            return 0
        total_pct = sum(f.porcentaje_tendido for f in self.fases.all())
        return round(total_pct / torres.count(), 2) if torres.exists() else 0

    @property
    def porcentaje_avance_civil_ponderado(self):
        """% avance OC ponderado por los pesos editables del proyecto (#61).
        Cada bloque aporta su peso solo cuando está completo en las 4 patas."""
        torres = list(self.torres.prefetch_related('pata_obra').all())
        if not torres:
            return 0
        pesos = {
            'CERRAMIENTO': self.peso_cerramiento_pct,
            'EXCAVACION': self.peso_excavacion_pct,
            'SOLADO': self.peso_solado_pct,
            'ACERO': self.peso_acero_pct,
            'VACIADO': self.peso_vaciado_pct,
            'COMPACTACION': self.peso_compactacion_pct,
        }
        total_pesos = sum(pesos.values()) or 1
        pct_por_torre = []
        for torre in torres:
            patas = list(torre.pata_obra.all())
            if not patas:
                pct_por_torre.append(0)
                continue
            peso_acumulado = 0
            for bloque, peso in pesos.items():
                patas_ok = sum(1 for p in patas if p.bloques_estado.get(bloque))
                peso_acumulado += peso * (patas_ok / len(patas))
            pct_por_torre.append((peso_acumulado / total_pesos) * 100)
        return round(sum(pct_por_torre) / len(pct_por_torre), 2)

    def curva_s_data(self):
        """Datos para Chart.js curva S: lista de tuplas (mes, planeado_acum, real_acum)
        agrupados a nivel proyecto. Lee de ProgramacionFase + valores reales."""
        from collections import defaultdict
        from datetime import date
        from .models import ProgramacionFase
        fases = ProgramacionFase.objects.filter(proyecto=self)
        if not fases.exists():
            return []
        # Determine project span
        fechas_inicio = [f.fecha_inicio_planeada for f in fases if f.fecha_inicio_planeada]
        fechas_fin = [f.fecha_fin_planeada for f in fases if f.fecha_fin_planeada]
        if not fechas_inicio or not fechas_fin:
            return []
        inicio = min(fechas_inicio)
        fin = max(fechas_fin)
        # Genera lista mes-a-mes
        meses = []
        cursor = date(inicio.year, inicio.month, 1)
        while cursor <= fin:
            meses.append(cursor)
            mes_next = cursor.month + 1
            anio_next = cursor.year + (1 if mes_next > 12 else 0)
            mes_next = 1 if mes_next > 12 else mes_next
            cursor = date(anio_next, mes_next, 1)
        # Para cada mes, suma % esperado acumulado (lineal por fase)
        resultado = []
        for m in meses:
            esperado = 0
            for fase in fases:
                if not fase.fecha_inicio_planeada or not fase.fecha_fin_planeada:
                    continue
                if m < fase.fecha_inicio_planeada:
                    aporte = 0
                elif m >= fase.fecha_fin_planeada:
                    aporte = fase.peso_pct
                else:
                    total_dias = (fase.fecha_fin_planeada - fase.fecha_inicio_planeada).days
                    transcurridos = (m - fase.fecha_inicio_planeada).days
                    aporte = (transcurridos / total_dias) * fase.peso_pct if total_dias else 0
                esperado += aporte
            resultado.append({
                'mes': m.isoformat(),
                'planeado': round(esperado, 1),
                'real': None,
            })
        # Sobrescribir 'real' con SnapshotAvance histórico (#61)
        from .models import SnapshotAvance
        snapshots = SnapshotAvance.objects.filter(
            proyecto=self, fecha__gte=inicio, fecha__lte=fin
        ).order_by('fecha')
        # Para cada mes, busca el último snapshot ≤ ese mes
        snap_list = [(s.fecha, s.pct_general) for s in snapshots]
        for row in resultado:
            from datetime import date as date_cls
            mes_date = date_cls.fromisoformat(row['mes'])
            mejor = None
            for snap_fecha, snap_pct in snap_list:
                if snap_fecha <= mes_date:
                    mejor = snap_pct
                else:
                    break
            row['real'] = mejor
        return resultado

    # === Financiero (#69 #66 #70) ===

    def pyg_resumen_ejecutivo(self):
        """Devuelve lista de dicts:
        [{categoria, presupuesto, real, variacion, pct_variacion}, ...]
        Una fila por categoría, agregando todos los períodos del proyecto."""
        from django.db.models import Sum, Q
        from decimal import Decimal
        from .models import CategoriaFinanciera, MovimientoFinanciero
        resultado = []
        for cat in CategoriaFinanciera.objects.filter(activa=True).order_by('orden'):
            presupuesto = MovimientoFinanciero.objects.filter(
                periodo__proyecto=self, categoria=cat, tipo='PRESUPUESTO'
            ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
            real = MovimientoFinanciero.objects.filter(
                periodo__proyecto=self, categoria=cat, tipo='REAL'
            ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
            variacion = real - presupuesto
            pct = (variacion / presupuesto * 100) if presupuesto else None
            resultado.append({
                'categoria': cat,
                'presupuesto': presupuesto,
                'real': real,
                'variacion': variacion,
                'pct_variacion': round(pct, 1) if pct is not None else None,
                'alerta': pct is not None and abs(pct) >= 50,
            })
        return resultado

    def curva_s_financiera(self):
        """Lista de {mes, presupuesto_acum, gastado_acum} para curva S
        financiera del proyecto (#70 iteración 2)."""
        from .models import MovimientoFinanciero
        from decimal import Decimal
        movs = MovimientoFinanciero.objects.filter(
            periodo__proyecto=self
        ).select_related('periodo', 'categoria').order_by(
            'periodo__anio', 'periodo__mes')
        if not movs.exists():
            return []
        # Agrupa por (año, mes) y tipo
        from collections import defaultdict
        from datetime import date
        agg = defaultdict(lambda: {'PRESUPUESTO': Decimal('0'), 'REAL': Decimal('0')})
        for m in movs:
            # solo categorías GASTO se acumulan como "gasto"
            if m.categoria.tipo != 'GASTO':
                continue
            key = (m.periodo.anio, m.periodo.mes)
            agg[key][m.tipo] += m.valor
        meses = sorted(agg.keys())
        resultado = []
        pres_acum = Decimal('0')
        real_acum = Decimal('0')
        for anio, mes in meses:
            pres_acum += agg[(anio, mes)]['PRESUPUESTO']
            real_acum += agg[(anio, mes)]['REAL']
            resultado.append({
                'mes': date(anio, mes, 1).isoformat(),
                'presupuesto_acum': float(pres_acum),
                'gastado_acum': float(real_acum),
            })
        return resultado

    @property
    def pyg_totales(self):
        """Totales agregados del proyecto: ingresos, gastos, utilidad."""
        from django.db.models import Sum
        from decimal import Decimal
        from .models import MovimientoFinanciero
        movs = MovimientoFinanciero.objects.filter(periodo__proyecto=self)
        ingresos_pres = movs.filter(
            categoria__tipo='INGRESO', tipo='PRESUPUESTO'
        ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        ingresos_real = movs.filter(
            categoria__tipo='INGRESO', tipo='REAL'
        ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        gastos_pres = movs.filter(
            categoria__tipo='GASTO', tipo='PRESUPUESTO'
        ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        gastos_real = movs.filter(
            categoria__tipo='GASTO', tipo='REAL'
        ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
        return {
            'ingresos_presupuesto': ingresos_pres,
            'ingresos_real': ingresos_real,
            'gastos_presupuesto': gastos_pres,
            'gastos_real': gastos_real,
            'utilidad_presupuesto': ingresos_pres - gastos_pres,
            'utilidad_real': ingresos_real - gastos_real,
        }


class TorreConstruccion(BaseModel):
    """
    A tower being constructed in a construction project.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='torres',
    )
    numero = models.CharField('Número de torre', max_length=20)
    tipo = models.CharField('Tipo de estructura', max_length=20, blank=True, help_text='e.g., D6, B4, C5')
    tipo_cimentacion = models.CharField(
        'Tipo de cimentación',
        max_length=20,
        choices=[
            ('ZAPATA', 'Zapata'),
            ('HELICOIDAL', 'Helicoidal'),
            ('PARRILLA', 'Parrilla'),
            ('PILOTE', 'Pilote'),
            ('MICROPILOTE', 'Micropilote'),
        ],
        blank=True,
    )
    peso_kg = models.FloatField('Peso de estructura (kg)', null=True, blank=True)
    tramo_tendido = models.CharField('Tramo de tendido', max_length=20, blank=True, help_text='e.g., TEND 1, TEND 4')

    # Geolocation
    latitud = models.FloatField('Latitud', null=True, blank=True)
    longitud = models.FloatField('Longitud', null=True, blank=True)
    geometry = gis_models.PointField('Localización', null=True, blank=True)

    # Cuadrillas assigned
    cuadrilla_civil = models.CharField('Cuadrilla civil', max_length=100, blank=True)
    cuadrilla_montaje = models.CharField('Cuadrilla montaje', max_length=100, blank=True)
    cuadrilla_tendido = models.CharField('Cuadrilla tendido', max_length=100, blank=True)

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_torres'
        verbose_name = 'Torre de Construcción'
        verbose_name_plural = 'Torres de Construcción'
        unique_together = [['proyecto', 'numero']]
        ordering = ['numero']

    def __str__(self):
        return f"Torre {self.numero} ({self.proyecto.nombre})"

    # === Habilitación paralela por torre (#67) ===
    @property
    def puede_iniciar_obra_civil(self):
        """Habilita OC si los semáforos predial Y ambiental están en VERDE
        para esta torre. Regla Gabriel Valencia (Reunión 8, 00:02:57)."""
        social = getattr(self, 'social_predial', None)
        ambiental = getattr(self, 'ambiental', None)
        social_ok = social is not None and social.liberado
        ambiental_ok = ambiental is not None and ambiental.liberado
        return social_ok and ambiental_ok

    @property
    def obra_civil_completa(self):
        """True si las 4 patas tienen lista_para_montaje=True."""
        patas = list(self.pata_obra.all())
        if len(patas) < 4:
            return False
        return all(p.lista_para_montaje for p in patas)

    @property
    def puede_iniciar_montaje(self):
        """Habilita Montaje cuando la OC de esta torre está completa.
        Regla 'torre por torre, no por finalización total de fase'."""
        return self.obra_civil_completa

    @property
    def puede_iniciar_tendido(self):
        """Habilita Tendido si Montaje entregó para carga."""
        fase = getattr(self, 'fase', None)
        return fase is not None and fase.entrega_carga_ok

    @property
    def fases_en_curso(self):
        """Lista de fases activas — para dashboard de traslape (#67)."""
        en_curso = []
        if self.puede_iniciar_obra_civil and not self.obra_civil_completa:
            en_curso.append('OBRA_CIVIL')
        if self.puede_iniciar_montaje:
            fase = getattr(self, 'fase', None)
            if fase and not fase.entrega_carga_ok:
                en_curso.append('MONTAJE')
            if fase and getattr(fase, 'spt_pct', 0) > 0 and fase.spt_pct < 100:
                en_curso.append('SPT')
        if self.puede_iniciar_tendido:
            fase = getattr(self, 'fase', None)
            if fase and fase.porcentaje_tendido < 100:
                en_curso.append('TENDIDO')
        return en_curso


class PataObra(BaseModel):
    """
    Civil work tracking per tower leg (Pata A, B, C, D).
    """
    PATA_CHOICES = [('A', 'Pata A'), ('B', 'Pata B'), ('C', 'Pata C'), ('D', 'Pata D')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.ForeignKey(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='pata_obra',
    )
    pata = models.CharField('Pata', max_length=1, choices=PATA_CHOICES)

    # Archaeological clearance
    liberacion_arqueologica_ok = models.BooleanField('Liberación arqueológica', default=False)
    liberacion_arqueologica_fecha = models.DateField('Fecha libración arqueológica', null=True, blank=True)

    # Topographic survey
    replanteo_ok = models.BooleanField('Replanteo', default=False)
    replanteo_fecha = models.DateField('Fecha replanteo', null=True, blank=True)

    # Excavation
    excavacion_ok = models.BooleanField('Excavación', default=False)
    excavacion_fecha = models.DateField('Fecha excavación', null=True, blank=True)
    excavacion_m3 = models.FloatField('Excavación (m3)', null=True, blank=True)

    # Lean concrete base
    solado_ok = models.BooleanField('Solado', default=False)
    solado_fecha = models.DateField('Fecha solado', null=True, blank=True)
    solado_m3 = models.FloatField('Solado (m3)', null=True, blank=True)

    # Pile installation (if applicable)
    instalacion_pilotes_ok = models.BooleanField('Instalación de pilotes', default=False)
    instalacion_pilotes_fecha = models.DateField('Fecha instalación pilotes', null=True, blank=True)

    # Steel reinforcement
    acero_refuerzo_ok = models.BooleanField('Acero de refuerzo', default=False)
    acero_refuerzo_fecha = models.DateField('Fecha acero refuerzo', null=True, blank=True)
    acero_kg = models.FloatField('Acero (kg)', null=True, blank=True)

    # Stub leveling
    nivelacion_ok = models.BooleanField('Nivelación', default=False)
    nivelacion_fecha = models.DateField('Fecha nivelación', null=True, blank=True)

    # Bloque 1: Cerramiento (#53)
    cerramiento_finalizado_ok = models.BooleanField(
        'Cerramiento finalizado', default=False,
        help_text='Habilita inicio de excavación (regla Gabriel Valencia)')
    cerramiento_fecha = models.DateField('Fecha cerramiento', null=True, blank=True)

    # Bloque 2: Excavación detalles (#53)
    tipo_excavacion = models.CharField(
        'Tipo de excavación', max_length=20, blank=True,
        choices=[('MANUAL', 'Manual'), ('MAQUINA', 'Con máquina')])
    aplica_pilotes = models.BooleanField('Aplica instalación de pilotes', default=False)

    # Bloque 4: Acero — diseño vs real (control materiales #54)
    acero_solicitado_kg = models.FloatField('Acero solicitado según planilla (kg)',
                                            null=True, blank=True)
    acero_instalado_kg = models.FloatField('Acero instalado (kg)', null=True, blank=True)

    # Concrete pour
    vaciado_ok = models.BooleanField('Vaciado de hormigón', default=False)
    vaciado_fecha = models.DateField('Fecha vaciado', null=True, blank=True,
        help_text='Trigger para alarmas de cilindros 7/14/21/51 días (#55)')
    concreto_m3 = models.FloatField('Concreto (m3)', null=True, blank=True)
    concreto_psi = models.CharField('Resistencia concreto', max_length=10, blank=True, help_text='1500, 2000, etc.')

    # Bloque 5: Vaciado — diseño vs real concreto (control materiales #54)
    concreto_solicitado_m3 = models.FloatField('Concreto solicitado (m3)',
                                               null=True, blank=True)
    concreto_instalado_m3 = models.FloatField('Concreto instalado (m3)',
                                              null=True, blank=True)
    resistencia_especificada_mpa = models.PositiveSmallIntegerField(
        'Resistencia especificada (MPa)', null=True, blank=True,
        help_text='Ej: 21, 28')

    # Bloque 5: Cilindros de fallo (resultados de pruebas — alarmas #55)
    cilindro_7d_mpa = models.FloatField('Cilindro 7 días (MPa)', null=True, blank=True)
    cilindro_14d_mpa = models.FloatField('Cilindro 14 días (MPa)', null=True, blank=True)
    cilindro_21d_mpa = models.FloatField('Cilindro 21 días (MPa)', null=True, blank=True)
    cilindro_51d_mpa = models.FloatField('Cilindro 51 días (MPa)', null=True, blank=True)

    # Backfill & compaction
    relleno_compactacion_ok = models.BooleanField('Relleno y compactación', default=False)
    relleno_compactacion_fecha = models.DateField('Fecha relleno y compactación', null=True, blank=True)
    relleno_m3 = models.FloatField('Relleno (m3)', null=True, blank=True)

    # Grounding systems
    spt_base_ok = models.BooleanField('SPT base', default=False)
    spt_base_fecha = models.DateField('Fecha SPT base', null=True, blank=True)

    spt_modulos_ok = models.BooleanField('SPT módulos', default=False)
    spt_modulos_fecha = models.DateField('Fecha SPT módulos', null=True, blank=True)

    # Crew & observations
    cuadrilla_civil = models.CharField('Cuadrilla civil', max_length=100, blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_pata_obra'
        verbose_name = 'Pata de Obra'
        verbose_name_plural = 'Patas de Obra'
        unique_together = [['torre', 'pata']]

    def __str__(self):
        return f"Torre {self.torre.numero} - Pata {self.pata}"

    @property
    def porcentaje_completado(self):
        """Calculate percentage of completion for this leg."""
        actividades = [
            self.liberacion_arqueologica_ok,
            self.replanteo_ok,
            self.excavacion_ok,
            self.solado_ok,
            self.acero_refuerzo_ok,
            self.nivelacion_ok,
            self.vaciado_ok,
            self.relleno_compactacion_ok,
            self.spt_base_ok,
            self.spt_modulos_ok,
        ]
        completadas = sum(1 for a in actividades if a)
        return round((completadas / len(actividades)) * 100, 2)

    # === Bloques secuenciales de Obra Civil (#53) ===

    BLOQUES_ORDEN = [
        ('CERRAMIENTO', 'Cerramiento'),
        ('EXCAVACION', 'Excavación'),
        ('SOLADO', 'Solado'),
        ('ACERO', 'Instalación de Acero'),
        ('VACIADO', 'Vaciado en Concreto'),
        ('COMPACTACION', 'Relleno y Compactación'),
    ]

    @property
    def bloques_estado(self):
        """Dict {bloque: bool ok}. Refleja la cascada del issue #53."""
        return {
            'CERRAMIENTO': self.cerramiento_finalizado_ok,
            'EXCAVACION': self.excavacion_ok,
            'SOLADO': self.solado_ok,
            'ACERO': self.acero_refuerzo_ok,
            'VACIADO': self.vaciado_ok,
            'COMPACTACION': self.relleno_compactacion_ok,
        }

    @property
    def bloque_actual(self):
        """Próximo bloque pendiente. None si todos completos."""
        estado = self.bloques_estado
        for codigo, _ in self.BLOQUES_ORDEN:
            if not estado[codigo]:
                return codigo
        return None

    @property
    def lista_para_montaje(self):
        """True si los 6 bloques de Obra Civil están completos."""
        return all(self.bloques_estado.values())

    @property
    def desviacion_acero_pct(self):
        """% de desviación instalado vs solicitado. None si falta data. (#54)"""
        if not self.acero_solicitado_kg or self.acero_solicitado_kg == 0:
            return None
        if self.acero_instalado_kg is None:
            return None
        return round(
            ((self.acero_instalado_kg - self.acero_solicitado_kg)
             / self.acero_solicitado_kg) * 100, 1
        )

    @property
    def desviacion_concreto_pct(self):
        """% de desviación instalado vs solicitado. None si falta data. (#54)"""
        if not self.concreto_solicitado_m3 or self.concreto_solicitado_m3 == 0:
            return None
        if self.concreto_instalado_m3 is None:
            return None
        return round(
            ((self.concreto_instalado_m3 - self.concreto_solicitado_m3)
             / self.concreto_solicitado_m3) * 100, 1
        )

    @property
    def alarma_materiales(self):
        """True si alguna desviación ≥5% absoluta (regla #54)."""
        for d in (self.desviacion_acero_pct, self.desviacion_concreto_pct):
            if d is not None and abs(d) >= 5.0:
                return True
        return False

    @property
    def cilindros_pendientes(self):
        """Lista de cilindros (7/14/21/51 días) cuya fecha de prueba ya
        pasó pero el resultado MPa no se cargó. Para alertas (#55)."""
        if not self.vaciado_fecha:
            return []
        from datetime import date
        hoy = date.today()
        dias = (hoy - self.vaciado_fecha).days
        pendientes = []
        for n_dias, atributo in [(7, 'cilindro_7d_mpa'),
                                 (14, 'cilindro_14d_mpa'),
                                 (21, 'cilindro_21d_mpa'),
                                 (51, 'cilindro_51d_mpa')]:
            if dias >= n_dias and getattr(self, atributo) is None:
                pendientes.append(n_dias)
        return pendientes

    @property
    def cilindros_proximos(self):
        """Lista de cilindros cuya prueba está a ≤2 días. Para pre-alertas (#55)."""
        if not self.vaciado_fecha:
            return []
        from datetime import date
        hoy = date.today()
        dias = (hoy - self.vaciado_fecha).days
        proximos = []
        for n_dias, atributo in [(7, 'cilindro_7d_mpa'),
                                 (14, 'cilindro_14d_mpa'),
                                 (21, 'cilindro_21d_mpa'),
                                 (51, 'cilindro_51d_mpa')]:
            faltan = n_dias - dias
            if 0 < faltan <= 2 and getattr(self, atributo) is None:
                proximos.append((n_dias, faltan))
        return proximos


class ObraCivilTorre(BaseModel):
    """Matriz Obra Civil torre×columna (#74).

    Cada fila representa una torre del proyecto, con 6 avances editables
    entre 0 y 1 (0 = no iniciado, 1 = completo), uno por columna de la hoja
    'CANT OOCC' del Excel del cliente: Cerramiento, Excavación, Solado,
    Acero, Vaciado, Compactación.

    El avance ponderado de cada torre se calcula como SUMPRODUCT entre estos
    valores y los pesos editables del proyecto (peso_*_pct de
    ProyectoConstruccion), que ya existen desde #61.

    PataObra sigue siendo la fuente granular pata×actividad para alarmas de
    cilindros y materiales; ObraCivilTorre es la capa agregada que el cliente
    edita en la matriz.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='obra_civil_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion',
        on_delete=models.CASCADE,
        related_name='obra_civil',
    )

    # 6 avances 0-1 — una columna del Excel del cliente
    avance_cerramiento = models.DecimalField(
        'Avance Cerramiento', max_digits=5, decimal_places=4, default=0,
        help_text='0 a 1 (1 = 100% completado)',
    )
    avance_excavacion = models.DecimalField(
        'Avance Excavación', max_digits=5, decimal_places=4, default=0,
    )
    avance_solado = models.DecimalField(
        'Avance Solado', max_digits=5, decimal_places=4, default=0,
    )
    avance_acero = models.DecimalField(
        'Avance Acero', max_digits=5, decimal_places=4, default=0,
    )
    avance_vaciado = models.DecimalField(
        'Avance Vaciado', max_digits=5, decimal_places=4, default=0,
    )
    avance_compactacion = models.DecimalField(
        'Avance Compactación', max_digits=5, decimal_places=4, default=0,
    )

    # Metadatos
    cuadrilla = models.CharField('Cuadrilla / Encargado', max_length=100, blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_obra_civil_torre'
        verbose_name = 'Obra Civil — Torre'
        verbose_name_plural = 'Obra Civil — Torres'
        ordering = ['torre__numero']

    def __str__(self):
        return f"OC {self.torre.numero}"

    COLUMNAS = [
        ('cerramiento', 'Cerramiento'),
        ('excavacion', 'Excavación'),
        ('solado', 'Solado'),
        ('acero', 'Acero'),
        ('vaciado', 'Vaciado'),
        ('compactacion', 'Compactación'),
    ]

    @property
    def avances_dict(self):
        """Dict columna → Decimal de avance, conveniente para templates."""
        return {
            'cerramiento': self.avance_cerramiento,
            'excavacion': self.avance_excavacion,
            'solado': self.avance_solado,
            'acero': self.avance_acero,
            'vaciado': self.avance_vaciado,
            'compactacion': self.avance_compactacion,
        }

    @property
    def avance_ponderado(self):
        """SUMPRODUCT(pesos del proyecto, avances de la torre).

        Devuelve un valor 0–1. El cliente ve el % multiplicando por 100.
        """
        from decimal import Decimal
        pesos = {
            'cerramiento': self.proyecto.peso_cerramiento_pct,
            'excavacion': self.proyecto.peso_excavacion_pct,
            'solado': self.proyecto.peso_solado_pct,
            'acero': self.proyecto.peso_acero_pct,
            'vaciado': self.proyecto.peso_vaciado_pct,
            'compactacion': self.proyecto.peso_compactacion_pct,
        }
        total_peso = sum(pesos.values()) or 1
        avances = self.avances_dict
        suma = Decimal('0')
        for columna, peso in pesos.items():
            suma += avances[columna] * Decimal(peso)
        return suma / Decimal(total_peso)

    @property
    def avance_ponderado_pct(self):
        """avance_ponderado expresado como float 0–100 con 1 decimal."""
        return round(float(self.avance_ponderado) * 100, 1)


def _pesos_obra_civil_validos(proyecto):
    """¿Los 6 pesos del proyecto suman exactamente 100?"""
    return (
        proyecto.peso_cerramiento_pct
        + proyecto.peso_excavacion_pct
        + proyecto.peso_solado_pct
        + proyecto.peso_acero_pct
        + proyecto.peso_vaciado_pct
        + proyecto.peso_compactacion_pct
    ) == 100


class MontajeEstructuraTorre(BaseModel):
    """Matriz CANT MONTAJE torre×etapa (#76).

    4 etapas secuenciales del Excel del cliente con pesos editables:
    Estructura en sitio (10%) → Prearmada (20%) → Torre Montada (45%) →
    Revisada (25%). Cada avance es 0–1; el avance ponderado de la torre es
    SUMPRODUCT(pesos del proyecto, avances) / 100.

    Validación cascada lógica (issue requirement): prearamada ≤
    estructura_en_sitio; torre_montada ≤ prearamada; revisada solo si
    torre_montada == 1.

    FaseTorre se conserva como capa granular (8 fases secuenciales con
    fechas y cuadrillas específicas). MontajeEstructuraTorre es la matriz
    agregada que el cliente edita.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='montaje_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion',
        on_delete=models.CASCADE,
        related_name='montaje_estructura',
    )

    # 4 avances 0-1 — una columna del Excel CANT MONTAJE
    avance_estructura_sitio = models.DecimalField(
        'Estructura en sitio', max_digits=5, decimal_places=4, default=0,
        help_text='0 a 1 (1 = recibida en sitio)',
    )
    avance_prearamada = models.DecimalField(
        'Prearmada', max_digits=5, decimal_places=4, default=0,
    )
    avance_torre_montada = models.DecimalField(
        'Torre Montada', max_digits=5, decimal_places=4, default=0,
    )
    avance_revisada = models.DecimalField(
        'Revisada (post-inspección)', max_digits=5, decimal_places=4, default=0,
    )

    # Metadatos
    encargado_prearmado = models.CharField('Cuadrilla prearmado', max_length=100, blank=True)
    encargado_montaje = models.CharField('Cuadrilla montaje', max_length=100, blank=True)
    entregada_para_carga = models.BooleanField(
        'Entregada para carga (habilita Tendido)', default=False,
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_montaje_estructura_torre'
        verbose_name = 'Montaje — Estructura Torre'
        verbose_name_plural = 'Montaje — Estructuras Torre'
        ordering = ['torre__numero']

    def __str__(self):
        return f"Montaje {self.torre.numero}"

    COLUMNAS = [
        ('estructura_sitio', 'Estructura en sitio'),
        ('prearamada', 'Prearmada'),
        ('torre_montada', 'Torre Montada'),
        ('revisada', 'Revisada'),
    ]

    @property
    def avances_dict(self):
        return {
            'estructura_sitio': self.avance_estructura_sitio,
            'prearamada': self.avance_prearamada,
            'torre_montada': self.avance_torre_montada,
            'revisada': self.avance_revisada,
        }

    @property
    def avance_ponderado(self):
        """SUMPRODUCT(pesos del proyecto, avances de la torre). Valor 0-1."""
        from decimal import Decimal
        pesos = {
            'estructura_sitio': self.proyecto.peso_mont_estructura_sitio_pct,
            'prearamada': self.proyecto.peso_mont_prearamada_pct,
            'torre_montada': self.proyecto.peso_mont_torre_montada_pct,
            'revisada': self.proyecto.peso_mont_revisada_pct,
        }
        total = sum(pesos.values()) or 1
        avances = self.avances_dict
        suma = Decimal('0')
        for col, peso in pesos.items():
            suma += avances[col] * Decimal(peso)
        return suma / Decimal(total)

    @property
    def avance_ponderado_pct(self):
        return round(float(self.avance_ponderado) * 100, 1)


def _pesos_montaje_validos(proyecto):
    return (
        proyecto.peso_mont_estructura_sitio_pct
        + proyecto.peso_mont_prearamada_pct
        + proyecto.peso_mont_torre_montada_pct
        + proyecto.peso_mont_revisada_pct
    ) == 100


# ==========================================================================
# SPT y Pintura (#78) — captura por torre del Excel `SPT PINTURA.xlsx`
# ==========================================================================

class SPTTorre(BaseModel):
    """Sistema de Puesta a Tierra por torre (#78 sección 1)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE, related_name='spt_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion', on_delete=models.CASCADE, related_name='spt',
    )
    # Cable SPT
    excavacion_m = models.DecimalField('Excavación (m)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    cable_planos_m = models.DecimalField('Cable según planos (m)',
        max_digits=10, decimal_places=2, null=True, blank=True)
    cable_instalado_m = models.DecimalField('Cable instalado (m)',
        max_digits=10, decimal_places=2, null=True, blank=True)
    cuadrilla_spt = models.CharField('Cuadrilla SPT', max_length=100, blank=True)
    observaciones_cable = models.TextField('Observaciones cable', blank=True)
    # Pólvora
    cantidad_tiros = models.PositiveSmallIntegerField('Cantidad de tiros',
        null=True, blank=True)
    polvora_teorica_cajas = models.DecimalField('Pólvora teórica (cajas)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    polvora_real_kg = models.DecimalField('Pólvora real (kg)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    observaciones_polvora = models.TextField('Observaciones pólvora', blank=True)
    # Control y avance
    porcentaje_avance = models.PositiveSmallIntegerField('Avance SPT %', default=0)
    control_compensacion = models.BooleanField('FT-068 Control compensación', default=False)
    control_medicion = models.BooleanField('FT-029 Lectura medición', default=False)
    informe_mediciones = models.BooleanField('Informe de mediciones entregado', default=False)

    class Meta:
        db_table = 'construccion_spt_torre'
        verbose_name = 'SPT — Torre'
        verbose_name_plural = 'SPT — Torres'
        ordering = ['torre__numero']

    def __str__(self):
        return f"SPT {self.torre.numero}"

    @property
    def diferencia_cable(self):
        if self.cable_planos_m is not None and self.cable_instalado_m is not None:
            return self.cable_planos_m - self.cable_instalado_m
        return None

    @property
    def diferencia_polvora(self):
        if self.polvora_teorica_cajas is not None and self.polvora_real_kg is not None:
            return self.polvora_teorica_cajas - self.polvora_real_kg
        return None


class PinturaPatasTorre(BaseModel):
    """Pintura de patas (#78 sección 2)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE, related_name='pintura_patas_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion', on_delete=models.CASCADE, related_name='pintura_patas',
    )
    control_espesor = models.BooleanField('FT-912 Control espesor', default=False)
    torres_pintadas = models.BooleanField('Torres pintadas', default=False)
    medicion_espesor = models.BooleanField('Medición de espesor', default=False)
    entrega_pintura = models.BooleanField('Entrega de pintura', default=False)
    cuadrilla = models.CharField('Cuadrilla', max_length=100, blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_pintura_patas_torre'
        verbose_name = 'Pintura Patas — Torre'
        verbose_name_plural = 'Pintura Patas — Torres'
        ordering = ['torre__numero']

    def __str__(self):
        return f"Pintura patas {self.torre.numero}"


class PinturaAeronauticaTorre(BaseModel):
    """Pintura aeronáutica (#78 sección 3) — contiene 7 PinturaFranja."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE, related_name='pintura_aero_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion', on_delete=models.CASCADE, related_name='pintura_aeronautica',
    )
    revision_espesor_micras = models.BooleanField('Revisión espesor en micras', default=False)
    entrega_pintura = models.BooleanField('Entrega de pintura', default=False)

    class Meta:
        db_table = 'construccion_pintura_aero_torre'
        verbose_name = 'Pintura Aeronáutica — Torre'
        verbose_name_plural = 'Pintura Aeronáutica — Torres'
        ordering = ['torre__numero']

    def __str__(self):
        return f"Pintura aero {self.torre.numero}"


class PinturaFranja(BaseModel):
    """Una de las 7 franjas de pintura aeronáutica. Base siempre gris;
    color complementario alterna NARANJA (1,3,5,7) y BLANCO (2,4,6).
    """
    class Color(models.TextChoices):
        NARANJA = 'NARANJA', 'Naranja'
        BLANCO = 'BLANCO', 'Blanco'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pintura_aeronautica = models.ForeignKey(
        PinturaAeronauticaTorre, on_delete=models.CASCADE, related_name='franjas',
    )
    numero_franja = models.PositiveSmallIntegerField(
        'Número de franja',
        choices=[(i, f'Franja {i}') for i in range(1, 8)],
    )
    color = models.CharField('Color', max_length=10, choices=Color.choices)
    # Base gris
    porcentaje_base = models.PositiveSmallIntegerField('Avance base gris (%)', default=0)
    cantidad_base_proyectada = models.DecimalField('Base proyectada (L)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    cantidad_base_consumida = models.DecimalField('Base consumida (L)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    observaciones_base = models.TextField('Observaciones base', blank=True)
    # Color
    porcentaje_color = models.PositiveSmallIntegerField('Avance color (%)', default=0)
    cantidad_color_proyectada = models.DecimalField('Color proyectado (L)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    cantidad_color_consumida = models.DecimalField('Color consumido (L)',
        max_digits=8, decimal_places=2, null=True, blank=True)
    observaciones_color = models.TextField('Observaciones color', blank=True)

    class Meta:
        db_table = 'construccion_pintura_franja'
        verbose_name = 'Franja de pintura'
        verbose_name_plural = 'Franjas de pintura'
        unique_together = [['pintura_aeronautica', 'numero_franja']]
        ordering = ['numero_franja']

    def __str__(self):
        return f"Franja {self.numero_franja} ({self.color})"

    @property
    def diferencia_base(self):
        if self.cantidad_base_proyectada is not None and self.cantidad_base_consumida is not None:
            return self.cantidad_base_proyectada - self.cantidad_base_consumida
        return None

    @property
    def diferencia_color(self):
        if self.cantidad_color_proyectada is not None and self.cantidad_color_consumida is not None:
            return self.cantidad_color_proyectada - self.cantidad_color_consumida
        return None


# ==========================================================================
# CANT TENDIDO (#79) — captura del Excel `TENDIDO.xlsx`
# ==========================================================================

class TendidoTorre(BaseModel):
    """Matriz CANT TENDIDO torre × 13 actividades (#79).

    Dos secciones con SUMPRODUCT independiente:
    - **Conductor** (6 actividades ponderadas suma=100): riega manila,
      riega guaya conductor, tendido conductor, grapado, accesorios,
      balizas. + 2 checks no ponderados: placas señalización, facturadas HMV.
    - **Fibra OPGW** (5 actividades ponderadas suma=100): riega manila
      fibra, riega guaya OPGW, tendido OPGW, grapado/amarre fibra,
      empalmes OPGW.

    FaseTorre legacy se conserva como capa granular con dos circuitos +
    cable de guarda. TendidoTorre es la matriz agregada que el cliente
    edita en CANT TENDIDO.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='tendido_torres',
    )
    torre = models.OneToOneField(
        'TorreConstruccion', on_delete=models.CASCADE,
        related_name='tendido',
    )

    # Conductor — 7 actividades (6 ponderadas + Vestida que es gate inicial)
    vestida_conductor = models.BooleanField('Vestida (conductor)', default=False)
    riega_manila_conductor = models.BooleanField('Riega de manila', default=False)
    riega_guaya_conductor = models.BooleanField('Riega guaya conductor', default=False)
    tendido_conductor = models.BooleanField('Tendido de conductor', default=False)
    grapado_amarre_conductor = models.BooleanField('Grapado / amarre', default=False)
    accesorios_puentes = models.BooleanField('Accesorios y puentes', default=False)
    balizas_desviadores = models.BooleanField('Balizas / desviadores de vuelo', default=False)
    # Control administrativo (no ponderado en SUMPRODUCT)
    placas_senalizacion = models.BooleanField('Placas de señalización', default=False)
    facturadas_hmv = models.BooleanField('Facturadas HMV', default=False)

    # Fibra OPGW — 6 actividades (5 ponderadas + Vestida gate)
    vestida_fibra = models.BooleanField('Vestida (fibra)', default=False)
    riega_manila_fibra = models.BooleanField('Riega manila (fibra)', default=False)
    riega_guaya_opgw = models.BooleanField('Riega guaya OPGW', default=False)
    tendido_opgw = models.BooleanField('Tendido OPGW', default=False)
    grapado_amarre_fibra = models.BooleanField('Grapado / amarre fibra', default=False)
    empalmes_opgw = models.BooleanField('Empalmes OPGW', default=False)

    # Cuadrilla
    realizo_conductor = models.CharField('Realizó (conductor)', max_length=100, blank=True)
    realizo_fibra = models.CharField('Realizó (fibra)', max_length=100, blank=True)

    class Meta:
        db_table = 'construccion_tendido_torre'
        verbose_name = 'Tendido — Torre'
        verbose_name_plural = 'Tendido — Torres'
        ordering = ['torre__numero']

    def __str__(self):
        return f"Tendido {self.torre.numero}"

    COLUMNAS_CONDUCTOR = [
        ('riega_manila_conductor', 'Riega manila'),
        ('riega_guaya_conductor', 'Riega guaya'),
        ('tendido_conductor', 'Tendido conductor'),
        ('grapado_amarre_conductor', 'Grapado'),
        ('accesorios_puentes', 'Accesorios'),
        ('balizas_desviadores', 'Balizas'),
    ]
    COLUMNAS_FIBRA = [
        ('riega_manila_fibra', 'Riega manila fibra'),
        ('riega_guaya_opgw', 'Riega guaya OPGW'),
        ('tendido_opgw', 'Tendido OPGW'),
        ('grapado_amarre_fibra', 'Grapado fibra'),
        ('empalmes_opgw', 'Empalmes OPGW'),
    ]

    @property
    def funcion(self):
        """Determina Suspensión vs Retención según tipo de torre (#79)."""
        tipo = (self.torre.tipo or '').strip().upper()
        if tipo in {'A', 'A ESPECIAL'}:
            return 'Suspensión'
        return 'Retención'

    @property
    def avance_conductor(self):
        """SUMPRODUCT(pesos conductor, valores). Valor 0-1."""
        p = self.proyecto
        pesos = {
            'riega_manila_conductor': p.peso_tend_riega_manila_pct,
            'riega_guaya_conductor': p.peso_tend_riega_guaya_pct,
            'tendido_conductor': p.peso_tend_tendido_conductor_pct,
            'grapado_amarre_conductor': p.peso_tend_grapado_pct,
            'accesorios_puentes': p.peso_tend_accesorios_pct,
            'balizas_desviadores': p.peso_tend_balizas_pct,
        }
        total = sum(pesos.values()) or 1
        suma = sum(peso * (1 if getattr(self, f) else 0) for f, peso in pesos.items())
        return suma / total

    @property
    def avance_fibra(self):
        """SUMPRODUCT(pesos fibra, valores). Valor 0-1."""
        p = self.proyecto
        pesos = {
            'riega_manila_fibra': p.peso_tend_riega_manila_fibra_pct,
            'riega_guaya_opgw': p.peso_tend_riega_guaya_opgw_pct,
            'tendido_opgw': p.peso_tend_tendido_opgw_pct,
            'grapado_amarre_fibra': p.peso_tend_grapado_fibra_pct,
            'empalmes_opgw': p.peso_tend_empalmes_opgw_pct,
        }
        total = sum(pesos.values()) or 1
        suma = sum(peso * (1 if getattr(self, f) else 0) for f, peso in pesos.items())
        return suma / total

    @property
    def avance_conductor_pct(self):
        return round(self.avance_conductor * 100, 1)

    @property
    def avance_fibra_pct(self):
        return round(self.avance_fibra * 100, 1)


def _pesos_tendido_conductor_validos(proyecto):
    return (
        proyecto.peso_tend_riega_manila_pct
        + proyecto.peso_tend_riega_guaya_pct
        + proyecto.peso_tend_tendido_conductor_pct
        + proyecto.peso_tend_grapado_pct
        + proyecto.peso_tend_accesorios_pct
        + proyecto.peso_tend_balizas_pct
    ) == 100


def _pesos_tendido_fibra_validos(proyecto):
    return (
        proyecto.peso_tend_riega_manila_fibra_pct
        + proyecto.peso_tend_riega_guaya_opgw_pct
        + proyecto.peso_tend_tendido_opgw_pct
        + proyecto.peso_tend_grapado_fibra_pct
        + proyecto.peso_tend_empalmes_opgw_pct
    ) == 100


# ==========================================================================
# Trinchos y Cunetas (#80) — Excel `trinchos y cunetas.xlsx`
# ==========================================================================

class TrinchoCuneta(BaseModel):
    """Obras de protección (trincho/cuneta) por torre con consumo de
    materiales (#80). Reemplaza a `ObraProteccion` (legacy) con campos
    directos según Excel del cliente.
    """
    class TipoObra(models.TextChoices):
        CUNETA = 'CUNETA', 'Cuneta'
        TRINCHO = 'TRINCHO', 'Trincho'
        AMBAS = 'AMBAS', 'Cuneta y Trincho'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='trinchos_cunetas',
    )
    torre = models.ForeignKey(
        'TorreConstruccion', on_delete=models.CASCADE,
        related_name='trinchos_cunetas',
    )

    # Tipo y cantidades
    medida_manejo = models.CharField(
        'Medida de manejo', max_length=10, choices=TipoObra.choices,
    )
    metros_trinchos = models.DecimalField(
        'Metros lineales trinchos', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    metros_cunetas = models.DecimalField(
        'Metros lineales cunetas', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    notas = models.TextField('Notas / especificaciones', blank=True)

    # 7 materiales del Excel
    tubo_metalico = models.DecimalField('Tubo metálico 3mx3" (un)',
        max_digits=10, decimal_places=2, default=0)
    malla_eslabonada = models.DecimalField('Malla eslabonada (un)',
        max_digits=10, decimal_places=2, default=0)
    alambre_galvanizado = models.DecimalField('Alambre galvanizado (kg)',
        max_digits=10, decimal_places=2, default=0)
    geotextil = models.DecimalField('Geotextil (m)',
        max_digits=10, decimal_places=2, default=0)
    cemento = models.DecimalField('Cemento (bultos 50K)',
        max_digits=10, decimal_places=2, default=0)
    arena = models.DecimalField('Arena (cuñetes)',
        max_digits=10, decimal_places=2, default=0)
    grava = models.DecimalField('Grava (cuñetes)',
        max_digits=10, decimal_places=2, default=0)

    cuadrilla = models.CharField('Cuadrilla / encargado', max_length=100, blank=True)
    completado = models.BooleanField('Completado', default=False)

    class Meta:
        db_table = 'construccion_trincho_cuneta'
        verbose_name = 'Trincho / Cuneta'
        verbose_name_plural = 'Trinchos y Cunetas'
        unique_together = [['proyecto', 'torre']]
        ordering = ['torre__numero']

    def __str__(self):
        return f"{self.torre.numero} - {self.get_medida_manejo_display()}"

    @property
    def total_metros_obra(self):
        return (self.metros_trinchos or 0) + (self.metros_cunetas or 0)

    @property
    def estado(self):
        return 'Completo' if self.completado else 'Incompleto'


# ==========================================================================
# Dashboards Curva S (#75 #77) — Avance semanal Programado vs Ejecutado
# ==========================================================================

class DashboardAvanceSemanal(BaseModel):
    """Captura semanal del avance Programado vs Ejecutado para los
    dashboards Curva S (#75 #77). Un registro por (proyecto, fase, semana).
    """
    class Fase(models.TextChoices):
        OOCC = 'OOCC', 'Obra Civil'
        MONTAJE = 'MONTAJE', 'Montaje'
        TENDIDO = 'TENDIDO', 'Tendido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='dashboards_semanales',
    )
    fase = models.CharField('Fase', max_length=10, choices=Fase.choices)
    semana = models.DateField('Semana (lunes)')

    # PROGRAMADAS
    torres_programadas_semana = models.PositiveSmallIntegerField(
        'Torres programadas (semana)', default=0,
    )
    torres_programadas_acum = models.PositiveSmallIntegerField(
        'Torres programadas (acum)', default=0,
    )
    pct_programado = models.DecimalField(
        '% Programado', max_digits=5, decimal_places=2, default=0,
    )
    torres_incluidas_prog = models.CharField(
        'Torres incluidas (prog)', max_length=300, blank=True,
        help_text='Lista separada por coma, ej "1, 38, 39"',
    )

    # EJECUTADAS / CONSTRUIDAS
    torres_construidas_semana = models.PositiveSmallIntegerField(
        'Torres ejecutadas (semana)', default=0,
    )
    torres_construidas_acum = models.PositiveSmallIntegerField(
        'Torres ejecutadas (acum)', default=0,
    )
    pct_construido = models.DecimalField(
        '% Ejecutado', max_digits=5, decimal_places=2, default=0,
    )
    torres_incluidas_cons = models.CharField(
        'Torres incluidas (cons)', max_length=300, blank=True,
    )

    class Meta:
        db_table = 'construccion_dashboard_semanal'
        verbose_name = 'Dashboard — Avance semanal'
        verbose_name_plural = 'Dashboard — Avances semanales'
        unique_together = [['proyecto', 'fase', 'semana']]
        ordering = ['semana']

    def __str__(self):
        return f"{self.fase} {self.semana}"

    @property
    def varianza_semana(self):
        return int(self.torres_construidas_semana) - int(self.torres_programadas_semana)

    @property
    def varianza_acum(self):
        return int(self.torres_construidas_acum) - int(self.torres_programadas_acum)


def recalcular_dashboard_acumulados(proyecto, fase):
    """Recalcula los acumulados de toda la serie de una fase del dashboard.

    Para cada semana en orden cronológico: prog_acum = prev.prog_acum +
    semana, igual cons_acum. pct_programado y pct_construido se computan
    contra el total de torres del proyecto.
    """
    semanas = list(DashboardAvanceSemanal.objects
        .filter(proyecto=proyecto, fase=fase)
        .order_by('semana'))
    total_torres = proyecto.torres.count() or 1
    prog_acum = 0
    cons_acum = 0
    from decimal import Decimal
    for s in semanas:
        prog_acum += int(s.torres_programadas_semana)
        cons_acum += int(s.torres_construidas_semana)
        s.torres_programadas_acum = prog_acum
        s.torres_construidas_acum = cons_acum
        s.pct_programado = Decimal(prog_acum * 100) / Decimal(total_torres)
        s.pct_construido = Decimal(cons_acum * 100) / Decimal(total_torres)
        s.save(update_fields=[
            'torres_programadas_acum', 'torres_construidas_acum',
            'pct_programado', 'pct_construido', 'updated_at',
        ])


class FaseTorre(BaseModel):
    """
    Assembly (montaje) and stringing (tendido) phases per tower.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='fase',
    )
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='fases',
    )

    # ===== INFO ESTRUCTURA (#56) =====
    class FuncionTorre(models.TextChoices):
        RETENCION = 'RETENCION', 'Retención'
        AMARRE = 'AMARRE', 'Amarre'
        SUSPENSION = 'SUSPENSION', 'Suspensión'

    funcion_torre = models.CharField('Función de la torre', max_length=15,
                                     choices=FuncionTorre.choices, blank=True)
    tipo_torre_montaje = models.CharField('Tipo de torre (nomenclatura proyecto)',
                                          max_length=30, blank=True)
    cuerpo_torre = models.CharField('Cuerpo / tramo de cuerpo', max_length=30, blank=True)

    # ===== MONTAJE (Assembly) =====
    seleccion_estructura_ok = models.BooleanField('Selección de estructura', default=False)
    seleccion_estructura_fecha = models.DateField(null=True, blank=True)

    transporte_estructura_ok = models.BooleanField('Transporte de estructura', default=False)
    transporte_estructura_fecha = models.DateField(null=True, blank=True)

    # Recepción en patio (#56 — agregada en Reunión 8)
    fecha_recepcion_patio = models.DateField('Fecha recepción en patio',
                                             null=True, blank=True)
    recibida_satisfaccion_ok = models.BooleanField(
        'Recibida a satisfacción (sin pendientes)', default=False)
    pct_completitud_estructura = models.PositiveSmallIntegerField(
        '% completitud estructura recibida', default=100,
        help_text='100 si llegó completa; <100 si faltan piezas')
    observaciones_recepcion = models.TextField('Observaciones piezas pendientes', blank=True)

    prearmado_ok = models.BooleanField('Prearmado', default=False)
    prearmado_fecha = models.DateField(null=True, blank=True)
    prearmado_fecha_inicio = models.DateField('Fecha inicio prearmado',
                                              null=True, blank=True)
    prearmado_fecha_fin = models.DateField('Fecha fin prearmado',
                                           null=True, blank=True)
    prearmado_pct = models.PositiveSmallIntegerField('% avance prearmado', default=0)
    cuadrilla_prearmado = models.CharField(max_length=100, blank=True)

    montaje_ok = models.BooleanField('Montaje', default=False)
    montaje_fecha = models.DateField(null=True, blank=True)
    cuadrilla_montaje = models.CharField(max_length=100, blank=True)

    torsion_ok = models.BooleanField('Verificación de torsión', default=False)
    torsion_fecha = models.DateField(null=True, blank=True)

    entrega_wsp_ok = models.BooleanField('Entrega WSP', default=False)
    entrega_wsp_fecha = models.DateField(null=True, blank=True)

    # Entrega para carga (#56 — gate de Tendido #58)
    entrega_carga_ok = models.BooleanField(
        'Entrega para carga', default=False,
        help_text='Habilita inicio del módulo Tendido para esta torre')
    entrega_carga_fecha = models.DateField('Fecha entrega para carga',
                                           null=True, blank=True)

    pct_montaje = models.FloatField('% Montaje', default=0)

    # ===== SPT — Sistema Puesta a Tierra (#57) =====
    spt_cantidad_excavacion_m = models.FloatField(
        'SPT — Cantidad excavación (m)', null=True, blank=True)
    spt_cable_planos_m = models.FloatField(
        'SPT — Cable según planos (m)', null=True, blank=True)
    spt_cable_instalado_m = models.FloatField(
        'SPT — Cable instalado (m)', null=True, blank=True)
    spt_polvora_tiros_planos = models.PositiveIntegerField(
        'SPT — Pólvora: tiros según planos', null=True, blank=True,
        help_text='Ej: 145 tiros por torre')
    spt_polvora_tiros_por_caja = models.PositiveSmallIntegerField(
        'Tiros por caja de pólvora', default=100,
        help_text='Para calcular cajas teóricas')
    spt_polvora_consumida_cajas = models.FloatField(
        'SPT — Pólvora real consumida (cajas)', null=True, blank=True)
    spt_observaciones = models.TextField('SPT — Observaciones', blank=True)
    spt_ft068_ok = models.BooleanField('FT-068 Control compensación', default=False)
    spt_ft029_ok = models.BooleanField('FT-029 Lectura medición PT', default=False)
    spt_informe_mediciones_ok = models.BooleanField(
        'Informe mediciones entregado', default=False)
    spt_pct = models.PositiveSmallIntegerField('% Avance SPT', default=0)

    # ===== PINTURA (#57) =====
    pintura_ft912_ok = models.BooleanField('FT-912 Control espesor pintura patas',
                                           default=False)
    pintura_observaciones = models.TextField('Pintura — Observaciones', blank=True)

    # ===== TENDIDO (Stringing) =====
    vestida_torres_ok = models.BooleanField('Vestida de torres', default=False)
    vestida_torres_fecha = models.DateField(null=True, blank=True)

    # Sub-flujo conductor (#58)
    riega_manila_ok = models.BooleanField('Riega de manila', default=False)
    riega_guaya_ok = models.BooleanField('Riega de guaya', default=False)
    ft046_ok = models.BooleanField('FT-046 Control riega y tendido', default=False)
    ft047_ok = models.BooleanField('FT-047 Control empalmes y terminales', default=False)
    ft932_ok = models.BooleanField('FT-932 Control regulación conductor', default=False)
    regulacion_flechado_ok = models.BooleanField('Regulación y flechado conductor',
                                                 default=False)
    ft918_ok = models.BooleanField('FT-918 Tabla cruces post-tendido', default=False)
    grapado_ok = models.BooleanField('Grapado / amarre final', default=False)
    accesorios_ok = models.BooleanField('Accesorios instalados (puentes, palizas)',
                                        default=False)
    placas_senalizacion_ok = models.BooleanField('Placas de señalización',
                                                 default=False)
    distancia_vano_adelante_m = models.FloatField('Distancia vano adelante (m)',
                                                  null=True, blank=True)

    # Conductor per phase (3 phases: A, B, C for single circuit)
    tendido_conductor_a_ok = models.BooleanField('Tendido conductor Fase A', default=False)
    tendido_conductor_a_fecha = models.DateField(null=True, blank=True)

    tendido_conductor_b_ok = models.BooleanField('Tendido conductor Fase B', default=False)
    tendido_conductor_b_fecha = models.DateField(null=True, blank=True)

    tendido_conductor_c_ok = models.BooleanField('Tendido conductor Fase C', default=False)
    tendido_conductor_c_fecha = models.DateField(null=True, blank=True)

    # OPGW (optical ground wire)
    tendido_opgw_izq_ok = models.BooleanField('Tendido OPGW izquierda', default=False)
    tendido_opgw_izq_fecha = models.DateField(null=True, blank=True)

    tendido_opgw_der_ok = models.BooleanField('Tendido OPGW derecha', default=False)
    tendido_opgw_der_fecha = models.DateField(null=True, blank=True)

    # Circuito 2 — 3 fases adicionales (#58: 2 circuitos × 3 fases)
    tendido_conductor_c2_a_ok = models.BooleanField(
        'Tendido conductor Circuito 2 Fase A', default=False)
    tendido_conductor_c2_a_fecha = models.DateField(null=True, blank=True)
    tendido_conductor_c2_b_ok = models.BooleanField(
        'Tendido conductor Circuito 2 Fase B', default=False)
    tendido_conductor_c2_b_fecha = models.DateField(null=True, blank=True)
    tendido_conductor_c2_c_ok = models.BooleanField(
        'Tendido conductor Circuito 2 Fase C', default=False)
    tendido_conductor_c2_c_fecha = models.DateField(null=True, blank=True)

    # Cable de guarda
    tendido_guarda_ok = models.BooleanField('Tendido cable de guarda', default=False)
    tendido_guarda_fecha = models.DateField(null=True, blank=True)

    # Regulation & finish
    regulacion_ok = models.BooleanField('Regulación y flechado', default=False)
    regulacion_fecha = models.DateField(null=True, blank=True)

    cuadrilla_tendido = models.CharField('Cuadrilla tendido', max_length=100, blank=True)
    pct_tendido = models.FloatField('% Tendido', default=0)

    # Billing
    pct_facturacion = models.FloatField('% Facturación', default=0)

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_fases_torres'
        verbose_name = 'Fase de Torre'
        verbose_name_plural = 'Fases de Torres'

    def __str__(self):
        return f"Fases - Torre {self.torre.numero}"

    @property
    def porcentaje_montaje(self):
        """Calculate assembly phase completion %."""
        actividades = [
            self.seleccion_estructura_ok,
            self.transporte_estructura_ok,
            self.prearmado_ok,
            self.montaje_ok,
            self.torsion_ok,
            self.entrega_wsp_ok,
        ]
        completadas = sum(1 for a in actividades if a)
        return round((completadas / len(actividades)) * 100, 2) if actividades else 0

    @property
    def porcentaje_tendido(self):
        """Calculate stringing phase completion %."""
        actividades = [
            self.vestida_torres_ok,
            self.tendido_conductor_a_ok,
            self.tendido_conductor_b_ok,
            self.tendido_conductor_c_ok,
            self.tendido_opgw_izq_ok,
            self.tendido_opgw_der_ok,
            self.regulacion_ok,
        ]
        completadas = sum(1 for a in actividades if a)
        return round((completadas / len(actividades)) * 100, 2) if actividades else 0

    # === Gate Tendido (#58) ===
    @property
    def puede_iniciar_tendido(self):
        """True si esta torre ya tiene 'Entrega para carga' del módulo Montaje.
        Regla Gabriel Valencia (Reunión 7): el tendido se habilita por
        la columna 'Entrega para carga' del módulo Montaje."""
        return self.entrega_carga_ok

    # === SPT properties (#57) ===
    @property
    def spt_cable_diferencia_m(self):
        """instalado - planos. None si falta data."""
        if self.spt_cable_planos_m is None or self.spt_cable_instalado_m is None:
            return None
        return round(self.spt_cable_instalado_m - self.spt_cable_planos_m, 2)

    @property
    def spt_polvora_cajas_teoricas(self):
        """tiros_planos / tiros_por_caja. None si falta data."""
        if not self.spt_polvora_tiros_planos or not self.spt_polvora_tiros_por_caja:
            return None
        return round(self.spt_polvora_tiros_planos / self.spt_polvora_tiros_por_caja, 2)

    @property
    def spt_polvora_diferencia_cajas(self):
        """consumida - teórica. Positivo = sobreconsumo (alerta de escasez)."""
        teoricas = self.spt_polvora_cajas_teoricas
        if teoricas is None or self.spt_polvora_consumida_cajas is None:
            return None
        return round(self.spt_polvora_consumida_cajas - teoricas, 2)

    @property
    def spt_polvora_sobreconsumo(self):
        """True si consumida > teórica (regla Gabriel Valencia, Reunión 7:
        'en todas las obras siempre hace falta pólvora ... al final ya cuando
        se va a ejecutar las últimas torres no hay pólvora')."""
        diff = self.spt_polvora_diferencia_cajas
        return diff is not None and diff > 0


class SocialPredial(BaseModel):
    """
    Land/social clearance tracking per tower.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='social_predial',
    )

    propietario = models.CharField('Propietario', max_length=300, blank=True)
    persona_contacto = models.CharField('Persona de contacto', max_length=300, blank=True,
                                        help_text='Si difiere del propietario')
    telefono = models.CharField('Teléfono de contacto', max_length=50, blank=True)
    predio = models.CharField('Nombre de la finca', max_length=200, blank=True)
    departamento = models.CharField('Departamento', max_length=100, blank=True)
    municipio = models.CharField('Municipio', max_length=100, blank=True)
    unidad_territorial = models.CharField('Vereda/corregimiento', max_length=200, blank=True)
    fecha_socializacion = models.DateField('Fecha de socialización del proyecto a comunidades',
                                           null=True, blank=True)

    # Document tracking: (fecha, ok) pairs
    pipc_municipio_fecha = models.DateField('PIPC Municipio - Fecha', null=True, blank=True)
    pipc_municipio_ok = models.BooleanField('PIPC Municipio - OK', default=False)

    pipc_unidad_fecha = models.DateField('PIPC Unidad Territorial - Fecha', null=True, blank=True)
    pipc_unidad_ok = models.BooleanField('PIPC Unidad Territorial - OK', default=False)

    acta_vecindad_fecha = models.DateField('Acta Vecindad - Fecha', null=True, blank=True)
    acta_vecindad_ok = models.BooleanField('Acta Vecindad - OK', default=False)

    acta_acceso_comunitario_fecha = models.DateField('Acta Acceso Comunitario - Fecha', null=True, blank=True)
    acta_acceso_comunitario_ok = models.BooleanField('Acta Acceso Comunitario - OK', default=False)

    autorizacion_propietario_fecha = models.DateField('Autorización Propietario - Fecha', null=True, blank=True)
    autorizacion_propietario_ok = models.BooleanField('Autorización Propietario - OK', default=False)

    acta_acceso_privado_fecha = models.DateField('Acta Acceso Privado - Fecha', null=True, blank=True)
    acta_acceso_privado_ok = models.BooleanField('Acta Acceso Privado - OK', default=False)

    liberacion_predial_pdo_fecha = models.DateField('Liberación Predial PDO - Fecha', null=True, blank=True)
    liberacion_predial_pdo_ok = models.BooleanField('Liberación Predial PDO - OK', default=False)

    contratacion_monc_fecha = models.DateField('Contratación MONC - Fecha', null=True, blank=True)
    contratacion_monc_ok = models.BooleanField('Contratación MONC - OK', default=False)

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_social_predial'
        verbose_name = 'Social Predial'
        verbose_name_plural = 'Social Predial'

    def __str__(self):
        return f"Social - Torre {self.torre.numero}"

    @property
    def semaforo(self):
        """Verde si las 4 actas de liberación tienen fecha; rojo en caso contrario.
        Regla definida por Ana Sofía Munera (Reunión 10, 00:05:52):
        'estas cuatro fechas, si están completas, me libere'. Las 4 actas son:
        Vecindad + Acceso Comunitario + Acta con Propietario (autorizacion) + Acceso Privado.
        """
        cuatro_actas = [
            self.acta_vecindad_fecha,
            self.acta_acceso_comunitario_fecha,
            self.autorizacion_propietario_fecha,
            self.acta_acceso_privado_fecha,
        ]
        return 'VERDE' if all(cuatro_actas) else 'ROJO'

    @property
    def liberado(self):
        return self.semaforo == 'VERDE'


class AmbientalTorre(BaseModel):
    """
    Environmental clearance per tower.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='ambiental',
    )

    # Ahuyentamiento (puede no aplicar — potrero limpio sin fauna)
    ahuyentamiento_aplica = models.BooleanField('Aplica ahuyentamiento', default=True)
    ahuyentamiento_fecha = models.DateField('Ahuyentamiento especies - Fecha', null=True, blank=True)
    ahuyentamiento_ok = models.BooleanField('Ahuyentamiento especies - OK', default=False)

    # Epífitas (puede no aplicar — sin árboles con epífitas)
    epifitas_aplica = models.BooleanField('Aplica gestión de epífitas', default=True)
    conteo_epifitas = models.PositiveIntegerField('Conteo de epífitas a reubicar',
                                                  null=True, blank=True)
    conteo_epifitas_fecha = models.DateField('Conteo de epífitas - Fecha',
                                             null=True, blank=True)
    traslado_epifitas_fecha = models.DateField('Traslado de epífitas a vivero - Fecha',
                                               null=True, blank=True)
    traslado_epifitas_ok = models.BooleanField('Traslado de epífitas - OK', default=False)
    reubicacion_epifitas_fecha = models.DateField(
        'Reubicación de epífitas (con corporación) - Fecha', null=True, blank=True)
    reubicacion_epifitas_ok = models.BooleanField('Reubicación de epífitas - OK', default=False)

    # Aprovechamiento forestal — torre + vanos
    aprov_forestal_torre_aplica = models.BooleanField('Aplica aprovechamiento forestal (torre)',
                                                      default=True)
    aprov_forestal_torre_fecha = models.DateField('Aprovech. Forestal (torre) - Fecha',
                                                  null=True, blank=True)
    aprov_forestal_torre_ok = models.BooleanField('Aprovech. Forestal (torre) - OK', default=False)

    aprov_forestal_vano_aplica = models.BooleanField('Aplica aprovechamiento forestal (vano)',
                                                     default=True)
    aprov_forestal_vano_fecha = models.DateField('Aprovech. Forestal (vano) - Fecha',
                                                 null=True, blank=True)
    aprov_forestal_vano_ok = models.BooleanField('Aprovech. Forestal (vano) - OK', default=False)

    # Arqueología
    arqueologia_poligonos_fecha = models.DateField('Polígonos prospección ICAN - Fecha',
                                                   null=True, blank=True)
    arqueologia_poligonos_ok = models.BooleanField('Polígonos ICAN - OK', default=False)
    arqueologia_torre_estado = models.CharField('Arqueología Torre', max_length=50, blank=True)
    rescate_arqueologico_aplica = models.BooleanField('Aplica rescate arqueológico', default=True)
    rescate_arqueologico_fecha = models.DateField('Rescate Arqueológico - Fecha',
                                                  null=True, blank=True)
    rescate_arqueologico_ok = models.BooleanField('Rescate Arqueológico - OK', default=False)
    monitoreo_arqueologico_aplica = models.BooleanField(
        'Monitoreo arqueológico durante excavaciones', default=False,
        help_text='Sí/No — definir si requiere monitoreo continuo')

    cambio_menor_la = models.TextField('Cambio Menor L.A.', blank=True)

    adecuacion_accesos_fecha = models.DateField('Adecuación de accesos - Fecha',
                                                null=True, blank=True)
    adecuacion_accesos_porcentaje = models.PositiveSmallIntegerField(
        'Adecuación de accesos - % avance', default=0)
    adecuacion_accesos_ok = models.BooleanField('Adecuación de accesos - OK', default=False)

    liberacion_pdo_fecha = models.DateField('Liberación PDO - Fecha', null=True, blank=True)
    liberacion_pdo_ok = models.BooleanField('Liberación PDO - OK', default=False)

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_ambiental'
        verbose_name = 'Ambiental Torre'
        verbose_name_plural = 'Ambientales Torres'

    def __str__(self):
        return f"Ambiental - Torre {self.torre.numero}"

    @property
    def semaforo(self):
        """Verde si todas las actividades QUE APLICAN tienen fecha.
        Regla definida por Gabriel Valencia (Reunión 10): 'aprovechamientos,
        traslado de epífitas si se hacen, ahuyentamiento si aplica'.
        Las actividades con `_aplica=False` se omiten del cálculo
        (caso: 'potrero limpio sin ahuyentamiento').
        """
        condiciones = []
        if self.ahuyentamiento_aplica:
            condiciones.append(self.ahuyentamiento_fecha is not None)
        if self.epifitas_aplica:
            condiciones.append(self.traslado_epifitas_fecha is not None)
            condiciones.append(self.reubicacion_epifitas_fecha is not None)
        if self.aprov_forestal_torre_aplica:
            condiciones.append(self.aprov_forestal_torre_fecha is not None)
        if self.aprov_forestal_vano_aplica:
            condiciones.append(self.aprov_forestal_vano_fecha is not None)
        if self.rescate_arqueologico_aplica:
            condiciones.append(self.rescate_arqueologico_fecha is not None)
        # Si nada aplica → libre automático
        if not condiciones:
            return 'VERDE'
        return 'VERDE' if all(condiciones) else 'ROJO'

    @property
    def liberado(self):
        return self.semaforo == 'VERDE'


class ControlLluvia(BaseModel):
    """
    Daily rain hours log per tower (used to justify construction delays).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.ForeignKey(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='lluvia',
    )
    fecha = models.DateField('Fecha')
    hora_inicio = models.TimeField('Hora inicio', null=True, blank=True)
    hora_fin = models.TimeField('Hora fin', null=True, blank=True)
    duracion_horas = models.DurationField('Duración', null=True, blank=True)

    class Meta:
        db_table = 'construccion_control_lluvia'
        verbose_name = 'Control de Lluvia'
        verbose_name_plural = 'Control de Lluvia'
        unique_together = [['torre', 'fecha']]

    def __str__(self):
        return f"Lluvia - Torre {self.torre.numero} ({self.fecha})"


class ReporteReplanteo(BaseModel):
    """
    Topographic survey (replanteo) daily report / journal.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='reportes_replanteo',
    )

    fecha_ejecutado = models.DateField('Fecha ejecutado', null=True, blank=True)
    torres_ejecutadas = models.TextField('Torres ejecutadas (texto)', blank=True, help_text='e.g., T29, 30, 31, 32')
    observaciones_ejecutado = models.TextField('Observaciones ejecutado', blank=True)

    fecha_programado = models.DateField('Fecha programado', null=True, blank=True)
    actividad_programada = models.TextField('Actividad programada', blank=True)

    observacion_ambiental = models.TextField('Observación ambiental', blank=True)

    class Meta:
        db_table = 'construccion_reporte_replanteo'
        verbose_name = 'Reporte Replanteo'
        verbose_name_plural = 'Reportes Replanteo'
        ordering = ['-fecha_ejecutado']

    def __str__(self):
        return f"Replanteo {self.fecha_ejecutado}"


class PersonalSST(BaseModel):
    """
    Health & Safety (SST) personnel assigned to the project.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='personal_sst',
    )

    codigo = models.IntegerField('Código', null=True, blank=True)
    numero_identificador = models.CharField('Identificador', max_length=20, blank=True)
    empresa = models.CharField('Empresa', max_length=200, blank=True)
    nombre_completo = models.CharField('Nombre completo', max_length=300)
    cuadrilla_asignada = models.CharField('Cuadrilla asignada', max_length=200, blank=True)
    cargo = models.CharField(
        'Cargo',
        max_length=100,
        choices=[
            ('SUPERVISOR_SST', 'Supervisor SST'),
            ('VIGIA_SST', 'Vigía SST'),
            ('COORDINADOR_SST', 'Coordinador SST'),
        ],
        blank=True,
    )
    estado_sylogi = models.CharField(
        'Estado SYLOGI',
        max_length=50,
        choices=[
            ('APROBADO', 'Aprobado'),
            ('PENDIENTE', 'Pendiente aprobación'),
            ('POR_INGRESAR', 'Por ingresar'),
            ('CERO', 'Cero'),
        ],
        blank=True,
    )

    class Meta:
        db_table = 'construccion_personal_sst'
        verbose_name = 'Personal SST'
        verbose_name_plural = 'Personal SST'

    def __str__(self):
        return f"{self.nombre_completo} ({self.cargo})"


class EntregaElectromecanica(BaseModel):
    """
    Electromechanical delivery/inspection record (entrega CTE/HMV-WSP).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='entrega_electromecanica',
    )

    observacion_formato = models.CharField('Observación formato', max_length=500, blank=True)

    obs_spt = models.TextField('Observación SPT', blank=True)
    obs_estructura = models.TextField('Observación estructura', blank=True)
    obs_conductor_a = models.TextField('Observación conductor Fase A', blank=True)
    obs_conductor_b = models.TextField('Observación conductor Fase B', blank=True)
    obs_conductor_c = models.TextField('Observación conductor Fase C', blank=True)
    obs_opgw_izq = models.TextField('Observación OPGW izquierda', blank=True)
    obs_opgw_der = models.TextField('Observación OPGW derecha', blank=True)

    firmo_hmv = models.BooleanField('Firmó HMV', default=False)
    firmo_wsp = models.BooleanField('Firmó WSP', default=False)
    cajas_opgw = models.IntegerField('Cajas OPGW', null=True, blank=True)

    fecha_primera_visita = models.DateField('Fecha primera visita', null=True, blank=True)
    fecha_segunda_visita = models.DateField('Fecha segunda visita', null=True, blank=True)

    avance = models.FloatField('Avance', default=0)
    estado = models.CharField(
        'Estado',
        max_length=50,
        choices=[
            ('LIBERADA', 'Liberada'),
            ('PENDIENTE', 'Pendiente'),
            ('RECHAZADA', 'Rechazada'),
        ],
        blank=True,
    )
    observaciones_adicionales = models.TextField('Observaciones adicionales', blank=True)

    class Meta:
        db_table = 'construccion_entrega_electromecanica'
        verbose_name = 'Entrega Electromecánica'
        verbose_name_plural = 'Entregas Electromecánicas'

    def __str__(self):
        return f"Entrega - Torre {self.torre.numero}"


class CorreccionEntrega(BaseModel):
    """
    Post-delivery corrections (punch-list) tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='correccion_entrega',
    )

    fecha_correccion = models.DateField('Fecha corrección', null=True, blank=True)
    avance_correccion = models.FloatField('Avance correcciones', default=0)

    fecha_entrega_oc_hmv = models.DateField('Fecha entrega OC-HMV', null=True, blank=True)
    fecha_segunda_visita = models.DateField('Fecha segunda visita', null=True, blank=True)

    avance_entrega = models.FloatField('Avance entregas', default=0)
    firma_hmv = models.BooleanField('Firma HMV', default=False)

    observaciones_trabajo = models.TextField('Observaciones de trabajo', blank=True)
    observaciones_pintura = models.TextField('Observaciones pintura', blank=True)
    observaciones_adicionales = models.TextField('Observaciones adicionales', blank=True)

    class Meta:
        db_table = 'construccion_correccion_entrega'
        verbose_name = 'Corrección de Entrega'
        verbose_name_plural = 'Correcciones de Entrega'

    def __str__(self):
        return f"Corrección - Torre {self.torre.numero}"


class ObraProteccion(BaseModel):
    """Obras de protección por torre (#59): trinchos, cunetas, gaviones,
    revegetalización, geotextil. Se ejecutan en torres en ladera/montaña.
    Cantidades de materiales derivadas de metros lineales (estándar)."""

    class TipoMedida(models.TextChoices):
        CUNETAS = 'CUNETAS', 'Cunetas'
        TRINCHOS = 'TRINCHOS', 'Trinchos'
        GAVIONES = 'GAVIONES', 'Gaviones'
        REVEGETALIZACION = 'REVEGETALIZACION', 'Revegetalización'
        GEOTEXTIL = 'GEOTEXTIL', 'Geotextil'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion, on_delete=models.CASCADE,
        related_name='obra_proteccion',
    )
    tipos_medida = models.CharField(
        'Tipos de medida de manejo', max_length=200, blank=True,
        help_text='Lista CSV: CUNETAS,TRINCHOS,GAVIONES,REVEGETALIZACION,GEOTEXTIL')
    metros_trinchos = models.FloatField('Metros lineales trinchos',
                                        null=True, blank=True)
    metros_cunetas = models.FloatField('Metros lineales cunetas',
                                       null=True, blank=True)
    nota = models.TextField('Nota / descripción', blank=True)

    # Materiales (declarados o calculados; UI puede precalcular desde m_lineales)
    tubo_metalico_unidades = models.FloatField('Tubo metálico 3x3" zinc 50µ (uds 3m)',
                                               null=True, blank=True)
    malla_eslabonada_m2 = models.FloatField('Malla eslabonada galvanizada (m²)',
                                            null=True, blank=True)
    alambre_galvanizado_kg = models.FloatField('Alambre galvanizado (kg)',
                                               null=True, blank=True)
    geotextil_m2 = models.FloatField('Geotextil (m²)', null=True, blank=True)
    cemento_bultos = models.FloatField('Cemento general (bultos 50 kg)',
                                       null=True, blank=True)
    arena_cunetes = models.FloatField('Arena (cuñetes)', null=True, blank=True,
                                      help_text='Zona montañosa — no camiones')
    grava_cunetes = models.FloatField('Grava (cuñetes)', null=True, blank=True)
    revegetalizacion_m2 = models.FloatField('Revegetalización (m²)',
                                            null=True, blank=True)

    cuadrilla = models.ForeignKey(
        'cuadrillas.Cuadrilla', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='obras_proteccion')
    fecha_ejecucion = models.DateField('Fecha de ejecución', null=True, blank=True)
    completada_ok = models.BooleanField('Obra completada', default=False)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_obra_proteccion'
        verbose_name = 'Obra de Protección'
        verbose_name_plural = 'Obras de Protección'

    def __str__(self):
        return f"Protección - Torre {self.torre.numero}"


class PruebaTecnica(BaseModel):
    """Pruebas técnicas certificadas del proyecto (#60). Configurable:
    número y nombres definidos por cliente. Ejemplos: empalmes F.O,
    pruebas comunicación OTDR, parámetros eléctricos LT, certificado Retie,
    mediciones paso/contacto."""

    class Resultado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        CUMPLE = 'CUMPLE', 'Cumple'
        NO_CUMPLE = 'NO_CUMPLE', 'No cumple'
        NO_APLICA = 'NO_APLICA', 'No aplica'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='pruebas_tecnicas')
    nombre = models.CharField('Nombre de la prueba', max_length=300,
                              help_text='Editable; ej: "Pruebas comunicación F.O entre subestaciones"')
    orden = models.PositiveSmallIntegerField('Orden', default=0)
    fecha_programada = models.DateField('Fecha programada', null=True, blank=True)
    fecha_ejecucion = models.DateField('Fecha real de ejecución',
                                       null=True, blank=True)
    laboratorio = models.CharField('Laboratorio / Empresa certificadora',
                                   max_length=200, blank=True)
    resultado = models.CharField('Resultado', max_length=15,
                                 choices=Resultado.choices,
                                 default=Resultado.PENDIENTE)
    adjunto = models.FileField('Documento del resultado',
                               upload_to='construccion/pruebas/',
                               null=True, blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_prueba_tecnica'
        verbose_name = 'Prueba Técnica'
        verbose_name_plural = 'Pruebas Técnicas'
        ordering = ['proyecto', 'orden', 'nombre']

    def __str__(self):
        return f"{self.proyecto.nombre} — {self.nombre}"


class KitCerramiento(BaseModel):
    """Kit reutilizable de cerramiento (#65). Madera/lona/alambre que se mueve
    de torre en torre. Caso real Gabriel Valencia: 33 torres encerradas porque
    los kits quedaron empeñados — se compró material extra innecesariamente."""

    class Estado(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        EN_USO = 'EN_USO', 'En uso'
        DAÑADO = 'DAÑADO', 'Dañado'
        PERDIDO = 'PERDIDO', 'Perdido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='kits_cerramiento')
    codigo = models.CharField('Código del kit', max_length=30,
                              help_text='Ej: KIT-001, KIT-002')
    componentes = models.CharField('Tipo de componentes', max_length=200,
                                   help_text='CSV libre: madera, lona, alambre')
    cantidad = models.PositiveIntegerField('Cantidad de componentes', default=1)
    estado = models.CharField('Estado', max_length=15, choices=Estado.choices,
                              default=Estado.DISPONIBLE)
    torre_actual = models.ForeignKey(
        TorreConstruccion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kits_en_torre',
        help_text='Torre donde está actualmente el kit')
    fecha_ingreso_torre = models.DateField('Fecha de ingreso a esta torre',
                                           null=True, blank=True)
    fecha_salida_torre = models.DateField('Fecha de salida de esta torre',
                                          null=True, blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_kit_cerramiento'
        verbose_name = 'Kit de Cerramiento'
        verbose_name_plural = 'Kits de Cerramiento'
        unique_together = [['proyecto', 'codigo']]
        ordering = ['proyecto', 'codigo']

    def __str__(self):
        return f"{self.codigo} ({self.estado})"

    @property
    def dias_en_torre_actual(self):
        if not self.torre_actual or not self.fecha_ingreso_torre:
            return None
        from datetime import date
        return (date.today() - self.fecha_ingreso_torre).days

    @property
    def alerta_demora(self):
        """True si lleva >30 días en la misma torre — caso 33 torres encerradas."""
        dias = self.dias_en_torre_actual
        return dias is not None and dias > 30


class MovimientoKit(BaseModel):
    """Histórico de movimientos de un kit entre torres (#65 iteración 2).
    Generado automáticamente por signal cuando KitCerramiento.torre_actual cambia.
    Permite auditar dónde estuvo el kit X del 1-mar al 15-mar, etc."""

    class Accion(models.TextChoices):
        ASIGNAR = 'ASIGNAR', 'Asignar a torre'
        LIBERAR = 'LIBERAR', 'Liberar de torre'
        MOVER = 'MOVER', 'Mover entre torres'
        ESTADO = 'ESTADO', 'Cambio de estado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kit = models.ForeignKey(KitCerramiento, on_delete=models.CASCADE,
                            related_name='movimientos')
    accion = models.CharField('Acción', max_length=10, choices=Accion.choices)
    torre_origen = models.ForeignKey(
        TorreConstruccion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kits_origen')
    torre_destino = models.ForeignKey(
        TorreConstruccion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kits_destino')
    fecha = models.DateTimeField('Fecha del movimiento', auto_now_add=True)
    estado_previo = models.CharField('Estado previo', max_length=15, blank=True)
    estado_nuevo = models.CharField('Estado nuevo', max_length=15, blank=True)
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movimientos_kit')
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_movimiento_kit'
        verbose_name = 'Movimiento de Kit'
        verbose_name_plural = 'Movimientos de Kits'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d} | {self.kit.codigo} | {self.accion}"


class ProgramacionFase(BaseModel):
    """Cronograma planeado vs real por sección del proyecto (#68).
    El equipo de ingeniería fija las fechas al inicio; el sistema calcula
    avance real consumiendo los modelos de ejecución."""

    class Seccion(models.TextChoices):
        INGENIERIA = 'INGENIERIA', 'Ingeniería'
        SOCIOPREDIAL = 'SOCIOPREDIAL', 'Actividades Preliminares — Sociopredial'
        SOCIOAMBIENTAL = 'SOCIOAMBIENTAL', 'Actividades Preliminares — Socioambiental'
        OBRA_CIVIL = 'OBRA_CIVIL', 'Obra Civil'
        MONTAJE = 'MONTAJE', 'Montaje'
        SPT = 'SPT', 'SPT y Pintura'
        TENDIDO = 'TENDIDO', 'Tendido'
        PROTECCIONES = 'PROTECCIONES', 'Trinchos y Cunetas'
        PRUEBAS = 'PRUEBAS', 'Pruebas y Actividades Finales'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='programacion_fases')
    seccion = models.CharField('Sección', max_length=20, choices=Seccion.choices)
    fecha_inicio_planeada = models.DateField('Fecha inicio planeada',
                                             null=True, blank=True)
    fecha_fin_planeada = models.DateField('Fecha fin planeada',
                                          null=True, blank=True)
    torres_planeadas = models.PositiveIntegerField('Torres / cantidad planeada',
                                                   null=True, blank=True)
    peso_pct = models.PositiveSmallIntegerField(
        'Peso % de la sección', default=0,
        help_text='Suma de pesos por proyecto debe ≈ 100; editable para curva S')
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_programacion_fase'
        verbose_name = 'Programación de Fase'
        verbose_name_plural = 'Programaciones de Fases'
        unique_together = [['proyecto', 'seccion']]
        ordering = ['proyecto', 'seccion']

    def __str__(self):
        return f"{self.proyecto.nombre} — {self.get_seccion_display()}"

    @property
    def dias_planeados(self):
        if not self.fecha_inicio_planeada or not self.fecha_fin_planeada:
            return None
        return (self.fecha_fin_planeada - self.fecha_inicio_planeada).days

    @property
    def pct_avance_esperado_hoy(self):
        """Avance lineal esperado a la fecha actual según fechas planeadas."""
        if not self.fecha_inicio_planeada or not self.fecha_fin_planeada:
            return None
        from datetime import date
        hoy = date.today()
        if hoy < self.fecha_inicio_planeada:
            return 0
        if hoy >= self.fecha_fin_planeada:
            return 100
        total = (self.fecha_fin_planeada - self.fecha_inicio_planeada).days
        transcurridos = (hoy - self.fecha_inicio_planeada).days
        return round((transcurridos / total) * 100, 1) if total > 0 else 0

    @property
    def pct_avance_real(self):
        """Lee el % real desde el ProyectoConstruccion según la sección."""
        p = self.proyecto
        mapeo = {
            'OBRA_CIVIL': p.porcentaje_avance_civil,
            'MONTAJE': p.porcentaje_avance_montaje,
            'TENDIDO': p.porcentaje_avance_tendido,
        }
        return mapeo.get(self.seccion)

    @property
    def estado(self):
        """ON_TIME / ADELANTADO / RETRASADO según comparación esperado vs real."""
        esp = self.pct_avance_esperado_hoy
        real = self.pct_avance_real
        if esp is None or real is None:
            return 'SIN_DATA'
        diff = real - esp
        if abs(diff) < 5:
            return 'ON_TIME'
        return 'ADELANTADO' if diff > 0 else 'RETRASADO'


# ====================================================================
# Módulo Financiero PDEO (#69 #66 #70) — replica estructura del Excel
# PDEO - Detalle 2024-2025-2026.xlsx
# ====================================================================

class CategoriaFinanciera(BaseModel):
    """Master de categorías de costos/ingresos del P&G (#69).
    Seedeable: las 21 categorías estándar del Excel PDEO."""

    class Tipo(models.TextChoices):
        INGRESO = 'INGRESO', 'Ingreso'
        GASTO = 'GASTO', 'Gasto'
        CALCULADO = 'CALCULADO', 'Calculado (totales)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo = models.CharField('Código', max_length=30, unique=True,
                              help_text='Slug interno, ej: SUBCONTRATISTAS, GASTOS_VIAJE')
    nombre = models.CharField('Nombre', max_length=100)
    tipo = models.CharField('Tipo', max_length=15, choices=Tipo.choices,
                            default=Tipo.GASTO)
    orden = models.PositiveSmallIntegerField('Orden', default=0)
    activa = models.BooleanField('Activa', default=True)
    categoria_padre = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hijos',
        help_text='Permite jerarquía: Ingresos → Operacionales, Egresos → CIF → Materiales')
    nivel = models.PositiveSmallIntegerField('Nivel jerárquico', default=1,
        help_text='1 = raíz, 2 = sub-categoría, 3 = detalle')

    class Meta:
        db_table = 'construccion_categoria_financiera'
        verbose_name = 'Categoría Financiera'
        verbose_name_plural = 'Categorías Financieras'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f"[{self.tipo}] {self.nombre}"


class PeriodoFinanciero(BaseModel):
    """Período mensual del proyecto (#69). Año fiscal puede no coincidir
    con año calendario."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='periodos_financieros')
    anio = models.PositiveSmallIntegerField('Año')
    mes = models.PositiveSmallIntegerField('Mes')
    cerrado = models.BooleanField('Período cerrado', default=False,
        help_text='Si está cerrado, no se aceptan nuevos movimientos REAL')

    class Meta:
        db_table = 'construccion_periodo_financiero'
        verbose_name = 'Período Financiero'
        verbose_name_plural = 'Períodos Financieros'
        unique_together = [['proyecto', 'anio', 'mes']]
        ordering = ['proyecto', 'anio', 'mes']

    def __str__(self):
        return f"{self.proyecto.nombre} — {self.mes:02d}/{self.anio}"


class MovimientoFinanciero(BaseModel):
    """Movimiento P&G: presupuesto o real, por categoría × período (#69).
    Para una celda de la matriz P&G existen 2 movimientos: PRESUPUESTO + REAL.
    """

    class Tipo(models.TextChoices):
        PRESUPUESTO = 'PRESUPUESTO', 'Presupuesto'
        REAL = 'REAL', 'Real'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    periodo = models.ForeignKey(
        PeriodoFinanciero, on_delete=models.CASCADE,
        related_name='movimientos')
    categoria = models.ForeignKey(
        CategoriaFinanciera, on_delete=models.PROTECT,
        related_name='movimientos')
    tipo = models.CharField('Tipo', max_length=15, choices=Tipo.choices)
    valor = models.DecimalField('Valor (COP)', max_digits=18, decimal_places=2,
                                default=0)
    fecha_registro = models.DateTimeField('Fecha registro', auto_now_add=True)
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movimientos_financieros')
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_movimiento_financiero'
        verbose_name = 'Movimiento Financiero'
        verbose_name_plural = 'Movimientos Financieros'
        unique_together = [['periodo', 'categoria', 'tipo']]
        ordering = ['periodo', 'categoria__orden']

    def __str__(self):
        return f"{self.periodo} | {self.categoria.codigo} | {self.tipo} | ${self.valor:,.0f}"


class CerramientoDetalle(BaseModel):
    """Detalles del bloque 1 Cerramiento (#53 iteración 2)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='cerramiento_detalle')
    cantidad_madera = models.PositiveIntegerField('Cantidad de madera (unidades)',
                                                  null=True, blank=True)
    metros_lona_pua = models.FloatField('Metros lona/alambre de púa',
                                        null=True, blank=True)
    senalizacion_ok = models.BooleanField('Señalización instalada', default=False)
    punto_ecologico_ok = models.BooleanField('Punto ecológico instalado', default=False)
    bano_ok = models.BooleanField('Baño instalado', default=False)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_cerramiento_detalle'
        verbose_name = 'Detalle Cerramiento'

    def __str__(self):
        return f"Cerramiento {self.pata}"


class ExcavacionDetalle(BaseModel):
    """Detalles del bloque 2 Excavación (#53 iteración 2)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='excavacion_detalle')
    procedimiento_ft022_ok = models.BooleanField('FT-022 Procedimiento aprobado', default=False)
    sst_ft023_ok = models.BooleanField('FT-023 Doc SST excavaciones', default=False)
    prueba_penetrometro_ok = models.BooleanField('Prueba de penetrómetro', default=False)
    entivado_ft058_ok = models.BooleanField('FT-058 Concepto entibado', default=False)
    monitoreo_arqueologico_ok = models.BooleanField('Monitoreo arqueológico', default=False)
    subcontratistas = models.CharField('Subcontratistas involucrados', max_length=300, blank=True)
    # Pilotes — 5 FTs cuando aplica
    ft925_carga_ok = models.BooleanField('FT-925 Carga pilotes', default=False)
    ft926_marcacion_ok = models.BooleanField('FT-926 Marcación', default=False)
    ft927_cantidades_ok = models.BooleanField('FT-927 Cantidades', default=False)
    ft928_torques_ok = models.BooleanField('FT-928 Torques', default=False)
    ft929_localizacion_ok = models.BooleanField('FT-929 Localización final', default=False)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_excavacion_detalle'
        verbose_name = 'Detalle Excavación'

    def __str__(self):
        return f"Excavación {self.pata}"


class SoladoDetalle(BaseModel):
    """Detalles del bloque 3 Solado (#53 iteración 2)."""
    class IngresoMateriales(models.TextChoices):
        VEHICULAR = 'VEHICULAR', 'Vehicular'
        MANUAL = 'MANUAL', 'Manual'
        MULAR = 'MULAR', 'Mular'
        TELEFERICO = 'TELEFERICO', 'Teleférico'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='solado_detalle')
    ingreso_materiales = models.CharField('Ingreso de materiales', max_length=15,
                                          choices=IngresoMateriales.choices, blank=True)
    agua_calc_m3 = models.FloatField('Agua calculada (m³)', null=True, blank=True)
    agua_util_m3 = models.FloatField('Agua utilizada (m³)', null=True, blank=True)
    arena_calc_m3 = models.FloatField('Arena calculada (m³)', null=True, blank=True)
    arena_util_m3 = models.FloatField('Arena utilizada (m³)', null=True, blank=True)
    grava_calc_m3 = models.FloatField('Grava calculada (m³)', null=True, blank=True)
    grava_util_m3 = models.FloatField('Grava utilizada (m³)', null=True, blank=True)
    cemento_calc_bultos = models.FloatField('Cemento calculado (bultos)', null=True, blank=True)
    cemento_util_bultos = models.FloatField('Cemento utilizado (bultos)', null=True, blank=True)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_solado_detalle'
        verbose_name = 'Detalle Solado'

    def __str__(self):
        return f"Solado {self.pata}"


class AceroDetalle(BaseModel):
    """Detalles del bloque 4 Acero (#53 iteración 2)."""
    class IngresoAcero(models.TextChoices):
        VEHICULAR = 'VEHICULAR', 'Vehicular'
        MULAR = 'MULAR', 'Mular'
        TELEFERICO = 'TELEFERICO', 'Teleférico'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='acero_detalle')
    soldadura_prolongas_ok = models.BooleanField('Soldadura prolongas a stub', default=False)
    ingreso_acero = models.CharField('Ingreso de acero', max_length=15,
                                     choices=IngresoAcero.choices, blank=True)
    it028_ok = models.BooleanField('IT-028 Instructivo instalación acero', default=False)
    ft930_ok = models.BooleanField('FT-930 Revisión acero/formaleta/SPT', default=False)
    corte_flejado_ok = models.BooleanField('Corte y flejado', default=False)
    acero_armado_ok = models.BooleanField('Acero armado en sitio', default=False)
    spt_base_completo_ok = models.BooleanField('SPT base: varilla+cable+conectores', default=False)
    nivelacion_stub_ft916_ok = models.BooleanField('FT-916 Nivelación stub', default=False)
    encofrado_ok = models.BooleanField('Encofrado / formaleteado', default=False)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_acero_detalle'
        verbose_name = 'Detalle Acero'

    def __str__(self):
        return f"Acero {self.pata}"


class VaciadoDetalle(BaseModel):
    """Detalles del bloque 5 Vaciado en Concreto (#53 iteración 2)."""
    class TipoConcreto(models.TextChoices):
        PREMEZCLADO = 'PREMEZCLADO', 'Premezclado'
        OBRA = 'OBRA', 'Hecho en obra'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='vaciado_detalle')
    it380_ok = models.BooleanField('IT-380 Instructivo cimentación', default=False)
    ft056_ok = models.BooleanField('FT-056 Control fundaciones', default=False)
    tipo_concreto = models.CharField('Tipo de concreto', max_length=15,
                                     choices=TipoConcreto.choices, blank=True)
    agua_calc_m3 = models.FloatField('Agua calc (m³)', null=True, blank=True)
    agua_util_m3 = models.FloatField('Agua util (m³)', null=True, blank=True)
    arena_calc_m3 = models.FloatField('Arena calc (m³)', null=True, blank=True)
    arena_util_m3 = models.FloatField('Arena util (m³)', null=True, blank=True)
    grava_calc_m3 = models.FloatField('Grava calc (m³)', null=True, blank=True)
    grava_util_m3 = models.FloatField('Grava util (m³)', null=True, blank=True)
    cemento_calc_bultos = models.FloatField('Cemento calc (bultos)', null=True, blank=True)
    cemento_util_bultos = models.FloatField('Cemento util (bultos)', null=True, blank=True)
    prueba_slump_ok = models.BooleanField('Prueba de slump', default=False)
    fecha_fabricacion_cilindros = models.DateField('Fecha fabricación cilindros',
                                                   null=True, blank=True)
    inspeccion_nivelacion_stub_post_ok = models.BooleanField(
        'Inspección nivelación stub post-vaciado', default=False)
    encargado_puntas_diamante = models.CharField('Encargado puntas de diamante',
                                                 max_length=200, blank=True)
    fecha_desencofrado = models.DateField('Fecha desencofrado', null=True, blank=True)
    hidratacion_pedestales_ok = models.BooleanField('Hidratación de pedestales', default=False)
    resane_pedestales_ok = models.BooleanField('Resane de pedestales', default=False)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_vaciado_detalle'
        verbose_name = 'Detalle Vaciado'

    def __str__(self):
        return f"Vaciado {self.pata}"


class CompactacionDetalle(BaseModel):
    """Detalles del bloque 6 Compactación (#53 iteración 2)."""
    class TipoCompactacion(models.TextChoices):
        NATURAL = 'NATURAL', 'Suelo natural'
        CEMENTO = 'CEMENTO', 'Suelo + cemento'
        PRESTAMO = 'PRESTAMO', 'Suelo de préstamo'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pata = models.OneToOneField(PataObra, on_delete=models.CASCADE,
                                related_name='compactacion_detalle')
    ft914_ok = models.BooleanField('FT-914 Control compactación', default=False)
    tipo_compactacion = models.CharField('Tipo de compactación', max_length=15,
                                         choices=TipoCompactacion.choices, blank=True)
    volumen_m3 = models.FloatField('Volumen compactación (m³)', null=True, blank=True)
    proctor_ok = models.BooleanField('Prueba Proctor', default=False)
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_compactacion_detalle'
        verbose_name = 'Detalle Compactación'

    def __str__(self):
        return f"Compactación {self.pata}"


class TransaccionContable(BaseModel):
    """Sección 3 del PDEO Excel: cada transacción individual con NIT
    proveedor, factura, valor (#69 iteración 2).

    Si MovimientoFinanciero es el agregado mensual, TransaccionContable
    es el detalle: cada factura/comprobante que suma al movimiento.
    Permite integración futura con SIIGO/Alegra."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movimiento = models.ForeignKey(
        MovimientoFinanciero, on_delete=models.CASCADE,
        related_name='transacciones',
        help_text='Movimiento mensual al que pertenece (real o presupuesto)')
    fecha = models.DateField('Fecha de la transacción')
    descripcion = models.CharField('Descripción', max_length=400)
    nit_proveedor = models.CharField('NIT proveedor', max_length=30, blank=True)
    nombre_proveedor = models.CharField('Nombre proveedor', max_length=200, blank=True)
    numero_factura = models.CharField('Número de factura', max_length=50, blank=True)
    valor = models.DecimalField('Valor (COP)', max_digits=16, decimal_places=2)
    iva = models.DecimalField('IVA (COP)', max_digits=14, decimal_places=2, default=0)
    centro_costo = models.CharField('Centro de costo', max_length=50, blank=True)
    adjunto = models.FileField('Soporte (factura/comprobante)',
                               upload_to='construccion/transacciones/',
                               null=True, blank=True)
    siigo_id = models.CharField('ID externo SIIGO/Alegra', max_length=50, blank=True,
        help_text='Para evitar duplicados al sincronizar')
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transacciones_registradas')
    notas = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'construccion_transaccion_contable'
        verbose_name = 'Transacción Contable'
        verbose_name_plural = 'Transacciones Contables'
        ordering = ['-fecha', '-created_at']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['nit_proveedor']),
            models.Index(fields=['siigo_id']),
        ]

    def __str__(self):
        return f"{self.fecha} | {self.descripcion[:50]} | ${self.valor:,.0f}"


class SnapshotAvance(BaseModel):
    """Snapshot mensual del % avance por sección de un proyecto (#61).

    Capturado por el management command `snapshot_avance_proyectos`,
    típicamente vía Celery beat el primer día del mes. Sirve para
    reconstruir la curva S del avance real histórico (sin snapshots
    solo tenemos el dato instantáneo)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        ProyectoConstruccion, on_delete=models.CASCADE,
        related_name='snapshots_avance')
    fecha = models.DateField('Fecha del snapshot')
    pct_civil = models.FloatField('% Obra Civil (ponderado)', default=0)
    pct_montaje = models.FloatField('% Montaje', default=0)
    pct_tendido = models.FloatField('% Tendido', default=0)
    pct_general = models.FloatField('% General (promedio)', default=0)

    class Meta:
        db_table = 'construccion_snapshot_avance'
        verbose_name = 'Snapshot de Avance'
        verbose_name_plural = 'Snapshots de Avance'
        unique_together = [['proyecto', 'fecha']]
        ordering = ['proyecto', 'fecha']

    def __str__(self):
        return f"{self.proyecto.nombre} @ {self.fecha} ({self.pct_general}%)"

    @classmethod
    def capturar(cls, proyecto, fecha=None):
        """Captura un snapshot del estado actual del proyecto."""
        from datetime import date
        fecha = fecha or date.today()
        civil = float(proyecto.porcentaje_avance_civil_ponderado or 0)
        montaje = float(proyecto.porcentaje_avance_montaje or 0)
        tendido = float(proyecto.porcentaje_avance_tendido or 0)
        general = round((civil + montaje + tendido) / 3, 2)
        snap, _ = cls.objects.update_or_create(
            proyecto=proyecto, fecha=fecha,
            defaults={
                'pct_civil': civil, 'pct_montaje': montaje,
                'pct_tendido': tendido, 'pct_general': general,
            },
        )
        return snap
