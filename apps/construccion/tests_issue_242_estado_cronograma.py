"""Contrato de estados del cronograma para Instelec#242 (A2)."""

from unittest.mock import PropertyMock, patch

import pytest

from apps.construccion.models import ProgramacionFase


@pytest.mark.django_db
class TestEstadoCronograma242:
    """La regla se prueba aislada de cada fuente rectora de avance (A1)."""

    @pytest.mark.parametrize(
        ('esperado', 'real'),
        [
            (50, 50),  # igualdad: no debe caer en retrasado
            (0, 0),  # 0% capturado sigue siendo un dato válido y a tiempo
            (40, 75),  # sobrecumplir sigue usando la etiqueta publicada
        ],
    )
    def test_real_igual_o_superior_al_esperado_es_a_tiempo(self, esperado, real):
        fase = ProgramacionFase()
        with patch.object(
            ProgramacionFase, 'pct_avance_esperado_hoy',
            new_callable=PropertyMock, return_value=esperado,
        ), patch.object(
            ProgramacionFase, 'pct_avance_real',
            new_callable=PropertyMock, return_value=real,
        ):
            assert fase.estado == 'ON_TIME'

    def test_real_menor_al_esperado_es_retrasado(self):
        fase = ProgramacionFase()
        with patch.object(
            ProgramacionFase, 'pct_avance_esperado_hoy',
            new_callable=PropertyMock, return_value=30,
        ), patch.object(
            ProgramacionFase, 'pct_avance_real',
            new_callable=PropertyMock, return_value=0,
        ):
            assert fase.estado == 'RETRASADO'

    @pytest.mark.parametrize(('esperado', 'real'), [(None, 0), (0, None)])
    def test_falta_de_dato_permanece_inequivocamente_sin_data(self, esperado, real):
        fase = ProgramacionFase()
        with patch.object(
            ProgramacionFase, 'pct_avance_esperado_hoy',
            new_callable=PropertyMock, return_value=esperado,
        ), patch.object(
            ProgramacionFase, 'pct_avance_real',
            new_callable=PropertyMock, return_value=real,
        ):
            assert fase.estado == 'SIN_DATA'
