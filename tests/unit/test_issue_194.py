"""Instelec#194 -- Falta poder editar la informacion de un usuario existente
+ actualizar carga masiva.

Bug (confirmado por F2 con evidencia real, 2026-07-25):
  1. No existia ninguna ruta 'gestion/<uuid>/editar/' -- GET real a prod
     (https://instelec-api-rvfp6uj2va-uc.a.run.app) devolvia 404 (ruta ni
     siquiera declarada, no un 302 a login). El ModelForm UsuarioChangeForm
     ya existia (forms.py) pero no estaba cableado a ninguna vista.
  2. CargaMasivaUsuariosCampoView (views.py:143-247) solo leia 4 columnas
     (Nombre, Documento, Cargo, Telefono), inferia el rol por keyword del
     cargo, siempre regeneraba el email como '{documento}@campo.instelec.co'
     y, al actualizar una persona ya existente, nunca tocaba rol ni
     is_active.

Fix:
  1. urls.py + views.py: nueva EditarUsuarioView (UpdateView) cableada con
     UsuarioChangeForm. El Requerimiento 1 del issue pide tambien poder
     editar "estado (activo/inactivo)" -- UsuarioChangeForm no incluia
     is_active, se agrego (forms.py). Template editar_usuario.html + boton
     "Editar" en gestion.html.
  2. views.py: CargaMasivaUsuariosCampoView reescrita a 6 columnas (Nombre,
     Documento, Email, Cargo, Rol, Estado). Rol explicito validado contra
     el catalogo BD-backed Role.objects.filter(activo=True) (#186 A4);
     codigo invalido rechaza la fila (no asume default silencioso). Email
     real con fallback autogenerado solo si viene vacio. Estado mapeado a
     is_active. El branch de update ahora incluye rol/is_active en
     update_fields.

Cubre tambien la hipotesis de riesgo evaluada por F2 (H3, DESCARTADA con
evidencia BD real -- 0 usuarios huerfanos sobre 123 usuarios de campo
reales) de que el catalogo BD-backed de roles NO cubriera los roles legacy
de campo (liniero=91, auxiliar=30, supervisor=2 en prod): test contra dato
legacy con LinieroFactory, no solo fixtures inventadas por este fix.
"""

import io
import uuid

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.usuarios.models import Usuario
from tests.factories import AdminFactory, LinieroFactory, UsuarioFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_excel_upload(rows, filename="carga.xlsx"):
    """Construye un .xlsx (6 columnas: Nombre,Documento,Email,Cargo,Rol,Estado)
    como SimpleUploadedFile, listo para POSTear a campo_upload."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nombre", "Documento", "Email", "Cargo", "Rol", "Estado"])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        filename,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _editar_post_data(usuario, **overrides):
    """Payload base para POST a editar_usuario, partiendo del estado actual
    del usuario (solo se sobreescriben los campos que el test quiere cambiar)."""
    data = {
        "email": usuario.email,
        "first_name": usuario.first_name,
        "last_name": usuario.last_name,
        "rol": usuario.rol,
        "telefono": usuario.telefono or "",
        "documento": usuario.documento or "",
        "cargo": usuario.cargo or "",
        "is_active": "true" if usuario.is_active else "false",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Requerimiento 1: vista de edicion individual
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEditarUsuarioViewExiste:
    """Antes: GET a /usuarios/gestion/<uuid>/editar/ devolvia 404 en prod
    real (confirmado por F2, 2026-07-25) -- la ruta ni siquiera existia
    (no era un 302 a login, era 'no matching URL pattern')."""

    def test_url_editar_usuario_resuelve(self):
        usuario = UsuarioFactory()
        url = reverse("usuarios:editar_usuario", kwargs={"pk": usuario.pk})
        assert url == f"/usuarios/gestion/{usuario.pk}/editar/"

    def test_get_editar_usuario_200_admin(self, client, user_password):
        admin = AdminFactory()
        objetivo = UsuarioFactory(first_name="Pedro", last_name="Gomez")
        client.login(username=admin.email, password=user_password)

        response = client.get(
            reverse("usuarios:editar_usuario", kwargs={"pk": objetivo.pk})
        )

        assert response.status_code == 200
        assert b"Pedro" in response.content

    def test_get_editar_usuario_sin_login_redirige(self, client):
        objetivo = UsuarioFactory()
        response = client.get(
            reverse("usuarios:editar_usuario", kwargs={"pk": objetivo.pk})
        )
        assert response.status_code == 302

    def test_get_editar_usuario_uuid_inexistente_404_por_objeto(self, client, user_password):
        """El 404 ahora es 'objeto no encontrado' (get_object_or_404), NO
        'no matching URL pattern' -- eso ya no puede pasar porque la ruta
        esta declarada (ver test_url_editar_usuario_resuelve)."""
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        response = client.get(f"/usuarios/gestion/{uuid.uuid4()}/editar/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestEditarUsuarioViewActualiza:
    """POST a editar_usuario persiste los cambios, incluyendo rol y estado
    (antes ninguno de los dos era editable para un usuario existente)."""

    def test_post_actualiza_nombre_correo_cargo(self, client, user_password):
        admin = AdminFactory()
        objetivo = UsuarioFactory(first_name="Ana", last_name="Ruiz", cargo="AYUDANTE")
        client.login(username=admin.email, password=user_password)

        response = client.post(
            reverse("usuarios:editar_usuario", kwargs={"pk": objetivo.pk}),
            data=_editar_post_data(
                objetivo,
                first_name="Ana Maria",
                last_name="Ruiz Perez",
                cargo="SUPERVISOR",
            ),
        )

        objetivo.refresh_from_db()
        assert response.status_code == 302
        assert objetivo.first_name == "Ana Maria"
        assert objetivo.last_name == "Ruiz Perez"
        assert objetivo.cargo == "SUPERVISOR"

    def test_post_permite_cambiar_rol(self, client, user_password):
        """Antes no existia forma de reasignar el rol de un usuario ya
        creado desde la UI (ni edicion individual -- no existia -- ni carga
        masiva -- nunca tocaba 'rol' en el update)."""
        admin = AdminFactory()
        objetivo = UsuarioFactory(rol="liniero")
        client.login(username=admin.email, password=user_password)

        response = client.post(
            reverse("usuarios:editar_usuario", kwargs={"pk": objetivo.pk}),
            data=_editar_post_data(objetivo, rol="supervisor"),
        )

        objetivo.refresh_from_db()
        assert response.status_code == 302
        assert objetivo.rol == "supervisor"

    def test_post_permite_inactivar_usuario(self, client, user_password):
        """Requerimiento 1 del issue: 'estado (activo/inactivo)' -- antes
        UsuarioChangeForm ni siquiera incluia is_active."""
        admin = AdminFactory()
        objetivo = UsuarioFactory(is_active=True)
        client.login(username=admin.email, password=user_password)

        response = client.post(
            reverse("usuarios:editar_usuario", kwargs={"pk": objetivo.pk}),
            data=_editar_post_data(objetivo, is_active="false"),
        )

        objetivo.refresh_from_db()
        assert response.status_code == 302
        assert objetivo.is_active is False


@pytest.mark.django_db
class TestEditarUsuarioDatoLegacy:
    """H3 de F2 (DESCARTADA con evidencia BD real -- 0 usuarios huerfanos):
    el catalogo BD-backed de roles (#186 A4) SI cubre los roles legacy de
    campo reales. Reproducido aqui contra LinieroFactory (dato legacy real,
    no un fixture inventado por este fix)."""

    def test_dropdown_incluye_rol_legacy_liniero(self, client, user_password):
        from apps.core.models import Role

        admin = AdminFactory()
        liniero = LinieroFactory()  # dato legacy real: rol='liniero'
        client.login(username=admin.email, password=user_password)

        response = client.get(
            reverse("usuarios:editar_usuario", kwargs={"pk": liniero.pk})
        )

        assert response.status_code == 200
        codigos = [codigo for codigo, _nombre in response.context["roles"]]
        assert "liniero" in codigos, (
            "El rol legacy 'liniero' (91 usuarios reales en prod, confirmado "
            "por F2) no aparece en el dropdown BD-backed -- H3 se "
            "confirmaria como falso positivo."
        )
        assert Role.objects.filter(codigo="liniero", activo=True).exists()

    def test_editar_preserva_rol_legacy_si_no_se_cambia(self, client, user_password):
        """Guardar sin tocar el rol de un liniero legacy no lo pierde ni lo
        cambia silenciosamente."""
        admin = AdminFactory()
        liniero = LinieroFactory()
        client.login(username=admin.email, password=user_password)

        client.post(
            reverse("usuarios:editar_usuario", kwargs={"pk": liniero.pk}),
            data=_editar_post_data(liniero),
        )

        liniero.refresh_from_db()
        assert liniero.rol == "liniero"


# ---------------------------------------------------------------------------
# Requerimiento 2: carga masiva a 6 columnas
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCargaMasivaSeisColumnas:
    """CargaMasivaUsuariosCampoView reescrita: Nombre,Documento,Email,
    Cargo,Rol,Estado (antes: Nombre,Documento,Cargo,Telefono)."""

    def test_crea_usuario_con_rol_explicito_y_email_real(self, client, user_password):
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        archivo = _make_excel_upload([
            ["Carlos Ramirez", "1122334455", "carlos.ramirez@instelec.co",
             "LINIERO_I", "liniero", "Activo"],
        ])
        response = client.post(
            reverse("usuarios:campo_upload"), data={"archivo": archivo}
        )

        # CargaMasivaUsuariosCampoView.post() siempre re-renderiza la misma
        # pagina (TemplateView, no redirect) -- comportamiento preexistente,
        # no modificado por este fix.
        assert response.status_code == 200
        creado = Usuario.objects.get(documento="1122334455")
        assert creado.email == "carlos.ramirez@instelec.co"  # email REAL, no autogenerado
        assert creado.rol == "liniero"
        assert creado.is_active is True

    def test_email_vacio_usa_fallback_autogenerado(self, client, user_password):
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        archivo = _make_excel_upload([
            ["Marta Diaz", "2233445566", "", "AYUDANTE", "auxiliar", "Activo"],
        ])
        client.post(reverse("usuarios:campo_upload"), data={"archivo": archivo})

        creado = Usuario.objects.get(documento="2233445566")
        assert creado.email == "2233445566@campo.instelec.co"

    def test_rol_invalido_rechaza_la_fila_no_asume_default(self, client, user_password):
        """Antes: un rol no reconocido nunca se rechazaba -- se inferia por
        keyword de cargo con default silencioso 'liniero'. Ahora: rechazo
        explicito, la fila NO crea usuario."""
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        archivo = _make_excel_upload([
            ["Jorge Vega", "3344556677", "", "CONDUCTOR",
             "rol_que_no_existe", "Activo"],
        ])
        client.post(reverse("usuarios:campo_upload"), data={"archivo": archivo})

        assert not Usuario.objects.filter(documento="3344556677").exists()

    def test_estado_inactivo_desde_excel(self, client, user_password):
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        archivo = _make_excel_upload([
            ["Luis Torres", "4455667788", "", "LINIERO_II", "liniero", "Inactivo"],
        ])
        client.post(reverse("usuarios:campo_upload"), data={"archivo": archivo})

        creado = Usuario.objects.get(documento="4455667788")
        assert creado.is_active is False

    def test_update_de_persona_existente_ahora_actualiza_rol_e_is_active(
        self, client, user_password
    ):
        """El bug principal reportado por el cliente: 'si la persona ya
        existe... nunca el rol, y no permite inactivarla'. Reproducido
        contra un usuario YA EXISTENTE (creado directo, simulando un
        registro pre-existente en prod) antes de correr la carga masiva."""
        admin = AdminFactory()
        UsuarioFactory(
            documento="5566778899", rol="liniero", is_active=True,
            first_name="Existe", last_name="Ya",
        )
        client.login(username=admin.email, password=user_password)

        archivo = _make_excel_upload([
            ["Existe Ya", "5566778899", "", "SUPERVISOR", "supervisor", "Inactivo"],
        ])
        client.post(reverse("usuarios:campo_upload"), data={"archivo": archivo})

        existente = Usuario.objects.get(documento="5566778899")
        assert existente.rol == "supervisor", (
            "El branch de update sigue sin tocar 'rol' -- bug original no resuelto."
        )
        assert existente.is_active is False, (
            "El branch de update sigue sin poder inactivar -- bug original no resuelto."
        )

    def test_formato_viejo_4_columnas_rechaza_fila_por_rol_faltante(
        self, client, user_password
    ):
        """Un archivo con el formato VIEJO (4 columnas: Nombre, Documento,
        Cargo, Telefono) ahora desplaza columnas (C='Cargo' leido como
        Email, D='Telefono' leido como Cargo) y no trae columna Rol (E) --
        la fila se rechaza por 'Rol es obligatoria' en vez de crear un
        usuario con datos corridos silenciosamente."""
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Nombre", "Documento", "Cargo", "Telefono"])
        ws.append(["Formato Viejo", "6677889900", "LINIERO_I", "3001112233"])
        buf = io.BytesIO()
        wb.save(buf)
        archivo = SimpleUploadedFile(
            "viejo.xlsx",
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        client.post(reverse("usuarios:campo_upload"), data={"archivo": archivo})

        assert not Usuario.objects.filter(documento="6677889900").exists()
