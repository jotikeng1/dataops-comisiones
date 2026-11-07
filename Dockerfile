# Imagen base de Python (igual que en clase)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 1) Dependencias primero: Docker reutiliza esta capa si requirements no cambia
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código de la aplicación y pruebas
COPY app/ .
COPY tests/ ./tests/
COPY data/ ./data/

# Por defecto ejecuta el pipeline; Jenkins sobrescribe el comando para pruebas/verificación
CMD ["python", "main.py"]
