#!/usr/bin/env python3
"""
Purga solicitudes FTP temporales cuya vigencia venció (usuario MySQL + datos en
/data + registro SQLite). Reemplaza al antiguo loop en proceso (`_cleanup_loop`
en main.py): ese loop corría dentro del lifespan de FastAPI, una vez POR WORKER
de uvicorn, duplicando el trabajo de limpieza según el número de workers.

Pensado para dispararse como unidad `oneshot` desde un systemd timer
(deployment/tempoftp-cleanup.service + .timer), igual que historic_query hace
con `update_query_status`/`process_notifications` vía historic-update.timer:
exactamente una ejecución por ciclo, sin importar cuántos workers sirvan HTTP.

Uso:
    python cleanup_expired.py
"""
import asyncio
import logging
import sys

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tempoftp.cleanup")


async def _run() -> None:
    # Import diferido a después de load_dotenv(): GestorFTP/FTPDB_MySQL leen
    # las variables de entorno (FTP_DB_HOST, etc.) al construirse/conectarse.
    # select_gestor() respeta TEMPOFTP_SIMULACRO igual que main.py (get_gestor),
    # para que este script y la API apunten siempre al mismo backend. Nota: en
    # modo simulacro, GestorFTPsim no implementa eliminar_expiradas todavía
    # (gap conocido, ver AUDITORIA_2026-07.md) — fallará con AttributeError,
    # capturado por main() más abajo.
    from gestorftpbase import select_gestor

    gestor = select_gestor()
    deleted = await gestor.eliminar_expiradas()
    logger.info("Cleanup FTP: %d solicitudes expiradas procesadas", deleted)


def main() -> int:
    try:
        asyncio.run(_run())
        return 0
    except Exception:
        logger.exception("Error en cleanup de solicitudes FTP expiradas")
        return 1


if __name__ == "__main__":
    sys.exit(main())
