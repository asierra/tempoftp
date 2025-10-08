import sqlite3
import json
import os
from typing import Optional

class GestorFTPDB:
    def _get_conn(self):
        if self._memory_conn:
            return self._memory_conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS solicitudes (
                id TEXT PRIMARY KEY,
                email TEXT,
                ruta TEXT,
                estado TEXT,
                info_json TEXT
            )
        ''')
        conn.commit()
        if not self._memory_conn:
            conn.close()
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
        conn = self._get_conn()
        c = conn.cursor()
        info_json = json.dumps(info)
        c.execute('''
            INSERT OR REPLACE INTO solicitudes (id, email, ruta, estado, info_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (id, email, ruta, estado, info_json))
        conn.commit()
        if not self._memory_conn:
            conn.close()

    def actualizar_estado(self, id: str, estado: str, info: Optional[dict] = None):
        conn = self._get_conn()
        c = conn.cursor()
        if info is not None:
            info_json = json.dumps(info)
            c.execute('''
                UPDATE solicitudes SET estado = ?, info_json = ? WHERE id = ?
            ''', (estado, info_json, id))
        else:
            c.execute('''
                UPDATE solicitudes SET estado = ? WHERE id = ?
            ''', (estado, id))
        conn.commit()
        if not self._memory_conn:
            conn.close()

    def obtener_solicitud(self, id: str) -> Optional[dict]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute('SELECT id, email, ruta, estado, info_json FROM solicitudes WHERE id = ?', (id,))
        row = c.fetchone()
        if not self._memory_conn:
            conn.close()
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
        conn = self._get_conn()
        c = conn.cursor()
        c.execute('DELETE FROM solicitudes WHERE id = ?', (id,))
        conn.commit()
        if not self._memory_conn:
            conn.close()
