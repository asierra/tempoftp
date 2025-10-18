import os
import sys
from cryptography.fernet import Fernet

key = os.environ['TEMPOFTP_ENCRYPTION_KEY'].encode()
cipher = Fernet(key)
token = sys.argv[1]
#token = b'gAAAAABo8uCjbB8Pvc5v5TZuM1rcai4a2TUsUHdWmurOW88KQ3Hr2vA7czBlQzlbeGzec2uqa5E423Ng3bjFit5j_qAYJPPsQg=='  # pega aquí el password cifrado
print(cipher.decrypt(token).decode())