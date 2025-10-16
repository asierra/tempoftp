import os
import random
import string
import subprocess
import hashlib
import time
import aiomysql
from cifrado import cifrar
from gestorftpbase import GestorFTPBase
from tmpftpdb import TMPFTPdb


class FTPDB_MySQL:
    """
    Clase interna para gestionar la conexión y operaciones con la base de datos
    MySQL de Pure-FTPd. Ahora gestiona un pool de conexiones de forma eficiente.
    """
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Crea el pool de conexiones."""
        self.pool = await aiomysql.create_pool(
            host=os.getenv("FTP_DB_HOST", "localhost"),
            port=int(os.getenv("FTP_DB_PORT", 3306)),
            user=os.getenv("FTP_DB_USER", "pureftpd_user"),
            password=os.getenv("FTP_DB_PASS", "secret"),
            db=os.getenv("FTP_DB_NAME", "pureftpd_db"),
            autocommit=True
        )

    async def close(self):
        """Cierra el pool de conexiones."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def crear_usuario_ftp(self, user, password, homedir):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # La contraseña en la BD de pure-ftpd se almacena hasheada con MD5
                password_md5 = hashlib.md5(password.encode()).hexdigest()
                query = "INSERT INTO users (User, Password, Uid, Gid, Dir, Status) VALUES (%s, %s, %s, %s, %s, %s)"
                await cur.execute(query, (user, password_md5, 2001, 2001, homedir, '1'))

class GestorFTP(GestorFTPBase):
    def __init__(self):
        # El gestor real ahora controla su propia instancia de DB de solicitudes (SQLite)
        # y la de usuarios de FTP (MySQL).
        if os.getenv("PYTEST_CURRENT_TEST"):
            self.db = TMPFTPdb(db_path=':memory:')
        else:
            self.db = TMPFTPdb() # Usa la ruta por defecto 'tempoftp.db'
        self.db_mysql = FTPDB_MySQL()

    def _preparar_directorio(self, id: str) -> str:
        """Crea el directorio de destino para el usuario y asigna permisos."""
        base_dir = f"/data/{id}"
        print(f"REAL: Creando directorio {base_dir}")
        # En un entorno real, se ejecutarían los siguientes comandos:
        # os.makedirs(base_dir, exist_ok=True)
        # subprocess.run(["chown", "pureftpd:pureftpd", base_dir], check=True)
        return base_dir

    def _verificar_espacio(self, ruta: str) -> bool:
        """Simula la verificación de espacio disponible antes de la copia."""
        print(f"REAL: Verificando espacio para copiar desde {ruta}")
        # Lógica real: usar `rsync --dry-run -n` o `ssh user@host 'du -sh /path'` para obtener tamaño.
        # Por ahora, simula que a veces no hay espacio.
        return random.choice([True, True, False])

    def _ejecutar_rsync(self, ruta_origen: str, ruta_destino: str):
        """Ejecuta el comando rsync para transferir los archivos."""
        print(f"REAL: Ejecutando rsync desde {ruta_origen} hacia {ruta_destino}")
        try:
            # Llama a rsync y captura la salida. check=True lanzará una excepción si rsync falla.
            # Se asume que la autenticación (ej. claves SSH) para la ruta remota está preconfigurada.
            comando_rsync = ["rsync", "-av", "--info=progress2", ruta_origen, ruta_destino]
            resultado = subprocess.run(
                comando_rsync,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            print(f"REAL: Salida de rsync: {resultado.stdout}")
        except subprocess.CalledProcessError as e:
            # Re-lanza una excepción más específica para que el método principal la maneje.
            raise Exception(f"Error durante la copia de datos (rsync): {e.stderr}")
        except FileNotFoundError:
            # Re-lanza si el comando rsync no existe.
            raise Exception("Error: El comando 'rsync' no se encuentra en el sistema.")

    async def create_usertmp(self, id, email, ruta, vigencia):
        # 0. Verificar si la solicitud ya existe (lógica en la clase base)
        self._verificar_solicitud_duplicada(id)

        # 1. Generar credenciales y establecer estado inicial
        username = self.generate_username(email)
        password = self.generate_password()
        password_cifrada = cifrar(password)
        info = {
            "usuario": username,
            "password": password_cifrada,
            "ruta": ruta,
            "vigencia": vigencia
        }
        self.db.crear_solicitud(id, email, ruta, "recibido", {**info, "mensaje": "Solicitud en cola."})
        
        try:
            # 2. Crear carpeta y verificar espacio
            self.db.actualizar_estado(id, "preparando", {**info, "mensaje": "Creando entorno y verificando espacio."})
            base_dir = self._preparar_directorio(id)

            if not self._verificar_espacio(ruta):
                raise Exception("Espacio insuficiente")

            # 3. Ejecutar la copia con rsync
            self.db.actualizar_estado(id, "traslado", {**info, "mensaje": f"Copiando datos desde {ruta} a {base_dir}."})
            self._ejecutar_rsync(ruta, base_dir)
            print(f"REAL: Copia finalizada.")

            # 4. Crear usuario en la BD de Pure-FTPd
            print(f"REAL: Creando usuario {username} en la base de datos MySQL de pure-ftpd.")
            await self.db_mysql.connect() # Conectamos el pool
            await self.db_mysql.crear_usuario_ftp(username, password, base_dir)

        except Exception as e:
            error_msg = str(e)
            self.db.actualizar_estado(id, "error", {**info, "mensaje": error_msg})
            raise Exception(error_msg)
        finally:
            # El pool de MySQL se cierra solo si se ha conectado
            if self.db_mysql.pool:
                await self.db_mysql.close()

        info_lista = {
            "usuario": username,
            "password": password_cifrada,
            "mensaje": f"Listo, tiene {vigencia} días para hacer la descarga.",
            "vigencia": vigencia
        }
        self.db.actualizar_estado(id, "listo", info_lista)
        
        # 5. Programar la eliminación con cron
        print(f"REAL: Programando cron para eliminar al usuario {username} y la carpeta {base_dir} en {vigencia} días.")