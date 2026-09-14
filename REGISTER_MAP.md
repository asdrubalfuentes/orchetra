# Contrato de registros Modbus TCP — Orquestación Aysafi

Documento maestro. Define **cómo hablan entre sí** el LOGO! 9, la pasarela LoRa
(`nodeIO_master`), el HMI (`miHMI`), el simulador de PLC (`modbusMaster`) y el
SCADA remoto. Todo lo que se codifique en esos proyectos debe cumplir este
documento. Si algo cambia aquí, se sube `CONTRACT_VERSION` y se actualizan los 4.

`CONTRACT_VERSION = 3` · fecha 2026-09-14
*(v3 — **cambio de rumbo**: el escalado, el filtro EMA, el totalizador día/mes
y la discretización de alarmas de nivel/caudal se mueven del LOGO! al nodo
remoto (`nodeIO`). El gateway (`nodeIO_master`) gana **MAPA A2** con esos
valores ya calculados; el LOGO! pasa de *calcular* a *relayar* — lee MAPA A2 y
lo copia a MAPA B tal cual. El bloque de escalado `hb+20..31` y el coil `cb+8`
quedan **obsoletos**. Los acumulados cambian de escala ×10 a **×1000**. Detalle
completo en el changelog, §8.)*

---

## 1. Topología y roles

```
  Nodos de campo (nodeIO)                Segmento de red de automatización
  ┌───────────┐   LoRa 915 MHz    ┌──────────────────┐
  │ Estación 0│◄────────────────► │  nodeIO_master   │  SERVIDOR Modbus TCP :502
  │  escala +  │                   │  (LoRa Gateway)  │  === MAPA A  (crudo por nodo)
  │  totaliza + ├──────────────────┘  === MAPA A2 (escalado/acumulados/alarma,
  │  alarma    │                                        ya calculado por el nodo)
  ├───────────┤                                       ▲
  │ Estación 1│◄──────────────────────────────────────┘ cliente Modbus TCP
  │  (idem)   │                                         (sondea Mapa A + A2)
  └───────────┘
                                            ┌──────────────────────┐
                                            │  LOGO! 9  (real)     │  SERVIDOR Modbus TCP :502
                                            │   —o—                │  === MAPA B (por estación)
                                            │  PLC-SIM (pruebas)   │  RELAYA A2→B + relés/sirena +
                                            └─────────┬────────────┘  alarmas de enlace/dispositivo
                                                      │ servidor
                              ┌───────────────────────┼───────────────────────┐
                              │ cliente Modbus TCP     │ cliente Modbus TCP (VPN)
                        ┌─────┴──────┐          ┌───────┴────────┐
                        │   miHMI    │          │  SCADA remoto  │
                        │ (lee Mapa B)│         │  (lee Mapa B)  │
                        └────────────┘          └────────────────┘
```

| Nodo | Rol Modbus | Mapa | Puerto | Unit ID |
|---|---|---|---|---|
| `nodeIO_master` (LoRa Gateway) | **Servidor / esclavo** | **A** (crudo, por nodo LoRa) | TCP 502 | 1 |
| LOGO! 9 real | **Servidor / esclavo** | **B** (ingeniería, por estación) | TCP 502 | 1 |
| `modbusMaster` PLC-SIM | **Servidor** (a HMI/SCADA) **+ Cliente** (al Gateway) | **B** hacia arriba, consume **A** | TCP 502 (servidor) | 1 |
| `miHMI` | Cliente / maestro | lee **B** | → 502 | 1 |
| SCADA remoto | Cliente / maestro | lee **B** | → 502 (por VPN) | 1 |

**Acople seguro:** el LOGO! real y el PLC-SIM exponen el **mismo Mapa B, mismo
puerto, mismo Unit ID**. Migrar de simulador a PLC = repuntar la IP en el HMI y
en el SCADA. El registro global `HR 103` indica contra quién se está hablando
(0 = SIM, 1 = LOGO! real).

---

## 2. Convenciones (válidas para Mapa A y Mapa B)

- **Códigos de función:** FC01 leer coils · FC02 leer discrete inputs · FC03 leer
  holding regs · FC04 leer input regs · FC05 escribir coil · FC06/FC16 escribir
  holding · FC15 escribir coils.
- **Direccionamiento:** direcciones **0-based de protocolo** (la que viaja en la
  PDU). En un maestro que muestre 4xxxxx/3xxxxx, sumar 40001 / 30001.
- **Enteros:** 16 bits **big-endian** (estándar Modbus), sin signo salvo que se
  indique `int16`.
- **Valores de 32 bits:** ocupan 2 registros consecutivos, **palabra alta en la
  dirección menor** (word order *hi-first* / "big-endian de palabra").
  Ejemplo: `123456` = `0x0001E240` → `reg[N] = 0x0001`, `reg[N+1] = 0xE240`.
  *(En el PLC-SIM es el flag único `MAPB_WORD_ORDER_HI_FIRST = True`; si al
  programar el LOGO! resulta más cómodo el orden inverso, se cambia aquí y en
  ese flag, y se sube `CONTRACT_VERSION`.)*
- **Escalas de ingeniería:** los físicos analógicos viajan como **entero ×100**
  (2 decimales). Los acumulados como **entero ×10 m³** (0,1 m³ de resolución).
- **Booleanos empaquetados:** además de los discrete inputs, hay *bitfields* en
  holding regs para lectura atómica; `bit0` = LSB.
- **Frescura del dato:** cada bloque de estación lleva "antigüedad en s desde la
  última respuesta LoRa del nodo". `>` umbral ⇒ alarma de dato obsoleto.
- **Sin lectura no significa cero:** un cliente debe distinguir *fallo de
  transacción* de *valor 0*. Usar los bits de enlace/frescura.

---

## 3. MAPA A — Pasarela LoRa (`nodeIO_master`, servidor TCP 502)

Crudo, **sin escalar**, tal cual lo entrega el nodo por LoRa. Es el mismo mapa
que ya implementa `src/modbus_gw.*` sobre RTU; solo se expone además por TCP.
**Congelado byte a byte** — no reordenar.

### 3.1 Bloque por nodo `i = 0..7`, base `b = i * 16`

**Input Registers (FC04)**

| Offset | Campo | Tipo | Notas |
|---|---|---|---|
| `b+0` | AI1 crudo | uint16 | cuentas ADC 0..4095 — **Nivel** |
| `b+1` | AI2 crudo | uint16 | cuentas ADC 0..4095 — **Caudal** |
| `b+2` | AI3 crudo | uint16 | reserva (0) |
| `b+3` | AI4 crudo | uint16 | reserva (0) |
| `b+4` | DI bitfield | uint16 | bit0 DI1 *presostato* · bit1 DI2 *voltaje local* · bit2 DI3 *tamper tapa* · bit3 DI4 reserva |
| `b+5` | Relés bitfield | uint16 | bit0..3 estado RO1..RO4 · bit8..11 = relé deshabilitado ('x'). RO1 = **sirena** |
| `b+6` | Enlace | uint16 | 1 = nodo en línea |
| `b+7` | RSSI | int16 | dBm de la última respuesta |
| `b+8` | Antigüedad | uint16 | s desde la última respuesta (65535 = nunca) |
| `b+9` | Dirección LoRa | uint16 | addr asignada al nodo (0 = slot vacío) |
| `b+10` | FW nodo | uint16 | versión de firmware del nodo (0 si desconocida) |
| `b+11..15` | reserva | uint16 | 0 |

**Discrete Inputs (FC02)** — `b+0..3` = DI1..DI4 · `b+4` = enlace en línea.

**Coils (FC01 / FC05 / FC15)**

| Offset | Campo | Escritura |
|---|---|---|
| `b+0..3` | Consigna relé RO1..RO4 | `1` = cerrar. RO1 = sirena |
| `b+4..7` | Disparo de pulso RO1..RO4 | `1` → el gateway manda `WP` al nodo; auto-limpia en el siguiente ciclo |

### 3.2 Bloque global — Input Registers (FC04)

| Dir | Campo | Notas |
|---|---|---|
| `900` | Marca de protocolo | `0x0203` |
| `901` | Nº de nodos configurados | 0..8 |
| `902` | Nodos en línea | conteo |
| `903` | IO local habilitado | 0/1 |
| `904..907` | AI local del carrier | solo si IO local ON |
| `908` | DI local bitfield | " |
| `909` | Relés local bitfield | " |
| `910..915` | reserva | |

### 3.3 Unit ID y TCP

- Responde a **Unit ID 1**. Peticiones con otro Unit ID: responder igual
  (no hay ambigüedad, es un host dedicado).
- Máx. conexiones TCP simultáneas recomendado: **4** (LOGO! + SIM/diagnóstico +
  margen). El LOGO! usa **1** sola conexión y multiplexa por offset.

### 3.4 MAPA A2 — escalado/totalizador/alarma del nodo (desde v3)

**Nuevo en `CONTRACT_VERSION 3`.** El nodo remoto (`nodeIO` ≥ `1.4.0`) ya no
manda solo crudo — escala, filtra (EMA), totaliza día/mes y discretiza alarma
de nivel/caudal él mismo (calibrado en su propio portal cautivo, ver
`nodeIO/src/channels.cpp`). El gateway relee eso por LoRa y lo publica aquí,
**además** de la §3.1 (que sigue igual, sin tocar).

**Input Registers (FC04), por nodo `i = 0..7`, base `c = 200 + i*16`:**

| Offset | Campo | Tipo | Notas |
|---|---|---|---|
| `c+0` | Nivel escalado | int16 | ×100, ya filtrado (EMA) — **siempre en metros** |
| `c+1` | Caudal escalado | int16 | ×100, ya filtrado — **siempre en m³/h** |
| `c+2..3` | Acumulado día, nivel | int32 | m³ ×1000, hi-first (§2). Solo si el nodo tiene `totDaily` habilitado en ese canal; si no, `0`. |
| `c+4..5` | Acumulado mes, nivel | int32 | ídem, `totMonthly` |
| `c+6..7` | Acumulado día, caudal | int32 | ídem — el que de verdad se usa (nivel no se totaliza en la práctica) |
| `c+8..9` | Acumulado mes, caudal | int32 | ídem |
| `c+10` | `almBits` | uint16 | bit0 nivel.almLo · bit1 nivel.almHi · bit2 caudal.almLo · bit3 caudal.almHi (umbrales configurados en el nodo) |
| `c+11..15` | reserva | uint16 | 0 |

> El nodo **nunca cierra día/mes solo** (sin reloj propio confiable): el
> gateway, con hora real vía SNTP, dispara el cierre por LoRa (`CD`/`CM`,
> automático a medianoche/fin de mes en hora local — ver `nodeIO_master` §
> "cierre automático" más abajo) — el nodo solo acumula y espera ese comando.

---

## 4. MAPA B — Planta / LOGO! (servidor TCP 502) — lo consume el HMI y el SCADA

Ingeniería, **por estación de bombeo**. Lo publica el LOGO! real; el PLC-SIM lo
replica idéntico. `CONTRACT_VERSION` aplica sobre todo a este mapa.

Estaciones: **`s = 0..N-1`**, hoy `N = 2`.

### 4.1 Bloque por estación — Holding Registers (FC03), base `hb = s * 32`

> Lectura para HMI/SCADA. `hb+0..19` son de solo lectura por convención (el LOGO!
> los reescribe cada ciclo, **relayando MAPA A2** desde v3 — ya no los calcula).
> `hb+20..31` (**bloque de escalado**) queda **OBSOLETO desde v3**: la
> calibración vive en el portal del nodo remoto, no en el HMI. Se deja el
> offset reservado (sin uso) para no romper el mapa de un tirón.

| Offset | Campo | Tipo | Unidad |
|---|---|---|---|
| `hb+0` | **Nivel** | uint16 | ×100, **metros** (relay directo de `MAPA A2 c+0`) |
| `hb+1` | **Caudal de bomba** | uint16 | ×100, **m³/h** (relay directo de `MAPA A2 c+1`) |
| `hb+2` | Nivel — crudo | uint16 | eco ADC 0..4095 (diagnóstico) |
| `hb+3` | Caudal — crudo | uint16 | eco ADC 0..4095 |
| `hb+4` | Acumulado del día — palabra alta (W0) | uint16 | 32b, **m³ ×1000** (orden hi-first, §2; cambió de ×10 en v3 — relay directo de `MAPA A2`, sin conversión) |
| `hb+5` | Acumulado del día — palabra baja (W1) | uint16 | " |
| `hb+6` | Acumulado del mes — palabra alta (W0) | uint16 | 32b, **m³ ×1000** |
| `hb+7` | Acumulado del mes — palabra baja (W1) | uint16 | " |
| `hb+8` | Estado (bitfield) | uint16 | bit0 presostato · bit1 voltaje local presente · bit2 tamper/tapa abierta · bit3 DI4 · bit4 sirena activa · bit5 enlace LoRa OK · bit6 estación en alarma · bit7 sirena en AUTO |
| `hb+9` | Alarmas activas (bitfield) | uint16 | ver §4.4 |
| `hb+10` | RSSI LoRa | int16 | dBm |
| `hb+11` | Antigüedad del dato | uint16 | s desde la última respuesta del nodo |
| `hb+12` | Vínculo | uint16 | dirección LoRa / slot del nodo ligado a esta estación |
| `hb+13` | Contador de fallos de lectura | uint16 | acumulado desde el arranque |
| `hb+14` | Alarmas latcheadas / sin reconocer (bitfield) | uint16 | mismos bits que `hb+9`. Se ponen en flanco y **se mantienen** hasta un ACK (`cb+5`) con la causa ya despejada. El HMI las pinta como "pendientes de reconocer". |
| `hb+15..19` | reserva | uint16 | 0 |
| `hb+20..31` | **OBSOLETO desde v3** — bloque de escalado | — | sin uso; calibración en el portal del nodo (`nodeIO`). Puede leerse basura, no tiene significado. |

**Mapa de estaciones (N = 2):** Estación 0 → HR `0..31` · Estación 1 → HR `32..63`.

### 4.2 Bloque por estación — Discrete Inputs (FC02), base `db = s * 16`

> **Opcional desde v2.** Todos estos bits están también en `HR_STATUS` (`hb+8`);
> un servidor (p.ej. el LOGO!, cuya VM no expone FC02 fácilmente) puede omitir
> este bloque. Los clientes deben tolerar que FC02 no responda y usar `HR_STATUS`.

| Offset | Campo |
|---|---|
| `db+0` | Presostato |
| `db+1` | Presencia de voltaje local |
| `db+2` | Tamper / tapa abierta |
| `db+3` | DI4 reserva |
| `db+4` | Enlace LoRa OK |
| `db+5` | Estación en alarma |
| `db+6` | Sirena físicamente activa |
| `db+7` | Dato fresco (antigüedad < umbral) |
| `db+8..15` | reserva |

### 4.3 Bloque por estación — Coils (FC01 / FC05 / FC15), base `cb = s * 16`

**Superficie de comandos — CONGELADA.** Es lo único que un cliente puede
escribir. El LOGO! real y el PLC-SIM deben interpretarlas igual.

| Offset | Comando | Semántica |
|---|---|---|
| `cb+0` | Sirena ON/OFF manual | `1` = ON. Solo efectivo si `cb+1` = 0 (manual) |
| `cb+1` | Sirena en AUTO | `1` = la controla la lógica del LOGO!; `0` = manual |
| `cb+2` | Silenciar alarma | **pulso** (auto-limpia): silencia la sirena hasta la próxima alarma nueva |
| `cb+3` | Reset acumulado del día | **OBSOLETO desde v3** — el LOGO! ya no totaliza, no hay nada que resetear aquí. El cierre de día real lo dispara el gateway al nodo (`CD`, automático por SNTP; ver §3.4). |
| `cb+4` | Reset acumulado del mes | **OBSOLETO desde v3**, ídem con `CM` |
| `cb+5` | Reconocer / resetear alarmas | **pulso** (auto-limpia): borra los bits de `hb+14` cuya causa ya no está presente. No silencia (eso es `cb+2`) ni afecta a alarmas aún activas. |
| `cb+6..7` | reserva | |
| `cb+8` | Aplicar bloque de escalado | **OBSOLETO desde v3** — nada lo lee en el LOGO! |
| `cb+9..15` | reserva | |

> `cb+3/4/8` se dejan reservados (sin efecto) en vez de reasignarlos, para no
> romper un cliente viejo que todavía los escriba — simplemente no pasa nada.

**Mapa de estaciones (N = 2):** Estación 0 → Coils/DI `0..15` · Estación 1 → `16..31`.

### 4.4 Tabla de alarmas (`hb+9` por estación, `HR 99` resumen global)

| Bit | Alarma | Origen |
|---|---|---|
| 0 | Nivel alto | `MAPA A2.almBits` bit1 (nivel.almHi, umbral del nodo) — relay directo, LOGO! solo funde el bit |
| 1 | Nivel bajo | `MAPA A2.almBits` bit0 (nivel.almLo) |
| 2 | Nivel muy bajo (marcha en seco) | **sin fuente desde v3** — el nodo solo tiene un umbral bajo de nivel (`almLo`), no dos niveles. Queda en 0 hasta que se decida un segundo umbral en el nodo, o se retira. |
| 3 | Caudal bajo | `MAPA A2.almBits` bit2 (caudal.almLo) — **redefinido en v3**: antes era "sin caudal con presostato activo" (nadie lo calcula ya); ahora es un simple umbral bajo configurado en el nodo |
| 4 | Falla de presostato | DI2 (presostato), lógica de enlace/dispositivo — **sigue en el LOGO!**, sin cambios |
| 5 | Pérdida de voltaje local | DI2 = 0 — sigue en el LOGO! |
| 6 | Tamper / tapa abierta | DI3 = 1 — sigue en el LOGO! |
| 7 | Pérdida de enlace LoRa | enlace = 0 durante T — sigue en el LOGO! |
| 8 | Dato obsoleto | antigüedad > umbral — sigue en el LOGO! |
| 9 | Config de escala inválida | **sin fuente desde v3** — el LOGO! ya no valida escala (vive en el nodo, que no expone este bit todavía) |
| 10 | Sobre-rango de instrumento | **sin fuente desde v3**, ídem |
| 11 | Caudal alto | **nuevo en v3** — `MAPA A2.almBits` bit3 (caudal.almHi) |
| 12..15 | reserva | |

> **Latcheo (`hb+14`).** Por defecto latchean **bit 2 (marcha en seco)** y **bit 6
> (tamper / tapa abierta)**: una vez despejada la causa siguen marcadas en `hb+14`
> hasta que llega el pulso `cb+5`. El resto de bits son de nivel (se borran al
> desaparecer la causa). La máscara de latcheo es un parámetro del LOGO! / PLC-SIM.

### 4.5 Bloque global — Holding Registers (FC03), base `96`

> **v2:** antes estaba en `IR 2000` (FC04). Se movió a Holding Registers `HR 96`
> porque `IR 2000` cae fuera del rango de VM del LOGO! 9 y los valores calculados
> por el LOGO! viven en VW → Holding Registers. Va justo detrás de las 2
> estaciones (`HR 0..63`), con hueco hasta `HR 95`.

| Dir | Campo | Notas |
|---|---|---|
| `96` | Marca de protocolo Mapa B | `0x0B01` |
| `97` | Nº de estaciones | hoy 2 |
| `98` | Estaciones en línea (bitfield) | bit`s` = 1 si la estación `s` tiene enlace |
| `99` | Alarma general (bitfield) | OR de las alarmas de todas las estaciones |
| `100` | **Heartbeat** | contador que incrementa cada 1 s; el HMI vigila que cambie |
| `101` | Uptime — palabra alta (W0) | 32b, s (orden hi-first, §2) |
| `102` | Uptime — palabra baja (W1) | 32b, s |
| `103` | Origen | 0 = PLC-SIM · 1 = LOGO! real |
| `104` | Versión de lógica / firmware | libre |
| `105` | `CONTRACT_VERSION` | debe coincidir con este documento (= 3) |
| `106..107` | reserva | |

---

## 5. Fórmula de escalado (crudo → ingeniería) — **movida al nodo desde v3**

Hasta `CONTRACT_VERSION 2` la aplicaba el LOGO!/PLC-SIM sobre `hb+20..31`. Desde
v3 la aplica el **nodo remoto** (`nodeIO/src/channels.cpp`), calibrada en su
propio portal cautivo — el LOGO! ya no la calcula, solo relaya el resultado
(§3.4/§4.1). Se deja la fórmula aquí por referencia, es la **misma**, solo
cambió *dónde* corre:

```
si raw_max <= raw_min  →  eng = eng_min      (config inválida, sin bit de alarma expuesto hoy)
eng_x100 = eng_min + (raw - raw_min) * (eng_max - eng_min) / (raw_max - raw_min)
eng_x100 = clamp(eng_x100, min(eng_min,eng_max), max(eng_min,eng_max))

si filtro > 0:
    eng_filt = eng_filt + (eng_x100 - eng_filt) * (1 - filtro/101)   # EMA simple
```

### Valores por defecto del nodo (`nodeIO`, `ChannelCfg`; configurar en terreno)

| Parámetro | Nivel (canal 0) | Caudal (canal 1) |
|---|---|---|
| raw_min / raw_max | 800 / 4000 | 800 / 4000 |
| eng_min / eng_max | 0 / 10000 (100,00 m) | 0 / 10000 (100,00 m³/h) |
| unidad | **fija: metros** | **fija: m³/h** |
| filtro (EMA) | 15 | 15 |
| alarma baja / alta | 500 (5,00 m) / — | — / 9000 (90,00 m³/h) |

---

## 6. Vínculo nodo ↔ estación

Configurable en el PLC-SIM y en el LOGO!. Por defecto **1 a 1 por orden de slot**:

| Estación (Mapa B) | Slot en Mapa A/A2 | Dirección LoRa del nodo |
|---|---|---|
| 0 | nodo `i = 0` | (la que asigne el gateway al adoptar) |
| 1 | nodo `i = 1` | " |

**LOGO! real (desde v3):** relaya `MAPA A2 [200+i*16 + 0..10]` directo a
`MAPA B [s*32 + ...]` (§3.4/§4.1) — sin aplicar §5, el nodo ya lo hizo. Sigue
leyendo `MAPA A [i*16 + 4..9]` (DI, RSSI, edad, dirección) igual que antes.

**PLC-SIM (`modbusMaster`, fuera del alcance de este cambio de rumbo):**
todavía aplica §5 él mismo sobre `MAPA A [i*16 + 0..9]` — no está migrado a
leer `MAPA A2`. Sirve para pruebas de banco del *resto* del contrato, pero no
para probar el escalado/totalizador del nodo — para eso hace falta el nodo
real (o el gateway con `MAPA A2` simulado a mano).

---

## 7. MAPA G — puente del gateway hacia MQTT

Para publicar toda la orquestación por **MQTT** sin cargar más al LOGO! (ver
[`MQTT_BRIDGE.md`](MQTT_BRIDGE.md)), el **`nodeIO_master`** (≥ `1.4.0`) gana dos
bloques nuevos en su servidor Modbus TCP :502, **en direcciones libres** (no
tocan MAPA A ni MAPA B). El LOGO! los usa por su **única** conexión Modbus al
gateway:

- **G.1 — Espejo de MAPA B (Holding Registers, FC03/FC16).** El LOGO! *escribe*
  aquí su MAPA B con **los mismos offsets que la §4**: estación `s` → `HR s*32 +
  k` (= `hb+k`), bloque global → `HR 96..105`. El firmware del gateway lo *lee*
  para publicarlo por MQTT; el HMI/SCADA también pueden leerlo aquí en vez de
  molestar al LOGO!.
- **G.2 — Comandos desde la nube (Coils, FC01/FC05/FC15), base `1000`.** El
  firmware del gateway *escribe* aquí lo que llega por MQTT; el LOGO! los *lee*
  con *Network Input*. Layout por estación `s`, base `1000 + s*16`, **mismos
  offsets que `cb+*` de la §4.3**:

  | Coil | Comando | Igual que |
  |---|---|---|
  | `1000 + s*16 + 0` | Sirena ON manual | `cb+0` |
  | `+1` | Sirena AUTO | `cb+1` |
  | `+2` | Silenciar (pulso) | `cb+2` |
  | `+3` / `+4` | **obsoleto desde v3**, igual que `cb+3`/`cb+4` | `cb+3` / `cb+4` |
  | `+5` | ACK de alarmas (pulso) | `cb+5` |
  | `+8` | **obsoleto desde v3**, igual que `cb+8` | `cb+8` |
  | `+9` | Armar reset | `cb+9` |

  Los pulsos los **auto-limpia el firmware del gateway** un ciclo después de
  reflejarlos (para que el flanco llegue al LOGO! una sola vez).

**Fusión de comandos en el LOGO!.** Hay dos orígenes de mando:

- *Fase A (incremental):* el HMI sigue escribiendo `cb+*` directo en el LOGO!;
  el LOGO! hace `OR` de `cb+X` (HMI) con el coil de G.2 (MQTT).
- *Fase B (objetivo):* el HMI también escribe en G.2 del gateway; el LOGO! tiene
  **un solo origen de mando** (Network Input desde G.2) y pierde esa conexión
  entrante. Recomendado a futuro.

**Escrituras a nodos desde MQTT** (relés `WR`/`WP`) no usan G.2: el firmware del
gateway ya tiene esa ruta (coils `i*16 + 0..7` del MAPA A → LoRa) y la reusa.

Esto es una **adición compatible** (direcciones nuevas, no sube
`CONTRACT_VERSION`). La escala Modbus de los valores es la de la §4; el bridge
MQTT publica además la versión en ingeniería (float) — detalle en `MQTT_BRIDGE.md`.

---

## 8. Versionado del contrato

- `CONTRACT_VERSION` vive en este documento y se refleja en `HR 105` del Mapa B.
- Cambios **compatibles** (añadir campos en reservas): no sube la versión, se
  anota en el changelog de abajo.
- Cambios **incompatibles** (mover/reinterpretar un campo, cambiar endianness o
  escalas): sube `CONTRACT_VERSION` y se actualizan los 4 proyectos + el LOGO!.

### Changelog

| Versión | Fecha | Cambio |
|---|---|---|
| 1 | 2026-09-02 | Versión inicial. Mapa A congelado desde `nodeIO_master/src/modbus_gw.*`. Mapa B nuevo: 2 estaciones, señales Nivel/Caudal + presostato/voltaje/tamper + sirena, escalado en `hb+20..31`, comandos en coils `cb+0..8`, global en `IR 2000..2009`. |
| 2 | 2026-09-03 | **Perfil LOGO! 9.** Bloque global movido de `IR 2000..2009` (FC04) a `HR 96..107` (FC03) — cabe en la VM del LOGO!. Discrete Inputs FC02 (§4.2) pasan a **opcionales** (sus bits ya están en `HR_STATUS`). Sin cambios en estaciones, escalado ni comandos. Migrados: `plc_sim.py`, `miHMI`, `tools/mapb_check.py`. |
| — | 2026-09-09 | *Adición compatible (no sube `CONTRACT_VERSION`, ocupa reservas):* `cb+5` = ACK/reset de alarmas · `hb+14` = bitfield de alarmas latcheadas. Latcheo por defecto: marcha en seco + tamper. Receta de construcción del programa del LOGO!: [`PLC_REGISTER_RECIPE.md`](PLC_REGISTER_RECIPE.md). |
| — | 2026-09-10 | *Adición compatible (direcciones nuevas):* **§7 MAPA G** — espejo de MAPA B (`HR`) + comandos desde la nube (`Coils 1000+`) en el servidor del `nodeIO_master`, para el puente MQTT ([`MQTT_BRIDGE.md`](MQTT_BRIDGE.md)). El LOGO! no gana conexiones. |
| **3** | **2026-09-14** | **Cambio de rumbo — incompatible.** Escalado, filtro EMA, totalizador día/mes y alarma de nivel/caudal se mueven del LOGO! al **nodo remoto** (`nodeIO` ≥ `1.4.0`, calibrado en su portal cautivo). Nuevo **§3.4 MAPA A2** (`IR 200+i*16`) en el gateway (`nodeIO_master` ≥ `1.5.0`) con esos valores ya calculados; el LOGO! pasa de calcular a *relayar*. **Incompatible:** acumulados `hb+4..7` cambian de m³ ×10 a **m³ ×1000**; `hb+20..31` (bloque de escala) y `cb+3/4/8` quedan **obsoletos**; tabla de alarmas `hb+9` reordenada (bit 2/9/10 sin fuente por ahora, bit 3 redefinido a "caudal bajo", bit 11 nuevo "caudal alto"). Nivel siempre en **metros**, caudal siempre en **m³/h** (`hb+28/29` dejan de leerse). El gateway cierra día/mes automático por SNTP (comandos LoRa `CD`/`CM`) — el nodo nunca cierra solo. Migrados: `nodeIO`, `nodeIO_master` (incl. `mqtt_bridge`), `miHMI`, `tools/mapb_check.py`. **Sin migrar** (fuera del alcance): `modbusMaster`/PLC-SIM, sigue aplicando §5 él mismo sobre MAPA A crudo — válido para probar el resto del contrato, no el escalado del nodo. |
