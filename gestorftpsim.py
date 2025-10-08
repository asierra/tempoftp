import os
import random
import time
from cifrado import cifrar
from gestorftpbase import GestorFTPBase
from tmpftpdb import TMPFTPdb

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
        username = self.generate_username(email)
        password = self.generate_password()
        password_cifrada = cifrar(password)
        info = {
            "usuario": username,            
            "password_cifrada": password_cifrada, # Guardamos la contraseña cifrada para uso interno
            "ruta": ruta,
            "vigencia": vigencia
        }
        self.db.crear_solicitud(id, email, ruta, "recibido", {**info, "mensaje": "Solicitud en cola."})
        # Simulación de proceso
        self.db.actualizar_estado(id, "preparando", info)
        print(f"SIMULACRO: Verificando espacio para copiar desde {ruta}")
        espacio_suficiente = random.choice([True, True, False])
        if not espacio_suficiente:
            error_msg = "Espacio insuficiente"
            self.db.actualizar_estado(id, "error", {**info, "mensaje": error_msg})
            raise Exception(error_msg)
        self.db.actualizar_estado(id, "traslado", {**info, "mensaje": f"Copiando datos desde {ruta} a destino."})
        print(f"SIMULACRO: Ejecutando rsync -av {ruta} destino")
        time.sleep(2)
        print("SIMULACRO: Copia finalizada.")        
        # Preparamos la información final para el cliente
        info_final = info.copy()
        info_final["password"] = password_cifrada # Enviamos la contraseña cifrada, como en el gestor real
        info_final["mensaje"] = f"Listo, tiene {vigencia} días para hacer la descarga."
        del info_final["password_cifrada"] # No es necesario enviarla al cliente
        self.db.actualizar_estado(id, "listo", info_final)
        print(f"SIMULACRO: Programando cron para eliminar al usuario {username} y la carpeta en {vigencia} días.")
        # Simulación de cron
        return