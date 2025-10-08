from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from gestorftp import GestorFTP
import sqlite3

app = FastAPI()
gestorftp = GestorFTP()

class TmpFTPRequest(BaseModel):
    usuario: str
    id: str
    ruta: str
    vigencia: int

@app.get("/")
async def get_status():
    # Consulta el estado actual del servicio
    return {"status": "active"}

@app.get("/healt")
async def get_healt():
    # Consulta el estado del servicio y recursos
    return {"status": "ok", "space": "20TB", "ftpd": "up", "database": "ok"}

@app.post("/tmpftp")
async def create_tmpftp(req: TmpFTPRequest):
    try:
        result = gestorftp.create_usertmp(req.id, req.usuario, req.ruta, req.vigencia)
        return result
    except Exception as e:
        return {"id": req.id, "status": "error", "mensaje": str(e)}

@app.get("/tmpftp/{id}")
async def get_tmpftp_status(id: str):
    # Consulta el estado de la solicitud por ID
    result = gestorftp.get_status(id)
    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail="No encontrado")
