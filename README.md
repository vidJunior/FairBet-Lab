# ⚽ FairBet Lab

**Simulador de apuestas deportivas con moneda virtual**  
Plataforma educativa construida con Django 5.x + DRF, PostgreSQL, Redis, Celery y Django Channels.

> ⚠️ *Plataforma educativa con moneda virtual. No constituye una casa de apuestas.*

---

## Entregables — Producto

### 1. Repositorio Git con README, Docker Compose, seed de eventos y usuarios

| Elemento | Ubicación / Instrucción |
|---|---|
| **README** | Este archivo (`README.md`). |
| **Docker Compose** | [`docker-compose.yml`](docker-compose.yml) — define 5 servicios: `web` (Django + Daphne ASGI), `db` (PostgreSQL 15), `redis` (Redis 7), `celery` (tareas asíncronas + beat), `pgadmin` (gestor BD). |
| **Dockerfile** | [`dockerfile`](dockerfile) — imagen Python 3.12-slim con dependencias del proyecto. |
| **Seed de eventos** | Ejecutar: `docker compose exec web python manage.py seed_partidos`  
  Este comando crea 6 partidos programados con equipos reales y mercados 1X2, Doble Oportunidad, Más/Menos 2.5 y BTTS. |
| **Seed de usuarios** | Usuarios de prueba se crean desde el panel de admin o vía registro en la UI. También se puede crear manualmente con:  
  `docker compose exec web python manage.py createsuperuser` |

**Comandos rápidos para levantar el proyecto:**

```bash
# Iniciar todos los servicios
docker compose up -d

# Ejecutar migraciones
docker compose exec web python manage.py migrate

# Sembrar eventos deportivos
docker compose exec web python manage.py seed_partidos

# Abrir en el navegador
# http://localhost:8000/
```

---

### 2. Diagrama ER + Diagrama de la Máquina de Estados de Bet

#### a) Diagrama Entidad-Relación (ER)

El diagrama ER modela el núcleo del sistema de partida doble y el ciclo de vida de las apuestas.

**Entidades principales:**

| Entidad | Propósito |
|---|---|
| `User` | Usuario con estados KYC: `pendiente_verificacion`, `verificado`, `bloqueado`, `autoexcluido`. |
| `Equipo` | Equipos deportivos participantes. |
| `Evento` | Partido con estados: `programado`, `en_vivo`, `finalizado`, `suspendido`, `anulado`. |
| `Mercado` | Tipo de apuesta (1X2, Más/Menos 2.5, BTTS, etc.). |
| `Seleccion` | Opción dentro de un mercado (ej. "Local", "Empate", "Visitante"). |
| `Apuesta` (Bet) | Apuesta del usuario con estados: `accepted`, `won`, `lost`, `refunded`, `cashed_out`. |
| `ApuestaSeleccion` | Relación muchos-a-muchos entre apuestas y selecciones. |
| `LedgerEntry` | **Corazón financiero:** registros de partida doble con `account`, `amount`, `direction` (DEBIT/CREDIT), `transaction_id`. El saldo nunca se almacena; se calcula como `SUM(credits) - SUM(debits)`. |

#### b) Diagrama de Máquina de Estados de Bet

La máquina de estados describe el ciclo de vida completo de una apuesta.

**Flujo resumido:**

```
DRAFT → VALIDATION → ACCEPTED → { WON / LOST / REFUNDED / CASHED_OUT } → LIQUIDATED_*
```

- **DRAFT**: El usuario está armando su ticket (selecciones + monto).
- **VALIDATION**: El sistema valida saldo, edad, límites, exclusión y cuotas.
- **ACCEPTED**: Apuesta aceptada. Fondos bloqueados vía partida doble (`wallet_usuario` → `apuestas_pendientes`).
- **WON**: Selección ganadora. Pago = `stake × odds`.
- **LOST**: Selección perdedora. Fondos van a la cuenta `casa`.
- **REFUNDED**: Evento suspendido/anulado. Stake devuelto.
- **CASHED_OUT**: Usuario cerró anticipadamente. Cashout calculado y transferido.

---

### 3. Documentación OpenAPI

La API está documentada automaticamente con **drf-spectacular** (OpenAPI 3).

**Endpoints disponibles:**

| Recurso | URL | Descripción |
|---|---|---|
| Esquema OpenAPI | `http://localhost:8000/api/schema/` | Schema en formato YAML/JSON |
| Swagger UI | `http://localhost:8000/api/docs/` | Interfaz interactiva para probar endpoints |
| ReDoc | `http://localhost:8000/api/redoc/` | Documentación visual alternativa |

**Configuración:** El proyecto usa `drf_spectacular.openapi.AutoSchema` como clase de schema por defecto (definido en `config/settings.py`).

Para regenerar el schema:

```bash
docker compose exec web python manage.py spectacular --file schema.yml
```

---

### 4. Reporte de Cobertura

Las pruebas unitarias se ejecutan con **pytest** y se mide cobertura con **pytest-cov**.

**Ejecutar pruebas con reporte de cobertura:**

```bash
# Ejecutar todos los tests con cobertura
docker compose exec web pytest --cov=betting --cov=wallet --cov-report=term --cov-report=html

# El reporte HTML se genera en htmlcov/index.html
```

**Requerimiento del reto:** Cobertura mínima del **80%** en las apps `betting` y `wallet` (son las apps críticas del sistema).

**Pruebas incluidas:**

- Pruebas unitarias de servicios (creación de apuestas, liquidación, cash-out).
- Pruebas de concurrencia (simula N peticiones simultáneas para verificar que no haya doble gasto).
- Property-based testing con `hypothesis` para invariantes financieras:
  - La suma global de débitos y créditos siempre es cero.
  - Ningún wallet termina con saldo negativo.
  - El payout de una apuesta ganadora siempre es `stake × odds` con precisión exacta.

---

### 5.Documento Corto: Integridad Financiera, Juego Responsable y Cumplimiento Ley 31557

#### a) ¿Cómo garantiza el diseño la integridad financiera?

- **Partida doble:** Cada transacción genera al menos dos asientos contables (un débito y un crédito) que suman cero. El saldo nunca se almacena; siempre se calcula al vuelo con `SUM(credits) - SUM(debits)`.
- **Bloqueo pesimista:** Toda operación de wallet usa `select_for_update` de PostgreSQL para evitar condiciones de carrera.
- **Idempotencia:** Los endpoints de apuesta y movimiento de fondos usan `Idempotency-Key` para prevenir duplicados por errores de red.
- **Atomicidad:** Las transacciones financieras se ejecutan dentro de `transaction.atomic()`.
- **Precisión decimal:** Todos los montos usan `DecimalField(max_digits=18, decimal_places=4)`. Prohibido el uso de `float`.

#### b) ¿Qué decisiones de juego responsable se tomaron?

- **Límites de depósito configurables:** Diario, semanal y mensual. El usuario puede bajarlos instantáneamente; subirlos requiere un cooldown de 24 horas.
- **Autoexclusión:** Temporal (7, 30 o 90 días) o indefinida. Es irreversible hasta que expire el plazo.
- **Validación KYC:** Edad mínima de 18 años con verificación de DNI peruano (dígito verificador).
- **Estados de cuenta:** `pendiente_verificacion`, `verificado`, `bloqueado`, `autoexcluido`. Los usuarios no verificados o autoexcluidos no pueden apostar.
- **Mensaje obligatorio:** En todas las pantallas de apuesta se muestra: *"Plataforma educativa con moneda virtual. No constituye una casa de apuestas."*

#### c) Requisitos de la Ley 31557 cubiertos y no cubiertos (autocrítica honesta)

| Requisito de la Ley 31557 | Estado | Nota |
|---|---|---|
| Registro con identidad verificada (KYC) | ✅ Cubierto | Validación de DNI y mayoría de edad. |
| Controles de juego responsable | ✅ Cubierto | Límites de depósito, autoexclusión, mensajes de advertencia. |
| Integridad financiera y auditoría | ✅ Cubierto | Partida doble, ledger inmutable, hash chain de auditoría. |
| Reportes regulatorios (MINCETUR) | ✅ Cubierto | Dashboard del operador con GGR, exposición, reporte CSV exportable. |
| Prohibición de créditos | ✅ Cubierto | Solo se permite apostar con saldo disponible; no hay crédito. |
| Pasarela de pago real | ❌ No cubierto | Es un simulador educativo sin dinero real. |
| Geolocalización para restringir acceso | ❌ No cubierto | No implementado por ser educativo. |
| Certificación de proveedor tecnológico | ❌ No cubierto | No aplica para simulador. |
| Registro ante MINCETUR | ❌ No cubierto | Simulador educativo, no opera como casa de apuestas. |

> **Autocrítica:** Al ser una plataforma educativa con moneda virtual, aspectos como pasarela de pago real, geolocalización y certificación oficial no fueron implementados. Sin embargo, la lógica financiera, de auditoría y de juego responsable ha sido diseñada para reflejar fielmente los requisitos de una plataforma real.

---

### 6.Video Demo

---

## Stack Tecnológico

| Tecnología | Versión | Propósito |
|---|---|---|
| Python | 3.12 | Lenguaje principal |
| Django | 5.x | Framework web |
| Django REST Framework | — | API REST |
| PostgreSQL | 15 | Base de datos principal |
| Redis | 7 | Cache + Channels + Celery broker |
| Celery | — | Tareas asíncronas (liquidación, notificaciones) |
| Django Channels | — | WebSockets para cuotas en tiempo real |
| Daphne | — | Servidor ASGI para Channels |

---

## 📁 Estructura del Proyecto

```
FairBet-Lab/
├── accounts/          # Registro, autenticación, perfiles de usuario
├── api/               # Configuración de rutas de la API (router)
├── betting/           # Núcleo: eventos, mercados, selecciones, apuestas, servicios
├── config/            # Configuración de Django (settings, urls, asgi)
├── docs/              # Documentación del proyecto
│   ├── adr/           # Architectural Decision Records (mínimo 10)
│   └── sketches/      # Bocetos a mano (ER, máquina de estados, secuencias)
├── panel/             # Dashboard del operador (GGR, exposición, reportes)
├── templates/         # Plantillas HTML (UI del usuario)
├── wallet/            # Wallet con partida doble (LedgerEntry)
├── docker-compose.yml # Orquestación de contenedores
├── dockerfile         # Imagen Docker del proyecto
└── requirements.txt   # Dependencias de Python
```

---

## Testing

```bash
# Ejecutar todos los tests
docker compose exec web pytest

# Con cobertura
docker compose exec web pytest --cov=betting --cov=wallet --cov-report=term --cov-report=html

# Tests de una app específica
docker compose exec web pytest betting/tests.py
```

---
