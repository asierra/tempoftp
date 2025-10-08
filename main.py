from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from gestorftpsim import GestorFTP
from gestorftpdb import GestorFTPDB
import os

app = FastAPI()
gestorftpdb = None

# Detecta si está en entorno de test
if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TEST_DB") == "1":
    gestorftpdb = GestorFTPDB(db_path=':memory:')
else:   
    gestorftpdb = GestorFTPDB() 
gestorftp = GestorFTP(gestorftpdb)

class TmpFTPRequest(BaseModel):
    usuario: str # <direccion email>
    id: str # <string>
    ruta: str # <IP:path>
    vigencia: int # <num dias>

@app.get("/")
async def get_status():
    # Consulta el estado actual del servicio
    return {"status": "active"}

@app.get("/health") # Corregido de /healt a /health
async def get_healt():
    # Consulta el estado del servicio y recursos
    return {"status": "ok", "space": "20TB", "ftpd": "up", "database": "ok"}

@app.post("/tmpftp")
async def create_tmpftp(req: TmpFTPRequest):
    # En un sistema real, esto podría ser una tarea en segundo plano.
    # Por ahora, la simulación es síncrona.
    try:
        # El gestor inicia el proceso y devuelve una confirmación inmediata.
        gestorftp.create_usertmp(req.id, req.usuario, req.ruta, req.vigencia)
        return {"id": req.id, "status": "recibido"}
    except Exception as e:
        # Captura errores iniciales, como espacio insuficiente.
        raise HTTPException(status_code=400, detail={"id": req.id, "status": "error", "mensaje": str(e)})

@app.get("/tmpftp/{id}")
async def get_tmpftp_status(id: str):
    # Consulta el estado de la solicitud por ID
    result = gestorftp.get_status(id)
    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail="No encontrado")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9043)          
