import mariadb
import sys
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# --- CONFIGURACIÓN ---
DB_CONFIG = {
    "host": "localhost",
    "user": "ftpuser",
    "password": "Fiakue3Shahm",
    "database": "ftpdb",
    "unix_socket": "/var/lib/mysql/mysql.sock"
}

ph = PasswordHasher()

def get_connection():
    """Establece conexión con la base de datos MariaDB."""
    try:
        return mariadb.connect(**DB_CONFIG)
    except mariadb.Error as e:
        print(f"❌ Error de conexión: {e}")
        sys.exit(1)

def list_users():
    """Lista todos los usuarios registrados."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT User, Dir, status FROM users")
    
    print(f"\n{'USUARIO':<25} | {'DIRECTORIO':<30} | {'ESTADO'}")
    print("-" * 75)
    
    rows = cur.fetchall()
    if not rows:
        print("   (No hay usuarios registrados)")
    else:
        for (user, directory, status) in rows:
            st_text = "🟢 Activo" if status == 1 else "🔴 Inactivo"
            print(f"{user:<25} | {directory:<30} | {st_text}")
    
    print("-" * 75)
    conn.close()

def upsert_user(username, password, directory):
    """Crea un usuario o actualiza su password/directorio si ya existe."""
    hashed_password = ph.hash(password)
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
    INSERT INTO users (User, Password, Uid, Gid, Dir, status)
    VALUES (?, ?, 2001, 2001, ?, 1)
    ON DUPLICATE KEY UPDATE Password = ?, Dir = ?
    """
    try:
        cur.execute(query, (username, hashed_password, directory, hashed_password, directory))
        conn.commit()
        print(f"✅ Usuario '{username}' guardado/actualizado correctamente.")
    except mariadb.Error as e:
        print(f"❌ Error al guardar: {e}")
    finally:
        conn.close()

def verify_password(username, password_to_test):
    """Verifica si una contraseña coincide con el hash almacenado."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT Password FROM users WHERE User = ?", (username,))
    result = cur.fetchone()
    conn.close()

    if not result:
        print(f"⚠️ El usuario '{username}' no existe en la base de datos.")
        return

    hashed_password = result[0]
    try:
        ph.verify(hashed_password, password_to_test)
        print(f"✅ COINCIDE: La contraseña es correcta para '{username}'.")
    except VerifyMismatchError:
        print(f"❌ ERROR: La contraseña NO coincide para '{username}'.")
    except Exception as e:
        print(f"❌ Error técnico durante la verificación: {e}")

def delete_user(username):
    """Elimina un usuario permanentemente."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE User = ?", (username,))
        conn.commit()
        if cur.rowcount > 0:
            print(f"✅ Usuario '{username}' eliminado definitivamente.")
        else:
            print(f"⚠️ No se encontró al usuario '{username}'.")
    except mariadb.Error as e:
        print(f"❌ Error al eliminar: {e}")
    finally:
        conn.close()

def show_help():
    """Muestra el menú de ayuda."""
    print("\n" + "="*50)
    print("      SISTEMA DE GESTIÓN FTP (PURE-FTPD + MYSQL)")
    print("="*50)
    print("Comandos disponibles:")
    print("  python3 ftp_admin.py list")
    print("  python3 ftp_admin.py add <user> <pass> <dir>")
    print("  python3 ftp_admin.py check <user> <pass>")
    print("  python3 ftp_admin.py del <user>")
    print("="*50 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "list":
        list_users()
    elif cmd == "add" and len(sys.argv) == 5:
        upsert_user(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "check" and len(sys.argv) == 4:
        verify_password(sys.argv[2], sys.argv[3])
    elif cmd == "del" and len(sys.argv) == 3:
        delete_user(sys.argv[2])
    else:
        show_help()

