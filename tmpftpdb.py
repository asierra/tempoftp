import sqlite3
import json
import os
from typing import Optional
from contextlib import contextmanager

class TMPFTPdb:
    @contextmanager
    def _get_conn(self):
        """Provee una conexión a la BD y se encarga de cerrarla."""
        conn = self._memory_conn if self._memory_conn else sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            if not self._memory_conn:
                conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes (
                    id TEXT PRIMARY KEY,
                    email TEXT,
                    ruta TEXT,
                    estado TEXT,
                    info_json TEXT
                )
            ''')
            conn.commit()
    def __init__(self, db_path: str = None):
        # Si se usa ':memory:', mantener la conexión viva para toda la instancia
        self._memory_conn = None
        if db_path is not None:
            self.db_path = db_path
        elif os.getenv("TEMPOFTP_SIMULACRO") == "1":
            self.db_path = "tempoftp_simulacro.db"
        else:
            self.db_path = "tempoftp.db"
        if self.db_path == ':memory:':
            self._memory_conn = sqlite3.connect(':memory:', check_same_thread=False)
        self._init_db()


    def crear_solicitud(self, id: str, email: str, ruta: str, estado: str, info: dict):
        with self._get_conn() as conn:
            info_json = json.dumps(info)
            # Cambiamos a INSERT para que falle si el ID ya existe,
            # permitiendo que la lógica de negocio maneje el error de duplicado.
            conn.execute(
                'INSERT INTO solicitudes (id, email, ruta, estado, info_json) VALUES (?, ?, ?, ?, ?)',
                (id, email, ruta, estado, info_json)
            )
            conn.commit()

    def actualizar_estado(self, id: str, estado: str, info: Optional[dict] = None):
        with self._get_conn() as conn:
            if info is not None:
                info_json = json.dumps(info)
                conn.execute('''
                    UPDATE solicitudes SET estado = ?, info_json = ? WHERE id = ?
                ''', (estado, info_json, id))
            else:
                conn.execute('''
                    UPDATE solicitudes SET estado = ? WHERE id = ?
                ''', (estado, id))
            conn.commit()

    def obtener_solicitud(self, id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, email, ruta, estado, info_json FROM solicitudes WHERE id = ?', (id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "email": row[1],
                    "ruta": row[2],
                    "estado": row[3],
                    "info": json.loads(row[4]) if row[4] else {}
                }
            return None

    def eliminar_solicitud(self, id: str):
        with self._get_conn() as conn:
            conn.execute('DELETE FROM solicitudes WHERE id = ?', (id,))
            conn.commit()