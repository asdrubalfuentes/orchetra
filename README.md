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

- **Contrato `CONTRACT_VERSION 2`** (perfil LOGO!: bloque global en Holding
  Registers `HR 96`, FC02 opcional). Adición compatible posterior (sin subir la
  versión): `cb+5` = ACK de alarmas · `hb+14` = alarmas latcheadas. Al día:
  `plc_sim.py`, `miHMI`, `mapb_check.py` — `mapb_check --write` da 0 FAIL.
- Cadena `nodo → pasarela → PLC-SIM → HMI` funcionando en banco.
- **LOGO! 9:** ingesta confirmada (el LOGO! es **cliente Modbus** y sondea la
  pasarela directo). Falta construir el programa FBD siguiendo
  [`PLC_REGISTER_RECIPE.md`](PLC_REGISTER_RECIPE.md) y verificar con `mapb_check`.
- **OTA "GitHub Releases pull"** ([`OTA_ROLLOUT.md`](OTA_ROLLOUT.md)): aplicado a
  `nodeIO` (por comando LoRa), `nodeIO_master` y `miHMI` (autoactualización).
  `LoraSenderAysafi` es la referencia (fix de redirects aplicado). Faltan los
  tags de release.
- **Puente MQTT** ([`MQTT_BRIDGE.md`](MQTT_BRIDGE.md)): **spec lista**. El
  `nodeIO_master` publicará toda la orquestación y aceptará comandos de la nube;
  el LOGO! espeja MAPA B en el gateway (`REGISTER_MAP.md §7`) sin ganar
  conexiones. Firmware del gateway y bloques FBD del LOGO! por implementar.

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
