"""
P0-1: cleanup_expired.py reemplaza al loop en proceso (_cleanup_loop, retirado
de main.py) que duplicaba la limpieza una vez por cada worker de uvicorn.
Estos tests verifican el script standalone en aislamiento (sin MySQL/SQLite
reales): que invoca select_gestor().eliminar_expiradas() y traduce el
resultado en el código de salida correcto.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import cleanup_expired


def test_run_invoca_eliminar_expiradas_y_loguea_conteo(caplog):
    fake_gestor = AsyncMock()
    fake_gestor.eliminar_expiradas.return_value = 3

    with patch("gestorftpbase.select_gestor", return_value=fake_gestor):
        with caplog.at_level("INFO"):
            asyncio.run(cleanup_expired._run())

    fake_gestor.eliminar_expiradas.assert_awaited_once()
    assert "Cleanup FTP: 3 solicitudes expiradas procesadas" in caplog.text


def test_main_retorna_0_en_exito():
    fake_gestor = AsyncMock()
    fake_gestor.eliminar_expiradas.return_value = 0

    with patch("gestorftpbase.select_gestor", return_value=fake_gestor):
        assert cleanup_expired.main() == 0


def test_main_retorna_1_si_eliminar_expiradas_falla():
    with patch("gestorftpbase.select_gestor", side_effect=RuntimeError("boom")):
        assert cleanup_expired.main() == 1
