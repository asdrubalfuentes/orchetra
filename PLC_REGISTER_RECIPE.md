# Receta de registros del LOGO! 9 — hoja de construcción

Qué **VW / VD / M** hay que crear en LOGO! Soft Comfort V9 y **con qué registro
Modbus** habla cada uno, para cumplir el [contrato](REGISTER_MAP.md)
(**`CONTRACT_VERSION 3`** — cambio de rumbo 2026-09: el LOGO! relaya, ya no
escala/totaliza; ver `REGISTER_MAP.md §8` para el changelog completo).

Complementa a [`PLC_LOGIC.md`](PLC_LOGIC.md): aquél explica *qué calcula* cada
bloque FBD; **éste es la lista literal de direcciones** para llenar los diálogos
de LSC y para marcar como hecho.

- **Regla de oro del mapeo (verificada en campo):** `Holding Register PDU N ↔ VW(2·N)`.
  Escribiste `2817` en `VW192` y se leyó en `HR 96` (192 = 2·96). ✔
- **Diálogos de LSC son 1-based.** En *Network Input/Output → Modbus* (el LOGO!
  como **cliente** de la pasarela): `dir_LSC = dir_PDU_gateway + 1`.
- **Enteros de 32 bits** (`VD`): palabra alta en la dirección menor (*hi-first*).
  `VD8` ocupa `VW8`(alta) + `VW10`(baja) ↔ `HR 4` + `HR 5`. Coincide con el contrato.
- **Bit dentro de un `VWx`:** `V(x+1).n` para bits `0..7` (byte bajo), `Vx.(n-8)`
  para bits `8..15` (byte alto) — **no** `Vx.n` a secas. Verificado en campo
  2026-09-12 (ver detalle en `PLC_LOGIC.md §5`).
- Desde v3, el **escalado y el totalizador ya no corren en el LOGO!** — ver
  `nodeIO/src/channels.cpp`. Lo que queda de `Float Mathematic` en este
  documento es solo para las alarmas de enlace/dispositivo que el LOGO! sigue
  calculando (§7).

---

## 0. Presupuesto de VM

| Zona | Rango VW | Bytes | Retentiva |
|---|---|---|---|
| MAPA B estación 0 (publicado) | `VW0 … VW62` | 64 | solo `VW40…VW62` (escala + sello) |
| MAPA B estación 1 (publicado) | `VW64 … VW126` | 64 | solo `VW104…VW126` |
| *(hueco)* | `VW128 … VW190` | — | — |
| MAPA B bloque global (publicado) | `VW192 … VW210` | 20 | no |
| ENTRADA cruda (interno, del MAPA A) | `VW400 … VW446` | 48 | no |
| Estado interno REAL (totalizador, filtros) | `VD500 … VD531` | 32 | `VD500…VD515` (acumulados) |
| Estado interno auxiliar | `VW540 … VW548` | 10 | `VW544` (máscara/sello previo) |

Total ≈ 250 bytes de ~850 disponibles. Holgado.

---

## 1. MAPA B — lo que el programa FBD **escribe** cada ciclo (servidor Modbus)

Lo leen HMI y SCADA por **FC03**. `s` = estación (0, 1).

### 1.1 Estación 0 — `HR 0…31` ↔ `VW0…VW62`

| HR | VW | Campo | Lo pone | Tipo |
|---:|---:|---|---|---|
| 0 | `VW0` | Nivel ×100 | **relay directo de MAPA A2** (§2.4), no hay fórmula | INT |
| 1 | `VW2` | Caudal ×100 | ídem, relay directo | INT |
| 2 | `VW4` | Nivel — crudo (eco) | Network Input (§2, bloque 1) | UINT |
| 3 | `VW6` | Caudal — crudo (eco) | Network Input (bloque 1) | UINT |
| 4–5 | `VD8` | Acumulado **día** m³ **×1000** | relay directo de MAPA A2 (cambió de ×10 en v3) | INT32 hi-first |
| 6–7 | `VD12` | Acumulado **mes** m³ **×1000** | ídem | INT32 hi-first |
| 8 | `VW16` | Estado (bitfield) | §6 — ver bits abajo | UINT |
| 9 | `VW18` | Alarmas **activas** (bitfield) | §5 | UINT |
| 10 | `VW20` | RSSI LoRa | Network Input (bloque 3) | INT16 |
| 11 | `VW22` | Antigüedad del dato (s) | Network Input (bloque 3) | UINT |
| 12 | `VW24` | Vínculo (dir. LoRa del nodo) | Network Input (bloque 3) | UINT |
| 13 | `VW26` | Contador de fallos de lectura | opcional (Up Counter en error de NI) | UINT |
| 14 | `VW28` | Alarmas **latcheadas** (bitfield) | §5 latcheo | UINT |
| 15–19 | `VW30…VW38` | reserva | — | 0 |
| 20–31 | `VW40…VW62` | **OBSOLETO desde v3** | sin uso — calibración en el portal del nodo (`nodeIO`); no cablees nada aquí | — |

### 1.2 Estación 1 — `HR 32…63` ↔ `VW64…VW126`

Misma tabla **sumando 32 al HR y 64 al VW**. Resumen de los que se usan:

| HR | VW | Campo |
|---:|---:|---|
| 32 / 33 | `VW64` / `VW66` | Nivel ×100 / Caudal ×100 |
| 34 / 35 | `VW68` / `VW70` | crudos (eco) |
| 36–37 / 38–39 | `VD72` / `VD76` | acumulado día / mes |
| 40 / 41 | `VW80` / `VW82` | Estado / Alarmas activas |
| 42 / 43 / 44 | `VW84` / `VW86` / `VW88` | RSSI / antigüedad / vínculo |
| 46 | `VW92` | Alarmas latcheadas |
| 52…63 | `VW104…VW126` | **OBSOLETO desde v3** (bloque de escala), sin uso |

### 1.3 Bloque global — `HR 96…105` ↔ `VW192…VW210`

| HR | VW | Campo | Valor / origen |
|---:|---:|---|---|
| 96 | `VW192` | Marca de protocolo | constante **`2817`** (`0x0B01`) |
| 97 | `VW194` | Nº de estaciones | constante **`2`** |
| 98 | `VW196` | Estaciones en línea (bit`s`) | `enlace0·1 + enlace1·2` |
| 99 | `VW198` | Alarma general | `HR9 OR HR41` (OR de alarmas activas) |
| 100 | `VW200` | **Heartbeat** | Up Counter +1 con pulso 1 Hz |
| 101–102 | `VD202` | Uptime (s) | Up Counter +1 con pulso 1 Hz | 
| 103 | `VW206` | Origen | constante **`1`** (LOGO! real) |
| 104 | `VW208` | Versión de lógica | constante libre (p. ej. `1`) |
| 105 | `VW210` | `CONTRACT_VERSION` | constante **`3`** |

> **Constantes:** ponlas con un bloque **Analog Amplifier** (Ganancia 0, Offset =
> valor) alimentado por cualquier entrada, salida mapeada a la VW; o fija el valor
> inicial de la VW y márcala retentiva. El heartbeat **debe** avanzar: el HMI lo
> vigila para declarar "enlace PLC vivo".

### Bits de `Estado` (`HR b+8`) y de `Alarmas` (`HR b+9` / `hb+14`)

```
Estado :  b0 presostato · b1 volt local · b2 tamper · b3 DI4
          b4 sirena activa · b5 enlace LoRa OK · b6 en alarma · b7 sirena AUTO
Alarmas:  1 LEVEL_HI(nodo) · 2 LEVEL_LO(nodo) · 4 LEVEL_LOLO(sin fuente) ·
          8 caudal bajo(nodo, antes NO_FLOW) · 16 PRESS_FAIL(LOGO!) ·
          32 VOLT_LOSS(LOGO!) · 64 TAMPER(LOGO!) · 128 LORA_LOSS(LOGO!) ·
          256 STALE(LOGO!) · 512 SCALE_BAD(sin fuente) · 1024 OVERRANGE(sin fuente) ·
          2048 caudal alto(nodo, nuevo en v3)
```
*(v3: bits marcados "nodo" vienen fusionados desde `MAPA A2.almBits` — ver §2.4;
"sin fuente" quedan en 0, nadie los calcula desde el cambio de rumbo.)*
En LOGO! cada bit se consigue mapeando una salida digital a un bit de VM (no
hace falta bloque "encoder") — **pero `VWx` son 2 bytes** (`x` alto, `x+1`
bajo) y la dirección de bit de LOGO! (`V<byte>.<bit>`) direcciona el **byte**,
no la palabra. **Verificado en campo (2026-09-12):** mapear a `Vx.n` escribe el
bit en el byte alto → aporta `256·2^n` al valor, no `2^n` (así se detectó:
`LINK_OK` mapeado a `V16.5` dejó `VW16 = 8192` en vez de `32`). Regla correcta:

- bit `0..7` del valor (`1..128`) → **`V(x+1).n`** (byte bajo)
- bit `8..15` del valor (`256..32768`) → **`Vx.(n-8)`** (byte alto)

Ejemplos con esta tabla: `Estado` completo (todos sus bits `0..7`) → `V(b+9).0
… V(b+9).7` (recordando que `HR b+8 = VW(2b+16)`, o sea el byte bajo es
`VW(2b+16)+1`). `Alarmas`: `LEVEL_HI…LORA_LOSS` (bits 0-7) → byte bajo de
`VW(2b+18)`; `STALE`/`SCALE_BAD`/`OVERRANGE` (bits 8-10) → byte alto (mismo
`VW`, bits 0-2 de ese byte).

---

## 2. MAPA A — lo que el LOGO! **lee** de la pasarela (cliente Modbus)

*Instrucciones → Network Input → Modbus*. Dispositivo remoto = pasarela
`nodeIO_master`, **IP fija** (reserva DHCP en el router), puerto `502`, Unit ID
`1`, **FC04 (Read Input Registers)** — la pasarela **no** tiene Holding Registers.
Periodo 500–1000 ms.

**3 bloques pequeños por estación** (así el crudo cae directo en su eco y en la
entrada del escalador, sin bloques de copia):

### Estación 0

| Bloque | Reg. gateway (PDU) | Dir. en LSC (1-based) | Cant. | Destino VW | Contenido |
|---|---|---|---|---|---|
| NI-0a | 0 | **1** | 2 | `VW4`, `VW6` | nivel crudo, caudal crudo → **eco `HR2/HR3`** (diagnóstico; ya no alimenta ningún escalado, eso vive en el nodo) |
| NI-0b | 4 | **5** | 3 | `VW400`, `VW402`, `VW404` | DI bitfield, relés bitfield, enlace |
| NI-0c | 7 | **8** | 3 | `VW20`, `VW22`, `VW24` | RSSI, antigüedad, dir. LoRa → **eco `HR10/11/12`** |

### Estación 1  (registros del gateway +16, VW de scratch +32)

| Bloque | Reg. gateway (PDU) | Dir. en LSC | Cant. | Destino VW |
|---|---|---|---|---|
| NI-1a | 16 | **17** | 2 | `VW68`, `VW70` |
| NI-1b | 20 | **21** | 3 | `VW432`, `VW434`, `VW436` |
| NI-1c | 23 | **24** | 3 | `VW84`, `VW86`, `VW88` |

**Bits de la palabra DI** (`VW400` est. 0 / `VW432` est. 1): `b0` presostato ·
`b1` voltaje local · `b2` tamper/tapa · `b3` DI4. **Corrección (regla de bit
verificada en campo, ver §1):** como esos bits están en el rango `0..7`, van en
el **byte bajo** de la palabra, no en `V400.x`/`V432.x` directo — léelos como
**`V401.0 / V401.1 / V401.2`** (estación 0) y **`V433.0 / V433.1 / V433.2`**
(estación 1).
**Enlace** (`VW404` / `VW436`): `> 0` ⇒ `LINK_OK` (esto sí es lectura de
palabra completa por umbral, no de un bit — sin cambios).

*(Opcional)* NI global: reg `900` → LSC `901`, cant. 1, a `VW446` — solo para
comprobar que ves `0x0203` y saber que el enlace con la pasarela vive.

### 2.4 MAPA A2 — escalado/acumulados/alarma que ya trae el nodo (desde v3)

**Mismo dispositivo, misma conexión Modbus** que el resto de esta sección —
solo agregas filas a la tabla que ya tienes. **As-built** (así quedó cargado):

| Fila | Dir. inicial (VW) | Long. | Sentido | Dir. inicial (IR) | Long. | Destino |
|---|---|---|---|---|---|---|
| Estación 0 — nivel/caudal | `VW0` | 2 words | `<-` | `IR201` | 2 words | copia directa, sin fórmula |
| Estación 0 — acum. día | `VW8` | 2 words | `<-` | `IR203` | 2 words | `VD8` |
| Estación 0 — acum. mes | `VW12` | 2 words | `<-` | `IR205` | 2 words | `VD12` |
| Estación 0 — `almBits` | `VW544` | 1 word | `<-` | `IR211` | 1 word | scratch, ver §1 fusión de alarmas |
| Estación 1 — nivel/caudal | `VW64` | 2 words | `<-` | `IR217` | 2 words | copia directa |
| Estación 1 — acum. día | `VW72` | 2 words | `<-` | `IR219` | 2 words | `VD72` |
| Estación 1 — acum. mes | `VW76` | 2 words | `<-` | `IR221` | 2 words | `VD76` |
| Estación 1 — `almBits` | `VW546` | 1 word | `<-` | `IR227` | 1 word | scratch |

Fusión de `almBits` en `Alarmas` (`VW18`/`VW82`) — **as-built**:

| Bit del nodo | Leer de (est. 0 / est. 1) | Escribir a `Alarmas` (est. 0 / est. 1) |
|---|---|---|
| bit0 nivel.almLo | `V545.0` / `V547.0` | `V19.1` (LEVEL_LO) / `V83.1` |
| bit1 nivel.almHi | `V545.1` / `V547.1` | `V19.0` (LEVEL_HI) / `V83.0` |
| bit2 caudal.almLo | `V545.2` / `V547.2` | `V19.3` (bit 3) / `V83.3` |
| bit3 caudal.almHi | `V545.3` / `V547.3` | `V18.3` (bit 11, byte alto) / `V82.3` |

No hace falta ningún `Float Mathematic` en toda esta sección — es relay puro.

---

## 3. Sirena de vuelta al nodo (cliente Modbus, escritura)

*Network Output → Modbus*, **FC05 (Write Single Coil)**, mismo dispositivo
(pasarela).

| Estación | Coil gateway (PDU) | Dir. en LSC | Valor |
|---|---|---|---|
| 0 | 0 | **1** | `sirena[0]` (§6 de PLC_LOGIC) |
| 1 | 16 | **17** | `sirena[1]` |

Si tu V9 no expone *Network Output* Modbus, cablea la sirena a un `Q` local del
LOGO! y deja este bloque fuera.

---

## 4. Comandos del HMI/SCADA — Coils ↔ marcas `M`

Los coils Modbus del LOGO! se mapean a marcas `M`. **El offset coil→M lo fija
LSC** (habitualmente `M(coil_PDU + 1)`); confírmalo en el diálogo de parámetros
de red y ajusta esta tabla:

| Coil PDU | Comando | `M` sugerida | El programa… |
|---:|---|---|---|
| `s·16+0` | Sirena ON manual | `M1` / `M17` | efectivo solo si AUTO = 0 |
| `s·16+1` | Sirena AUTO | `M2` / `M18` | selecciona rama AUTO/MANUAL |
| `s·16+2` | Silenciar (pulso) | `M3` / `M19` | Set del RS `SIL`; **auto-limpia** |
| `s·16+3` | **OBSOLETO desde v3** | `M4` / `M20` | el LOGO! ya no totaliza; puedes dejar de cablear esta `M` |
| `s·16+4` | **OBSOLETO desde v3** | `M5` / `M21` | ídem |
| `s·16+5` | **ACK / reset de alarmas** (pulso) | `M6` / `M22` | Reset de los RS de latcheo con la causa despejada; **auto-limpia** |
| `s·16+8` | **OBSOLETO desde v3** | `M9` / `M25` | ídem, no hay nada que aplicar |
| `s·16+9` | Armar reset | `M10` / `M26` | sin uso (solo protegía `cb+3`/`cb+4`) |

**Auto-limpia** = tras actuar en el flanco, un bloque fuerza la `M` a `0` al ciclo
siguiente (el LOGO! sí puede escribir sus propias `M`). Patrón FBD: `M` → detector
de flanco → acción + un `Reset` sobre la propia `M` con 1 ciclo de retardo.

---

## 5. VM interna (no se publica)

### 5.1 ENTRADA cruda — scratch de los Network Input

| VW | Estación 0 | Estación 1 |
|---|---|---|
| DI bitfield | `VW400` | `VW432` |
| Relés bitfield | `VW402` | `VW434` |
| Enlace | `VW404` | `VW436` |
| *(NI global opcional)* | `VW446` | — |

*(Nivel/caudal crudo y RSSI/edad/vínculo NO están aquí: caen directo en las VW de
eco `VW4/6/20/22/24` y `VW68/70/84/86/88`.)*

### 5.2 Estado REAL del totalizador y filtros — **OBSOLETO desde v3, libre**

`VD500…VD531` ya no los usa nada (el totalizador y el filtro EMA corren en el
nodo). Queda libre para lo que necesites a futuro.

### 5.3 Auxiliares

| VW | Contenido |
|---|---|
| `VW540` | `alarmas_prev` est. 0 (para detectar "alarma nueva" → sirena) — **sigue en uso**, la sirena no cambió |
| `VW542` | `alarmas_prev` est. 1 — sigue en uso |
| `VW544` | `almBits` del nodo, estación 0 (desde v3, ver §2.4) — **ya no está libre** |
| `VW546` | `almBits` del nodo, estación 1 (desde v3) — nuevo, tampoco libre |

---

## 6. Qué produce cada ciclo (resumen por estación `s`) — actualizado a v3

```
// --- entradas ya en VM por los Network Input, MAPA A (crudo/DI/enlace) ---
di       = VW401.0/.1/.2 (s0) / VW433.0/.1/.2 (s1)   // b0 presos, b1 volt, b2 tamper
link     = VW404 (s0) / VW436 (s1) > 0
rssi,age,addr ya en VW20/22/24 (s0) y VW84/86/88 (s1)

// --- MAPA A2 (§2.4): nivel/caudal escalados y acumulados, RELAY DIRECTO ---
VW0, VW2, VD8, VD12   (s0)  /  VW64, VW66, VD72, VD76  (s1)   -- copia, sin formula
almBits: VW544 (s0) / VW546 (s1) -- fusionado en VW18/VW82, ver §2.4

// --- alarmas: fusion (bits 0,1,3,11 desde el nodo) + lo que sigue calculando
//     el LOGO! (bits 4,5,6,7,8 -- presostato, volt, tamper, enlace, edad).
//     Bits 2,9,10 sin fuente desde v3. Ver PLC_LOGIC.md §5.
// latcheo: RS por bit  (Set = bit activo ; Reset = M6 AND NOT bit activo). PLC_LOGIC.md §5
VW28 = latch(VW18, MASCARA_LATCH={TAMPER}, ACK=M6)   // LEVEL_LOLO ya no existe, ver nota

// --- estado ---
VW16 = di.b0 | di.b1<<1 | di.b2<<2 | di.b3<<3
       | sirena<<4 | link<<5 | (VW18!=0)<<6 | M2<<7

// --- sirena (§6 PLC_LOGIC) ---
sirena = M2 ? (alarma_activa AND NOT SIL) : M1
Q_local = sirena ; NetOut coil = sirena

// --- aplicar escala: OBSOLETO desde v3, no hay nada que cablear aquí ---
```

Bloque global (`PLC_LOGIC.md §7`):
- constantes: `VW192 = 2817` · `VW194 = 2` · `VW206 = 1` · `VW208 = 1` · `VW210 = 3`
- `VW196` = enlaces (`bit0` est.0, `bit1` est.1) — recuerda: van en el **byte bajo**, `V197.0`/`V197.1`
- `VW198` = **`VW18 OR VW82`** (alarmas activas de est.0 `HR9` OR est.1 `HR41`)
- `VW200` (heartbeat) y `VD202` (uptime, s) cuentan con el pulso de 1 Hz

---

## 7. Parámetros por defecto — **movidos al nodo desde v3**

El escalado (raw_min/max, eng_min/max, unidad, filtro) ya **no** se configura
aquí — vive en el portal cautivo del `nodeIO`, con sus propios valores por
defecto (ver `nodeIO/src/node_config.cpp` o `REGISTER_MAP.md §5`: nivel en
metros 800..4000→0..100,00, caudal en m³/h 800..4000→0..100,00, filtro 15,
alarma baja nivel 5,00 m, alarma alta caudal 90,00 m³/h). Igual para el factor
`k` del totalizador (ahora en `nodeIO/src/channels.cpp::kFactor()`).

Lo que **sigue** siendo del LOGO! (`plc_sim.py` debe igualarlo para acople
seguro):

### Umbrales de alarma que sigue calculando el LOGO! (por estación)

| Alarma | Condición | Umbral / retardo por defecto |
|---|---|---|
| `PRESS_FAIL` (bit 4) | `volt_local AND NOT presostato` sostenido | **15 s** |
| `VOLT_LOSS` (bit 5) | `NOT volt_local` | inmediato |
| `TAMPER` (bit 6) | `tamper` | inmediato |
| `LORA_LOSS` (bit 7) | `NOT enlace` sostenido | **20 s** |
| `STALE` (bit 8) | `edad > ` | **15 s** |

### Máscaras

| Nombre | Valor por defecto | Uso |
|---|---|---|
| Sirena | **cualquier alarma** (`siren_on_any_alarm = True`) | si se pone selectivo: `LEVEL_HI \| caudal_bajo \| PRESS_FAIL \| VOLT_LOSS \| TAMPER \| LORA_LOSS \| caudal_alto` |
| Latcheo (`HR b+14`) | **`TAMPER`** (antes `LEVEL_LOLO \| TAMPER` — `LEVEL_LOLO` ya no tiene fuente, se quitó de la máscara) | bits que se mantienen hasta `cb+5` (ACK) con la causa despejada |

---

## 8. Checklist de construcción en LSC V9

- [ ] Proyecto nuevo con el BM del LOGO! 9; IP fija = la que puso el HMI en `PLC_HOST`.
- [ ] Propiedades → Comunicación → **Modbus (servidor)** activado. Verifica en el
      diálogo de mapeo que `HR0=VW0`, `HR1=VW2`, … `HR96=VW192`.
- [ ] ~~Retentivas `VW40…VW62`, `VW104…VW126`, `VD500…VD515`~~ — **ya no aplica
      desde v3**, ese rango quedó libre/sin uso.
- [ ] **Network Input Modbus** × 6 (NI-0a/b/c, NI-1a/b/c) según §2 + **× 8 más**
      (§2.4, MAPA A2: nivel/caudal, día, mes, `almBits`, por estación).
- [ ] **Network Output Modbus** × 2 (sirena) según §3, o `Q` local.
- [ ] Mapear **coils → M** según §4; anotar el offset real coil→M de tu LSC.
- [ ] Bloque **global** §1.3 + pulso 1 Hz (reloj asíncrono) para heartbeat/uptime.
- [ ] Fusión de `almBits` → `Alarmas` (§2.4) — 4 mapeos por estación (bit-lectura
      directa, sin comparador, el nodo ya lo discretizó).
- [ ] Lógica de sirena (`PLC_LOGIC.md §6`) — sin cambios de v2.
- [ ] Alarmas de enlace/dispositivo que sigue calculando el LOGO! (§7 de este
      doc: `PRESS_FAIL/VOLT_LOSS/TAMPER/LORA_LOSS/STALE`) — sin cambios de v2.
- [ ] **Descargar** por Ethernet.
- [ ] Verificar:
      `python ORCHESTRATION/tools/mapb_check.py --host <IP_LOGO> --port 502 --write`
      → **0 FAIL**, `origen = LOGO! real`, `CONTRACT_VERSION = 3`, heartbeat avanza,
      `cb+2` (silenciar) y `cb+5` (ACK) se auto-limpian.
- [ ] *(Cuando el puente MQTT esté habilitado)* **§10**: Network Output ×2/3
      (NO-B0/B1/BG) + Network Input ×2 (NI-C0/C1) hacia el **gateway**, `OR` de
      cada `Mnube` con su `M` homóloga del HMI. Verificar publicando por MQTT y
      comparando `station/<s>/data` contra `mapb_check` en el mismo instante.

---

## 9. Orden recomendado de puesta en obra (incremental) — actualizado a v3

Este es el orden que de hecho se siguió al migrar de v2 a v3, ya verificado:

1. **Global**: `VW192/194/206/208/210` constantes + heartbeat `VW200` + enlaces
   `VW196` (fusión `V197.0/.1`). Descarga → `mapb_check` debe ver marca y
   versión OK, latido avanzando.
2. **Eco de crudos** (MAPA A): NI-0a/0c y NI-1a/1c → `HR2/3/10/11/12` y
   `HR34/35/42/43/44`. Verifica contra `mb_dump.py --tcp <IP_gateway>`.
3. ~~Escalado~~ → **reemplazado**: agrega en su lugar el `Network Input` de
   `MAPA A2` (§2.4) que trae nivel/caudal **ya escalados** — 1 fila, `HR0/1`.
4. Acumulados de `MAPA A2` (§2.4) → `HR4..7` (día/mes) — copia directa, sin
   `Float Mathematic`.
5. `almBits` de `MAPA A2` (§2.4) → fusión en `Alarmas` `HR9` (2 bits limpios:
   `LEVEL_HI`/`LEVEL_LO`; deja `caudal bajo`/`caudal alto` para cuando decidas
   dónde van en tu árbol).
6. **Sirena** (`M1/M2/M3` + `cb+5` ACK) y salida al nodo — sin cambios de v2.
7. Repite 3-6 para la estación 1.
8. *(Cuando exista el puente MQTT)* **§10** — espejo de MAPA B al gateway y
   lectura de los comandos de la nube.

> Ya **no** hay pasos de "totalizador" ni "aplicar escala" — quedaron
> eliminados del programa (ver §6/§7 de este doc y `PLC_LOGIC.md §3/§4`).

---

## 10. Puente MQTT — bloques Network I/O extra (opcional, [`MQTT_BRIDGE.md`](MQTT_BRIDGE.md))

Para que el `nodeIO_master` publique todo por MQTT sin sondear al LOGO!, el LOGO!
**espeja su MAPA B en el gateway** y **lee de ahí los comandos de la nube**. Todo
por la conexión Modbus que ya tiene con el gateway — **cero conexiones nuevas**.
Direcciones: [`REGISTER_MAP.md §7`](REGISTER_MAP.md).

### 10.1 Network Output → Modbus  (escribe el espejo de MAPA B)

Dispositivo = gateway `nodeIO_master` (IP fija, `:502`, Unit ID `1`),
**FC16 (Write Multiple Holding Registers)**.

| Bloque | Origen (VW) | Destino gateway (HR, **1-based en LSC**) | Cant. |
|---|---|---|---|
| NO-B0 | `VW0`   | `1`  (`HR 0`)  | 32 |
| NO-B1 | `VW64`  | `33` (`HR 32`) | 32 |
| NO-BG | `VW192` | `97` (`HR 96`) | 10 |

Periodo 500–1000 ms. Si tu V9 no permite bloques de 32, parte en 2×16. El gateway
lee estos `HR` para publicar `station/<s>/data`, `plant` y `scale`.

### 10.2 Network Input → Modbus  (lee los comandos de la nube)

Mismo dispositivo, **FC01 (Read Coils)**. Por estación `s`, base gateway
`1000 + s*16` → LSC 1-based `1001 + s*16`:

| Bloque | Coil gateway (PDU) | Dir. en LSC | Cant. | Destino |
|---|---|---|---|---|
| NI-C0 | `1000` | **1001** | 10 | `Mnube` comando nube, est. 0 → `M40…M49` |
| NI-C1 | `1016` | **1017** | 10 | `Mnube` comando nube, est. 1 → `M56…M65` |

Offsets dentro del bloque = los de `cb+*` (§4). Marca `M` sugerida (mismo patrón
+16 entre estaciones que usa §4; no choca con `M1…M10` / `M17…M26`):

| Offset coil | Comando | `Mnube` est. 0 | `Mnube` est. 1 |
|---:|---|---|---|
| `+0` | Sirena ON manual | `M40` | `M56` |
| `+1` | Sirena AUTO | `M41` | `M57` |
| `+2` | Silenciar (pulso) | `M42` | `M58` |
| `+3` | Reset día (pulso) | `M43` | `M59` |
| `+4` | Reset mes (pulso) | `M44` | `M60` |
| `+5` | ACK (pulso) | `M45` | `M61` |
| `+6`/`+7` | *(sin uso en `cb+*`)* | — | — |
| `+8` | Aplicar escala (pulso) | `M48` | `M64` |
| `+9` | Armar reset | `M49` | `M65` |

El gateway auto-limpia los pulsos (`+2/+3/+4/+5/+8`) a los 1,5 s de escribirlos
en `1`; no hace falta que el LOGO! los borre.

### 10.3 Fusión con los comandos del HMI (Fase A)

El HMI sigue escribiendo `cb+*` directo en el LOGO! (§4: `M1…M10` / `M17…M26`).
En el FBD, cada mando efectivo = **`OR`** de la `M` del HMI con su `Mnube`
homóloga — inserta el `OR` **entre** la `M` y el bloque que hoy la consume
(detector de flanco para los pulsos, entrada directa para AUTO/armar):

| Mando | `OR` de | Alimenta a (igual que hoy) |
|---|---|---|
| Sirena manual | `M1 OR M40` (· `M17 OR M56`) | selector `sirena = AUTO ? … : M1` (§6 PLC_LOGIC) |
| Sirena AUTO | `M2 OR M41` (· `M18 OR M57`) | selector AUTO/MANUAL |
| Silenciar | `M3 OR M42` (· `M19 OR M58`) | `Set` del RS `SIL` |
| Reset día | `M4 OR M43` (· `M20 OR M59`) | `AND M10` → reset `VD500`/`VD508` |
| Reset mes | `M5 OR M44` (· `M21 OR M60`) | `AND M10` → reset `VD504`/`VD512` |
| ACK | `M6 OR M45` (· `M22 OR M61`) | `Reset` del latcheo `VW28`/`VW92` |
| Aplicar escala | `M9 OR M48` (· `M25 OR M64`) | flanco → `VW62`/`VW126` +1, reset filtros |
| Armar | `M10 OR M49` (· `M26 OR M65`) | habilita los dos resets de arriba |

```
silenciar_efectivo = flanco(M3  OR M42)
ack_efectivo       = flanco(M6  OR M45)
sirena_auto        = M2  OR M41
armar              = M10 OR M49
...
```

*Fase B (a futuro):* el HMI también escribe en los coils `1000+` del gateway; el
LOGO! deja de exponer `cb+*` para escritura y tiene **un solo origen de mando**.
