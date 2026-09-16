"""#225 Sprint B — UI de colaboradores/presupuesto (B1+B2+B3)."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.construccion.models import (
    AsignacionPersonalProyectoConstruccion,
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProyectoConstruccion,
)
from apps.construccion.services_psc_presupuesto import (
    congelar_plan_presupuesto_por_primer_real,
    construir_asignacion_presupuestada,
)
from apps.contratos.models import Contrato
from apps.cuadrillas.models import Cargo, Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import ProduccionDiaria
from apps.usuarios.models import Usuario


@pytest.fixture
def psc_admin(db):
    return Usuario.objects.create_superuser(
        email="psc-admin-225b@instelec.test",
        password="ClaudeQA2026!",
        first_name="Admin",
        last_name="PSC225B",
        documento="PSC-225-B-ADMIN",
    )


@pytest.fixture
def psc_programacion(db):
    contrato = Contrato.objects.create(
        codigo="PSC-225-B",
        nombre="Contrato presupuesto PSC B",
        unidad_negocio="CONSTRUCCION",
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Proyecto presupuesto PSC B"
    )
    cargo = Cargo.objects.create(
        codigo="PSC225B-CARGO", nombre="Cargo PSC B", salario_base=Decimal("3000.00")
    )
    supervisor_personal = PersonalCuadrilla.objects.create(
        nombre="Supervisor PSC B",
        documento="PSC-225-B-1",
        rol_cuadrilla=cargo,
        salario_base=Decimal("9000.00"),
        area="CONSTRUCCION",
        activo=True,
    )
    colaborador_personal = PersonalCuadrilla.objects.create(
        nombre="Colaborador PSC B",
        documento="PSC-225-B-2",
        rol_cuadrilla=cargo,
        salario_base=Decimal("6000.00"),
        area="CONSTRUCCION",
        activo=True,
    )
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto,
        tipo_actividad="OBRA_CIVIL",
        subactividad="Excavación",
        fecha_inicio=date(2026, 9, 14),
        fecha_fin=date(2026, 9, 16),
    )
    # `validar_personal_elegible` exige una aprobación vigente por proyecto (#225 Sprint A).
    for persona in (supervisor_personal, colaborador_personal):
        AsignacionPersonalProyectoConstruccion.objects.create(
            proyecto=proyecto,
            personal=persona,
            fecha_inicio=date(2026, 1, 1),
        )
    return programacion, supervisor_personal, colaborador_personal, cargo


@pytest.mark.django_db
class TestB1FormularioSupervisorColaboradoresPresupuesto:
    """B1 — asignación de supervisor/colaboradores con tarifa no editable y validaciones."""

    def test_agregar_supervisor_presupuestario_toma_snapshot_automatico(
        self, client, psc_admin, psc_programacion
    ):
        programacion, supervisor_personal, _, _ = psc_programacion
        client.force_login(psc_admin)
        url = reverse("construccion:psc_personal_agregar", kwargs={"pk": programacion.pk})

        response = client.post(
            url,
            {
                "personal_ids": [str(supervisor_personal.pk)],
                "categoria": ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO,
                "rol_presupuesto": ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
            },
            follow=True,
        )

        assert response.status_code == 200
        asignacion = ProgramacionSemanalConstruccionPersonal.objects.get(
            programacion=programacion,
            personal=supervisor_personal,
        )
        assert (
            asignacion.rol_presupuesto
            == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR
        )
        assert asignacion.tarifa_diaria_snapshot == Decimal("300.0000")
        assert (
            asignacion.fuente_tarifa
            == ProgramacionSemanalConstruccionPersonal.FuenteTarifa.PERSONAL
        )

    def test_no_permite_dos_supervisores_presupuestarios(self, client, psc_admin, psc_programacion):
        programacion, supervisor_personal, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(
            programacion,
            supervisor_personal,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()
        client.force_login(psc_admin)
        url = reverse("construccion:psc_personal_agregar", kwargs={"pk": programacion.pk})

        response = client.post(
            url,
            {
                "personal_ids": [str(colaborador_personal.pk)],
                "categoria": ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO,
                "rol_presupuesto": ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
            },
            follow=True,
        )

        assert response.status_code == 200
        assert not ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion,
            personal=colaborador_personal,
        ).exists()
        mensajes = [str(m) for m in response.context["messages"]]
        assert any("ya tiene un supervisor presupuestario" in m for m in mensajes)

    def test_rechaza_duplicado_de_la_misma_persona(self, client, psc_admin, psc_programacion):
        programacion, _, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(programacion, colaborador_personal).save()
        client.force_login(psc_admin)
        url = reverse("construccion:psc_personal_agregar", kwargs={"pk": programacion.pk})

        response = client.post(
            url,
            {
                "personal_ids": [str(colaborador_personal.pk)],
                "categoria": ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO,
                "rol_presupuesto": ProgramacionSemanalConstruccionPersonal.RolPresupuesto.COLABORADOR,
            },
            follow=True,
        )

        assert response.status_code == 200
        assert (
            ProgramacionSemanalConstruccionPersonal.objects.filter(
                programacion=programacion,
                personal=colaborador_personal,
            ).count()
            == 1
        )

    def test_form_bloquea_edicion_cuando_presupuesto_esta_congelado(
        self, client, psc_admin, psc_programacion
    ):
        programacion, supervisor_personal, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(
            programacion,
            supervisor_personal,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()
        construir_asignacion_presupuestada(programacion, colaborador_personal).save()
        cuadrilla = Cuadrilla.objects.create(codigo="PSC225B-1", nombre="Cuadrilla PSC 225B")
        semanal = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, anio=2026, semana=38
        )
        primer_real = ProduccionDiaria.objects.create(programacion=semanal, fecha=date(2026, 9, 14))
        congelar_plan_presupuesto_por_primer_real(programacion.pk, primer_real.pk, timezone.now())
        client.force_login(psc_admin)

        detalle_url = reverse(
            "construccion:psc_programacion_detalle", kwargs={"pk": programacion.pk}
        )
        detalle = client.get(detalle_url)
        assert detalle.status_code == 200
        contenido = detalle.content.decode()
        assert "Congelado" in contenido
        assert "no se puede agregar ni quitar personal" in contenido

        otra_persona = PersonalCuadrilla.objects.create(
            nombre="Tercera persona PSC B",
            documento="PSC-225-B-3",
            rol_cuadrilla=colaborador_personal.rol_cuadrilla,
            salario_base=Decimal("5000.00"),
            area="CONSTRUCCION",
            activo=True,
        )
        agregar_url = reverse("construccion:psc_personal_agregar", kwargs={"pk": programacion.pk})
        response = client.post(
            agregar_url,
            {
                "personal_ids": [str(otra_persona.pk)],
                "categoria": ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO,
                "rol_presupuesto": ProgramacionSemanalConstruccionPersonal.RolPresupuesto.COLABORADOR,
            },
            follow=True,
        )
        assert not ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion,
            personal=otra_persona,
        ).exists()
        mensajes = [str(m) for m in response.context["messages"]]
        assert any("congelado" in m for m in mensajes)

        quitar_url = reverse(
            "construccion:psc_personal_quitar",
            kwargs={"pk": programacion.pk, "personal_pk": colaborador_personal.pk},
        )
        client.post(quitar_url, follow=True)
        assert ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion,
            personal=colaborador_personal,
        ).exists()


@pytest.mark.django_db
class TestB2ListadoYDetallePresupuestados:
    """B2 — composición, subtotales, presupuesto total y estado en listado/detalle."""

    def test_detalle_muestra_composicion_subtotales_y_total(
        self, client, psc_admin, psc_programacion
    ):
        programacion, supervisor_personal, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(
            programacion,
            supervisor_personal,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()
        construir_asignacion_presupuestada(programacion, colaborador_personal).save()
        client.force_login(psc_admin)

        response = client.get(
            reverse("construccion:psc_programacion_detalle", kwargs={"pk": programacion.pk})
        )

        assert response.status_code == 200
        contenido = response.content.decode()
        assert "Editable" in contenido
        assert "Supervisor PSC B" in contenido
        assert "Colaborador PSC B" in contenido
        # 3 días programados (14-16 inclusive): 300*3=900, 200*3=600 -> total 1500
        # (convención del repo: dinero se muestra floatformat:0|intcomma, sin
        # decimales, ej. "1,500" para el total).
        assert "900" in contenido
        assert "600" in contenido
        assert "1.500" in contenido

    def test_listado_muestra_presupuesto_total_por_fila_y_legacy_sin_error(
        self, client, psc_admin, psc_programacion
    ):
        programacion, supervisor_personal, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(
            programacion,
            supervisor_personal,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()
        construir_asignacion_presupuestada(programacion, colaborador_personal).save()

        # Programación legacy sin ninguna asignación presupuestada: no debe reventar.
        ProgramacionSemanalConstruccion.objects.create(
            proyecto=programacion.proyecto,
            tipo_actividad="TENDIDO",
            subactividad="Legacy",
            fecha_inicio=date(2026, 9, 20),
            fecha_fin=date(2026, 9, 20),
        )

        client.force_login(psc_admin)
        response = client.get(reverse("construccion:psc_programacion_lista"))
        assert response.status_code == 200
        contenido = response.content.decode()
        assert "1.500" in contenido
        assert "Sin presupuestar" in contenido
        assert len(response.context["filas_programacion"]) == 2


@pytest.mark.django_db
class TestB3ReconciliacionDomYAccesibilidad:
    """B3 — un widget por control dinámico, errores visibles cerca del campo."""

    def test_boton_quitar_colaborador_apunta_a_url_unica_por_persona(
        self, client, psc_admin, psc_programacion
    ):
        programacion, supervisor_personal, colaborador_personal, _ = psc_programacion
        construir_asignacion_presupuestada(
            programacion,
            supervisor_personal,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()
        construir_asignacion_presupuestada(programacion, colaborador_personal).save()
        client.force_login(psc_admin)

        response = client.get(
            reverse("construccion:psc_programacion_detalle", kwargs={"pk": programacion.pk})
        )
        contenido = response.content.decode()

        url_supervisor = reverse(
            "construccion:psc_personal_quitar",
            kwargs={"pk": programacion.pk, "personal_pk": supervisor_personal.pk},
        )
        url_colaborador = reverse(
            "construccion:psc_personal_quitar",
            kwargs={"pk": programacion.pk, "personal_pk": colaborador_personal.pk},
        )
        assert contenido.count(url_supervisor) == 1
        assert contenido.count(url_colaborador) == 1

    def test_agregar_rol_invalido_devuelve_mensaje_de_error_sin_persistir(
        self, client, psc_admin, psc_programacion
    ):
        programacion, _, colaborador_personal, _ = psc_programacion
        client.force_login(psc_admin)
        url = reverse("construccion:psc_personal_agregar", kwargs={"pk": programacion.pk})

        response = client.post(
            url,
            {
                "personal_ids": [str(colaborador_personal.pk)],
                "categoria": ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO,
                "rol_presupuesto": "INEXISTENTE",
            },
            follow=True,
        )

        assert response.status_code == 200
        assert not ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion,
            personal=colaborador_personal,
        ).exists()
        mensajes = [str(m) for m in response.context["messages"]]
        assert any("rol presupuestario válido" in m for m in mensajes)
