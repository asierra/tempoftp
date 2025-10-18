import os
import sys
import asyncio
import hashlib

def hash_password(password):
    fmt = (os.getenv("FTP_PASSWORD_FORMAT", "md5") or "md5").lower()
    if fmt == "md5":
        return hashlib.md5(password.encode()).hexdigest()
    elif fmt == "cleartext":
        return password
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

async def actualizar_password(user, password):
    import aiomysql
    host = os.getenv("FTP_DB_HOST", "localhost")
    port = int(os.getenv("FTP_DB_PORT", 3306))
    dbuser = os.getenv("FTP_DB_USER", "ftpduser")
    dbpass = os.getenv("FTP_DB_PASS", "secret")
    dbname = os.getenv("FTP_DB_NAME", "ftpdb")
    hashed = hash_password(password)
    print(f"Actualizando usuario: {user}\nPassword (hash): {hashed}\nPrefix: {hashed[:10]}\nLength: {len(hashed)}")
    pool = await aiomysql.create_pool(host=host, port=port, user=dbuser, password=dbpass, db=dbname, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "UPDATE users SET Password=%s WHERE User=%s"
            try:
                await cur.execute(query, (hashed, user))
                print("Password actualizado correctamente.")
            except Exception as e:
                print(f"ERROR: {e}")
    pool.close()
    await pool.wait_closed()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: actualizar_password_ftp.py <usuario> <password_en_claro>")
        sys.exit(1)
    user, password = sys.argv[1:3]
    asyncio.run(actualizar_password(user, password))
