# Orquestación Aysafi

Repositorio transversal de la orquestación: una **lógica en un PLC (Siemens
LOGO! 9)** cuyas entradas/salidas están muy remotas y viajan por **LoRa**,
monitoreada desde un **HMI pequeño** y publicable a un **SCADA remoto por VPN**.

Los otros proyectos (nodo, pasarela, HMI, simulador de PLC) viven en sus propios
repos; este define **el contrato que los une** y la documentación que los cruza.

```
  nodos LoRa (nodeIO) ─LoRa─►  nodeIO_master ─Modbus TCP :502─►  LOGO! 9 / PLC-SIM
                               (LoRa Gateway)   · MAPA A (crudo)     · calcula la lógica
                                     │  ◄── espejo MAPA B + comandos ─┘  (1 conexión, MAPA G)
                                     ├─ Modbus ─► miHMI  (lee MAPA B)
                                     └─ MQTT/TLS ─► broker ─► SCADA / dashboards / apps
```

- **MAPA A** — lo sirve la pasarela: E/S **cruda** por nodo LoRa (cuentas ADC, bits).
- **MAPA B** — lo calcula el PLC (o el simulador): ingeniería por estación,
  acumulados, alarmas, superficie de comandos. Lo consumen el HMI y el SCADA.
- **MAPA G** — extensión en el gateway para el **puente MQTT**: el LOGO! espeja
  MAPA B ahí y lee de ahí los comandos de la nube, por su única conexión Modbus.

## Documentos

| Archivo | Qué es |
|---|---|
| [`REGISTER_MAP.md`](REGISTER_MAP.md) | **Contrato de registros Modbus TCP** (`CONTRACT_VERSION`). MAPA A y MAPA B: FC, offsets, escalas, endianness, árbol de alarmas, superficie de comandos. Todo lo demás cumple esto. |
| [`PLC_LOGIC.md`](PLC_LOGIC.md) | **Lógica del LOGO! 9**: mapa de VM, escalado, totalizador, alarmas, sirena y bloque global — como especificación + pseudocódigo tipo ST + guía de construcción en **FBD** (LOGO! Soft Comfort V9 no tiene ST). |
| [`PLC_REGISTER_RECIPE.md`](PLC_REGISTER_RECIPE.md) | **Hoja de construcción**: la lista literal de `VW/VD/M` a crear en LSC y con qué registro Modbus habla cada uno (MAPA A que lee, MAPA B que publica, coils de comando), + checklist y orden incremental de puesta en obra. |
| [`BRINGUP.md`](BRINGUP.md) | Guía de puesta en marcha por fases + checks por salto + problemas frecuentes + migración al LOGO! real. |
| [`OTA_ROLLOUT.md`](OTA_ROLLOUT.md) | Changelog de despliegue del OTA "GitHub Releases pull" (modelo `LoraSenderAysafi`) a `nodeIO`, `nodeIO_master` y `miHMI` + módulo común [`tools/ota/`](tools/ota/). |
| [`MQTT_BRIDGE.md`](MQTT_BRIDGE.md) | Puente **MQTT** en el `nodeIO_master`: tópicos, payloads JSON y superficie de comandos desde la nube. El LOGO! espeja MAPA B en el gateway (`REGISTER_MAP.md §7 — MAPA G`); no gana conexiones. |
| [`tools/mapb_check.py`](tools/mapb_check.py) | Verificador de conformidad de un endpoint MAPA B (el PLC-SIM ahora, el LOGO! después). |
| [`tools/fake_gateway.py`](tools/fake_gateway.py) | Pasarela LoRa falsa (sirve el MAPA A con escenarios) para probar sin hardware LoRa. |
| [`tools/ota/`](tools/ota/) | Módulo común de OTA (`ota_update.{h,cpp}`) + plantilla de CI (`release.yml`) para los firmwares. |

## Repos del sistema

| Repo | Rol |
|---|---|
| `asdrubalfuentes/nodeIO` | Nodo remoto LoRa: 4 AI / 4 DI / 4 relés. `ROLLCALL`/`HERE`, OTA por comando LoRa. |
| `asdrubalfuentes/nodeIO_master` | Pasarela LoRa ↔ Modbus. Servidor **MAPA A** por TCP :502 (WiFi STA) o RTU. Autoactualización OTA. |
| `asdrubalfuentes/modbusWEB` | `modbusMaster` — web Modbus + **PLC-SIM** que sirve el **MAPA B** :502. |
| `asdrubalfuentes/miHMI` | HMI (Cheap Yellow Display): cliente **MAPA B**, 2 estaciones, página de rangos. |
| `asdrubalfuentes/orchetra` | Este repo (contrato + docs + herramientas). |

## Estado

- **Contrato `CONTRACT_VERSION 3`** — **cambio de rumbo (2026-09-14):** el
  escalado, filtro EMA, totalizador día/mes y alarma de nivel/caudal se
  mueven del LOGO! al **nodo remoto** (`nodeIO`, calibrado en su portal
  cautivo). El gateway gana **MAPA A2** con esos valores ya calculados y
  cierra día/mes automático por SNTP; el LOGO! pasa de *calcular* a *relayar*.
  Detalle completo: [`REGISTER_MAP.md` §3.4 y §8](REGISTER_MAP.md).
- **Fix de campo (2026-09-14b):** ningún gateway con **IP fija** tenía DNS
  configurado (`WiFi.config()` no traía `dns1`/`dns2` — a diferencia de DHCP,
  que lo recibe del router solo) → `github.com` (OTA) y `pool.ntp.org`/
  `time.google.com` (SNTP, cierre automático de día/mes) fallaban siempre,
  el 100% de las veces, sin ser un problema de la red. `nodeIO_master
  v1.5.3`: `dns1` = el propio router LAN, `dns2` = `8.8.8.8` de respaldo.
- **Firmwares migrados y etiquetados:** `nodeIO v1.4.1`, `nodeIO_master
  v1.5.3`, `miHMI v0.5.0` — todos con OTA "GitHub Releases pull". `nodeIO` no
  se auto-chequea (botón del portal del gateway, **F2 4-5s**, o el comando
  **`buscar actualizacion`** por Serial/USB); `nodeIO_master` y `miHMI` sí,
  automático (además de F2/serial para forzarlo ya — ver
  [`OTA_ROLLOUT.md` §9](OTA_ROLLOUT.md)).
- **Fix de campo (2026-09-14):** `nodeIO_master` mostraba el nodo adoptado
  siempre `offline` — `ackTimeoutMs` (500 ms de fábrica) quedaba corto para
  la trama `ST` v3 (~650-700 ms de aire a SF9/BW125). Subido a 2000 ms
  (`v1.5.2`); equipos ya en campo solo necesitan el cambio por portal, sin
  reflashear.
- **LOGO! 9 real:** migrado por el usuario en LSC siguiendo
  [`PLC_REGISTER_RECIPE.md`](PLC_REGISTER_RECIPE.md) — MAPA A2 (nivel/caudal/
  acumulados/`almBits`), fusión de alarmas y bloque global verificados en
  campo. Pendiente: replicar en estación 1 el detalle fino, y decidir dónde
  van `caudal bajo`/`caudal alto` en el árbol de 11→12 alarmas si hace falta
  más que la fusión ya hecha.
- **Sin migrar, fuera del alcance de este cambio:** `modbusMaster`/PLC-SIM
  sigue aplicando el escalado él mismo sobre MAPA A crudo (útil para probar
  el resto del contrato, no el escalado del nodo).
- **Puente MQTT** ([`MQTT_BRIDGE.md`](MQTT_BRIDGE.md)): firmware del gateway
  hecho, con `acum_dia_m3`/`acum_mes_m3` ya alineados a la escala ×1000 de v3.
  Identidad (tabla de nodos, canal, WiFi, MQTT, TZ) sobrevive a bumps de
  `CFG_MAGIC` (claves sueltas NVS + espejo LittleFS).

## Verificador de conformidad

```bash
cd tools
pip install -r requirements.txt
python mapb_check.py --host 127.0.0.1 --port 502          # solo lectura
python mapb_check.py --host 192.168.1.50 --write          # + pruebas de escritura (silenciar, escala)
```

Comprueba: marca `0x0B01`, `CONTRACT_VERSION`, latido que avanza, estructura de
cada bloque de estación, coherencia DI ↔ `HR_STATUS`, bloque de escala válido, y
—con `--write`— que el coil de silenciar se auto-limpia y que aplicar el bloque
de escala cambia el sello. Código de salida 0 = OK.
