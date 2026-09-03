# Contrato de registros Modbus TCP — Orquestación Aysafi

Documento maestro. Define **cómo hablan entre sí** el LOGO! 9, la pasarela LoRa
(`nodeIO_master`), el HMI (`miHMI`), el simulador de PLC (`modbusMaster`) y el
SCADA remoto. Todo lo que se codifique en esos proyectos debe cumplir este
documento. Si algo cambia aquí, se sube `CONTRACT_VERSION` y se actualizan los 4.

`CONTRACT_VERSION = 2` · fecha 2026-09-03
*(v2: el bloque global pasa de Input Registers `IR 2000` a Holding Registers
`HR 96` para que quepa en la VM del LOGO! 9; los Discrete Inputs FC02 pasan a
opcionales. El resto es idéntico a v1.)*

---

## 1. Topología y roles

```
  Nodos de campo (nodeIO)                Segmento de red de automatización
  ┌───────────┐   LoRa 915 MHz    ┌──────────────────┐
  │ Estación 0│◄────────────────► │  nodeIO_master   │  SERVIDOR Modbus TCP :502
  │  (nodo)   │                   │  (LoRa Gateway)  │  === MAPA A (crudo por nodo)
  ├───────────┤                   └────────┬─────────┘
  │ Estación 1│◄───────────────────────────┘         ▲
  │  (nodo)   │                                       │ cliente Modbus TCP (sondea Mapa A)
  └───────────┘                                       │
                                            ┌─────────┴──────────┐
                                            │  LOGO! 9  (real)   │  SERVIDOR Modbus TCP :502
                                            │   —o—              │  === MAPA B (ingeniería/estación)
                                            │  PLC-SIM (pruebas) │  + lógica, integraciones, alarmas
                                            └─────────┬──────────┘
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

---

## 4. MAPA B — Planta / LOGO! (servidor TCP 502) — lo consume el HMI y el SCADA

Ingeniería, **por estación de bombeo**. Lo publica el LOGO! real; el PLC-SIM lo
replica idéntico. `CONTRACT_VERSION` aplica sobre todo a este mapa.

Estaciones: **`s = 0..N-1`**, hoy `N = 2`.

### 4.1 Bloque por estación — Holding Registers (FC03), base `hb = s * 32`

> Lectura para HMI/SCADA. `hb+0..19` son de solo lectura por convención (el LOGO!
> los reescribe cada ciclo). `hb+20..31` (**bloque de escalado**) son de
> lectura/escritura: los edita la página de rangos del HMI.

| Offset | Campo | Tipo | Unidad |
|---|---|---|---|
| `hb+0` | **Nivel** | uint16 | ×100 (unidad en `hb+28`) |
| `hb+1` | **Caudal de bomba** | uint16 | ×100 (unidad en `hb+29`) |
| `hb+2` | Nivel — crudo | uint16 | eco ADC 0..4095 (diagnóstico) |
| `hb+3` | Caudal — crudo | uint16 | eco ADC 0..4095 |
| `hb+4` | Acumulado del día — palabra alta (W0) | uint16 | 32b, m³ ×10 (orden hi-first, §2) |
| `hb+5` | Acumulado del día — palabra baja (W1) | uint16 | " |
| `hb+6` | Acumulado del mes — palabra alta (W0) | uint16 | 32b, m³ ×10 |
| `hb+7` | Acumulado del mes — palabra baja (W1) | uint16 | " |
| `hb+8` | Estado (bitfield) | uint16 | bit0 presostato · bit1 voltaje local presente · bit2 tamper/tapa abierta · bit3 DI4 · bit4 sirena activa · bit5 enlace LoRa OK · bit6 estación en alarma · bit7 sirena en AUTO |
| `hb+9` | Alarmas activas (bitfield) | uint16 | ver §4.4 |
| `hb+10` | RSSI LoRa | int16 | dBm |
| `hb+11` | Antigüedad del dato | uint16 | s desde la última respuesta del nodo |
| `hb+12` | Vínculo | uint16 | dirección LoRa / slot del nodo ligado a esta estación |
| `hb+13` | Contador de fallos de lectura | uint16 | acumulado desde el arranque |
| `hb+14..19` | reserva | uint16 | 0 |
| `hb+20` | Nivel — raw_min ("cero") | uint16 | cuentas ADC |
| `hb+21` | Nivel — raw_max ("span") | uint16 | cuentas ADC |
| `hb+22` | Nivel — eng_min | int16 | ×100 |
| `hb+23` | Nivel — eng_max | int16 | ×100 |
| `hb+24` | Caudal — raw_min | uint16 | cuentas ADC |
| `hb+25` | Caudal — raw_max | uint16 | cuentas ADC |
| `hb+26` | Caudal — eng_min | int16 | ×100 |
| `hb+27` | Caudal — eng_max | int16 | ×100 |
| `hb+28` | Unidad de Nivel | uint16 | 0 = % · 1 = m · 2 = cm · 3 = mca |
| `hb+29` | Unidad de Caudal | uint16 | 0 = L/s · 1 = m³/h · 2 = L/min · 3 = GPM |
| `hb+30` | Suavizado / filtro | uint16 | 0..100 (0 = sin filtro) |
| `hb+31` | Sello de config | uint16 | lo incrementa quien escribe el bloque; el HMI compara para confirmar que se aplicó |

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
| `cb+3` | Reset acumulado del día | **pulso**, protegido (ver nota) |
| `cb+4` | Reset acumulado del mes | **pulso**, protegido |
| `cb+5..7` | reserva | |
| `cb+8` | Aplicar bloque de escalado | **pulso**: el LOGO! toma `hb+20..31`, valida, persiste y actualiza `hb+31` |
| `cb+9..15` | reserva | |

> **Protección de resets:** `cb+3/cb+4` solo se aceptan si en el mismo ciclo (o
> el inmediato anterior) hay un `1` en `cb+9` (coil "armar reset"). Evita resets
> accidentales desde el SCADA. El PLC-SIM implementa la misma condición.

**Mapa de estaciones (N = 2):** Estación 0 → Coils/DI `0..15` · Estación 1 → `16..31`.

### 4.4 Tabla de alarmas (`hb+9` por estación, `HR 99` resumen global)

| Bit | Alarma | Origen |
|---|---|---|
| 0 | Nivel alto | Nivel ≥ umbral alto |
| 1 | Nivel bajo | Nivel ≤ umbral bajo |
| 2 | Nivel muy bajo (marcha en seco) | Nivel ≤ umbral MB |
| 3 | Sin caudal con presostato activo | presostato = 1 y Caudal ≈ 0 durante T |
| 4 | Falla de presostato | arrancó y el presostato no cerró en T |
| 5 | Pérdida de voltaje local | DI2 = 0 |
| 6 | Tamper / tapa abierta | DI3 = 1 |
| 7 | Pérdida de enlace LoRa | enlace = 0 durante T |
| 8 | Dato obsoleto | antigüedad > umbral |
| 9 | Config de escala inválida | raw_max ≤ raw_min, o eng_max = eng_min |
| 10 | Sobre-rango de instrumento | crudo fuera de [raw_min, raw_max] con margen |
| 11..15 | reserva | |

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
| `105` | `CONTRACT_VERSION` | debe coincidir con este documento (= 2) |
| `106..107` | reserva | |

---

## 5. Fórmula de escalado (crudo → ingeniería)

Aplicada por el LOGO! / PLC-SIM, **no** por el HMI. El HMI solo edita los
parámetros `hb+20..31`.

```
si raw_max <= raw_min  →  eng = eng_min ; alarma bit9 (config inválida)
si raw < raw_min - MARGEN  o  raw > raw_max + MARGEN  →  alarma bit10 (sobre-rango)

eng_x100 = eng_min + (raw - raw_min) * (eng_max - eng_min) / (raw_max - raw_min)
eng_x100 = clamp(eng_x100, min(eng_min,eng_max), max(eng_min,eng_max))

si filtro (hb+30) > 0:
    eng_filt = eng_filt + (eng_x100 - eng_filt) * (1 - hb30/101)   # EMA simple
```

`MARGEN` por defecto = 2 % del span (`(raw_max - raw_min) * 2 / 100`).

### Valores por defecto (PLACEHOLDER — ajustar en puesta en marcha)

| Parámetro | Nivel | Caudal |
|---|---|---|
| raw_min (`hb+20`/`hb+24`) | 800 | 800 |
| raw_max (`hb+21`/`hb+25`) | 4000 | 4000 |
| eng_min (`hb+22`/`hb+26`) | 0 | 0 |
| eng_max (`hb+23`/`hb+27`) | 10000 (100,00 %) | 5000 (50,00 L/s) |
| unidad (`hb+28`/`hb+29`) | 0 (%) | 0 (L/s) |
| filtro (`hb+30`) | 20 | 10 |

---

## 6. Vínculo nodo ↔ estación

Configurable en el PLC-SIM y en el LOGO!. Por defecto **1 a 1 por orden de slot**:

| Estación (Mapa B) | Slot en Mapa A | Dirección LoRa del nodo |
|---|---|---|
| 0 | nodo `i = 0` | (la que asigne el gateway al adoptar) |
| 1 | nodo `i = 1` | " |

El PLC-SIM lee `MAPA A [i*16 + 0..9]` del gateway, aplica §5 y escribe
`MAPA B [s*32 + ...]`. Antigüedad y enlace se propagan tal cual.

---

## 7. Versionado del contrato

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
