# Puente MQTT de la orquestación

Publica **toda** la orquestación (PLC/MAPA B, gateway/MAPA A, nodos, salud del
HMI) a un broker MQTT y acepta **comandos desde la nube** hacia los registros
escribibles. El puente vive en el **`nodeIO_master`** (gateway) — ver
[por qué en el análisis de arquitectura] al final.

- Contrato Modbus del puente: [`REGISTER_MAP.md §7 — MAPA G`](REGISTER_MAP.md).
- Estado: **firmware del gateway implementado** (`nodeIO_master` ≥ `1.4.0`:
  `modbus_gw` MAPA G + `mqtt_bridge` + SNTP + fieldset en el portal). Falta el
  lado **LOGO! (FBD)** — bloques Network I/O de
  [`PLC_REGISTER_RECIPE.md §10`](PLC_REGISTER_RECIPE.md) — y, opcional, el
  `hmi/state` del HMI. `station/<s>/scale/set` desde MQTT queda para una 2ª fase.

---

## 1. Topología

```
 nodos LoRa ─LoRa─►  nodeIO_master (gateway)  ─MQTT/TLS─►  broker  ─►  SCADA / dashboards / apps
                     │  · LoRa master + MAPA A (server :502)
   LOGO! 9 ─Modbus──►│  · espejo MAPA B  (HR, lo escribe el LOGO!)
   (1 sola conexión) │  · comandos nube  (Coils 1000+, los lee el LOGO!)
                     │  · cliente MQTT (publica + se suscribe)
 miHMI ─Modbus──────►┘  (lee MAPA B del LOGO! hoy; puede leer del gateway a futuro)
```

El LOGO! **no habla MQTT** y **no gana conexiones**: escribe el espejo y lee los
comandos por la misma conexión Modbus que ya usa para el MAPA A y la sirena.

---

## 2. Broker y seguridad

| Parámetro | Valor por defecto | Dónde se configura |
|---|---|---|
| Host | `emqx.aysafi.com` | portal cautivo del gateway → NVS |
| Puerto | **8883 (TLS)**; `1883` solo en banco | " |
| Usuario / clave | por planta | NVS (no en el repo; patrón `secrets`) |
| Client ID | `orq-<site>-<mac6>` | derivado |
| TLS | `setInsecure()` (sin CA fija) o CA embebida | build flag |
| Keepalive | 30 s | |
| Clean session | sí (telemetría), retención en el broker para los "…/state" | |

**ACL recomendada en el broker:** el usuario de la nube (SCADA) solo **publica**
en `…/cmd/#` y **se suscribe** a la telemetría; el gateway publica todo y se
suscribe a `…/cmd/#`. Así una credencial filtrada del SCADA no puede falsificar
telemetría.

**LWT (last will):** `aysafi/<site>/orq/gw/state` = `{"online":false}` retenido;
al conectar publica `{"online":true,...}` retenido.

---

## 3. Espacio de tópicos

Raíz: `aysafi/<site>/orq/` — `<site>` = id de planta configurable (p.ej. `mina1`).

### 3.1 Telemetría (gateway → nube)

| Tópico | Retenido | Cadencia | Contenido |
|---|---|---|---|
| `…/gw/state` | sí | al conectar / LWT | online, ip, rssi, fw, uptime, hora |
| `…/plant` | sí | 5 s o al cambiar | bloque global de MAPA B (`HR 96..105`) |
| `…/station/<s>/data` | no | 2 s o al cambiar | MAPA B de la estación `s` (§4 del contrato) en **ingeniería** |
| `…/station/<s>/scale` | sí | al cambiar el sello | bloque de escala `hb+20..31` |
| `…/node/<addr>/raw` | no | 5 s | MAPA A del nodo (crudos, DI, relés, enlace, RSSI, edad) |
| `…/nodes` | sí | al cambiar la tabla | lista de nodos adoptados (addr, mac, fw, enabled, online) |
| `…/hmi/state` | sí | 30 s (lo publica **el HMI**) | ip, rssi, fuente activa, tramas ok/err, fw |

> "al cambiar" = además del periódico, publica inmediato si un valor relevante
> cambió (alarma nueva, cambio de estado, sello de escala) — *report by exception*.

### 3.2 Comandos (nube → gateway)

| Tópico | Payload | Efecto |
|---|---|---|
| `…/station/<s>/cmd` | `{"siren":"auto\|manual\|on\|off"}` · `{"silence":true}` · `{"ack":true}` · `{"reset":"day\|month","arm":true}` | escribe el coil de **MAPA G.2** (`1000 + s*16 + k`) |
| `…/station/<s>/scale/set` | bloque de escala completo (ver §5) | escribe `HR` del espejo + pulsa "aplicar" |
| `…/node/<addr>/relay` | `{"ro":[0,1,-1,-1]}` · `{"pulse":{"idx":1,"ms":500}}` | el gateway manda `WR`/`WP` por LoRa (ruta ya existente) |
| `…/gw/cmd` | `{"rollcall":true}` · `{"ota":true}` · `{"reboot":true}` | acción a nivel gateway (sin Modbus) |

Cada comando aceptado se responde en `…/<mismo tópico>/ack`:

```json
{ "ts": 1757534400, "req": "silence", "ok": true, "detail": "coil 2 = 1" }
```

`ok:false` con `detail` si se rechaza (payload inválido, reset sin armar, fuera de
rango, sin enlace con el nodo…).

---

## 4. Esquema de payload

JSON compacto, UTF-8. Campos comunes en todos los mensajes:

| Campo | Tipo | Sentido |
|---|---|---|
| `ts` | int | época UNIX en segundos (SNTP del gateway; `0` si sin hora) |
| `site` | str | id de planta |
| `v` | int | versión de este esquema (hoy `1`) |

### 4.1 `…/plant`

```json
{ "ts":1757534400, "site":"mina1", "v":1,
  "marca":"0x0B01", "contrato_v":2, "logica_v":1,
  "origen":"LOGO!",              // "LOGO!" (HR103=1) | "PLC-SIM" (=0)
  "n_estaciones":2, "online":[true,true],
  "alarma_general":false, "latido":18234, "uptime_s":18234,
  "gw_fw":"1.3.0" }
```

### 4.2 `…/station/<s>/data`

Valores en **ingeniería** (ya escalados) + crudos + banderas legibles:

```json
{ "ts":1757534400, "site":"mina1", "v":1, "st":0,
  "nivel":52.3, "nivel_u":"%",   "nivel_raw":2475,
  "caudal":12.4,"caudal_u":"L/s","caudal_raw":1592,
  "acum_dia_m3":0.0, "acum_mes_m3":0.0,
  "estado":{ "presostato":true,"volt_local":true,"tamper":false,
             "sirena":false,"sirena_auto":true,"enlace":true,"en_alarma":false },
  "alarmas":["NIVEL_ALTO"],        // nombres de los bits de hb+9 activos
  "alarmas_latch":["MARCHA_SECO"], // nombres de los bits de hb+14 sin reconocer
  "rssi":-70, "edad_s":1, "vinculo":11, "sello_escala":3, "rderr":0 }
```

Unidades por su código: nivel `0=% 1=m 2=cm 3=mca`; caudal `0=L/s 1=m³/h 2=L/min
3=GPM`.

### 4.3 `…/station/<s>/scale`

```json
{ "ts":..., "site":"mina1", "v":1, "st":0, "sello":3,
  "nivel":{ "raw_min":800,"raw_max":4000,"eng_min":0,"eng_max":10000,"unidad":0,"filtro":20 },
  "caudal":{ "raw_min":800,"raw_max":4000,"eng_min":0,"eng_max":5000, "unidad":0,"filtro":10 } }
```
`eng_*` en el mismo ×100 del contrato.

### 4.4 `…/node/<addr>/raw`  (MAPA A)

```json
{ "ts":..., "site":"mina1", "v":1, "nodo":0, "addr":11, "mac":"A1B2C3D4E5F6",
  "fw":"1.2026.006",
  "ai":[2475,1592,0,0], "di":[1,1,0,0], "ro":["0","x","x","x"],
  "enlace":true, "rssi":-70, "edad_s":1 }
```

### 4.5 `…/nodes` / `…/gw/state` / `…/hmi/state`

```json
// nodes
{ "ts":..., "site":"mina1", "v":1, "nodos":[
  {"slot":0,"addr":11,"mac":"A1B2C3D4E5F6","fw":"1.2026.006","enabled":true,"online":true},
  {"slot":1,"addr":12,"mac":"...","fw":"1.2026.006","enabled":true,"online":false} ] }

// gw/state (retenido; LWT invierte "online")
{ "ts":..., "site":"mina1", "v":1, "online":true, "ip":"192.168.1.241",
  "rssi":-58, "fw":"1.3.0", "uptime_s":18234, "hora_ok":true }

// hmi/state  (lo publica el HMI)
{ "ts":..., "site":"mina1", "v":1, "online":true, "ip":"192.168.1.60",
  "rssi":-61, "fuente":"PLC-TCP", "tramas_ok":9210, "tramas_err":3, "fw":"0.4.0" }
```

---

## 5. Comandos: mapeo a registros y salvaguardas

| Comando MQTT | Registro (MAPA G) | Regla |
|---|---|---|
| `siren:on` / `off` | coil `1000+s*16+0` | efectivo solo si AUTO = 0 |
| `siren:auto` / `manual` | coil `…+1` (1 / 0) | nivel, no pulso |
| `silence:true` | coil `…+2` = 1 (pulso) | el gateway lo auto-limpia al ciclo siguiente |
| `reset:"day"` + `arm:true` | coil `…+9` = 1 **y** `…+3` = 1 (pulsos) | se rechaza sin `arm:true` en el **mismo** mensaje |
| `reset:"month"` + `arm:true` | coil `…+9` y `…+4` | ídem |
| `ack:true` | coil `…+5` = 1 (pulso) | limpia `hb+14` con la causa despejada (lo hace el LOGO!) |
| `scale/set` | `HR` espejo `s*32+20..31` (FC16) + coil `…+8` = 1 | valida rangos antes de escribir; el LOGO! sube el sello |
| `node/<addr>/relay` | LoRa `WR`/`WP` | rechaza si el nodo está offline |
| `gw/cmd rollcall\|ota\|reboot` | acción interna del gateway | — |

**Salvaguardas del gateway:**
- **Anti-rebote:** ignora comandos idénticos repetidos en < 2 s.
- **Resets protegidos:** exigen `arm` en el propio payload (espejo de `cb+9`).
- **Rango:** `scale/set` valida `raw_max > raw_min`, `eng_max ≠ eng_min`,
  unidades 0..3, filtro 0..100; si no, `ack ok:false`.
- **Sin hora:** si SNTP no sincronizó, `ts:0` y se sigue operando.
- **Sin broker:** la operación local (LoRa ↔ Modbus ↔ LOGO!) no depende de MQTT;
  el puente reconecta en segundo plano.
- **QoS:** telemetría QoS 0; comandos y sus `ack` QoS 1.

---

## 6. Requisitos de firmware — `nodeIO_master`

1. **SNTP**: `configTime()` cuando `netStaUp()`; `ts` de los payloads.
2. **Servidor Modbus**: añadir el **espacio de Holding Registers** (hoy el
   gateway no expone HR) para el espejo G.1, y el bloque de **coils `1000+`**
   G.2 con auto-limpieza de pulsos.
3. **Cliente MQTT**: librería ligera (`PubSubClient` sobre `WiFiClientSecure`, o
   `MQTTPubSubClient` como en `LoraSenderAysafi`). Reconexión no bloqueante en
   `loop()` (nunca frenar el sondeo LoRa/Modbus).
4. **Serializador**: `ArduinoJson` (documentos pequeños en stack).
5. **Publicador**: temporizadores por tópico + *report by exception* (compara con
   el último publicado).
6. **Suscriptor**: `…/cmd/#`; parsea, valida (§5), escribe el coil/HR o manda por
   LoRa, responde el `ack`.
7. **Config**: host/puerto/usuario/clave/`site`/TLS en `MasterConfig` (NVS) +
   campos en el portal cautivo. `CFG_MAGIC` +1.
8. **`FW_SEMVER`** sube a `1.4.0` (el bridge es una función nueva).

## 7. Requisitos de firmware — `miHMI` (mínimo)

- Publicar solo **`…/hmi/state`** cada 30 s (un `mqtt.publish` pequeño; sin
  suscripciones, sin TLS persistente si se usa `1883` interno). Opcional; si no,
  la salud del HMI se omite.
- A futuro (Fase B): repuntar su cliente Modbus del LOGO! al **espejo del
  gateway** y escribir comandos en **G.2** en vez de en `cb+*` del LOGO!.

## 8. Requisitos — LOGO! 9 (FBD)

Ver [`PLC_REGISTER_RECIPE.md §10`](PLC_REGISTER_RECIPE.md):

- **Network Output → Modbus (FC16)** al gateway: escribe VW`s*64` → `HR s*32`
  (32 regs por estación) y VW192 → `HR 96` (10 regs). Es el espejo G.1.
- **Network Input → Modbus (FC01)** del gateway: lee coils `1001 + s*16` (1-based)
  ×10 → marcas `M`. `OR` con los `cb+*` que escribe el HMI directo (Fase A).

---

## 9. Plan de implementación

1. ✅ **Contrato** (este doc + `REGISTER_MAP.md §7` + `PLC_REGISTER_RECIPE.md §10`).
2. ✅ **Gateway – espejo y coils** (`modbus_gw`): HR `0..105` + coils `1000+` con
   auto-limpieza de pulsos.
3. ✅ **Gateway – SNTP + publicadores** (`mqtt_bridge`): `gw/state`, `nodes`,
   `plant`, `station/*/data`, `node/*/raw`.
4. ✅ **Gateway – suscriptor** de `station/+/cmd`, `node/+/relay`, `gw/cmd` +
   `ack` + salvaguardas + fieldset en el portal.
5. ⏳ **LOGO! – Network Output** del espejo → el gateway tendría MAPA B local.
6. ⏳ **LOGO! – Network Input** de G.2 + `OR` con `cb+*`.
7. ⏳ **HMI – `hmi/state`** (opcional).
8. ⏳ **`scale/set` desde MQTT** (2ª fase; hoy responde `ack ok:false`).
9. ⏳ **Fase B**: HMI y SCADA leen del gateway; el LOGO! se queda con 1 conexión.

---

## Anexo — por qué el gateway y no el HMI

| | `nodeIO_master` | `miHMI` |
|---|---|---|
| Disponibilidad | siempre encendido | se apaga en mantenimiento |
| Datos nativos | MAPA A completo + tabla de nodos + fw | MAPA B completo |
| Recursos | ESP32-S3, 8 MB, 31 % flash, sin UI | WROOM, 320 KB RAM, 73 % flash, LVGL+TLS ya al límite |
| Estabilidad | una reconexión MQTT no molesta a nadie | congelaría la pantalla |
| Conexiones al LOGO! | **0 nuevas** (el LOGO! empuja/lee por su conexión actual) | el HMI ya ocupa una; el LOGO! tiene muy pocas |

El PLC queda descartado como publicador: debe centrarse en la lógica de control
(y tendrá más carga a futuro), y necesita a un tercero que traduzca Modbus ↔ MQTT
para enviar y recibir comandos.
