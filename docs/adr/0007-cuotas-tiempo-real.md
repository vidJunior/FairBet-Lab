# ADR 0007: Cuotas en tiempo real y Política de Re-cotización

## Contexto
La plataforma requiere actualizar dinámicamente las cuotas (odds) y marcadores en la pantalla del usuario en tiempo real. Además, si las cuotas cambian mientras el usuario tiene abierto su cupón de apuestas y se dispone a apostar, se debe exigir una reconfirmación explícita (política de re-cotización) para proteger tanto a la casa de apuestas como al jugador.

## Opciones consideradas
* **Opción 1: Short Polling (HTTP Polling)**
  * *Pros:* Fácil de implementar mediante peticiones AJAX periódicas cada 2 o 3 segundos.
  * *Contras:* Elevado consumo de recursos de red y servidor al realizar peticiones continuas de usuarios inactivos; latencia visible de los datos en tiempo real.
* **Opción 2: WebSockets (Django Channels) + Validación de Backend**
  * *Pros:* Comunicación bidireccional en tiempo real y de baja latencia mediante el protocolo WS.
  * *Contras:* Requiere de infraestructura adicional como Redis (Channel Layer) y servidores ASGI (como Daphne) corriendo en producción.

## Decisión
Se eligió la **Opción 2 (Django Channels)**. Para implementar la política de re-cotización de manera segura:
1. Las actualizaciones de cuotas se transmiten a los clientes vía WebSocket.
2. Al intentar colocar la apuesta, el cliente envía las cuotas que visualizó.
3. El backend valida si estas coinciden con las de la base de datos actual. Si han cambiado, el backend cancela la operación y devuelve un error indicando la nueva cuota para forzar la reconfirmación por parte del usuario.

## Consecuencias
* *Más fácil:* Mantener la interfaz viva en tiempo real con mínima sobrecarga de red y garantizar la consistencia financiera en el momento de crear la apuesta.
* *Más difícil:* Configurar y mantener el servidor ASGI y el Channel Layer en entornos de producción.
* *Deudas técnicas:* Ninguna.

## Fecha y Autor
* **Fecha:** 2026-05-29
* **Autor:** Silupu Becerra Nilson Jesus
