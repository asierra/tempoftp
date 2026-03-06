import os
os.environ["TEMPOFTP_SIMULACRO"] = "1"
os.environ["TEMPOFTP_RATE_LIMIT_POST"] = "1000/hour"  # sin restricción en tests
import asyncio
import pytest
from fastapi.testclient import TestClient
from main import app, get_gestor
from cifrado import descifrar, ENCRYPTION_KEY
from gestorftp import GestorFTP
from gestorftpsim import GestorFTPsim

# Asegurarnos de que las pruebas usen la misma clave de cifrado
os.environ["TEMPOFTP_ENCRYPTION_KEY"] = ENCRYPTION_KEY

@pytest.fixture
def client():
    """Crea una instancia de TestClient para cada prueba, asegurando el aislamiento."""
    # Reinicia la base de datos del gestor antes de cada prueba para evitar fugas de estado.
    # Limpiamos la cache para asegurar que cada test obtenga una instancia fresca del gestor.
    get_gestor.cache_clear()
    # Obtenemos la instancia que se usará en este entorno de test.
    gestor_actual = get_gestor()
    if hasattr(gestor_actual, '_reiniciar_db_para_test'):
        gestor_actual._reiniciar_db_para_test()
    with TestClient(app) as c:
        yield c

def test_get_status(client):
    """Prueba que el endpoint de estado base funciona correctamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "active"}

def test_get_health(client):
    """Prueba que el endpoint de salud devuelve la estructura esperada."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # El endpoint puede reportar espacio real o 'space_error' si /data no existe en este entorno
    has_disk_info = "space_free_gb" in data or "space_error" in data
    assert has_disk_info, f"Respuesta inesperada de /health: {data}"
    assert "ftpd" in data
    assert "database" in data

def test_get_tmpftp_status_not_found(client):
    """Prueba que se devuelve un 404 para un ID que no existe."""
    response = client.get("/tmpftp/id_inexistente")
    assert response.status_code == 404
    assert response.json()["detail"] == "No encontrado"

def test_create_and_get_status_success(client, monkeypatch):
    """Prueba el flujo completo: crear una solicitud y verificar su estado final."""
    # Forzar éxito determinista
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")

    request_data = {
        "usuario": "test.user@example.com",
        "id": "proyecto_test_1",
        "ruta": "10.0.0.1:/data/source",
        "vigencia": 5
    }

    # 1. Enviar la solicitud de creación
    post_response = client.post("/tmpftp", json=request_data)
    assert post_response.status_code == 200
    assert post_response.json()["id"] == "proyecto_test_1"

    # 2. Verificar el estado final (la simulación es síncrona)
    get_response = client.get("/tmpftp/proyecto_test_1")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["status"] == "listo"
    assert "ftpuser" in data
    assert "password" in data
    assert descifrar(data["password"]) # Verificamos que se pueda descifrar

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_create_fails_due_to_space(client, monkeypatch):
    """Prueba que la creación falla si no hay espacio suficiente."""
    # Forzar fallo determinista en simulador
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "fail")

    request_data = {"usuario": "fail.user@example.com", "id": "proyecto_test_2", "ruta": "10.0.0.1:/data/source", "vigencia": 1}
    response = client.post("/tmpftp", json=request_data)
    assert response.status_code == 400
    assert response.json()["detail"] == {'id': 'proyecto_test_2', 'status': 'error', 'mensaje':  'Espacio insuficiente'}

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_create_duplicate_id_fails(client, monkeypatch):
    """Prueba que no se puede crear una solicitud con un ID duplicado."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")

    request_data = {
        "usuario": "duplicate.user@example.com",
        "id": "proyecto_duplicado",
        "ruta": "10.0.0.1:/data/source",
        "vigencia": 1
    }

    # 1. Primera solicitud (debería ser exitosa)
    response1 = client.post("/tmpftp", json=request_data)
    assert response1.status_code == 200

    # 2. Segunda solicitud con el mismo ID (debería fallar)
    response2 = client.post("/tmpftp", json=request_data)
    assert response2.status_code == 400
    assert "Ya existe una solicitud en proceso con el ID 'proyecto_duplicado'" in response2.json()["detail"]["mensaje"]

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_force_ok(client, monkeypatch):
    """Forzar éxito con TEMPOFTP_SIM_FORCE=ok"""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    request_data = {"usuario": "force.ok@example.com", "id": "force_ok_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200
    st = client.get("/tmpftp/force_ok_1").json()
    assert st["status"] == "listo"
    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_force_fail(client, monkeypatch):
    """Forzar falla con TEMPOFTP_SIM_FORCE=fail"""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "fail")
    request_data = {"usuario": "force.fail@example.com", "id": "force_fail_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["status"] == "error"
    assert body["detail"]["mensaje"] == "Espacio insuficiente"
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_sizes_ok(client, monkeypatch):
    """Controlar por tamaños: remoto < libre => ok"""
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)
    monkeypatch.setenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", "1000")
    monkeypatch.setenv("TEMPOFTP_SIM_DATA_FREE_BYTES", "2000")
    request_data = {"usuario": "sizes.ok@example.com", "id": "sizes_ok_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200
    st = client.get("/tmpftp/sizes_ok_1").json()
    assert st["status"] == "listo"
    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", raising=False)
    monkeypatch.delenv("TEMPOFTP_SIM_DATA_FREE_BYTES", raising=False)


def test_sim_sizes_fail(client, monkeypatch):
    """Controlar por tamaños: remoto > libre => fail"""
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)
    monkeypatch.setenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", "2000000")
    monkeypatch.setenv("TEMPOFTP_SIM_DATA_FREE_BYTES", "1000000")
    request_data = {"usuario": "sizes.fail@example.com", "id": "sizes_fail_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["status"] == "error"
    assert body["detail"]["mensaje"] == "Espacio insuficiente"
    monkeypatch.delenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", raising=False)
    monkeypatch.delenv("TEMPOFTP_SIM_DATA_FREE_BYTES", raising=False)

def test_delete_request_lifecycle(client, monkeypatch):
    """Prueba el ciclo de vida: crear, verificar y eliminar una solicitud."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    
    req_id = "del_test_1"
    request_data = {
        "usuario": "del.user@example.com",
        "id": req_id,
        "ruta": "host:/data",
        "vigencia": 1
    }

    # 1. Crear
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200

    # 2. Verificar que existe
    r = client.get(f"/tmpftp/{req_id}")
    assert r.status_code == 200

    # 3. Eliminar
    r = client.delete(f"/tmpftp/{req_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    # 4. Verificar que ya no existe
    r = client.get(f"/tmpftp/{req_id}")
    assert r.status_code == 404

    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_delete_request_not_found(client):
    """Prueba borrar una solicitud inexistente."""
    r = client.delete("/tmpftp/id_no_existe_123")
    assert r.status_code == 404

def test_delete_user_success(client):
    """Prueba borrar un usuario FTP (simulado)."""
    # El simulador siempre devuelve éxito por defecto
    r = client.delete("/tmpftp/user/ftp_usuario_test")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

def test_delete_user_not_found(client, monkeypatch):
    """Prueba borrar un usuario inexistente (simulando respuesta not_found del gestor)."""
    
    # Monkeypatching el método en la clase para que devuelva not_found
    async def mock_delete_not_found(self, user):
        return {"status": "not_found", "mensaje": "Usuario no encontrado"}
    
    monkeypatch.setattr(GestorFTPsim, "delete_ftp_user", mock_delete_not_found)
    
    r = client.delete("/tmpftp/user/usuario_fantasma")
    assert r.status_code == 404
    assert r.json()["detail"] == "Usuario no encontrado"
