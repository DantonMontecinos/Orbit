# Orbit — Network Observability Platform

Plataforma simple de observabilidad de infraestructura de red en tiempo real para **MikroTik RouterOS**, **Access Points Ubiquiti** y dispositivos de red.

Arquitectura simple y ligera: **Python + FastAPI + SQLite + Bootstrap + Chart.js**.

---

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)

---

## Instalación rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/orbit.git
cd orbit

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales de tu router y APs

# 3. Levantar el servicio
docker compose up -d --build
```

Orbit estará disponible en **http://localhost:8000**

---

## Secciones principales

- **📊 Dashboard**: Estado general del router MikroTik, consumo de ancho de banda WAN (24h/7d), uso de CPU/RAM, usuarios unificados (LAN, VPN, VMs, Queues) y alertas activas.
- **📶 WiFi**: Monitoreo de SSIDs agregados a través de todos los Access Points, gráfico histórico de clientes por hora y estado de cada AP Ubiquiti (vía SSH read-only).
- **🌍 Topología**: Representación visual de la infraestructura (Internet → MikroTik → APs → Clientes) con estados en tiempo real.

---

## Configuración

Editar el archivo `.env`:

```env
# ── MikroTik RouterOS ──
ROUTER_HOST=192.168.1.1
ROUTER_PORT=8728
ROUTER_USER=readonly
ROUTER_PASSWORD=tu_password
ROUTER_WAN_INTERFACE=ether1

# ── Ubiquiti Access Points (SSH Read-Only) ──
UBNT_1_HOST=192.168.7.251
UBNT_1_USER=ubnt
UBNT_1_PASSWORD=tu_password_ssh
UBNT_1_NAME=DSC AP 1 RACK

UBNT_2_HOST=192.168.7.250
UBNT_2_USER=ubnt
UBNT_2_PASSWORD=tu_password_ssh
UBNT_2_NAME=DSC AP 2 INGRESO

UBNT_3_HOST=192.168.7.249
UBNT_3_USER=ubnt
UBNT_3_PASSWORD=tu_password_ssh
UBNT_3_NAME=DSC AP 3 DIRECTORIO
```

Ver `.env.example` para la lista completa de opciones.

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

## Persistencia de datos

| Dato | Volumen Docker | Ruta interna |
|---|---|---|
| Base SQLite | `orbit-data` | `/data/orbit.db` |
| Logs | `orbit-logs` | `/logs/orbit.log` |

Los volúmenes sobreviven a `docker compose down` y actualizaciones.

---

## Health Check

```
GET http://localhost:8000/health
→ {"status": "ok"}
```
