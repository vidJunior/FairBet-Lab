# ADR 0008: Apuestas en vivo (in-play) y Suspensión Automática

## Contexto
El juego en vivo requiere cuotas altamente cambiantes y dinámicas. Durante incidentes críticos (como un gol o una tarjeta roja), se debe suspender temporalmente el mercado de apuestas durante un periodo de enfriamiento (cooldown) de N segundos. Esto evita que los usuarios tomen ventaja maliciosa realizando apuestas sobre eventos que ya sucedieron en la realidad pero no se han reflejado aún en la base de datos de manera definitiva.

## Opciones consideradas
* **Opción 1: Bloqueo Síncrono a Nivel de Hilo (Thread Sleep)**
  * *Pros:* Fácil de estructurar secuencialmente dentro del proceso principal.
  * *Contras:* Bloquea los hilos de ejecución del servidor web principal de Django, degradando la disponibilidad del sitio y su escalabilidad.
* **Opción 2: Orquestación Asíncrona (Celery + Banderas en Base de Datos)**
  * *Pros:* Permite suspender de inmediato el mercado colocando la bandera `activo=False` en la base de datos, notificando al frontend por WebSockets y planificando la reactivación mediante una tarea programada asíncrona en Celery (`reactivar_mercados_evento.delay`).
  * *Contras:* Introduce una dependencia directa del worker de Celery y el servicio de cola de mensajes (Redis).

## Decisión
Se eligió la **Opción 2 (Orquestación Asíncrona con Celery)**. Garantiza que la suspensión sea inmediata y reactiva sin penalizar la velocidad de respuesta del servidor web de Django.

## Consecuencias
* *Más fácil:* Evitar apuestas fraudulentas en momentos críticos del juego sin comprometer la estabilidad y el rendimiento del servidor web.
* *Más difícil:* Garantizar que los workers de Celery se mantengan activos para procesar la cola de reactivación tras el cooldown de 15 segundos.
* *Deudas técnicas:* Se asume la dependencia de la fiabilidad del despachador de tareas de Celery.

## Fecha y Autor
* **Fecha:** 2026-05-29
* **Autor:** Silupu Becerra Nilson Jesus
