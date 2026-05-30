# ADR 0002: Wallet con Partida Doble

## Contexto

Requerimos un monedero (wallet) para manejar las fichas virtuales que garantice la integridad financiera, evite el doble gasto y mantenga un historial auditable, sin guardar el saldo como un simple número que pueda desincronizarse.

## Opciones Consideradas

### Opción 1: Campo de saldo simple

Tener un campo numérico `saldo` en el modelo del usuario y sumarle o restarle directamente cada vez que haya una recarga o una apuesta.

* **Pros**: Es muy directo, rápido y fácil de programar.
* **Contras**: Si ocurre un error de concurrencia o se cae el servidor durante una apuesta, el saldo se corrompe sin dejar un rastro claro.

### Opción 2: Sistema de Partida Doble

Crear un modelo `LedgerEntry` donde cada transacción genere al menos dos registros balanceados (un débito y un crédito que sumen cero). El saldo siempre se calcula al vuelo restando débitos de créditos.

* **Pros**: Integridad financiera absoluta, historial 100% auditable y prevención nativa contra el doble gasto y saldos fantasma.
* **Contras**: Cuesta más implementar y hay que calcular el saldo al vuelo en la base de datos para cada consulta.

## Decisión

Elegimos la **Opción 2** para asegurar que ningún usuario termine con saldo negativo por un error y para tener una auditoría perfecta de todos los movimientos de las fichas.

## Consecuencias

* **Fácil**: Rastrear a dónde fue a parar cada ficha virtual y auditar las cuentas es muy directo y seguro.
* **Difícil**: Obliga a usar bloqueos pesimistas (`select_for_update`) y a sumar todos los movimientos cada vez que necesitamos saber el saldo del usuario.

**Fecha**: 2026-05-30  
**Autor**: Vidarte Cruz Jose Junior
