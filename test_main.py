import pytest
from fastapi.testclient import TestClient
from main import app, gestorftp
from cifrado import descifrar, ENCRYPTION_KEY
import os

# Asegurarnos de que las pruebas usen la misma clave de cifrado
os.environ["TEMPOFTP_ENCRYPTION_KEY"] = ENCRYPTION_KEY

@pytest.fixture
def client():
    """Crea una instancia de TestClient para cada prueba, asegurando el aislamiento."""
    # Reinicia la base de datos del gestor antes de cada prueba para evitar fugas de estado.
    if hasattr(gestorftp, '_reiniciar_db_para_test'):
        gestorftp._reiniciar_db_para_test()
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
    assert "space" in data
    assert "ftpd" in data
    assert "database" in data

def test_get_tmpftp_status_not_found(client):
    """Prueba que se devuelve un 404 para un ID que no existe."""
    response = client.get("/tmpftp/id_inexistente")
    assert response.status_code == 404
    assert response.json()["detail"] == "No encontrado"

def test_create_and_get_status_success(client, monkeypatch):
    """Prueba el flujo completo: crear una solicitud y verificar su estado final."""
    # Forzamos a que la simulación de espacio siempre sea exitosa para esta prueba
    monkeypatch.setattr("random.choice", lambda _: True)

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
    assert "usuario" in data
    assert "password" in data
    assert descifrar(data["password"]) # Verificamos que se pueda descifrar

def test_create_fails_due_to_space(client, monkeypatch):
    """Prueba que la creación falla si no hay espacio suficiente."""
    # Forzamos a que la simulación de espacio siempre falle
    monkeypatch.setattr("random.choice", lambda _: False)

    request_data = {"usuario": "fail.user@example.com", "id": "proyecto_test_2", "ruta": "...", "vigencia": 1}
    response = client.post("/tmpftp", json=request_data)
    assert response.status_code == 400
    assert response.json()["detail"] == {'id': 'proyecto_test_2', 'status': 'error', 'mensaje':  'Espacio insuficiente'}

def test_create_duplicate_id_fails(client, monkeypatch):
    """Prueba que no se puede crear una solicitud con un ID duplicado."""
    monkeypatch.setattr("random.choice", lambda _: True)

    request_data = {
        "usuario": "duplicate.user@example.com",
        "id": "proyecto_duplicado",
        "ruta": "...",
        "vigencia": 1
    }

    # 1. Primera solicitud (debería ser exitosa)
    response1 = client.post("/tmpftp", json=request_data)
    assert response1.status_code == 200

    # 2. Segunda solicitud con el mismo ID (debería fallar)
    response2 = client.post("/tmpftp", json=request_data)
    assert response2.status_code == 400
    assert "Ya existe una solicitud en proceso con el ID 'proyecto_duplicado'" in response2.json()["detail"]["mensaje"]