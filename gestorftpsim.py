import os
import random
import time
import logging
from typing import Dict
from cifrado import cifrar
from gestorftpbase import GestorFTPBase
from tmpftpdb import TMPFTPdb

logger = logging.getLogger(__name__)

class GestorFTPsim(GestorFTPBase):
    def __init__(self):
        # El gestor simulado ahora controla su propia instancia de DB.
        # Usa una DB en memoria para tests o un archivo para simulación normal.
        if os.getenv("PYTEST_CURRENT_TEST"):
            self.db = TMPFTPdb(db_path=':memory:')
        else:
            self.db = TMPFTPdb(db_path='tempoftp_simulacro.db')

    async def create_usertmp(self, id, email, ruta, vigencia):
        # Verificar si la solicitud ya existe (lógica en la clase base)
        self._verificar_solicitud_duplicada(id)
        # Validación estricta de ruta remota (como en el real)
        if not ruta or ':' not in ruta:
            raise Exception("Ruta remota inválida, use 'host:/ruta' o 'usuario@host:/ruta'")
        hostinfo, path = ruta.split(':', 1)
        if not hostinfo:
            raise Exception("Ruta remota inválida: falta host antes de ':'")
        if not path or not path.startswith('/'):
            raise Exception("Ruta remota inválida: la ruta debe iniciar con '/'")
        if '@' in hostinfo:
            user_host = hostinfo.split('@', 1)
            if len(user_host) != 2 or not user_host[0] or not user_host[1]:
                raise Exception("Ruta remota inválida: formato de usuario@host incorrecto")
        username = self.generate_username(email)
        password = self.generate_password()
        password_cifrada = cifrar(password)
        # Simular la ruta destino igual que en el gestor real
        homedir = f"/data/{username}"
        destino = f"{homedir}/{id}"
        info = {
            "usuario": username,            
            "password_cifrada": password_cifrada, # Guardamos la contraseña cifrada para uso interno
            "ruta": ruta,
            "vigencia": vigencia,
            "destino": destino
        }
        self.db.crear_solicitud(id, email, ruta, "recibido", {**info, "mensaje": "Solicitud en cola."})
        # Simulación de proceso
        self.db.actualizar_estado(id, "preparando", info)
        logger.info("SIMULACRO: Verificando espacio para copiar desde %s", ruta)
        # Determinismo configurable por variables de entorno:
        # - TEMPOFTP_SIM_FORCE: 'ok'/'fail' para forzar resultado
        # - TEMPOFTP_SIM_REMOTE_SIZE_BYTES: tamaño simulado de origen (bytes)
        # - TEMPOFTP_SIM_DATA_FREE_BYTES: espacio libre simulado en /data (bytes)
        force = (os.getenv("TEMPOFTP_SIM_FORCE", "").strip().lower())
        if force in ("ok", "true", "1"):
            espacio_suficiente = True
        elif force in ("fail", "error", "0"):
            espacio_suficiente = False
        else:
            try:
                remote_size = int(os.getenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", "100000000"))  # 100 MB
                free_size = int(os.getenv("TEMPOFTP_SIM_DATA_FREE_BYTES", "1000000000"))    # 1 GB
            except ValueError:
                remote_size, free_size = 100_000_000, 1_000_000_000
            espacio_suficiente = remote_size <= free_size
            # Guardar pistas en info para debugging
            info["tamano_remoto_sim"] = remote_size
            info["espacio_libre_sim"] = free_size
        if not espacio_suficiente:
            error_msg = "Espacio insuficiente"
            self.db.actualizar_estado(id, "error", {**info, "mensaje": error_msg})
            raise Exception(error_msg)
        self.db.actualizar_estado(id, "traslado", {**info, "mensaje": f"Copiando datos desde {ruta} a {destino}."})
        logger.info("SIMULACRO: Ejecutando rsync -av %s %s", ruta, destino)
        time.sleep(2)
        logger.info("SIMULACRO: Copia finalizada.")        
        # Preparamos la información final para el cliente
        info_final = info.copy()
        info_final["password"] = password_cifrada # Enviamos la contraseña cifrada, como en el gestor real
        info_final["mensaje"] = f"Listo, tiene {vigencia} días para hacer la descarga."
        del info_final["password_cifrada"] # No es necesario enviarla al cliente
        self.db.actualizar_estado(id, "listo", info_final)
        logger.info("SIMULACRO: Programando cron para eliminar al usuario %s y la carpeta en %s días.", username, vigencia)
        # Simulación de cron
        return