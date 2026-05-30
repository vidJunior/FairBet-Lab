# ADR 0005: Controles de Juego Responsable

## Contexto

Debemos implementar controles obligatorios para promover un juego responsable (límites de depósito y autoexclusión), cumpliendo el propósito educativo de la plataforma sobre las normativas, a pesar de que solo usemos fichas virtuales.

## Opciones Consideradas

### Opción 1: Controles manuales por soporte

Dejar que los usuarios envíen un mensaje a soporte para que los administradores apliquen los límites o suspendan las cuentas.

* **Pros**: Requiere menos código y menos lógica del lado del usuario.
* **Contras**: Mala experiencia, propenso a errores humanos y no cumple con el requerimiento de que el usuario lo gestione instantáneamente.

### Opción 2: Límites y autoexclusión automáticos gestionados por el usuario

Crear vistas donde el usuario pueda bajar sus límites de depósito (diario, semanal, mensual) de forma instantánea, o subirlos esperando un cooldown de 24h. Además, poder autoexcluirse por 7, 30, 90 días o de forma indefinida de manera irreversible.

* **Pros**: Cumplimiento absoluto de los requisitos de juego responsable. Le da control total, automático y seguro al jugador.
* **Contras**: Mucha lógica de validación extra cada vez que el usuario intenta recargar o apostar.

## Decisión

Elegimos la **Opción 2** porque es un requisito obligatorio en la guía y es la forma más realista de proteger al jugador frente a conductas compulsivas en una simulación de apuestas.

## Consecuencias

* **Fácil**: Cumplimos con creces las normativas de simulación de juego seguro y auditoría.
* **Difícil**: Hay que interceptar cada transacción de recarga o apuesta en el código para validar los límites de tiempo, montos y estados de exclusión.

**Fecha**: 2026-05-30  
**Autor**: Vidarte Cruz Jose Junior
