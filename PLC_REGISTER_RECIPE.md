# Receta de registros del LOGO! 9 — hoja de construcción

Qué **VW / VD / M** hay que crear en LOGO! Soft Comfort V9 y **con qué registro
Modbus** habla cada uno, para cumplir el [contrato](REGISTER_MAP.md)
(`CONTRACT_VERSION 2` + adición compatible del ACK de alarmas).

Complementa a [`PLC_LOGIC.md`](PLC_LOGIC.md): aquél explica *qué calcula* cada
bloque FBD; **éste es la lista literal de direcciones** para llenar los diálogos
de LSC y para marcar como hecho.

- **Regla de oro del mapeo (verificada en campo):** `Holding Register PDU N ↔ VW(2·N)`.
  Escribiste `2817` en `VW192` y se leyó en `HR 96` (192 = 2·96). ✔
- **Diálogos de LSC son 1-based.** En *Network Input/Output → Modbus* (el LOGO!
  como **cliente** de la pasarela): `dir_LSC = dir_PDU_gateway + 1`.
- **Enteros de 32 bits** (`VD`): palabra alta en la dirección menor (*hi-first*).
  `VD8` ocupa `VW8`(alta) + `VW10`(baja) ↔ `HR 4` + `HR 5`. Coincide con el contrato.
- **Analógicos** del LOGO! 9 en **float 32-bit**; usa **Float Mathematic** para el
  escalado y el totalizador.

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
| 0 | `VW0` | Nivel ×100 | escalado §3 de PLC_LOGIC | INT |
| 1 | `VW2` | Caudal ×100 | escalado §3 | INT |
| 2 | `VW4` | Nivel — crudo (eco) | Network Input (§2, bloque 1) | UINT |
| 3 | `VW6` | Caudal — crudo (eco) | Network Input (bloque 1) | UINT |
| 4–5 | `VD8` | Acumulado **día** m³ ×10 | totalizador §4 | INT32 hi-first |
| 6–7 | `VD12` | Acumulado **mes** m³ ×10 | totalizador §4 | INT32 hi-first |
| 8 | `VW16` | Estado (bitfield) | §6 — ver bits abajo | UINT |
| 9 | `VW18` | Alarmas **activas** (bitfield) | §5 | UINT |
| 10 | `VW20` | RSSI LoRa | Network Input (bloque 3) | INT16 |
| 11 | `VW22` | Antigüedad del dato (s) | Network Input (bloque 3) | UINT |
| 12 | `VW24` | Vínculo (dir. LoRa del nodo) | Network Input (bloque 3) | UINT |
| 13 | `VW26` | Contador de fallos de lectura | opcional (Up Counter en error de NI) | UINT |
| 14 | `VW28` | Alarmas **latcheadas** (bitfield) | §5 latcheo | UINT |
| 15–19 | `VW30…VW38` | reserva | — | 0 |
| 20 | `VW40` | Nivel raw_min ("cero") | **lo escribe el HMI** (FC16) | UINT · **RET** |
| 21 | `VW42` | Nivel raw_max ("span") | HMI | UINT · **RET** |
| 22 | `VW44` | Nivel eng_min ×100 | HMI | INT16 · **RET** |
| 23 | `VW46` | Nivel eng_max ×100 | HMI | INT16 · **RET** |
| 24 | `VW48` | Caudal raw_min | HMI | UINT · **RET** |
| 25 | `VW50` | Caudal raw_max | HMI | UINT · **RET** |
| 26 | `VW52` | Caudal eng_min ×100 | HMI | INT16 · **RET** |
| 27 | `VW54` | Caudal eng_max ×100 | HMI | INT16 · **RET** |
| 28 | `VW56` | Unidad de Nivel (0 % · 1 m · 2 cm · 3 mca) | HMI | UINT · **RET** |
| 29 | `VW58` | Unidad de Caudal (0 L/s · 1 m³/h · 2 L/min · 3 GPM) | HMI | UINT · **RET** |
| 30 | `VW60` | Filtro 0…100 | HMI | UINT · **RET** |
| 31 | `VW62` | Sello de config | lo **incrementa el LOGO!** al aplicar `cb+8` | UINT · **RET** |

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
| 52…63 | `VW104…VW126` | bloque de escala + sello (**RET**) |

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
| 105 | `VW210` | `CONTRACT_VERSION` | constante **`2`** |

> **Constantes:** ponlas con un bloque **Analog Amplifier** (Ganancia 0, Offset =
> valor) alimentado por cualquier entrada, salida mapeada a la VW; o fija el valor
> inicial de la VW y márcala retentiva. El heartbeat **debe** avanzar: el HMI lo
> vigila para declarar "enlace PLC vivo".

### Bits de `Estado` (`HR b+8`) y de `Alarmas` (`HR b+9` / `hb+14`)

```
Estado :  b0 presostato · b1 volt local · b2 tamper · b3 DI4
          b4 sirena activa · b5 enlace LoRa OK · b6 en alarma · b7 sirena AUTO
Alarmas:  1 LEVEL_HI · 2 LEVEL_LO · 4 LEVEL_LOLO · 8 NO_FLOW · 16 PRESS_FAIL
          32 VOLT_LOSS · 64 TAMPER · 128 LORA_LOSS · 256 STALE
          512 SCALE_BAD · 1024 OVERRANGE
```
En LOGO! cada bit se consigue mapeando una salida digital a `VWx.0 … VWx.10` en
el diálogo de parámetros VM (no hace falta bloque "encoder").

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
| NI-0a | 0 | **1** | 2 | `VW4`, `VW6` | nivel crudo, caudal crudo → **eco `HR2/HR3` + entrada del escalado** |
| NI-0b | 4 | **5** | 3 | `VW400`, `VW402`, `VW404` | DI bitfield, relés bitfield, enlace |
| NI-0c | 7 | **8** | 3 | `VW20`, `VW22`, `VW24` | RSSI, antigüedad, dir. LoRa → **eco `HR10/11/12`** |

### Estación 1  (registros del gateway +16, VW de scratch +32)

| Bloque | Reg. gateway (PDU) | Dir. en LSC | Cant. | Destino VW |
|---|---|---|---|---|
| NI-1a | 16 | **17** | 2 | `VW68`, `VW70` |
| NI-1b | 20 | **21** | 3 | `VW432`, `VW434`, `VW436` |
| NI-1c | 23 | **24** | 3 | `VW84`, `VW86`, `VW88` |

**Bits de la palabra DI** (`VW400` est. 0 / `VW432` est. 1): `b0` presostato ·
`b1` voltaje local · `b2` tamper/tapa · `b3` DI4. Léelos como `V400.0 / V400.1 /
V400.2` en FBD.
**Enlace** (`VW404` / `VW436`): `> 0` ⇒ `LINK_OK`.

*(Opcional)* NI global: reg `900` → LSC `901`, cant. 1, a `VW446` — solo para
comprobar que ves `0x0203` y saber que el enlace con la pasarela vive.

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
| `s·16+3` | Reset acumulado día (pulso) | `M4` / `M20` | solo si `M10`/`M26` armado; **auto-limpia** |
| `s·16+4` | Reset acumulado mes (pulso) | `M5` / `M21` | ídem; **auto-limpia** |
| `s·16+5` | **ACK / reset de alarmas** (pulso) | `M6` / `M22` | Reset de los RS de latcheo con la causa despejada; **auto-limpia** |
| `s·16+8` | Aplicar bloque de escala (pulso) | `M9` / `M25` | valida `HR b+20..31`, +1 al sello `HR b+31`; **auto-limpia** |
| `s·16+9` | Armar reset | `M10` / `M26` | habilita `cb+3`/`cb+4` (nivel, no pulso) |

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

### 5.2 Estado REAL del totalizador y filtros

| VD | Contenido | Retentiva |
|---|---|---|
| `VD500` | acumulado día est. 0 (m³, REAL) | **sí** |
| `VD504` | acumulado mes est. 0 | **sí** |
| `VD508` | acumulado día est. 1 | **sí** |
| `VD512` | acumulado mes est. 1 | **sí** |
| `VD516` | `y_filt` nivel est. 0 (EMA) | no |
| `VD520` | `y_filt` caudal est. 0 | no |
| `VD524` | `y_filt` nivel est. 1 | no |
| `VD528` | `y_filt` caudal est. 1 | no |

### 5.3 Auxiliares

| VW | Contenido |
|---|---|
| `VW540` | `alarmas_prev` est. 0 (para detectar "alarma nueva" → sirena) |
| `VW542` | `alarmas_prev` est. 1 |
| `VW544` | reserva / uso libre del programa |

---

## 6. Qué produce cada ciclo (resumen por estación `s`)

```
// --- entradas ya en VM por los Network Input ---
niv_raw  = VW4  (s0) / VW68 (s1)
cau_raw  = VW6  (s0) / VW70 (s1)
di       = VW400 (s0) / VW432 (s1)      // b0 presos, b1 volt, b2 tamper, b3 DI4
link     = VW404 (s0) / VW436 (s1) > 0
rssi,age,addr ya en VW20/22/24 (s0) y VW84/86/88 (s1)

// --- escalado (§3 PLC_LOGIC) con VW40..VW54 (s0) / VW104..VW118 (s1) ---
VW0  = escala(niv_raw, n_rmin, n_rmax, n_emin, n_emax, filtro, VD516)
VW2  = escala(cau_raw, c_rmin, c_rmax, c_emin, c_emax, filtro, VD520)

// --- totalizador (§4 PLC_LOGIC), pulso 1 Hz, k según unidad VW58 ---
VD500 += (VW2/100)*k       ; VD8  = REAL_TO_DINT(VD500*10)     // día
VD504 += (VW2/100)*k       ; VD12 = REAL_TO_DINT(VD504*10)     // mes
reset con medianoche / fin de mes / (M4·M10) / (M5·M10)

// --- alarmas (PLC_LOGIC.md §5; umbrales en §7 de este doc) ---
VW18 = arbol_de_alarmas(niv, cau, di, link, age, scale_bad, overrange)
// latcheo: RS por bit  (Set = bit activo ; Reset = M6 AND NOT bit activo). PLC_LOGIC.md §5
VW28 = latch(VW18, MASCARA_LATCH={LEVEL_LOLO,TAMPER}, ACK=M6)

// --- estado ---
VW16 = di.b0 | di.b1<<1 | di.b2<<2 | di.b3<<3
       | sirena<<4 | link<<5 | (VW18!=0)<<6 | M2<<7

// --- sirena (§6 PLC_LOGIC) ---
sirena = M2 ? (alarma_activa AND NOT SIL) : M1
Q_local = sirena ; NetOut coil = sirena

// --- aplicar escala (M9 flanco) ---
if pulso(M9) and escala_valida: VW62 = (VW62+1) & 0xFFFF ; reset VD516/VD520
```

Bloque global (`PLC_LOGIC.md §7`):
- constantes: `VW192 = 2817` · `VW194 = 2` · `VW206 = 1` · `VW208 = 1` · `VW210 = 2`
- `VW196` = enlaces (`bit0` est.0, `bit1` est.1)
- `VW198` = **`VW18 OR VW82`** (alarmas activas de est.0 `HR9` OR est.1 `HR41`)
- `VW200` (heartbeat) y `VD202` (uptime, s) cuentan con el pulso de 1 Hz

---

## 7. Parámetros por defecto — igualar al PLC-SIM

El contrato exige **acople seguro**: el LOGO! real y el PLC-SIM se comportan
igual. Estos son los valores del `modbusMaster/plc_sim.py` (`_default_station`);
ajústalos en puesta en marcha, pero arranca con ellos.

### Escalado (`HR b+20..31`) — también en `REGISTER_MAP.md §5`

| Parámetro | Nivel | Caudal |
|---|---|---|
| `raw_min` / `raw_max` | 800 / 4000 | 800 / 4000 |
| `eng_min` / `eng_max` (×100) | 0 / 10000 (0…100,00) | 0 / 5000 (0…50,00) |
| unidad | 0 (%) | 0 (L/s) |
| filtro (EMA) | 20 | 10 |

### Umbrales de alarma (por estación)

| Alarma | Condición | Umbral / retardo por defecto |
|---|---|---|
| `LEVEL_HI` (bit 0) | `nivel_x100 ≥` | **9000** (90,00) |
| `LEVEL_LO` (bit 1) | `nivel_x100 ≤` | **1000** (10,00) |
| `LEVEL_LOLO` (bit 2) | `nivel_x100 ≤` | **500** (5,00) |
| `NO_FLOW` (bit 3) | `presostato AND caudal_x100 ≤ eps` sostenido | eps = **20** · **10 s** |
| `PRESS_FAIL` (bit 4) | `volt_local AND NOT presostato` sostenido | **15 s** |
| `VOLT_LOSS` (bit 5) | `NOT volt_local` | inmediato |
| `TAMPER` (bit 6) | `tamper` | inmediato |
| `LORA_LOSS` (bit 7) | `NOT enlace` sostenido | **20 s** |
| `STALE` (bit 8) | `edad > ` | **15 s** |
| `SCALE_BAD` (bit 9) | `raw_max ≤ raw_min` o `eng_max = eng_min` | — |
| `OVERRANGE` (bit 10) | `raw` fuera de `[raw_min, raw_max]` con margen | margen = **2 %** del span |

### Máscaras

| Nombre | Valor por defecto | Uso |
|---|---|---|
| Sirena | **cualquier alarma** (`siren_on_any_alarm = True`) | si se pone selectivo: `LEVEL_HI \| LEVEL_LOLO \| NO_FLOW \| PRESS_FAIL \| VOLT_LOSS \| TAMPER \| LORA_LOSS` |
| Latcheo (`HR b+14`) | `LEVEL_LOLO \| TAMPER` | bits que se mantienen hasta `cb+5` (ACK) con la causa despejada |

### Totalizador — factor `k` (caudal → m³/s) según unidad (`HR b+29`)

`0` L/s → `1/1000` · `1` m³/h → `1/3600` · `2` L/min → `1/60000` ·
`3` GPM → `3.785411784/60000`

---

## 8. Checklist de construcción en LSC V9

- [ ] Proyecto nuevo con el BM del LOGO! 9; IP fija = la que puso el HMI en `PLC_HOST`.
- [ ] Propiedades → Comunicación → **Modbus (servidor)** activado. Verifica en el
      diálogo de mapeo que `HR0=VW0`, `HR1=VW2`, … `HR96=VW192`.
- [ ] **Retentivas**: `VW40…VW62`, `VW104…VW126`, `VD500…VD515`.
- [ ] **Network Input Modbus** × 6 (NI-0a/b/c, NI-1a/b/c) según §2.
- [ ] **Network Output Modbus** × 2 (sirena) según §3, o `Q` local.
- [ ] Mapear **coils → M** según §4; anotar el offset real coil→M de tu LSC.
- [ ] **UDF "Estación"** con §3–§6 de PLC_LOGIC; instánciala 2 veces (parámetros:
      base VW, base M, umbrales, tiempos TON).
- [ ] Bloque **global** §1.3 + pulso 1 Hz (reloj asíncrono) para heartbeat/uptime
      y para el totalizador.
- [ ] **Parámetros** = los de **§7** (escala, umbrales de alarma, retardos TON,
      `MARGEN 2 %`, máscara de sirena, máscara de latcheo `{LEVEL_LOLO, TAMPER}`,
      factor `k` del totalizador). Deben coincidir con el PLC-SIM.
- [ ] **Simular** en LSC (emulador con red): escala, alarmas, latcheo+ACK, sirena,
      totalizador y reset.
- [ ] **Descargar** por Ethernet.
- [ ] Verificar:
      `python ORCHESTRATION/tools/mapb_check.py --host <IP_LOGO> --port 502 --write`
      → **0 FAIL**, `origen = LOGO! real`, `CONTRACT_VERSION = 2`, heartbeat avanza,
      `cb+2` (silenciar) y `cb+5` (ACK) se auto-limpian, aplicar escala cambia el sello.

---

## 9. Orden recomendado de puesta en obra (incremental)

1. **Global**: `VW192/194/206/208/210` constantes + heartbeat `VW200`. Descarga →
   `mapb_check` debe ver marca y versión OK y latido avanzando.
2. **Eco de crudos**: NI-0a/0c y NI-1a/1c → `HR2/3/10/11/12` y `HR34/35/42/43/44`.
   Verifica contra `mb_dump.py --tcp <IP_gateway>`.
3. **Escalado** de las 2 variables × 2 estaciones → `HR0/1` y `HR32/33`.
4. **Alarmas** `HR9/41` + estado `HR8/40` + latcheadas `HR14/46` + `HR99`.
5. **Sirena** (`M1/M2/M3` + `cb+5` ACK) y salida al nodo.
6. **Totalizador** día/mes + `HR98` + resets protegidos (`M4/M5` con `M10`).
7. **Aplicar escala** (`M9`) + sello.
