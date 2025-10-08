import pytest
from fastapi.testclient import TestClient
from main import app
import os

# Use an in-memory SQLite database for testing
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Creamos un cliente de prueba que interactuará con nuestra app
client = TestClient(app)

def test_get_status():
    """Prueba que el endpoint de estado base funciona correctamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "active"}

def test_get_health():
    """Prueba que el endpoint de salud devuelve la estructura esperada."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "space" in data
    assert "ftpd" in data
    assert "database" in data

def test_get_tmpftp_status_not_found():
    """Prueba que se devuelve un 404 para un ID que no existe."""
    response = client.get("/tmpftp/id_inexistente")
    assert response.status_code == 404
    assert response.json()["detail"] == "No encontrado"

def test_create_and_get_status_success(monkeypatch):
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
    assert data["status"] == "listo para descarga"
    assert "Usuario:" in data["mensaje"]

def test_create_fails_due_to_space(monkeypatch):
    """Prueba que la creación falla si no hay espacio suficiente."""
    # Forzamos a que la simulación de espacio siempre falle
    monkeypatch.setattr("random.choice", lambda _: False)

    request_data = {"usuario": "fail.user@example.com", "id": "proyecto_test_2", "ruta": "...", "vigencia": 1}
    response = client.post("/tmpftp", json=request_data)
    assert response.status_code == 400
    assert response.json()["detail"] == {'id': 'proyecto_test_2', 'status': 'error', 'mensaje':  'Espacio insuficiente'}