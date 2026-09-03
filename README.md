# Orquestación Aysafi

Repositorio transversal de la orquestación de 4 proyectos en uno: una **lógica en
un PLC (Siemens LOGO! 9)** cuyas entradas/salidas están muy remotas y viajan por
**LoRa**, monitoreada desde un **HMI pequeño** y publicable a un **SCADA remoto
por VPN**.

```
  nodos LoRa (nodeIO)  ──LoRa──►  nodeIO_master  ──Modbus TCP :502 (MAPA A)──►  LOGO! 9 / PLC-SIM
                                  (LoRa Gateway)                                  │  servidor MAPA B :502
                                                                                 ▼
                                                              miHMI  +  SCADA remoto (VPN)
```

## Documentos

| Archivo | Qué es |
|---|---|
| [`REGISTER_MAP.md`](REGISTER_MAP.md) | **Contrato de registros Modbus TCP** (`CONTRACT_VERSION 1`). MAPA A (pasarela, crudo por nodo) y MAPA B (PLC, ingeniería por estación): FC, offsets, escalas, endianness, árbol de alarmas, superficie de comandos. Todo lo demás cumple esto. |
| [`BRINGUP.md`](BRINGUP.md) | Guía de puesta en marcha por fases + checks por salto + problemas frecuentes + migración al LOGO! real. |
| [`tools/mapb_check.py`](tools/mapb_check.py) | Verificador de conformidad de un endpoint MAPA B (el PLC-SIM ahora, el LOGO! después). |

## Repos del sistema

| Repo | Rol |
|---|---|
| `asdrubalfuentes/nodeIO` | Nodo remoto LoRa: 4 AI / 4 DI / 4 relés. `ROLLCALL`/`HERE`. |
| `asdrubalfuentes/nodeIO_master` | Pasarela LoRa ↔ Modbus. Servidor **MAPA A** por TCP :502 (WiFi STA) o RTU. |
| `asdrubalfuentes/modbusWEB` | `modbusMaster` — web Modbus + **PLC-SIM** que sirve el **MAPA B** :502. |
| `asdrubalfuentes/miHMI` | HMI (Cheap Yellow Display): cliente **MAPA B**, 2 estaciones, página de rangos. |
| `asdrubalfuentes/orchetra` | Este repo. |

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
