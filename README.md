Sistema de Recibos y Pagos — Backend (Django + DRF + MySQL)

API del sistema de Recibos y Pagos.
Stack: Django 5 · Django REST Framework · SimpleJWT · MySQL · Gunicorn · WhiteNoise · Docker · Railway.

Endpoints de salud y auth

GET /health/ → {"ok": true} (para comprobar despliegue)

POST /api/token/ → { "access": "...", "refresh": "..." }

POST /api/token/refresh/ → { "access": "..." }

.
├─ recibos/                  # app de negocio
├─ transferencias/
├─ usuarios_log/
├─ sist_rec_api/             # proyecto Django (settings, urls, wsgi/asgi)
├─ manage.py
├─ requirements.txt
├─ Dockerfile
├─ entrypoint.sh             # migra + collectstatic + arranca gunicorn
├─ .gitignore
└─ .env.example              # variables de entorno (placeholders)

Requisitos

Python 3.11+

MySQL 8 (o compatible)

(Opcional) Docker Desktop

Variables de entorno

Crea un .env (no lo subas) a partir de .env.example.
Variables utilizadas por settings.py:
# Django
DJANGO_SECRET_KEY=tu_clave_super_secreta
DJANGO_DEBUG=1            # 0 en producción
ALLOWED_HOSTS=localhost,127.0.0.1

# BD MySQL
DB_HOST=localhost
DB_PORT=3306
DB_NAME=tu_base
DB_USER=tu_usuario
DB_PASSWORD=tu_password

# CORS (origins del FRONT)
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:4173

Desarrollo local
# 1 Crear venv
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 2 Instalar
pip install -r requirements.txt

# 3 Configurar .env (ver sección anterior) y crear la BD vacía en MySQL

# 4 Migraciones + superusuario
python manage.py migrate
python manage.py createsuperuser

# 5 Correr
python manage.py runserver 8000
# http://127.0.0.1:8000/health/