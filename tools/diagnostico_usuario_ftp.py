import os
import sys
import asyncio

async def diagnostico_usuario(user):
    import aiomysql
    host = os.getenv("FTP_DB_HOST", "localhost")
    port = int(os.getenv("FTP_DB_PORT", 3306))
    dbuser = os.getenv("FTP_DB_USER", "ftpduser")
    dbpass = os.getenv("FTP_DB_PASS", "secret")
    dbname = os.getenv("FTP_DB_NAME", "ftpdb")
    pool = await aiomysql.create_pool(host=host, port=port, user=dbuser, password=dbpass, db=dbname, autocommit=True)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "SELECT User, Password, LENGTH(Password), LEFT(Password,10), Uid, Gid, Dir, Status FROM users WHERE User=%s"
            await cur.execute(query, (user,))
            row = await cur.fetchone()
            if row:
                print(f"User: {row[0]}")
                print(f"Password: {row[1]}")
                print(f"Password prefix: {row[3]}")
                print(f"Password length: {row[2]}")
                print(f"Uid: {row[4]}")
                print(f"Gid: {row[5]}")
                print(f"Dir: {row[6]}")
                print(f"Status: {row[7]}")
            else:
                print(f"No se encontró el usuario {user}")
    pool.close()
    await pool.wait_closed()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: diagnostico_usuario_ftp.py <usuario>")
        sys.exit(1)
    user = sys.argv[1]
    asyncio.run(diagnostico_usuario(user))
