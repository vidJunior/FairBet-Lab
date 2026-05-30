# ADR 0010: Mercados Adicionales y Apuestas Combinadas

## Contexto
Hasta ahora el sistema solo manejaba apuestas al mercado 1X2 (Local/Empate/Visitante). Para ser competitivos necesitamos ampliar la oferta de mercados por evento (doble oportunidad, más/menos, ambos equipos anotan) y además soportar apuestas combinadas (parlay) donde el usuario selecciona múltiples pronósticos en un solo boleto.

## Opciones Consideradas

### Opción 1: Solo mercado 1X2
Cada evento tiene únicamente el mercado tradicional de resultado final.
* **Pros**: Simplicidad total, modelo de datos mínimo, lógica de liquidación trivial.
* **Contras**: Oferta muy pobre frente a la competencia, el usuario no tiene variedad para apostar, las apuestas combinadas no son posibles.

### Opción 2: Mercados fijos en código con combinadas
Definir 4 mercados por evento (1X2, Doble Oportunidad, Más/Menos 2.5, Ambos Anotan) y soportar selección múltiple en un mismo boleto. Los mercados se crean automáticamente al crear el evento mediante `crear_mercados_para_evento()`.
* **Pros**: Riqueza de mercado competitiva, el usuario puede armar combinadas, los mercados se generan sin intervención manual, se reutiliza la infraestructura existente de Selección/Mercado.
* **Contras**: Más mercados implica más cuotas que mantener actualizadas en vivo.

### Opción 3: Mercados configurables por administrador
El admin puede crear mercados personalizados por evento desde el panel de administración.
* **Pros**: Flexibilidad total para añadir mercados exóticos.
* **Contras**: Requiere interfaz de admin más compleja, riesgo de errores humanos al definir cuotas, sobrecarga operativa.

## Decisión
Elegimos la **Opción 2**: 4 mercados fijos por evento generados automáticamente, más soporte para apuestas combinadas con cuota acumulada (producto de cuotas individuales). La implementación incluye el refactor del boleto en el template `catalogo.html` para selección múltiple y la visualización de detalles en "Mis Apuestas".

## Consecuencias
* **Fácil**: Los usuarios tienen 4 mercados para elegir y pueden combinar selecciones en un solo boleto. El sistema crea los mercados automáticamente al crear un evento sin intervención del admin. Se agregó el modelo `Equipo` con validación de duplicados y FK a `Evento`.
* **Difícil**: Mantener 4 mercados actualizados en vivo cuadruplica el esfuerzo de sincronización de cuotas. La lógica de liquidación de combinadas es más compleja (todas las selecciones deben ganar). Se asume deuda técnica: la creación de mercados está acoplada al momento de creación del evento; si en el futuro se quieren agregar mercados a eventos existentes, hay que ejecutar la función manualmente.

**Fecha**: 2026-05-29
**Autor**: Jhaysson
