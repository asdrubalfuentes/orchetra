# Puesta en marcha — Orquestación Aysafi

Guía de bring-up de la cadena `nodeIO → nodeIO_master → PLC-SIM/LOGO! → miHMI`.
Contrato de datos: [`REGISTER_MAP.md`](REGISTER_MAP.md) (`CONTRACT_VERSION 1`).

## Prerrequisitos

- **Hardware:** 2× `nodeIO` (Heltec V3), 1× `nodeIO_master` (Heltec V3),
  1× `miHMI` (Cheap Yellow Display), 1× PC con Python para el PLC-SIM.
- **Red:** un segmento único (misma subred, sin *client isolation* en el AP,
  cortafuegos del PC abierto al puerto Modbus entrante). Ideal: SSID + VLAN
  dedicada. Recomendado dar **IP fija** al gateway.
- **Puerto 502:** en Windows requiere ejecutar como administrador. Si no,
  usa **1502** en el PLC-SIM y en `miHMI/include/config.h` (`PLC_PORT`).
- **Orden de flasheo:** primero los `nodeIO`, luego el `nodeIO_master`. (El
  firmware nuevo sube `CFG_MAGIC`; ROLLCALL solo recupera nodos que ya corren
  el firmware nuevo.)

## Señales de campo por estación (contrato §4, §6)

| Canal nodo | Señal |
|---|---|
| AI1 | Nivel |
| AI2 | Caudal de bomba |
| DI1 | Presostato |
| DI2 | Presencia de voltaje local |
| DI3 | Switch de tapa (tamper) |
| RELÉ1 | Sirena |

---

## Fase 0 — Humo mínimo (PC + HMI, sin LoRa)

1. **PLC-SIM:** `cd modbusMaster && pip install -r requirements.txt && python app.py`
   → http://localhost:5000 → pestaña **🏭 PLC-SIM**.
   - Servidor Modbus TCP: `0.0.0.0` : `502` (o `1502`). **Iniciar.**
   - Sin gateway aún: las estaciones salen *SIN ENLACE* + alarma de enlace. Es lo esperado.
   - **Con datos vivos sin LoRa:** en otra terminal
     `python orchestration/tools/fake_gateway.py --port 1602 --scenario normal`
     y en *PLC-SIM → Cliente → Pasarela LoRa* pon `127.0.0.1:1602`. Escenarios:
     `normal`, `lowlevel`, `highlevel`, `tamper`, `noflow`, `novolt`.
   - **Verificar el MAPA B:** `python orchestration/tools/mapb_check.py --host 127.0.0.1 --port 502`
     (añade `--write` para probar silenciar y aplicar escala). Salida 0 = conforme.
2. **miHMI** — en `include/config.h`: `WIFI_SSID/PASS` de tu red, `PLC_HOST` = IP
   del PC en esa red, `PLC_PORT` = 502/1502. Compilar y flashear.
3. En el HMI → **Ajustes**: *Fuente activa* debe pasar a `PLC-TCP`, *Origen* =
   `PLC-SIM`, *latido* incrementando.
   - Si ves ondas senoidales "bonitas": el HMI cayó a `MockSource` (no llegó al
     PLC). Revisa WiFi, IP, puerto y cortafuegos del PC.

## Fase 1 — Añadir el gateway (Modbus TCP)

4. **Flashear `nodeIO_master`.** Primer arranque sin tabla → ROLLCALL (vacío) → **portal**.
   Conéctate a `MasterIO-Setup` / `aysafi1234` → http://192.168.4.1
   - **WiFi de planta (STA):** SSID/clave del segmento; IP fija recomendada.
   - **Modbus — transporte:** TCP · Unit ID 1 · puerto 502.
   - **Guardar y reiniciar.** El OLED debe mostrar `TCP <ip>:502` al asociar.
5. **PLC-SIM** → *Cliente → Pasarela LoRa*: pon la IP del gateway, puerto 502,
   Unit ID 1, sondeo 1000 ms. **Guardar configuración.**
   - La línea de estado debe decir *gateway conectado*. Aún sin nodos: online 0.

## Fase 2 — Añadir los nodos (LoRa, adopción)

6. **Flashear los 2 `nodeIO`.** Arrancan *SIN ADOPTAR* (OLED muestra su MAC).
7. Gateway → portal (botón *Builtin* ~5 s) → **Descubrir nodos** → *Buscar*.
   Asigna dirección (p.ej. 11 y 12) y nombre a cada uno. **No** fijes el canal
   LoRa a mano: el gateway lo empuja al adoptar.
8. Guardar y reiniciar. OLED del gateway: `Nodos online 2/2`. OLED de cada nodo:
   `ADOPTADO addr N`.
9. Verifica en el PLC-SIM que las 2 estaciones pasan a *con enlace* y muestran
   Nivel/Caudal (con la escala por defecto, aún sin calibrar).

## Fase 3 — Señales de campo y calibración

10. Cablea sensores/actuadores según la tabla de arriba. El instrumentista ajusta
    el lazo 4–20 mA en campo.
11. En el HMI → **Ajustes → Rangos de escala**: por estación y variable, ajusta
    `cero` (raw_min) y `span` (raw_max) y los `eng_min/eng_max`, unidad y filtro
    → **APLICAR AL PLC**. El *sello* debe cambiar (confirma que el PLC lo tomó).
12. Prueba comandos desde el detalle de estación: **SILENCIAR**,
    **SIRENA AUTO/MAN**. En el PLC-SIM se ve el coil de sirena escrito al gateway.

---

## Checks por salto

| Punto | Qué mirar | OK si… |
|---|---|---|
| Nodo | OLED | `ADOPTADO addr N`, RSSI razonable |
| Gateway | OLED | `Nodos online 2/2` y `TCP <ip>:502` |
| PLC-SIM (web) | estado | *gateway conectado*; Nivel/Caudal coherentes; sin errores de lectura |
| PLC-SIM (web) | estación en alarma | la sirena AUTO enciende y se escribe al coil del nodo |
| HMI | Ajustes | *Fuente activa* = `PLC-TCP`, *Origen* = `PLC-SIM`, latido vivo |
| HMI | Estaciones | 2 tarjetas sin solape, datos y estado correctos |
| HMI | Rangos de escala | LEER trae valores; APLICAR cambia el sello |

## Problemas frecuentes

| Síntoma | Causa / arreglo |
|---|---|
| HMI muestra datos senoidales | cayó a `MockSource`; PLC inalcanzable (WiFi/IP/puerto/cortafuegos) |
| `TCP :502 wifi...` fijo en el gateway | no asocia a la WiFi de planta; SSID/clave/cobertura |
| PLC-SIM: *sin conexión* al gateway | distinta subred, *client isolation* del AP, o el gateway aún sin IP |
| No abre el 502 en el PC | ejecuta como administrador o usa 1502 en todos lados |
| *Buscar* no ve un nodo | ya está adoptado → usa **ROLLCALL**; o canal LoRa distinto |
| Tras actualizar el gateway no hay nodos | pulsa **ROLLCALL** (o se lanza solo al arrancar); los nodos siguen adoptados |
| Acumulados no suben | el caudal escalado es 0, o la unidad de caudal (hb+29) no coincide |

## Migración al LOGO! 9 real

Cuando el LOGO! esté programado con el MAPA B:

1. Repunta `PLC_HOST` (HMI) y el cliente del SCADA a la IP del LOGO!.
2. `IR 2007` debe leer **1** (origen LOGO! real); el HMI lo muestra en *Ajustes*.
3. El gateway y el resto no cambian: mismo MAPA A, mismo puerto, mismo Unit ID.
