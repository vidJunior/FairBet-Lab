# ADR 0001: Registro y KYC Simulado

## Contexto

Necesitamos un proceso de registro y validación de usuarios (KYC simulado) para asegurar que la plataforma solo sea utilizada por mayores de edad y gestionar los distintos estados de la cuenta, según la guía.

## Opciones Consideradas

### Opción 1: Validaciones simples con un solo estado

Usar solo un flag booleano y confiar en que el usuario introduzca una fecha de nacimiento válida sin mayor comprobación del DNI.

* **Pros**: Se programa muy rápido.
* **Contras**: No cumple con la simulación realista de KYC, permite datos inválidos y carece de un ciclo de vida para el usuario (como bloqueos o exclusiones).

### Opción 2: Validación de DNI y estados de cuenta complejos

Validar que la edad sea mayor o igual a 18 años por la fecha de nacimiento, aplicar el algoritmo de dígito verificador para el DNI peruano, y usar estados de cuenta: `pendiente_verificacion`, `verificado`, `bloqueado`, `autoexcluido`.

* **Pros**: Cumple con todos los requerimientos de simulación de KYC y permite controlar estrictamente el acceso.
* **Contras**: Hay que programar más validaciones y mantener el algoritmo del DNI.

## Decisión

Elegimos la **Opción 2** para cumplir estrictamente con los requerimientos del reto y tener un control preciso de la edad y los estados de los usuarios.

## Consecuencias

* **Fácil**: Garantiza el cumplimiento regulatorio simulado y el control sobre quién puede apostar en la plataforma.
* **Difícil**: Hay que programar y mantener la lógica matemática del dígito verificador del DNI.

**Fecha**: 2026-05-30  
**Autor**: Vidarte Cruz Jose Junior
