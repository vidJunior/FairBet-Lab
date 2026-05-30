# ADR 0006: Apuestas combinadas (acumuladoras)

## Contexto
El reto FairBet Lab exige admitir apuestas combinadas (acumuladoras) formadas por múltiples selecciones de distintos eventos, donde la cuota final es el producto de las cuotas individuales de cada selección. El ciclo de vida de estas apuestas indica que si una sola selección falla, el ticket completo se pierde. Además, existe la restricción de validación antifraude: evitar la inclusión de selecciones mutuamente excluyentes del mismo partido (por ejemplo, combinar "gana local" y "gana visitante" en un mismo cupón).

## Opciones consideradas
* **Opción 1: Estructura Many-to-Many Directa en Apuesta**
  * *Pros:* Menos tablas en el esquema de base de datos; modelo de datos más simple.
  * *Contras:* Difícil para registrar y auditar la cuota exacta que se fijó para cada selección individual en el momento exacto de la apuesta, y para registrar el estado de resolución de cada selección individual (ganada/perdida/anulada).
* **Opción 2: Cabecera-Detalle (Modelos `Apuesta` y `DetalleApuesta`)**
  * *Pros:* Permite guardar las cuotas fijadas y el estado individual de resolución de cada selección; facilita la auditoría e integridad de la contabilidad; simplifica la validación de exclusión mutua comparando los IDs de mercado/evento antes de registrar la apuesta.
  * *Contras:* Aumenta ligeramente la complejidad del código y requiere más consultas de inserción.

## Decisión
Se eligió la **Opción 2 (Cabecera-Detalle)**. Esta estructura relacional está normalizada y permite una auditoría precisa de cada cuota fijada al momento de apostar. La validación de exclusión mutua se resuelve en el serializador de creación, verificando que no existan múltiples selecciones asociadas al mismo `mercado_id` o `evento_id`.

## Consecuencias
* *Más fácil:* Registrar el estado de liquidación de cada partido por separado, recalcular el retorno final si una selección se anula (cuota a 1.00) y validar la exclusión mutua en tiempo de creación.
* *Más difícil:* Requiere consultas JOIN para evaluar el estado final de las combinadas cuando finaliza un evento.
* *Deudas técnicas:* Ninguna deuda técnica crítica.

## Fecha y Autor
* **Fecha:** 2026-05-29
* **Autor:** Silupu Becerra Nilson Jesus
