"""B1 — ActividadFinalTorre.

Modelo para registrar las 13 actividades finales (pruebas y cierre) de cada
torre/estructura de un proyecto L.T. 230kV. Implementa la matriz 14×64 del
issue #96 con validaciones de progresión lógica server-side.

Columnas del Excel (PRUEBAS Y ACTIVIDADES FINALES):
- A: Estructura (identificador, viene de TorreConstruccion.numero)
- B: Empalme F.O. subestaciones        (empalmes_subestacion)
- C: Empalmes F.O. intermedios         (empalmes_intermedios)
- D: Pruebas comunicación F.O.         (pruebas_comunicacion)
- E: Pruebas eléctricas LT 230kV       (pruebas_electricas)
- F: Visita certificación RETIE        (visita_retie)
- G: Certificado RETIE                 (certificado_retie)
- H: Mediciones paso/contacto          (mediciones_paso_contacto)
- I: Reuniones cierre comunidades      (reuniones_cierre)
- J: Cierre actas vecindad             (cierre_actas)
- K: Paz y salvo propietarios          (paz_salvo_propietarios)
- L: Paz y salvo proveedores           (paz_salvo_proveedores)
- M: Informe socioambiental            (informe_socioambiental)
- N: Dossier final                     (dossier)

Validaciones de progresión lógica:
  - G requiere F (no certificado sin visita)
  - K requiere J (no paz y salvo sin actas cerradas)
  - N (dossier) requiere TODOS los anteriores
"""
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel
from .models import TorreConstruccion


# Lista canónica de las 13 actividades (orden = columna B..N del Excel).
ACTIVIDAD_CAMPOS = [
    'empalmes_subestacion',
    'empalmes_intermedios',
    'pruebas_comunicacion',
    'pruebas_electricas',
    'visita_retie',
    'certificado_retie',
    'mediciones_paso_contacto',
    'reuniones_cierre',
    'cierre_actas',
    'paz_salvo_propietarios',
    'paz_salvo_proveedores',
    'informe_socioambiental',
    'dossier',
]


# Agrupación por sección del Excel (para headers colspan en la matriz).
# Cada tupla: (slug_seccion, label, [(slug_campo, label_corto, letra), ...])
SECCIONES_ACTIVIDADES = [
    ('fibra_optica', 'Empalmes F.O.', [
        ('empalmes_subestacion', 'Subestación', 'B'),
        ('empalmes_intermedios', 'Intermedios', 'C'),
    ]),
    ('comunicacion', 'Comunicación', [
        ('pruebas_comunicacion', 'Pruebas F.O.', 'D'),
    ]),
    ('electricas', 'Pruebas Eléctricas / RETIE', [
        ('pruebas_electricas', 'Pruebas 230kV', 'E'),
        ('visita_retie', 'Visita RETIE', 'F'),
        ('certificado_retie', 'Certificado', 'G'),
    ]),
    ('seguridad', 'Seguridad', [
        ('mediciones_paso_contacto', 'Paso/Contacto', 'H'),
    ]),
    ('social', 'Gestión Social', [
        ('reuniones_cierre', 'Reuniones', 'I'),
        ('cierre_actas', 'Cierre actas', 'J'),
        ('paz_salvo_propietarios', 'P&S Propietarios', 'K'),
    ]),
    ('administrativa', 'Administrativa', [
        ('paz_salvo_proveedores', 'P&S Proveedores', 'L'),
        ('informe_socioambiental', 'Informe socioamb.', 'M'),
    ]),
    ('cierre', 'Cierre', [
        ('dossier', 'Dossier', 'N'),
    ]),
]


class ActividadFinalTorre(BaseModel):
    """Registro de actividades finales para una torre/estructura.

    Una sola fila por torre con 13 BooleanField más observaciones libres.
    """

    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='actividades_finales',
        verbose_name='Torre',
    )

    # Aplicabilidad por torre (#150). default=True = comportamiento histórico.
    # Si False, la torre se marca como "No aplica" y se excluye del avance.
    aplica = models.BooleanField(
        'Aplica esta torre', default=True,
        help_text='Si False, la torre no cuenta para el avance (estado "No aplica").',
    )

    # SECCIÓN 2: EMPALMES F.O.
    empalmes_subestacion = models.BooleanField(
        'B. Empalme F.O. subestaciones', default=False,
    )
    empalmes_intermedios = models.BooleanField(
        'C. Empalmes F.O. intermedios', default=False,
    )

    # SECCIÓN 3: COMUNICACIÓN
    pruebas_comunicacion = models.BooleanField(
        'D. Pruebas comunicación F.O.', default=False,
    )

    # SECCIÓN 4: PRUEBAS ELÉCTRICAS Y RETIE
    pruebas_electricas = models.BooleanField(
        'E. Pruebas eléctricas LT 230kV', default=False,
    )
    visita_retie = models.BooleanField(
        'F. Visita certificación RETIE', default=False,
    )
    certificado_retie = models.BooleanField(
        'G. Certificado RETIE', default=False,
    )

    # SECCIÓN 5: SEGURIDAD ELÉCTRICA
    mediciones_paso_contacto = models.BooleanField(
        'H. Mediciones paso/contacto', default=False,
    )

    # SECCIÓN 6: GESTIÓN SOCIAL Y COMUNITARIA
    reuniones_cierre = models.BooleanField(
        'I. Reuniones cierre con comunidades', default=False,
    )
    cierre_actas = models.BooleanField(
        'J. Cierre actas de vecindad', default=False,
    )
    paz_salvo_propietarios = models.BooleanField(
        'K. Paz y salvo propietarios', default=False,
    )

    # SECCIÓN 7: GESTIÓN ADMINISTRATIVA
    paz_salvo_proveedores = models.BooleanField(
        'L. Paz y salvo proveedores', default=False,
    )
    informe_socioambiental = models.BooleanField(
        'M. Informe final socioambiental', default=False,
    )

    # SECCIÓN 8: DOCUMENTACIÓN FINAL
    dossier = models.BooleanField(
        'N. Dossier final compilado', default=False,
    )

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_actividad_final_torre'
        verbose_name = 'Actividad Final por Torre'
        verbose_name_plural = 'Actividades Finales por Torre'
        ordering = ['torre__numero']

    def __str__(self):
        return f'ActividadesFinales {self.torre.numero_display} ({self.pct_avance:.0f}%)'

    # ==================================================================
    # Validaciones de progresión lógica (server-side)
    # ==================================================================

    def _validar_progresion(self):
        """Reglas duras (referenciadas en el issue #96):
        - G (certificado_retie) requiere F (visita_retie)
        - K (paz_salvo_propietarios) requiere J (cierre_actas)
        - N (dossier) requiere TODOS los anteriores
        """
        errors = {}

        if self.certificado_retie and not self.visita_retie:
            errors['certificado_retie'] = (
                'No puede emitirse el Certificado RETIE sin la Visita de certificación previa (F).'
            )

        if self.paz_salvo_propietarios and not self.cierre_actas:
            errors['paz_salvo_propietarios'] = (
                'No puede firmarse Paz y Salvo con propietarios sin cerrar las actas de vecindad primero (J).'
            )

        if self.dossier:
            faltantes = [
                campo for campo in ACTIVIDAD_CAMPOS
                if campo != 'dossier' and not getattr(self, campo)
            ]
            if faltantes:
                errors['dossier'] = (
                    'El Dossier solo puede marcarse cuando TODAS las demás actividades '
                    f'están completas. Faltan: {", ".join(faltantes)}'
                )

        if errors:
            raise ValidationError(errors)

    def clean(self):
        super().clean()
        # #150: si la torre no aplica, no validar progresión lógica (la matriz
        # queda inactiva y los flags no se cuentan).
        if not self.aplica:
            return
        self._validar_progresion()

    def save(self, *args, **kwargs):
        # full_clean para garantizar la validación incluso desde toggles HTMX
        # que no usan ModelForm.
        self.full_clean()
        super().save(*args, **kwargs)

    # ==================================================================
    # Métricas / estado
    # ==================================================================

    @property
    def total_actividades(self):
        return len(ACTIVIDAD_CAMPOS)

    @property
    def actividades_completas(self):
        return sum(1 for campo in ACTIVIDAD_CAMPOS if getattr(self, campo))

    @property
    def pct_avance(self):
        """Porcentaje 0..100 de actividades completadas.

        Si la torre no aplica (#150), devuelve 100.0 para que NO figure como
        pendiente en los agregados de avance (queda fuera del cómputo de
        actividades por hacer).
        """
        if not self.aplica:
            return 100.0
        if not self.total_actividades:
            return 0.0
        return (self.actividades_completas / self.total_actividades) * 100.0

    @property
    def estado_semaforo(self):
        """5 estados color (4 del #96 + NO_APLICA del #150):
        - NO_APLICA (gris): la torre no aplica al módulo
        - NO_INICIADO (rojo): 0 actividades
        - EN_PROCESO (amarillo): >0 y <100% y sin bloqueos
        - BLOQUEADO (naranja): hay actividad marcada pero falta una previa lógica
        - COMPLETADO (verde): dossier=True (todo en 1)
        """
        if not self.aplica:
            return 'NO_APLICA'
        if self.dossier:
            return 'COMPLETADO'
        if self.actividades_completas == 0:
            return 'NO_INICIADO'
        # ¿Hay alguna progresión rota latente que el usuario aún no ha intentado?
        # No usamos `clean()` aquí porque ese ya cortó al guardar — pero sí podemos
        # detectar "falta lógica próxima":
        bloqueos = []
        if self.visita_retie and not self.pruebas_electricas:
            bloqueos.append('falta pruebas eléctricas previas a visita RETIE')
        if self.certificado_retie and not self.visita_retie:
            bloqueos.append('certificado sin visita')
        if self.paz_salvo_propietarios and not self.cierre_actas:
            bloqueos.append('paz y salvo sin cierre de actas')
        if bloqueos:
            return 'BLOQUEADO'
        return 'EN_PROCESO'

    @property
    def estado_semaforo_color(self):
        """Clase CSS Tailwind para el badge del estado."""
        return {
            'NO_APLICA': 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
            'NO_INICIADO': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
            'EN_PROCESO': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
            'BLOQUEADO': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
            'COMPLETADO': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
        }.get(self.estado_semaforo, 'bg-gray-100 text-gray-700')

    @property
    def estado_semaforo_label(self):
        return {
            'NO_APLICA': 'No aplica',
            'NO_INICIADO': 'No iniciado',
            'EN_PROCESO': 'En proceso',
            'BLOQUEADO': 'Bloqueado',
            'COMPLETADO': 'Completado',
        }.get(self.estado_semaforo, '—')

    def proxima_actividad_pendiente(self):
        """Devuelve el slug de la próxima actividad lógica disponible (la primera
        no completada cuyas dependencias previas SÍ están cumplidas). Útil para UI."""
        # Orden por flujo del issue
        flujo = [
            'pruebas_electricas', 'visita_retie', 'certificado_retie',
            'pruebas_comunicacion',
            'empalmes_subestacion', 'empalmes_intermedios',
            'mediciones_paso_contacto',
            'reuniones_cierre', 'cierre_actas', 'paz_salvo_propietarios',
            'paz_salvo_proveedores', 'informe_socioambiental', 'dossier',
        ]
        for campo in flujo:
            if not getattr(self, campo):
                return campo
        return None
