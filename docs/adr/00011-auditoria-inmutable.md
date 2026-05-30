# ADR 00011: Diseño de Auditoría Inmutable mediante Encadenamiento de Hashes

## Contexto
El sistema requiere un registro inmutable (append-only) para auditar cada apuesta, movimiento de wallet y cambio de cuotas, garantizando el cumplimiento normativo y la integridad frente a manipulaciones maliciosas.

## Opciones Consideradas
* **Opción 1: Triggers a nivel de Base de Datos (PostgreSQL):** Alta eficiencia, pero dificulta la portabilidad y el cálculo del hash secuencial con lógica de aplicación compleja.
* **Opción 2: Tabla Append-Only en Django + Señales (Signals):** Permite centralizar la lógica en Python, capturar los datos antes/después del guardado de forma desacoplada y estructurar los payloads en JSON de manera uniforme.

## Decisión
Se elige la **Opción 2**. Creamos un modelo centralizado `AuditLog` en la app `api` que no depende de relaciones directas (ForeignKeys), sino que almacena estados en un campo JSON. Cada registro se encadenará usando SHA256.

## Consecuencias
* **Ventajas:** Desacoplamiento total de los modelos de los compañeros. Facilidad para verificar la integridad recorriendo la tabla secuencialmente.
* **Desventajas:** Se debe asegurar que el parseo de JSON mantenga un orden estricto de llaves para evitar discrepancias en el hash.

## Fecha y Autor
* **Fecha:** 28 Mayo 2026
* **Autor:** [Karen Segundo]