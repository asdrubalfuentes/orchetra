# Lógica del PLC LOGO! 9 — Orquestación Aysafi

Programa del **Siemens LOGO! 9** (LOGO! Soft Comfort V9). **Desde
`CONTRACT_VERSION 3`** (cambio de rumbo 2026-09) el LOGO! ya **no** escala,
filtra ni totaliza — eso lo hace el **nodo remoto** (`nodeIO`, ver
`nodeIO/src/channels.cpp` y su portal cautivo). El LOGO! ahora: relee **MAPA
A2** del gateway (nivel/caudal ya escalados + acumulados + alarma de proceso,
ya calculados) y lo **relaya** a MAPA B, combina eso con las alarmas de
enlace/dispositivo que sí sigue calculando él, gobierna la sirena y
lee/escribe relés. Ver [`REGISTER_MAP.md` §3.4](REGISTER_MAP.md) para el
detalle de MAPA A2 y el changelog completo del cambio de rumbo.

## 0. Realidad de la herramienta (léelo antes)

- **LOGO! Soft Comfort V9 programa en FBD o LAD. No existe Structured Text / SCL**
  en LOGO!. Por tanto este documento entrega:
  1. La **especificación funcional** exacta.
  2. **Pseudocódigo tipo ST** — referencia inequívoca de la lógica, **no cargable**.
  3. Una **guía de construcción en FBD** bloque a bloque.
- LOGO! 9: analógicos en **coma flotante 32-bit**, bloque **Float Mathematic**,
  hasta 800 bloques, IEC-CRA security. Todo lo de abajo asume el formato float.
- **LOGO! Modbus TCP** (confirmado en V9): el LOGO! es a la vez **servidor**
  (publica el MAPA B) y **cliente** — vía *Network Input/Output → Modbus* lee el
  MAPA A del gateway y le escribe la sirena de vuelta. Ver §1.
- Direcciones Modbus: **0-based de PDU** (las que viajan en el frame). El diálogo
  de mapeo de LSC puede mostrarlas como `4xxxx`/`3xxxx` (1-based).

---

## 1. Arquitectura con el LOGO! real

```
  nodos LoRa (nodeIO) ──LoRa──► nodeIO_master ──Modbus TCP──►  LOGO! 9
  escala+totaliza+alarma        (LoRa Gateway)  MAPA A  (:502)   │  cliente Modbus: LEE MAPA A (DI/RSSI/
                                                MAPA A2 (:502)   │  edad) y MAPA A2 (nivel/caudal ya
                                                servidor         │  escalados + acumulados + almBits)
                                                                 │  programa FBD: RELAYA A2→B + alarmas
                                                                 │  de enlace/dispositivo + sirena
                                                                 │  servidor Modbus: MAPA B (:502)
  HMI / SCADA ──Modbus TCP──► leen el MAPA B del LOGO! ◄─────────┘
```

El LOGO! 9 hace **de las dos cosas a la vez**:
- **cliente** Modbus TCP → sondea MAPA A (crudo/DI/enlace) **y MAPA A2** (ya
  escalado) del gateway y los mete en su VM;
- **servidor** Modbus TCP → publica el MAPA B (relay de A2 + lo que sí calcula
  él: alarmas de enlace/dispositivo, sirena) para el HMI y el SCADA.

Zonas de VM:

| Zona | Quién escribe | Quién lee | Contenido |
|---|---|---|---|
| **ENTRADA (crudo, MAPA A)** | el propio LOGO! (Network Input Modbus) | el programa FBD | por estación: DI (presostato/voltaje/tamper), enlace, RSSI, edad — nivel/caudal raw quedan de diagnóstico, ya no alimentan ningún cálculo |
| **ENTRADA (MAPA A2, desde v3)** | el propio LOGO! (Network Input Modbus) | el programa FBD (solo relay) | nivel/caudal ya escalados, 4 acumulados, `almBits` — ver [`REGISTER_MAP.md` §3.4](REGISTER_MAP.md) |
| **MAPA B** | el programa FBD (relay de A2 + alarmas propias + sirena; coils de comando los escribe el HMI) | HMI, SCADA | nivel/caudal, acumulados, estado, alarmas, RSSI, edad. `hb+20..31` (bloque de escala) **obsoleto**, no se toca |

### Cómo entra el MAPA A al LOGO!  (confirmado: LOGO! cliente Modbus)

> **Direccionamiento (importante).** El gateway sirve los registros **0-based**
> (dirección de PDU: `AI1` del nodo 0 = registro `0` en el cable). **LOGO! Soft
> Comfort es 1-based**: en su diálogo hay que poner `registro_LOGO = registro_gateway + 1`.
> Verificado en campo: donde la tabla dice "registro 0", en el LOGO! se escribe **1**.

En LSC V9, *Instrucciones → Network Input → Modbus*, **por cada estación** `s`:

| Parámetro | Valor |
|---|---|
| Dispositivo remoto | IP **fija** del gateway `nodeIO_master`, puerto `502`, Unit ID `1` |
| Función | **FC04 — Read Input Registers** (el gateway **no tiene Holding Registers**; con FC03 no lee nada) |
| Dirección de inicio (en el LOGO!, 1-based) | `slot·16 + 1` → estación 0 → **1**, estación 1 → **17** |
| Cantidad | 11 (cubre offsets 0..10 del bloque de nodo) |
| Destino | `NAI`/`VW` de la zona de ENTRADA (§2.1) |
| Periodo de sondeo | 500–1000 ms |

Registro por registro (estación 0; para la 1 sumar 16):

| Campo | Registro gateway (cable) | **Registro en el LOGO!** |
|---|---|---|
| AI1 = nivel raw | 0 | **1** |
| AI2 = caudal raw | 1 | **2** |
| DI bitfield (b0 presostato, b1 volt, b2 tamper, b3 DI4) | 4 | **5** |
| enlace (0/1) | 6 | **7** |
| RSSI (int16) | 7 | **8** |
| edad (s) | 8 | **9** |
| dirección LoRa | 9 | **10** |

Bloque **global** del MAPA A: marca `0x0203` en registro `900` (cable) → **`901`** en el LOGO!.

### MAPA A2 — nivel/caudal/acumulados/alarma ya calculados (desde v3)

Mismo dispositivo (el gateway), **mismo objeto de conexión Modbus** que ya usas
para MAPA A — solo agregas filas a su tabla de transferencia. Base gateway
`c = 200 + slot·16`; en LSC (1-based) = `c+1`. Por estación (slot 0; para el
slot 1 sumar 16 al origen y 64 al destino VW — mismo patrón que MAPA B):

| Campo | Registro gateway (cable) | LSC (1-based) | Palabras | Destino VW | Nota |
|---|---|---|---|---|---|
| Nivel + caudal escalados | `200` | **201** | 2 | `VW0` | **copia directa**, sin fórmula — el nodo ya lo escaló |
| Acumulado día | `202` | **203** | 2 | `VW8` (`VD8`) | copia directa (m³ ×1000, mismo que publica MAPA B — sin conversión) |
| Acumulado mes | `204` | **205** | 2 | `VW12` (`VD12`) | ídem |
| `almBits` | `210` | **211** | 1 | `VW544` (scratch) | ver fusión de alarmas, §5 |

Estación 1 (slot 1, base gateway `216`): `IR217`→`VW64`, `IR219`→`VW72`
(`VD72`), `IR221`→`VW76` (`VD76`), `IR227`→`VW546`.

> Nada de esto pasa por ningún `Float Mathematic` — es relay puro. El único
> bloque que sigue existiendo es la fusión de `almBits` en `Alarmas` (§5).

**Escritura de la sirena de vuelta al nodo:** *Network Output → Modbus*, **FC05**
(escribir 1 coil), dispositivo = el mismo gateway, coil `slot·16 + 0` (cable) →
**`slot·16 + 1`** en el LOGO!, valor = `sirena[s]` (§6).
Si tu V9 no permite *Network Output* Modbus, cablea la sirena a un **`Q` local**.

> El gateway obtiene la IP por DHCP. Fíjala (portal → *WiFi de planta (STA)* →
> *IP fija*, o reserva en el router) para que el LOGO! no pierda el enlace al
> renovarse el DHCP.

---

## 2. Mapa VM ↔ Modbus (perfil LOGO!, `CONTRACT_VERSION 3`)

`CONTRACT_VERSION 2` = el MAPA B v1 con **dos ajustes obligados por el LOGO!**:

1. **El bloque global pasa de Input Registers `IR 2000` a Holding Registers `HR 96`**
   (los valores calculados por el LOGO! viven en VW → Holding Registers; e
   `IR 2000` cae fuera del rango de VM).
2. **Los Discrete Inputs (FC02) son opcionales** — sus bits ya están en
   `HR_STATUS`. El LOGO! puede no exponerlos.

Convención LOGO!: **Holding Register PDU `N` ↔ `VW(2·N)`** (VW par). Confírmalo en
el diálogo *Parámetros de red / Modbus* de LSC V9 (muestra el mapeo real).

### 2.1 Zona ENTRADA (crudo del MAPA A) — VW a elección, aquí desde VW400

Por estación `s = 0..1`, base `e = 400 + s·16` (VW):

| VW | Campo | Origen (MAPA A del gateway, nodo `slot`) |
|---|---|---|
| `e+0` | nivel raw (AI1, 0..4095) | `IREG slot*16 + 0` |
| `e+2` | caudal raw (AI2) | `IREG slot*16 + 1` |
| `e+4` | DI bitfield (b0 presostato, b1 volt local, b2 tamper) | `IREG slot*16 + 4` |
| `e+6` | enlace (0/1) | `IREG slot*16 + 6` |
| `e+8` | RSSI (int16) | `IREG slot*16 + 7` |
| `e+10` | edad (s) | `IREG slot*16 + 8` |
| `e+12` | dirección LoRa | `IREG slot*16 + 9` |

### 2.2 Zona MAPA B — Holding Registers (FC03)

Por estación `s`, base `b = s·32` (HR PDU) ↔ `VW(2·b)`:

| HR | Campo | Tipo | Notas |
|---|---|---|---|
| `b+0` | Nivel ×100 | int16 | **relay directo** desde MAPA A2 (ya escalado por el nodo, §3) |
| `b+1` | Caudal ×100 | int16 | **relay directo** desde MAPA A2 |
| `b+2` | Nivel raw (eco) | uint16 | copia de la zona ENTRADA |
| `b+3` | Caudal raw (eco) | uint16 | |
| `b+4..5` | Acumulado día, m³ **×1000** | int32 (VD, palabra alta primero) | **relay directo** desde MAPA A2 (§4) — cambió de ×10 en v3 |
| `b+6..7` | Acumulado mes, m³ **×1000** | int32 (VD) | ídem |
| `b+8` | Estado (bitfield) | uint16 | b0 presostato · b1 volt local · b2 tamper · b3 reserva · b4 sirena activa · b5 enlace OK · b6 en alarma · b7 sirena AUTO |
| `b+9` | Alarmas (bitfield) | uint16 | §5 |
| `b+10` | RSSI | int16 | eco |
| `b+11` | Edad del dato | uint16 | eco |
| `b+12` | Vínculo (dir. LoRa) | uint16 | eco |
| `b+13` | Contador de fallos de lectura | uint16 | opcional |
| `b+14` | Alarmas latcheadas (bitfield) | uint16 | flanco + hold hasta ACK (`cb+5`); ver §5 |
| `b+20..31` | **OBSOLETO desde v3** | — | calibración movida al portal del nodo (`nodeIO`); no toques este rango |

Estación 0 → HR `0..31` (VW0..VW62). Estación 1 → HR `32..63` (VW64..VW126).

> **Bitfields (`Estado`, `Alarmas`, `hb+14`, `HR98`):** para mapear un bit a un
> `VWx` en LOGO!, la dirección de bit correcta es **`V(x+1).n`** para bits
> `0..7` y **`Vx.(n-8)`** para bits `8..15` — no `Vx.n` a secas. Detalle y
> ejemplo verificado en campo: **§5 "En FBD, por estación"** más abajo.

### 2.3 Bloque global — Holding Registers, base `HR 96` (VW192)

| HR | Campo | Valor |
|---|---|---|
| `96` | Marca de protocolo | `0x0B01` (constante) |
| `97` | Nº de estaciones | `2` |
| `98` | Estaciones en línea (bitfield, bit`s`) | del enlace de cada estación |
| `99` | Alarma general (OR de `HR_ALARMS` de todas) | |
| `100` | **Heartbeat** | contador +1 cada segundo |
| `101..102` | Uptime (s, int32) | contador de segundos |
| `103` | Origen | **`1` = LOGO! real** (constante) |
| `104` | Versión de lógica | libre (p.ej. `1`) |
| `105` | `CONTRACT_VERSION` | **`3`** (subir la constante `VW210` si venías de v2) |

### 2.4 Comandos — Coils (FC01/05), base `s·16`

Los coils Modbus del LOGO! se mapean a marcas `M` que el programa lee.

| Coil | Comando | Semántica |
|---|---|---|
| `s·16 + 0` | Sirena ON manual | efectivo solo si `cb+1 = 0` |
| `s·16 + 1` | Sirena AUTO | `1` = la controla la lógica |
| `s·16 + 2` | Silenciar (pulso) | el LOGO! lo auto-limpia |
| `s·16 + 3` | **OBSOLETO desde v3** | el LOGO! ya no totaliza; el cierre real lo dispara el gateway al nodo por SNTP |
| `s·16 + 4` | **OBSOLETO desde v3** | ídem |
| `s·16 + 5` | Reconocer / resetear alarmas (pulso) | borra `HR b+14` con la causa despejada |
| `s·16 + 8` | **OBSOLETO desde v3** | nada lo lee |
| `s·16 + 9` | Armar reset | sin uso (solo protegía `cb+3`/`cb+4`, ambos obsoletos) |

---

## 3. Escalado crudo → ingeniería — **movido al nodo desde v3**

Ya no corre en el LOGO!. El nodo remoto (`nodeIO/src/channels.cpp`) escala,
filtra (EMA) y publica el resultado en MAPA A2; el LOGO! solo lo copia a
`hb+0`/`hb+1` (ver §1, sección "MAPA A2"). La fórmula (idéntica, solo cambió
de sitio) y los valores por defecto están en
[`REGISTER_MAP.md` §5](REGISTER_MAP.md). Calibración: portal cautivo del nodo,
no la página de rangos del HMI (que se eliminó).

## 4. Totalizador de acumulados — **movido al nodo desde v3**

Ya no corre en el LOGO!. El nodo integra caudal → m³/día y m³/mes-en-curso
(mismo factor `k` por unidad que documentaba esta sección, ahora en
`nodeIO/src/channels.cpp`), persistido en su propia NVS. El LOGO! solo copia
el resultado a `hb+4..7` (MAPA A2 → MAPA B, sin conversión — ambos ya en
m³ ×1000). El nodo **nunca cierra día/mes solo** (sin reloj propio confiable):
el gateway, con hora real por SNTP, se lo dispara por LoRa (`CD`/`CM`,
automático al cruzar medianoche/fin de mes en hora local) — ver
`nodeIO_master`, `dayMonthScheduler()`. Los coils `cb+3`/`cb+4`/`cb+8` del
LOGO! quedaron obsoletos, nada los lee.

---

## 5. Árbol de alarmas  (bitfield `HR b+9`) — parte nodo, parte LOGO! desde v3

| Bit | Alarma | Origen desde v3 | Condición / retardo |
|---|---|---|---|
| 0 | Nivel alto | **nodo** (`MAPA A2.almBits` bit1) | umbral configurado en el nodo |
| 1 | Nivel bajo | **nodo** (bit0) | ídem |
| 2 | Nivel muy bajo (marcha en seco) | *sin fuente* | el nodo solo tiene 1 umbral bajo, no 2 |
| 3 | Caudal bajo | **nodo** (bit2) — antes "sin caudal con presostato" | umbral configurado en el nodo |
| 4 | Falla de presostato | **LOGO!** (sin cambios) | `volt_local AND NOT presostato`, `T_pressfail` (15 s) |
| 5 | Pérdida de voltaje local | **LOGO!** | `NOT volt_local` |
| 6 | Tamper / tapa abierta | **LOGO!** | `tamper` |
| 7 | Pérdida de enlace LoRa | **LOGO!** | `NOT enlace`, `T_loraloss` (20 s) |
| 8 | Dato obsoleto | **LOGO!** | `edad > T_stale` (15 s) |
| 9 | Config de escala inválida | *sin fuente* | el LOGO! ya no valida escala |
| 10 | Sobre-rango de instrumento | *sin fuente* | ídem |
| 11 | Caudal alto | **nodo** (bit3) — nuevo en v3 | umbral configurado en el nodo |

### Pseudocódigo — solo lo que sigue calculando el LOGO! (bits 4,5,6,7,8)

```
al := 0
IF TON(volt_local AND NOT presostato, T_pressfail)  THEN al := al OR ALM_PRESS_FAIL END_IF
IF NOT volt_local THEN al := al OR ALM_VOLT_LOSS END_IF
IF tamper        THEN al := al OR ALM_TAMPER    END_IF
IF TON(NOT enlace, T_loraloss)  THEN al := al OR ALM_LORA_LOSS END_IF
IF edad > T_stale THEN al := al OR ALM_STALE END_IF
al := al OR nivel_alto_del_nodo OR nivel_bajo_del_nodo OR caudal_bajo_del_nodo OR caudal_alto_del_nodo
B[s].alarmas := al
```

### En FBD, por estación — regla de bit (la misma para todo `Vx.n`)

`VWx` son 2 bytes (`x` alto, `x+1` bajo); el bit-address de LOGO! (`V<byte>.<bit>`)
direcciona **byte**, no la palabra completa. **Verificado en campo
(2026-09-12): mapear a `Vx.n` escribe el bit en el byte alto → aporta
`256·2^n`, no `2^n`.** Regla correcta:
- bit `0..7` del valor (`1..128`) → **`V(x+1).n`** (byte bajo)
- bit `8..15` del valor (`256..32768`) → **`Vx.(n-8)`** (byte alto)

**Bits 4,5,6,7,8** (LOGO!, sin cambios de v2): 5× **On-Delay/Comparator**
directos, empaquetados en el byte bajo de `HR9`/`VW18` → `V19.4…V19.8`.

**Bits 0,1,3,11** (fusión con el nodo, **as-built** — estación 0):
la señal cruda `almBits` del nodo llega por *Network Input* a `VW544` (scratch,
§1 "MAPA A2"); sus bits 0-3 viven en el byte bajo → se leen de **`V545.n`**.
De ahí, cada uno se cablea directo (sin comparador, ya viene discretizado del
nodo) al bit de `Alarmas` que le toca:

| Bit del nodo (`almBits`) | Leer de | Escribir a (`Alarmas`, `VW18`) |
|---|---|---|
| bit0 nivel.almLo | `V545.0` | `V19.1` (LEVEL_LO) |
| bit1 nivel.almHi | `V545.1` | `V19.0` (LEVEL_HI) |
| bit2 caudal.almLo | `V545.2` | `V19.3` (bit 3, "Caudal bajo") |
| bit3 caudal.almHi | `V545.3` | `V18.3` (bit 11 = byte **alto** de `VW18`, bit `11-8=3`) |

Estación 1: `almBits` llega a `VW546` → leer de `V547.n`; destino `Alarmas` es
`VW82` (byte bajo `83`, byte alto `82`) → mismos offsets de bit: bits 0/1/3 a
`V83.*`, bit 11 (caudal alto) a `V82.3`.

- **OR** de los 12 bits usados → bit 6 de `HR_STATUS` (`en alarma`) y entra al `HR 99` global.

### Latcheo y reconocimiento (`HR b+14`, coil `cb+5`)

```
FOR cada bit b EN MASCARA_LATCH:            // por defecto: LEVEL_LOLO, TAMPER
   IF flanco_subida(al.b) THEN latch[s].b := TRUE END_IF
   IF NOT al.b AND pulso(cb[s].ACK) THEN latch[s].b := FALSE END_IF
B[s].latched := latch[s]                    // -> HR b+14
```

FBD: por cada bit latcheable, un **RS flip-flop** (Set = alarma activa, Reset =
`ACK AND NOT alarma`). Empaqueta las salidas en `VW(b+14)` igual que `HR b+9`.
El HMI resta `hb+14` de la sirena silenciada: una alarma latcheada no vuelve a
sonar sola, pero sigue visible hasta el ACK.

---

## 6. Lógica de sirena  (por estación)

### Pseudocódigo

```
alarma_activa := (B[s].alarmas AND MASCARA_SIRENA) <> 0     // MASCARA por defecto = todos menos STALE
nuevos := B[s].alarmas AND NOT alarmas_prev[s]
IF nuevos <> 0 THEN silenciada[s] := FALSE END_IF
IF NOT alarma_activa THEN silenciada[s] := FALSE END_IF
IF pulso(cb[s].SILENCE) THEN silenciada[s] := TRUE END_IF

IF cb[s].SIREN_AUTO THEN
   sirena[s] := alarma_activa AND NOT silenciada[s]
ELSE
   sirena[s] := cb[s].SIREN_MANUAL
END_IF
alarmas_prev[s] := B[s].alarmas

// salida física
Q_sirena[s]  := sirena[s]                 // relé local del LOGO!  (o…)
gw_coil[s]   := sirena[s]                 // …y escribir el coil RO1 del nodo (Network Output Modbus, FC05)
B[s].estado.bit4 := sirena[s]
B[s].estado.bit7 := cb[s].SIREN_AUTO
```

### En FBD

- **RS flip-flop** `SIL`: Set = pulso `SILENCE`; Reset = flanco de "nueva alarma"
  (compara `alarmas` con su valor anterior guardado en `AM`) **OR** `NOT
  alarma_activa`.
- **AND** `alarma_activa AND NOT SIL` → rama AUTO.
- **Analog/Digital MUX** o simple **selector con `SIREN_AUTO`**: AUTO→rama de
  arriba, MANUAL→`SIREN_MANUAL`.
- Salida → **`Q1`** (relé del LOGO! a la sirena física) y, si el LOGO! escribe al
  gateway, a la *Network Output / Modbus write* del coil `slot*16 + 0`.

---

## 7. Bloque global  (`HR 96..105`)

```
HR96  := 16#0B01                        // constante
HR97  := 2                              // constante
HR98  := (enlace[0]?1:0) OR (enlace[1]?2:0)
HR99  := B[0].alarmas OR B[1].alarmas
ON pulso_1s: HR100 := HR100 + 1         // heartbeat
             uptime := uptime + 1
HR101..102 := uptime (int32)
HR103 := 1                              // origen = LOGO! real
HR104 := 1                              // versión de lógica
HR105 := 3                              // CONTRACT_VERSION
```

FBD: **Up Counter** sobre `HR100` y `uptime` disparado por `P1s`; el resto son
constantes o un **OR** de bits mapeado a VW.

> `HR98 = VW196`: sus bits `0`/`1` (enlace est.0/est.1) van al **byte bajo**,
> es decir **`V197.0`** / **`V197.1`** — no `V196.0`/`V196.1` (ver regla de
> bits en §5 "En FBD, por estación" / verificado en campo 2026-09-12).

---

## 8. Construcción en LOGO! Soft Comfort V9 — pasos

1. **Nuevo proyecto** → elige el BM de tu LOGO! 9. En *Configuración de red*
   fija su IP (la que puso el HMI en `PLC_HOST`).
2. **Propiedades del proyecto → Comunicación**:
   - Activa **Modbus** (servidor). Anota/ajusta el **mapeo VM ↔ registro** — es la
     tabla de §2. Confirma que `HR0 = VW0`, `HR1 = VW2`, …
   - Configura el **Network Input Modbus** que lee el gateway (§1) y el
     **Network Output Modbus** que escribe la sirena.
   - Deja **OPC UA** activado si el SCADA lo va a usar (perfil DA).
3. **Marcas retentivas**: marca como retentivas las VW/VD de acumulados, sello de
   config y parámetros de escala (para que sobrevivan a un corte).
4. **Coloca los bloques** por estación siguiendo §3–§7. Usa **UDF** (bloque de
   usuario) para "una estación" y **instáncialo 2 veces** — ahorra la mitad del
   trabajo y de los 800 bloques.
5. **Parámetros**: los de [`PLC_REGISTER_RECIPE.md §7`](PLC_REGISTER_RECIPE.md)
   (umbrales de alarma, tiempos `TON`, `MARGEN_PCT`, máscara de sirena y de
   latcheo, escala por defecto, factor `k`) — deben coincidir con el PLC-SIM.
6. **Textos de aviso** (opcional): mensajes en la pantalla del BM por alarma.
7. **Simulación** (LSC V9 trae emulador con comunicación de red): comprueba
   escalado, alarmas, sirena y totalizador antes de descargar.
8. **Descarga** al LOGO! por Ethernet. Verifica con
   `python ORCHESTRATION/tools/mapb_check.py --host <IP_LOGO> --port 502` →
   debe dar **0 FAIL** y `origen = LOGO! real`, `CONTRACT_VERSION = 3`.

---

## 9. Cambios acompañantes (fuera de este documento)

| Dónde | Cambio | Estado |
|---|---|---|
| `REGISTER_MAP.md` | `CONTRACT_VERSION 2`: bloque global a `HR 96..105`; FC02 opcional | **hecho** |
| `modbusMaster/plc_sim.py` | global a `HR 96`; `contract` = 2 | **hecho** (reinicia `python app.py` para cargarlo) |
| `miHMI` | leer el global por `HR 96`; `CONTRACT_VERSION 2` | **hecho** — recompilar/flashear |
| `tools/mapb_check.py` | global por `HR`; acepta FC02 ausente; espera `CONTRACT_VERSION 2`; imprime `hb+14` y verifica que `cb+5` (ACK) se auto-limpia | **hecho** (verificado 0 FAIL con `--write`) |
| `REGISTER_MAP.md` / `plc_sim.py` / `miHMI` / `mapb_check.py` | adición compatible `cb+5` (ACK de alarmas) + `hb+14` (alarmas latcheadas); latcheo por defecto `{LEVEL_LOLO, TAMPER}` | **hecho** — no sube `CONTRACT_VERSION` |
| [`PLC_REGISTER_RECIPE.md`](PLC_REGISTER_RECIPE.md) | hoja de construcción literal (VW/VD/M ↔ Modbus) + §7 parámetros por defecto + §10 puente MQTT | **hecho** |
| `nodeIO_master` | ninguno en el MAPA A (el OTA por comando LoRa no toca el Modbus) | **no necesario** para el control |
| **Puente MQTT** ([`MQTT_BRIDGE.md`](MQTT_BRIDGE.md) · [`REGISTER_MAP.md §7`](REGISTER_MAP.md)) | el LOGO! espeja MAPA B en el gateway (Network Output FC16) y lee de ahí los comandos de la nube (Network Input FC01), por su conexión Modbus actual. FBD extra en [`PLC_REGISTER_RECIPE.md §10`](PLC_REGISTER_RECIPE.md) | **firmware del gateway hecho** (`nodeIO_master` ≥ `1.4.0`); FBD del LOGO! pendiente |
| **v3 — cambio de rumbo** ([`REGISTER_MAP.md` §3.4/§8](REGISTER_MAP.md)) | escalado/totalizador/alarma de proceso al nodo (`nodeIO` ≥ `1.4.0`); gateway gana MAPA A2 (`nodeIO_master` ≥ `1.5.0`) + cierre automático de día/mes por SNTP; LOGO! simplificado a relay + alarmas de enlace/dispositivo (este documento); `miHMI` sin página de rangos + histórico de 6 meses (`miHMI` ≥ `0.5.0`) | **firmwares y docs hechos; construcción en LSC hecha por el usuario (§1 MAPA A2, §5 fusión de alarmas) — pendiente `hb+0..7`/alarmas estación 1 y verificación de punta a punta con hardware real** |

---

## Apéndice — constantes de bits (para el mapeo VM y el pseudocódigo)

```
Estado (HR b+8):  PRESOSTATO=1  VOLT_LOCAL=2  TAMPER=4  (b3 reserva=8)
                  SIREN_ON=16  LINK_OK=32  IN_ALARM=64  SIREN_AUTO=128

Alarmas (HR b+9): LEVEL_HI=1  LEVEL_LO=2  LEVEL_LOLO=4  NO_FLOW=8  PRESS_FAIL=16
                  VOLT_LOSS=32  TAMPER=64  LORA_LOSS=128  STALE=256
                  SCALE_BAD=512  OVERRANGE=1024
```
