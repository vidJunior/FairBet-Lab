# ADR 0003: Manejo de Estados de las Apuestas

## Contexto
Necesitamos controlar el ciclo de vida de cada apuesta colocada por el usuario para saber qué hacer con su plata en caso de que gane, pierda o si el partido se llega a suspender.

## Opciones Consideradas

### Opción 1: Booleanos simples
Usar campos True/False como `ganada` o `procesada`.
* **Pros**: Se programa rápido y fácil.
* **Contras**: Es problemático. Si el partido se anula o se suspende, un booleano no ayuda a manejar la devolución de fichas y desordena el historial.

### Opción 2: Estados fijos con choices
Usar estados claros:
* `accepted`: Fondos congelados en apuestas pendientes.
* `won`: Apuesta ganadora y pagada.
* `lost`: Apuesta perdedora, el dinero se lo queda la casa.
* `cancelled`: Partido anulado, se devuelve la plata al usuario.
* **Pros**: Muy ordenado. Evita errores como pagar una apuesta que ya había perdido.
* **Contras**: Obliga a meter más validaciones en el código.

## Decisión
Elegimos la **Opción 2** para evitar dolores de cabeza con el cuadre de caja y tener un control exacto de cada jugada.

## Consecuencias
* **Fácil**: Es súper fácil auditar qué pasó con cada apuesta y por qué se movió el dinero.
* **Difícil**: Hay que validar bien el estado del partido antes de cambiar el estado de la apuesta.

**Fecha**: 2026-05-27  
**Autor**: Jose Manuel Carrasco Millan
