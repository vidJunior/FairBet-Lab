# ADR 0009: Cashout Dinámico para Apuestas

## Contexto
El usuario que apuesta en vivo no quiere esperar hasta el final del partido para ver si gana o pierde. Necesitamos ofrecerle la opción de retirar anticipadamente ("cashout") un monto proporcional a lo que su apuesta vale en ese momento, permitiéndole asegurar ganancias parciales o minimizar pérdidas antes de que el evento termine.

## Opciones Consideradas

### Opción 1: No implementar cashout
El usuario espera hasta el final del evento; si gana cobra, si pierde no.
* **Pros**: Cero desarrollo, cero riesgo de errores de cálculo, sin comisiones que explicar.
* **Contras**: Peor experiencia de usuario frente a la competencia (BetPlay, Rushbet, etc. ya ofrecen cashout). El usuario se siente atrapado en su apuesta.

### Opción 2: Cashout manual por administrador
El usuario solicita cashout por soporte y un admin lo procesa manualmente.
* **Pros**: Control humano sobre cada operación.
* **Contras**: No escala, requiere personal 24/7, el usuario espera minutos/horas, frustración garantizada.

### Opción 3: Cashout dinámico automático
Fórmula: `cashout = stake * odds_original / odds_actual * FACTOR_CASA (0.95)`. Se calcula en tiempo real, el usuario ve el monto disponible y lo retira con un clic.
* **Pros**: Experiencia instantánea, el usuario ve el monto actualizado, nos quedamos con 5% de comisión, la plataforma es más competitiva.
* **Contras**: Mayor complejidad técnica (cálculo en vivo, soporte para combinadas), riesgo de que el usuario intente abusar del timing del cálculo.

## Decisión
Elegimos la **Opción 3** con la fórmula `stake * odds_original / odds_actual * 0.95`, implementando `calcular_cashout()` y `procesar_cashout()` en `betting/services.py`. Para apuestas combinadas, las selecciones ya finalizadas se tratan con cuota 1.0, y la comisión del 5% se descuenta automáticamente.

## Consecuencias
* **Fácil**: Los usuarios pueden retirar sus apuestas al instante desde la interfaz del catálogo. La plataforma genera comisión del 5% en cada cashout sin intervención manual.
* **Difícil**: Hay que mantener actualizadas las cuotas en vivo para que el cálculo sea justo. Para combinadas, el manejo de selecciones finalizadas requiere lógica adicional. Se agregó deuda técnica: el valor actual del cashout se recalcula en cada request; una optimización futura podría cachearlo o servirlo por WebSocket.

**Fecha**: 2026-05-29
**Autor**: Jhaysson
