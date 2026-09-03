# Lógica del PLC LOGO! 9 — Orquestación Aysafi

Programa del **Siemens LOGO! 9** (LOGO! Soft Comfort V9) que cubre los
requerimientos de la orquestación: escalar la E/S remota que llega por LoRa,
integrar acumulados, generar alarmas, gobernar la sirena y publicar todo por
Modbus TCP (**MAPA B** del [contrato](REGISTER_MAP.md)) para el HMI y el SCADA.

## 0. Realidad de la herramienta (léelo antes)

- **LOGO! Soft Comfort V9 programa en FBD o LAD. No existe Structured Text / SCL**
  en LOGO!. Por tanto este documento entrega:
  1. La **especificación funcional** exacta.
  2. **Pseudocódigo tipo ST** — referencia inequívoca de la lógica, **no cargable**.
  3. Una **guía de construcción en FBD** bloque a bloque.
- LOGO! 9: analógicos en **coma flotante 32-bit**, bloque **Float Mathematic**,
  hasta 800 bloques, IEC-CRA security. Todo lo de abajo asume el formato float.
- **LOGO! Modbus TCP**: históricamente el LOGO! es **servidor/esclavo** Modbus.
  V9 *podría* permitir lecturas Modbus como *Network Input* — ver §2. La lógica
  de este documento no depende de ello: el dato crudo llega a una zona de VM y de
  ahí en adelante da igual quién la escribió.
- Direcciones Modbus: **0-based de PDU** (las que viajan en el frame). El diálogo
  de mapeo de LSC puede mostrarlas como `4xxxx`/`3xxxx` (1-based).

---

## 1. Arquitectura con el LOGO! real

```
  nodos LoRa (nodeIO) ──LoRa──► nodeIO_master ──Modbus TCP──►  LOGO! 9 (servidor Modbus, VM)
                                (LoRa Gateway)   MAPA A crudo    │  programa FBD: escala + alarmas
                                                                 │  + sirena + totalizador
  HMI / SCADA ──Modbus TCP──► lee MAPA B de la VM ◄──────────────┘
```

El LOGO! tiene en VM **dos zonas**:

| Zona | Quién escribe | Quién lee | Contenido |
|---|---|---|---|
| **ENTRADA (crudo)** | el gateway (o el propio LOGO! si hace de cliente) | el programa FBD | por estación: nivel raw, caudal raw, DI (presostato/voltaje/tamper), enlace, RSSI, edad |
| **MAPA B** | el programa FBD (+ el HMI escribe el bloque de escala y los coils de comando) | HMI, SCADA | nivel/caudal escalados, acumulados, estado, alarmas, RSSI, edad, bloque de escala |

### Cómo entra el MAPA A al LOGO!

**Opción A — LOGO! cliente Modbus (preferida si V9 la trae).**
En LSC V9, *Instrucciones → Network Input*: añade una lectura Modbus TCP contra el
gateway (`192.168.1.241:502`), **FC04**, dirección de inicio `slot*16`, 11
registros, hacia `NAI`/`VW` de la zona de ENTRADA. Es exactamente lo que hace el
PLC-SIM. **Verifica en tu V9** si "Network Input" ofrece "Modbus" (además de
LOGO!/S7).

**Opción B — el gateway empuja (si el LOGO! solo es servidor).**
`nodeIO_master` añade un **cliente Modbus TCP** que, además de servir el MAPA A,
**escribe** el bloque de cada nodo en la VM del LOGO! (`writeHreg`). Es un cambio
acotado de firmware (§9). La zona de ENTRADA del LOGO! queda igual.

En ambos casos el programa FBD lee la **misma** zona de VM.

---

## 2. Mapa VM ↔ Modbus (perfil LOGO!, `CONTRACT_VERSION 2`)

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
| `b+0` | Nivel ×100 | int16 | escalado (§3) |
| `b+1` | Caudal ×100 | int16 | escalado (§3) |
| `b+2` | Nivel raw (eco) | uint16 | copia de la zona ENTRADA |
| `b+3` | Caudal raw (eco) | uint16 | |
| `b+4..5` | Acumulado día, m³ ×10 | int32 (VD, palabra alta primero) | totalizador (§4) |
| `b+6..7` | Acumulado mes, m³ ×10 | int32 (VD) | |
| `b+8` | Estado (bitfield) | uint16 | b0 presostato · b1 volt local · b2 tamper · b3 reserva · b4 sirena activa · b5 enlace OK · b6 en alarma · b7 sirena AUTO |
| `b+9` | Alarmas (bitfield) | uint16 | §5 |
| `b+10` | RSSI | int16 | eco |
| `b+11` | Edad del dato | uint16 | eco |
| `b+12` | Vínculo (dir. LoRa) | uint16 | eco |
| `b+13` | Contador de fallos de lectura | uint16 | opcional |
| `b+20` | Nivel raw_min ("cero") | uint16 | **lo escribe el HMI** |
| `b+21` | Nivel raw_max ("span") | uint16 | " |
| `b+22` | Nivel eng_min ×100 | int16 | " |
| `b+23` | Nivel eng_max ×100 | int16 | " |
| `b+24..27` | Caudal raw_min/raw_max/eng_min/eng_max | | " |
| `b+28` | Unidad de nivel (0=%,1=m,2=cm,3=mca) | uint16 | " |
| `b+29` | Unidad de caudal (0=L/s,1=m³/h,2=L/min,3=GPM) | uint16 | " |
| `b+30` | Filtro 0..100 | uint16 | " (EMA en §3) |
| `b+31` | Sello de config | uint16 | lo **incrementa el LOGO!** al aplicar `cb+8` |

Estación 0 → HR `0..31` (VW0..VW62). Estación 1 → HR `32..63` (VW64..VW126).

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
| `105` | `CONTRACT_VERSION` | `2` |

### 2.4 Comandos — Coils (FC01/05), base `s·16`

Los coils Modbus del LOGO! se mapean a marcas `M` que el programa lee.

| Coil | Comando | Semántica |
|---|---|---|
| `s·16 + 0` | Sirena ON manual | efectivo solo si `cb+1 = 0` |
| `s·16 + 1` | Sirena AUTO | `1` = la controla la lógica |
| `s·16 + 2` | Silenciar (pulso) | el LOGO! lo auto-limpia |
| `s·16 + 3` | Reset acumulado del día (pulso) | exige `cb+9` armado |
| `s·16 + 4` | Reset acumulado del mes (pulso) | exige `cb+9` armado |
| `s·16 + 8` | Aplicar bloque de escala (pulso) | el LOGO! valida `HR b+20..31`, persiste y sube `HR b+31` |
| `s·16 + 9` | Armar reset | habilita `cb+3`/`cb+4` |

---

## 3. Escalado crudo → ingeniería  (por estación, por variable)

Parámetros desde `HR b+20..31` (los edita el HMI). Fórmula del contrato §5.

### Pseudocódigo (referencia)

```
FUNCTION escala(raw : INT; rmin, rmax : INT; emin, emax : INT;
                filtro : INT; VAR y_filt : REAL) : INT
  IF rmax <= rmin OR emax = emin THEN
     alarma[SCALE_BAD] := TRUE ;  RETURN emin
  END_IF
  span := rmax - rmin
  margen := span * MARGEN_PCT / 100          // MARGEN_PCT = 2
  IF raw < rmin - margen OR raw > rmax + margen THEN alarma[OVERRANGE] := TRUE END_IF

  y := emin + (raw - rmin) * (emax - emin) / span
  y := LIMIT(min(emin,emax), y, max(emin,emax))

  IF filtro > 0 THEN                          // EMA
     a := 1.0 - filtro / 101.0
     y_filt := y_filt + (y - y_filt) * a
     RETURN REAL_TO_INT(y_filt)
  END_IF
  RETURN REAL_TO_INT(y)
END_FUNCTION

// por ciclo, por estación s y variable v (nivel, caudal):
ENT_B[s].nivel_x100  := escala(ENT[s].nivel_raw,  B[s].n_rmin, B[s].n_rmax,
                               B[s].n_emin, B[s].n_emax, B[s].filtro, filt_n[s])
ENT_B[s].caudal_x100 := escala(ENT[s].caudal_raw, B[s].c_rmin, B[s].c_rmax,
                               B[s].c_emin, B[s].c_emax, B[s].filtro, filt_c[s])
```

### En FBD (por cada variable de cada estación)

1. **Float Mathematic** `M1`: `(raw − rmin)` — entradas: `Vraw` (zona ENTRADA),
   `V(b+20)` (rmin). *(raw y rmin llegan como VW; el bloque los toma como float.)*
2. **Float Mathematic** `M2`: `(emax − emin)` — `V(b+23) − V(b+22)`.
3. **Float Mathematic** `M3`: `(rmax − rmin)` — `V(b+21) − V(b+20)`.
4. **Float Mathematic** `M4`: `M1 · M2 / M3` (con prioridad; si tu V9 no permite
   3 operandos con `·` y `/`, encadena: `M4a = M1·M2`, `M4 = M4a / M3`).
5. **Float Mathematic** `M5`: `emin + M4` → **valor escalado**.
6. **Analog Filter** (media móvil): entrada `M5`, "número de muestras" ≈ f(filtro).
   *(Si prefieres el EMA exacto del contrato, hazlo con un Float Math:
   `y_filt = y_filt + (M5 − y_filt)·a`, realimentando su salida; `a` de `V(b+30)`.)*
7. **Analog Comparator** `C_bad`: `rmax ≤ rmin` → bit `SCALE_BAD` de esa estación.
8. **Analog Threshold Trigger** `T_or`: `raw` fuera de `[rmin−m, rmax+m]` → bit
   `OVERRANGE`.
9. La salida de (6) → `V(b+0)` (nivel) o `V(b+1)` (caudal) mediante el mapeo VM.

> Si en tu instalación el nivel siempre es **%** con `0..4095 → 0..100`, puedes
> sustituir M1..M5 por **un solo Analog Amplifier** (Gain = 100/4095, Offset = 0)
> y dejar el bloque de escala editable para el caudal. Es menos flexible pero usa
> 1 bloque en vez de 5.

### Aplicar cambios de escala (coil `cb+8`)

```
IF pulso(cb[s].APPLY_SCALE) THEN
   IF escala válida(B[s]) THEN
      persistir B[s].(rmin..filtro)          // el LOGO! guarda en VM retentiva
      B[s].sello := (B[s].sello + 1) AND 16#FFFF
      reset filt_n[s], filt_c[s]
   END_IF
END_IF
```

FBD: **Latch/RS** o **pulso** desde el coil → habilita un **Analog MUX** que copia
`V(b+20..31)` a un juego de VW retentivos (o simplemente los deja como están si ya
son retentivos) → **Up Counter** de 1 paso sobre `V(b+31)`.

---

## 4. Totalizador de acumulados  (día y mes, por estación)

LOGO! 9 float: integración por realimentación, **muestreada a 1 s** para que el
paso sea determinista.

### Pseudocódigo

```
// factor de unidad de caudal -> m³/s  (unidad en HR b+29)
CASE B[s].unidad_caudal OF
  0: k := 1.0/1000.0        // L/s
  1: k := 1.0/3600.0        // m³/h
  2: k := 1.0/60000.0       // L/min
  3: k := 3.785411784/60000.0   // GPM
END_CASE

ON pulso_1s:                                 // cada 1 s exacto
  incr_m3 := (B[s].caudal_x100 / 100.0) * k * 1.0     // dt = 1 s
  IF día_cambió(s) OR pulso(cb[s].RESET_DAY  AND cb[s].ARM) THEN acc_dia[s]  := 0.0
  ELSE acc_dia[s] := acc_dia[s] + incr_m3 END_IF
  IF mes_cambió(s) OR pulso(cb[s].RESET_MONTH AND cb[s].ARM) THEN acc_mes[s] := 0.0
  ELSE acc_mes[s] := acc_mes[s] + incr_m3 END_IF

// publicar como int32 ×10 (contrato)
B[s].acc_dia_i32 := REAL_TO_DINT(acc_dia[s] * 10.0)
B[s].acc_mes_i32 := REAL_TO_DINT(acc_mes[s] * 10.0)
```

### En FBD

- **Reloj simétrico / generador de pulsos asíncrono** a **1 Hz** → señal
  `P1s` (ancho 1 ciclo).
- **Float Mathematic** `INCR`: `V(b+1) / 100 · k` (k según unidad; si la unidad es
  fija, k es constante; si no, un **Analog MUX** elige k entre 4 constantes según
  `V(b+29)`).
- **Float Mathematic** `ACC_DIA`: entradas `ACC_DIA` (su propia salida) `+`
  `INCR·P1s` → realimentar. `P1s` multiplica el incremento (0 cuando no toca).
- **Analog MUX** `SEL_DIA`: entrada 0 = `ACC_DIA`, entrada 1 = `0.0`, control =
  `reset_dia = P_media_noche OR (pulso(RESET_DAY) AND ARM)`. Salida → realimenta a
  `ACC_DIA`.
- **Reloj astronómico / temporizador semanal** para `P_media_noche` (flanco a las
  00:00) y `P_fin_de_mes` (día del mes vuelve a 1).
- **Float Mathematic** `PUB_DIA`: `ACC_DIA · 10` → **Analog → DWord** → `VD(b+4)`
  (2 Holding Registers, palabra alta primero — configúralo en el mapeo Modbus).
- Idéntico para el mes con `ACC_MES` y `P_fin_de_mes`.

> Si tu V9 no permite realimentar un Float Math a sí mismo, intercala una **marca
> analógica `AM`** (o un `Analog flag`) entre la salida y la entrada: `AM` guarda
> el acumulado y se re-lee al ciclo siguiente.

---

## 5. Árbol de alarmas  (bitfield `HR b+9`)

| Bit | Alarma | Condición | Retardo |
|---|---|---|---|
| 0 | Nivel alto | `nivel_x100 ≥ umbral_alto[s]` | — |
| 1 | Nivel bajo | `nivel_x100 ≤ umbral_bajo[s]` | — |
| 2 | Nivel muy bajo (marcha en seco) | `nivel_x100 ≤ umbral_mb[s]` | — |
| 3 | Sin caudal con presostato | `presostato AND caudal_x100 ≤ eps` | `T_noflow` (10 s) |
| 4 | Falla de presostato | `volt_local AND NOT presostato` | `T_pressfail` (15 s) |
| 5 | Pérdida de voltaje local | `NOT volt_local` | — |
| 6 | Tamper / tapa abierta | `tamper` | — |
| 7 | Pérdida de enlace LoRa | `NOT enlace` | `T_loraloss` (20 s) |
| 8 | Dato obsoleto | `edad > T_stale (15 s)` | — |
| 9 | Config de escala inválida | de §3 | — |
| 10 | Sobre-rango de instrumento | de §3 | — |

### Pseudocódigo

```
al := 0
IF niv >= UA[s] THEN al := al OR ALM_LEVEL_HI   END_IF
IF niv <= UB[s] THEN al := al OR ALM_LEVEL_LO   END_IF
IF niv <= UMB[s] THEN al := al OR ALM_LEVEL_LOLO END_IF
IF TON(presostato AND (cau <= EPS), T_noflow)       THEN al := al OR ALM_NO_FLOW    END_IF
IF TON(volt_local AND NOT presostato, T_pressfail)  THEN al := al OR ALM_PRESS_FAIL END_IF
IF NOT volt_local THEN al := al OR ALM_VOLT_LOSS END_IF
IF tamper        THEN al := al OR ALM_TAMPER    END_IF
IF TON(NOT enlace, T_loraloss)  THEN al := al OR ALM_LORA_LOSS END_IF
IF edad > T_stale THEN al := al OR ALM_STALE END_IF
al := al OR (scale_bad[s] ? ALM_SCALE_BAD : 0) OR (overrange[s] ? ALM_OVERRANGE : 0)
B[s].alarmas := al
```

### En FBD, por estación

- Nivel alto/bajo/mb: 3× **Analog Threshold Trigger** (o **Analog Comparator**)
  con el umbral desde una constante o `VW` de parámetros.
- Bits 3, 4, 7: **AND** de las señales digitales → **On-Delay (TON)** con el
  tiempo correspondiente → bit.
- Bits 5, 6, 8, 9, 10: directos.
- Empaquetar los 11 bits en `VW(b+9)`: en LOGO! esto se hace **mapeando cada
  salida digital a un bit de VW** (`VWx.0 … VWx.10`) en el diálogo de mapeo de
  parámetros / VM. No hace falta un bloque "encoder".
- **OR** de los 11 → bit 6 de `HR_STATUS` (`en alarma`) y entra al `HR 99` global.

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
gw_coil[s]   := sirena[s]                 // …escribir el coil RO1 del nodo por el MAPA A (Opción A/B)
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
HR105 := 2                              // CONTRACT_VERSION
```

FBD: **Up Counter** sobre `HR100` y `uptime` disparado por `P1s`; el resto son
constantes o un **OR** de bits mapeado a VW.

---

## 8. Construcción en LOGO! Soft Comfort V9 — pasos

1. **Nuevo proyecto** → elige el BM de tu LOGO! 9. En *Configuración de red*
   fija su IP (la que puso el HMI en `PLC_HOST`).
2. **Propiedades del proyecto → Comunicación**:
   - Activa **Modbus** (servidor). Anota/ajusta el **mapeo VM ↔ registro** — es la
     tabla de §2. Confirma que `HR0 = VW0`, `HR1 = VW2`, …
   - (Opción A) Si vas a leer el gateway desde el LOGO!, configura la conexión
     Modbus cliente / *Network Input*.
   - Deja **OPC UA** activado si el SCADA lo va a usar (perfil DA).
3. **Marcas retentivas**: marca como retentivas las VW/VD de acumulados, sello de
   config y parámetros de escala (para que sobrevivan a un corte).
4. **Coloca los bloques** por estación siguiendo §3–§7. Usa **UDF** (bloque de
   usuario) para "una estación" y **instáncialo 2 veces** — ahorra la mitad del
   trabajo y de los 800 bloques.
5. **Parámetros**: umbrales de alarma, tiempos `TON`, `MARGEN_PCT`, máscara de
   sirena, valores por defecto del bloque de escala.
6. **Textos de aviso** (opcional): mensajes en la pantalla del BM por alarma.
7. **Simulación** (LSC V9 trae emulador con comunicación de red): comprueba
   escalado, alarmas, sirena y totalizador antes de descargar.
8. **Descarga** al LOGO! por Ethernet. Verifica con
   `python ORCHESTRATION/tools/mapb_check.py --host <IP_LOGO> --port 502` →
   debe dar **0 FAIL** y `origen = LOGO! real`, `CONTRACT_VERSION = 2`.

---

## 9. Cambios acompañantes (fuera de este documento)

| Dónde | Cambio | Estado |
|---|---|---|
| `REGISTER_MAP.md` | `CONTRACT_VERSION 2`: bloque global a `HR 96..105`; FC02 opcional | **hecho** |
| `modbusMaster/plc_sim.py` | global a `HR 96`; `contract` = 2 | **hecho** (reinicia `python app.py` para cargarlo) |
| `miHMI` | leer el global por `HR 96`; `CONTRACT_VERSION 2` | **hecho** — recompilar/flashear |
| `tools/mapb_check.py` | global por `HR`; acepta FC02 ausente; espera `CONTRACT_VERSION 2` | **hecho** (verificado 0 FAIL) |
| `nodeIO_master` | **Opción B**: modo "push" — cliente Modbus TCP que escribe el bloque de cada nodo en la VM del LOGO! (`plcHost`/`plcPort`/`vmBase` en el portal). Solo si tu LOGO! 9 **no** hace de cliente Modbus | **pendiente** — dímelo y lo hago |

---

## Apéndice — constantes de bits (para el mapeo VM y el pseudocódigo)

```
Estado (HR b+8):  PRESOSTATO=1  VOLT_LOCAL=2  TAMPER=4  (b3 reserva=8)
                  SIREN_ON=16  LINK_OK=32  IN_ALARM=64  SIREN_AUTO=128

Alarmas (HR b+9): LEVEL_HI=1  LEVEL_LO=2  LEVEL_LOLO=4  NO_FLOW=8  PRESS_FAIL=16
                  VOLT_LOSS=32  TAMPER=64  LORA_LOSS=128  STALE=256
                  SCALE_BAD=512  OVERRANGE=1024
```
