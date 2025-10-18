import os
import sys
import asyncio
import hashlib

# Hash helpers (argon2, crypt, md5, cleartext)
def hash_password(password):
    fmt = (os.getenv("FTP_PASSWORD_FORMAT", "md5") or "md5").lower()
    if fmt == "md5":
        return hashlib.md5(password.encode()).hexdigest()
    elif fmt == "cleartext":
        return password
    elif fmt == "argon2":
        from argon2 import PasswordHasher, Type
        argon_type = (os.getenv("FTP_ARGON2_TYPE", "id") or "id").lower()
        type_map = {"i": Type.I, "id": Type.ID, "d": Type.D}
        ph_type = type_map.get(argon_type, Type.ID)
        time_cost = int(os.getenv("FTP_ARGON2_TIME_COST", 2))
        memory_cost = int(os.getenv("FTP_ARGON2_MEMORY_COST", 102400))
        parallelism = int(os.getenv("FTP_ARGON2_PARALLELISM", 8))
        ph = PasswordHasher(time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism, type=ph_type)
        return ph.hash(password)
    elif fmt == "crypt":
        from passlib.hash import sha512_crypt, sha256_crypt, md5_crypt, des_crypt
        scheme = (os.getenv("FTP_CRYPT_SCHEME", "sha512_crypt") or "sha512_crypt").lower()
        if scheme == "sha512_crypt":
            return sha512_crypt.hash(password)
        elif scheme == "sha256_crypt":
            return sha256_crypt.hash(password)
        elif scheme == "md5_crypt":
            return md5_crypt.hash(password)
        elif scheme == "des_crypt":
            return des_crypt.hash(password)
        else:
            raise Exception(f"FTP_CRYPT_SCHEME desconocido: {scheme}")
    else:
        raise Exception(f"FTP_PASSWORD_FORMAT desconocido: {fmt}")

async def crear_usuario(user, password, homedir):
    import aiomysql
    host = os.getenv("FTP_DB_HOST", "localhost")
    port = int(os.getenv("FTP_DB_PORT", 3306))
    dbuser = os.getenv("FTP_DB_USER", "ftpduser")
    dbpass = os.getenv("FTP_DB_PASS", "secret")
    dbname = os.getenv("FTP_DB_NAME", "ftpdb")
    uid = int(os.getenv("FTP_UID", 2001))
    gid = int(os.getenv("FTP_GID", 2001))
    hashed = hash_password(password)
    print(f"Insertando usuario: {user}\nPassword (hash): {hashed}\nHomedir: {homedir}\nUID: {uid} GID: {gid}")
    pool = await aiomysql.create_pool(host=host, port=port, user=dbuser, password=dbpass, db=dbname, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "INSERT INTO users (User, Password, Uid, Gid, Dir, Status) VALUES (%s, %s, %s, %s, %s, %s)"
            try:
                await cur.execute(query, (user, hashed, uid, gid, homedir, '1'))
                print("Usuario insertado correctamente.")
            except Exception as e:
                print(f"ERROR: {e}")
    pool.close()
    await pool.wait_closed()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: crear_usuario_ftp.py <usuario> <password_en_claro> <homedir>")
        sys.exit(1)
    user, password, homedir = sys.argv[1:4]
    asyncio.run(crear_usuario(user, password, homedir))
