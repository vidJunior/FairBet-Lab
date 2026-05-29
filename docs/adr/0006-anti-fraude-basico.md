# ADR 0006: Sistema de Alertas Anti-fraude Básico

## Contexto
La plataforma requiere detectar patrones de comportamiento maliciosos o fraudulentos (como multicuenta, colusión en apuestas y lavado de fichas mediante depósitos/retiros rápidos) para cumplir con el espíritu normativo.

## Opciones Consideradas
* **Opción 1: Procesamiento Síncrono (En tiempo real en los endpoints):** Evaluar las reglas cada vez que un usuario apuesta o se registra. Esto añade demasiada latencia a las operaciones críticas del usuario.
* **Opción 2: Procesamiento Asíncrono en Segundo Plano (Celery + Signals):** Capturar los eventos mediante señales de Django y delegar el análisis pesado a tareas de Celery. Mantiene los endpoints principales rápidos.

## Decisión
Se elige la **Opción 2**. Las alertas se guardarán en un modelo `SuspiciousActivity`. Dado que los modelos de apuestas (`Bet`) y transacciones (`LedgerEntry`) de los compañeros están en desarrollo, se diseñará un servicio intermedio que pueda ser invocado por tareas periódicas o señales. 

## Umbrales para minimizar Falsos Positivos
* **Regla 1 (Multicuenta):** Se dispara si una misma IP registra más de $N=3$ cuentas en las últimas 24 horas.
* **Regla 2 (Apuestas en espejo):** Se dispara si un grupo de $\ge2$ usuarios realizan apuestas idénticas con diferencias menores a 5 minutos.
* **Regla 3 (Simulación de Cash-out):** Se dispara si un usuario ejecuta un cash-out en menos de 10 minutos tras un depósito, habiendo arriesgado menos del 20% del valor depositado.

## Fecha y Autor
* **Fecha:** 28 Mayo 2026
* **Autor:** [Karen Segundo]