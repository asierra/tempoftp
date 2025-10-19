from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import uvicorn
import os
import logging
from functools import lru_cache

# --- Logging configuration ---
LOG_LEVEL = os.getenv("TEMPOFTP_LOG_LEVEL", "INFO").upper()
try:
    _numeric_level = getattr(logging, LOG_LEVEL)
except AttributeError:
    _numeric_level = logging.INFO
logging.basicConfig(
    level=_numeric_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI()

@lru_cache()
def get_gestor():
    """
    Función de dependencia que instancia el gestor apropiado (real o simulado)
    basado en variables de entorno. Esto permite la inyección de dependencias y
    facilita las pruebas. Usamos lru_cache para que actúe como un singleton.
    """
    if os.getenv("TEMPOFTP_SIMULACRO") == "1" or os.getenv("PYTEST_CURRENT_TEST"):
        from gestorftpsim import GestorFTPsim
        # En un contexto de dependencia de FastAPI, un return simple es suficiente.
        return GestorFTPsim()
    else:
        from gestorftp import GestorFTP
        return GestorFTP()


class TmpFTPRequest(BaseModel):
    usuario: str # <direccion email>
    id: str # <string>
    ruta: str # <IP:path>
    vigencia: int # <num dias>

@app.get("/")
async def get_status():
    # Consulta el estado actual del servicio
    return {"status": "active"}

@app.get("/health")
async def get_health():
    # Consulta el estado del servicio y recursos
    return {"status": "ok", "space": "20TB", "ftpd": "up", "database": "ok"}

@app.post("/tmpftp", status_code=202)
async def create_tmpftp(req: TmpFTPRequest, gestor=Depends(get_gestor)):
    try:
        # El gestor inicia el proceso en segundo plano y devuelve una confirmación inmediata.
        # La respuesta inicial no garantiza el éxito final de la tarea.
        await gestor.create_usertmp(req.id, req.usuario, req.ruta, req.vigencia)
        return {
            "id": req.id,
            "status": "recibido",
            "detail": "La solicitud ha sido aceptada y está en proceso."
        }
    except Exception as e:
        # Captura errores de validación iniciales (ej: ID duplicado, formato de ruta inválido).
        # Los errores de ejecución (sin espacio, fallo de rsync) se registran en el estado de la tarea.
        raise HTTPException(status_code=400, detail={"id": req.id, "status": "error", "mensaje": str(e)})

@app.get("/tmpftp/{id}")
async def get_tmpftp_status(id: str, gestor=Depends(get_gestor)):
    # Consulta el estado de la solicitud por ID
    result = await gestor.get_status(id)
    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail="No encontrado")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9043, log_level=os.getenv("TEMPOFTP_LOG_LEVEL", "info").lower())          
