import os
import subprocess
import hashlib
import asyncio
import shutil
import logging
from typing import Optional, Tuple, Dict
import aiomysql
from cifrado import cifrar
from gestorftpbase import GestorFTPBase
from tmpftpdb import TMPFTPdb

logger = logging.getLogger(__name__)


class FTPDB_MySQL:
    """
    Gestor simple de conexión MySQL para Pure-FTPd con pool aiomysql.
    """
    def __init__(self) -> None:
        self.pool: Optional[aiomysql.Pool] = None
        self.conf: Optional[Dict[str, object]] = None

    async def connect(self) -> None:
        host = os.getenv("FTP_DB_HOST", "localhost")
        port = int(os.getenv("FTP_DB_PORT", 3306))
        user = os.getenv("FTP_DB_USER", "ftpduser")
        password = os.getenv("FTP_DB_PASS", "secret")
        dbname = os.getenv("FTP_DB_NAME", "ftpdb")
        self.conf = {"host": host, "port": port, "user": user, "db": dbname}
        if self.pool is None:
            self.pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                db=dbname,
                autocommit=True
            )

    async def close(self) -> None:
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None

    async def obtener_password_hash(self, user: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT Password FROM users WHERE User=%s", (user,))
                row = await cur.fetchone()
                return row[0] if row else None

    async def crear_usuario_ftp(self, user: str, password: str, homedir: str) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM users WHERE User=%s", (user,))
                existe = (await cur.fetchone())[0] > 0
                if existe:
                    return

                fmt = (os.getenv("FTP_PASSWORD_FORMAT", "md5") or "md5").lower()
                if fmt == "md5":
                    stored_password = hashlib.md5(password.encode()).hexdigest()
                elif fmt == "cleartext":
                    stored_password = password
                elif fmt == "crypt":
                    scheme = (os.getenv("FTP_CRYPT_SCHEME", "sha512_crypt") or "sha512_crypt").lower()
                    try:
                        from passlib.hash import sha512_crypt, sha256_crypt, md5_crypt, des_crypt
                        if scheme == "sha512_crypt":
                            stored_password = sha512_crypt.hash(password)
                        elif scheme == "sha256_crypt":
                            stored_password = sha256_crypt.hash(password)
                        elif scheme == "md5_crypt":
                            stored_password = md5_crypt.hash(password)
                        elif scheme == "des_crypt":
                            stored_password = des_crypt.hash(password)
                        else:
                            raise Exception(f"FTP_CRYPT_SCHEME desconocido: {scheme}")
                    except Exception as e:
                        raise Exception(
                            "No se pudo generar hash 'crypt'. Instale 'passlib' y configure FTP_CRYPT_SCHEME. Detalle: "
                            + str(e)
                        )
                else:
                    raise Exception(
                        f"FTP_PASSWORD_FORMAT desconocido: {fmt}. Use 'md5', 'cleartext' o 'crypt'."
                    )

                uid = int(os.getenv("FTP_UID", 2001))
                gid = int(os.getenv("FTP_GID", 2001))
                query = (
                    "INSERT INTO users (User, Password, Uid, Gid, Dir, Status) VALUES (%s, %s, %s, %s, %s, %s)"
                )
                try:
                    await cur.execute(query, (user, stored_password, uid, gid, homedir, '1'))
                except Exception as e:
                    conf = self.conf or {}
                    ctx = f"user={conf.get('user')} host={conf.get('host')} db={conf.get('db')} table=users"
                    msg = (
                        f"Error al insertar usuario FTP en MySQL ({ctx}). Detalle original: {e}. "
                        "Sugerencia: privilegios INSERT en ftpdb.users y que MYSQLCrypt coincide con FTP_PASSWORD_FORMAT."
                    )
                    raise Exception(msg)


class GestorFTP(GestorFTPBase):
    def __init__(self) -> None:
        # Base de datos de solicitudes (SQLite)
        if os.getenv("PYTEST_CURRENT_TEST"):
            self.db = TMPFTPdb(db_path=':memory:')
        else:
            self.db = TMPFTPdb()
        # Conector MySQL para usuarios FTP
        self.db_mysql = FTPDB_MySQL()

    def _validar_ruta_remota(self, ruta_remota: str) -> None:
        if not ruta_remota or ':' not in ruta_remota:
            raise Exception("Ruta remota inválida, use 'host:/ruta' o 'usuario@host:/ruta'")
        hostinfo, path = ruta_remota.split(':', 1)
        if not hostinfo:
            raise Exception("Ruta remota inválida: falta host antes de ':'")
        if not path or not path.startswith('/'):
            raise Exception("Ruta remota inválida: la ruta debe iniciar con '/'")
        if '@' in hostinfo:
            user_host = hostinfo.split('@', 1)
            if len(user_host) != 2 or not user_host[0] or not user_host[1]:
                raise Exception("Ruta remota inválida: formato de usuario@host incorrecto")

    def _parse_ruta_remota(self, ruta_remota: str) -> Tuple[str, Optional[str], str]:
        ssh_user = os.getenv("RSYNC_SSH_USER") or "lanotadm"
        host_ssh: Optional[str] = None
        ruta = ruta_remota
        if ':' in ruta_remota:
            hostinfo, path = ruta_remota.split(':', 1)
            if hostinfo == "":
                if '/' in path:
                    host_ssh, rest = path.split('/', 1)
                    ruta = '/' + rest
                else:
                    host_ssh = path
                    ruta = '/'
            elif '@' in hostinfo:
                _, host_ssh = hostinfo.split('@', 1)
                ruta = path if path.startswith('/') else '/' + path
            else:
                host_ssh = hostinfo
                ruta = path if path.startswith('/') else '/' + path
        return ssh_user, host_ssh, ruta

    def obtener_tamano_remoto(self, ruta_remota: str, usuario_ssh: Optional[str] = None, host_ssh: Optional[str] = None) -> int:
        ssh_user_env, host_detectado, ruta = self._parse_ruta_remota(ruta_remota)
        host_ssh = host_ssh or host_detectado
        ssh_user = usuario_ssh or ssh_user_env
        if not host_ssh:
            raise Exception("No se pudo determinar el host remoto para SSH")
        ssh_target = f"{ssh_user}@{host_ssh}"
        try:
            # du -sb <ruta> | awk '{print $1}'
            cmd = ["ssh", ssh_target, "du", "-sb", ruta]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            out = result.stdout.strip().splitlines()
            if not out:
                raise Exception("Salida vacía de du -sb")
            first = out[0].split()[0]
            size = int(first)
            logger.info("Tamaño remoto para %s en %s: %s bytes", ruta, ssh_target, size)
            return size
        except subprocess.CalledProcessError as e:
            msg = e.stderr.strip()
            logger.error("SSH/du falló para %s@%s:%s: %s", ssh_user, host_ssh, ruta, msg)
            raise Exception(f"SSH/du falló: {msg}")
        except Exception as e:
            logger.error("Error al obtener tamaño remoto %s@%s:%s: %s", ssh_user, host_ssh, ruta, e)
            raise Exception(f"Error al obtener tamaño remoto: {e}")

    def verificar_espacio_data(self, minimo_bytes: int = 1_000_000_000) -> bool:
        usage = shutil.disk_usage('/data')
        ok = usage.free >= minimo_bytes
        logger.info("Espacio libre en /data: %s bytes (mínimo requerido %s): %s", usage.free, minimo_bytes, ok)
        return ok

    def _preparar_directorio(self, usuario: str, id: str, ruta_remota: Optional[str] = None) -> str:
        homedir = f"/data/{usuario}"
        owner_user = os.getenv("DATA_OWNER_USER") or os.getenv("RSYNC_SSH_USER") or "lanotadm"
        owner_group = os.getenv("DATA_OWNER_GROUP") or owner_user
        skip_chown = os.getenv("SKIP_CHOWN", "0") in ("1", "true", "True")

        def _safe_chown(path: str) -> None:
            try:
                if not skip_chown:
                    subprocess.run(["chown", f"{owner_user}:{owner_group}", path], check=True)
            except Exception as e:
                logger.warning("chown falló para %s: %s. Continuando.", path, e)
            try:
                os.chmod(path, 0o755)
            except Exception as e:
                logger.warning("chmod falló para %s: %s", path, e)

        if not os.path.exists(homedir):
            os.makedirs(homedir, exist_ok=True)
            _safe_chown(homedir)

        solicitud_dir = os.path.join(homedir, id)
        os.makedirs(solicitud_dir, exist_ok=True)
        _safe_chown(solicitud_dir)
        return solicitud_dir

    def _ejecutar_rsync(self, ruta_origen: str, ruta_destino: str) -> None:
        try:
            comando_rsync = ["rsync", "-av", "--info=progress2", ruta_origen, ruta_destino]
            subprocess.run(
                comando_rsync,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
        except subprocess.CalledProcessError as e:
            logger.error("rsync falló: %s", e.stderr)
            raise Exception(f"Error durante la copia de datos (rsync): {e.stderr}")
        except FileNotFoundError:
            logger.error("El comando rsync no se encuentra en el sistema.")
            raise Exception("Error: El comando 'rsync' no se encuentra en el sistema.")

    async def create_usertmp(self, id: str, email: str, ruta: str, vigencia: int) -> Dict[str, object]:
        # Validaciones iniciales
        self._verificar_solicitud_duplicada(id)
        self._validar_ruta_remota(ruta)
        username = self.generate_username(email)

        # Obtener/crear password (sin exponer el claro en la respuesta final)
        await self.db_mysql.connect()
        hash_existente = await self.db_mysql.obtener_password_hash(username)
        if hash_existente:
            password_claro = None
            password_cifrada = cifrar(hash_existente)
            ya_existe = True
        else:
            password_claro = self.generate_password()
            password_cifrada = cifrar(password_claro)
            ya_existe = False

        info_inicial = {
            "usuario": username,
            "password": password_cifrada,
            "vigencia": vigencia
        }
        self.db.crear_solicitud(id, email, ruta, "recibido", {**info_inicial, "mensaje": "Solicitud en cola."})

        async def proceso_copia() -> None:
            try:
                self.db.actualizar_estado(id, "preparando", {**info_inicial, "mensaje": "Creando entorno y verificando espacio."})
                logger.info("Preparando entorno para %s (usuario=%s)", id, username)
                tamano_remoto = await asyncio.to_thread(self.obtener_tamano_remoto, ruta)
                if not self.verificar_espacio_data(tamano_remoto):
                    logger.error("Espacio insuficiente: requerido=%s bytes", tamano_remoto)
                    raise Exception(f"Espacio insuficiente en /data: se requieren {tamano_remoto} bytes")
                base_dir = await asyncio.to_thread(self._preparar_directorio, username, id, ruta)

                self.db.actualizar_estado(id, "traslado", {**info_inicial, "mensaje": f"Copiando datos desde {ruta} a {base_dir}."})
                logger.info("Iniciando rsync %s -> %s", ruta, base_dir)
                ssh_user_env, host_detectado, ruta_norm = self._parse_ruta_remota(ruta)
                origen = ruta if not host_detectado else f"{ssh_user_env}@{host_detectado}:{ruta_norm}"
                # Si el último segmento coincide con el ID, copiar el contenido (añadir /)
                last_segment = os.path.basename(ruta_norm.rstrip("/"))
                rsync_origen = f"{origen.rstrip('/')}" + "/" if last_segment == id else origen
                rsync_destino = base_dir
                await asyncio.to_thread(self._ejecutar_rsync, rsync_origen, rsync_destino)

                if not ya_existe and password_claro:
                    await self.db_mysql.crear_usuario_ftp(username, password_claro, f"/data/{username}")

                info_final = {
                    "usuario": username,
                    "password": password_cifrada,
                    "mensaje": f"Listo, tiene {vigencia} días para hacer la descarga.",
                    "vigencia": vigencia
                }
                self.db.actualizar_estado(id, "listo", info_final)
                logger.info("Solicitud %s lista para usuario %s", id, username)
            except Exception as e:
                logger.error("Fallo en proceso_copia (%s): %s", id, e)
                self.db.actualizar_estado(id, "error", {**info_inicial, "mensaje": str(e)})
            finally:
                await self.db_mysql.close()

        asyncio.create_task(proceso_copia())
        return {
            "usuario": username,
            "password": password_cifrada,
            "mensaje": "Solicitud en proceso. Recibirá notificación cuando esté lista.",
            "vigencia": vigencia
        }