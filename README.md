# Orbit — MikroTik NOC Monitoring System

Sistema de monitoreo NOC (*Network Operations Center*) en tiempo real para routers **MikroTik RouterOS**.

Arquitectura simple: **Python + FastAPI + SQLite + Bootstrap + Chart.js**.

---

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/orbit.git
cd orbit

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales de tu router MikroTik

# 3. Levantar el servicio
docker compose up -d --build
```

Orbit estará disponible en **http://localhost:8000**

---

## Configuración

Editar el archivo `.env` con los datos de tu router:

```env
ROUTER_HOST=192.168.88.1
ROUTER_PORT=8728
ROUTER_USER=readonly
ROUTER_PASSWORD=tu_password
ROUTER_WAN_INTERFACE=ether1
```

Ver `.env.example` para todas las variables disponibles.

---

## Comandos útiles

| Acción | Comando |
|---|---|
| **Iniciar** | `docker compose up -d --build` |
| **Detener** | `docker compose down` |
| **Ver logs** | `docker compose logs -f orbit` |
| **Estado** | `docker compose ps` |
| **Reiniciar** | `docker compose restart orbit` |

---

## Actualización

```bash
git pull
docker compose up -d --build
```

La base de datos y los logs se conservan entre actualizaciones (volúmenes persistentes).

---

## Persistencia

| Dato | Volumen Docker | Ruta dentro del contenedor |
|---|---|---|
| Base SQLite | `orbit-data` | `/data/orbit.db` |
| Logs | `orbit-logs` | `/logs/orbit.log` |

Los volúmenes sobreviven a `docker compose down` y reconstrucciones de imagen.

Para eliminar todo incluyendo datos:
```bash
docker compose down -v
```

---

## Health Check

```
GET http://localhost:8000/health
→ {"status": "ok"}
```

Docker verifica automáticamente la salud del contenedor cada 30 segundos.

---

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Python 3.12 + FastAPI + Uvicorn |
| Base de datos | SQLite (WAL mode) |
| ORM | SQLAlchemy 2.0 |
| Scheduler | APScheduler |
| Frontend | HTML5 + Jinja2 + Vanilla CSS/JS |
| Gráficos | Chart.js |
| UI Framework | Bootstrap 5 |
| Integración | RouterOS API (solo lectura) |

---

## Seguridad

- **Garantía Read-Only**: Orbit únicamente consulta información del router. Nunca ejecuta operaciones de escritura.
- **Credenciales**: Todas las credenciales se gestionan mediante variables de entorno (`.env`). Nunca se versionan.

---

## Desarrollo local (sin Docker)

```bash
python -m venv venv
.\venv\Scripts\activate          # Windows
source venv/bin/activate         # Linux/Mac

pip install -r requirements.txt
cp .env.example .env
# Editar .env: DB_PATH=./data/noc.db y LOG_DIR=./logs

python run.py
```

## Pruebas unitarias

```bash
python -m unittest discover -s tests
```
