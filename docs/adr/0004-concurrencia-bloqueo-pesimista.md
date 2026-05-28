# ADR 0004: Control de Concurrencia al Apostar

## Contexto
Si un usuario con poco saldo manda dos clicks seguidos al mismo tiempo para apostar, el sistema podría validar ambas peticiones a la vez antes de restar la plata, dejando su saldo en negativo.

## Opciones Consideradas

### Opción 1: Bloqueo optimista
Asumir que no van a chocar y controlar versiones en la base de datos.
* **Pros**: Es muy rápido y ligero para el servidor.
* **Contras**: Si dos peticiones chocan, el sistema cancela una y le saca un error feo al usuario diciéndole que reintente, lo cual es molesto.

### Opción 2: Bloqueo pesimista (`select_for_update`)
Bloquear la fila del perfil y el saldo del usuario en la base de datos mientras se procesa la apuesta.
* **Pros**: Seguridad total. Nadie puede gastar dinero que no tiene porque las peticiones se procesan en fila estricta.
* **Contras**: El servidor espera unos milisegundos más mientras la fila está bloqueada.

## Decisión
Elegimos la **Opción 2** porque con el saldo y la plata virtual no se puede jugar; la exactitud del saldo es prioridad número uno frente a la velocidad.

## Consecuencias
* **Fácil**: Es imposible que un usuario duplique una apuesta o se quede con saldo negativo.
* **Difícil**: Hay que tener cuidado con el orden de los bloqueos dentro del código para evitar que la base de datos se trabe (deadlocks).

**Fecha**: 2026-05-27  
**Autor**: Jose Manuel Carrasco Millan
