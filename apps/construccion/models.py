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

    # ===== MONTAJE (Assembly) =====
    seleccion_estructura_ok = models.BooleanField('Selección de estructura', default=False)
    seleccion_estructura_fecha = models.DateField(null=True, blank=True)

    transporte_estructura_ok = models.BooleanField('Transporte de estructura', default=False)
    transporte_estructura_fecha = models.DateField(null=True, blank=True)

    prearmado_ok = models.BooleanField('Prearmado', default=False)
    prearmado_fecha = models.DateField(null=True, blank=True)
    cuadrilla_prearmado = models.CharField(max_length=100, blank=True)

    montaje_ok = models.BooleanField('Montaje', default=False)
    montaje_fecha = models.DateField(null=True, blank=True)
    cuadrilla_montaje = models.CharField(max_length=100, blank=True)

    torsion_ok = models.BooleanField('Verificación de torsión', default=False)
    torsion_fecha = models.DateField(null=True, blank=True)

    entrega_wsp_ok = models.BooleanField('Entrega WSP', default=False)
    entrega_wsp_fecha = models.DateField(null=True, blank=True)

    pct_montaje = models.FloatField('% Montaje', default=0)

    # ===== TENDIDO (Stringing) =====
    vestida_torres_ok = models.BooleanField('Vestida de torres', default=False)
    vestida_torres_fecha = models.DateField(null=True, blank=True)

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
