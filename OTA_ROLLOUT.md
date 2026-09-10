# OTA para `nodeIO`, `nodeIO_master` y `miHMI` — changelog de despliegue

Replica en los tres firmwares el sistema OTA ya montado en **`LoraSenderAysafi`**
("GitHub Releases pull"). Este documento es el **conjunto de cambios** a aplicar
por repo + el plan de acción.

Fecha: 2026-09-10 · Referencia: `LoraSenderAysafi` (revisado abajo) · Módulo
listo para copiar: [`tools/ota/ota_update.{h,cpp}`](tools/ota/) · CI:
[`tools/ota/release.yml`](tools/ota/release.yml)

---

## 1. El modelo (qué hace `LoraSenderAysafi`)

```
 tag vX.Y.Z sobre main ─► GitHub Actions (release.yml)
                          · pio run  (FW_VERSION_OVERRIDE = X.Y.Z)
                          · sha256(firmware.bin)
                          · publica Release "latest":
                              firmware.bin · version.txt · firmware.sha256
 equipo (WiFi arriba) ─► GET releases/latest/download/version.txt
                          si  version.txt > versión embebida (semver numérico):
                          ─► GET firmware.bin  (+ firmware.sha256)
                          ─► verifica SHA-256 mientras escribe la partición OTA
                          ─► Update.end() + ESP.restart()
```

- **"Aprobado" = tag manual del mantenedor.** El workflow solo corre con
  `vX.Y.Z` y exige que el tag sea ancestro de `main`.
- **URL estable:** `releases/latest/download/<asset>` — el equipo no necesita
  saber el número de versión.
- **Integridad:** SHA-256 verificado en el equipo (no autenticidad; no hay firma).
- **Versión embebida:** `FW_VERSION_OVERRIDE` (lo inyecta el CI desde el tag);
  fuera de CI, un literal `X.Y.Z` de respaldo.
- **Credenciales:** nunca en el repo. En `LoraSenderAysafi` van por `build_flags`
  desde `sysenv`/secrets. **El trío no las necesita en build**: toman WiFi de
  NVS / microSD en runtime → compilan en CI con credenciales vacías.

---

## 2. Revisión de `LoraSenderAysafi` — 1 hallazgo a corregir

**`src/board_def.h`** — `getLatestVersion()`, `getLatestFirmwareSha256()` y
`updateFirmware()` hacen `http.begin(url)` sin `setFollowRedirects(...)`.
`releases/latest/download/<asset>` responde **302** hacia el host de assets de
GitHub; con `HTTPClient` en su modo por defecto (`HTTPC_DISABLE_FOLLOW_REDIRECTS`)
el GET devuelve 302, el cuerpo llega vacío y **la OTA no baja nada
silenciosamente**.

Corrección (en los 3 GET):

```cpp
http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
http.setTimeout(15000);
```

Y, para robustez en cores estrictos, cliente TLS explícito:

```cpp
WiFiClientSecure sec; sec.setInsecure();
http.begin(sec, url);
```

El módulo `tools/ota/ota_update.cpp` ya nace con estas tres cosas — conviene que
`LoraSenderAysafi` migre a ese módulo o incorpore el fix.

Resto de la revisión: **correcto** — semver numérico (`isVersionNewer`), SHA-256
en streaming con `mbedtls`, `Update.abort()` ante fallo/checksum, barra de
progreso en OLED, chequeo en boot + reinicio cada 30 min como disparador.

---

## 3. Particiones — los tres ya son dual-OTA (sin reflash)

| Proyecto | Placa | Tabla | app0 / app1 | Build actual | Holgura |
|---|---|---|---|---|---|
| `miHMI` | ESP32-2432S028R (4 MB) | `min_spiffs.csv` | **1.875 MB** c/u | 1.26 MB | 0.71 MB |
| `nodeIO` | Heltec V3 (8 MB) | `default_8MB.csv` | **3.19 MB** c/u | ~0.5 MB | amplia |
| `nodeIO_master` | Heltec V3 (8 MB) | `default_8MB.csv` | **3.19 MB** c/u | ~0.7 MB | amplia |

**No hay migración de particiones ni flasheo por serie obligatorio.** El OTA es
puro código nuevo + CI. (Sí conviene un último flasheo por serie de cada equipo
con la versión que ya trae el cliente OTA, para que a partir de ahí se
autoactualicen.)

---

## 4. Módulo común `ota_update`

Copiar `tools/ota/ota_update.h` + `tools/ota/ota_update.cpp` a `src/` de cada
proyecto (o a `lib/aysafi_ota/`). API:

```cpp
ota::Config cfg{ .owner = "asdrubalfuentes", .repo = "nodeIO",
                 .currentVersion = FW_SEMVER };
ota::run(cfg, onOtaProgress);      // check + (si hay) apply + reboot
```

`onOtaProgress(Phase, pct, detail)` es opcional — se usa para pintar el avance
(OLED en los Heltec, barra LVGL en el HMI). Sin callback, la OTA es silenciosa y
solo loguea por serie.

Depende solo de `WiFi`, `HTTPClient`, `Update`, `mbedtls` (todo del core
arduino-esp32) — **cero `lib_deps` nuevos**.

---

## 5. Cambios por proyecto

### 5.1 `nodeIO_master` (pasarela — ya tiene WiFi STA)

| Archivo | Cambio |
|---|---|
| `platformio.ini` | añadir `build_flags = ${sysenv.EXTRA_BUILD_FLAGS}` |
| `src/ota_update.{h,cpp}` | **nuevo** — copia de `tools/ota/` |
| `src/main.cpp` | `#define FW_SEMVER "1.2.0"` (nuevo, X.Y.Z); dejar `FW_VERSION` descriptivo. `#ifdef FW_VERSION_OVERRIDE` → usar ese como `FW_SEMVER`. Tras `netStaUp()` por primera vez en `setup()`/primer `loop` con IP: `ota::run({"asdrubalfuentes","nodeIO_master",FW_SEMVER}, otaOled)`. |
| `src/portal_master.cpp` | botón **"Buscar actualización"** → `web.on("/ota", ...)` que setea un flag; el `loop` lo atiende fuera del handler HTTP. |
| `.github/workflows/release.yml` | copia de `tools/ota/release.yml`, `PIO_ENV: heltec_wifi_lora_32_V3` |
| `versionControl.py` | copia (bump + tag + push). Ajustar el `re` a `FW_SEMVER`. |
| `CHANGELOG.md` | entrada `1.2.0 — OTA vía GitHub Releases` |

Chequeo en boot: sólo si `WiFi.status()==WL_CONNECTED`. No bloquear el arranque
del Modbus más de ~10 s si GitHub no responde (el módulo ya trae timeouts).

### 5.2 `miHMI` (HMI — WiFi STA + LVGL + microSD)

| Archivo | Cambio |
|---|---|
| `platformio.ini` | añadir `${sysenv.EXTRA_BUILD_FLAGS}` a `build_flags` (mantener `min_spiffs.csv`) |
| `src/net/ota_update.{h,cpp}` | **nuevo** — copia de `tools/ota/` |
| `include/config.h` | `#ifdef FW_VERSION_OVERRIDE` → `#undef APP_VERSION` / `#define APP_VERSION FW_VERSION_OVERRIDE`. `APP_VERSION` (`"0.3.0"`) ya es X.Y.Z → sirve de `currentVersion`. |
| `src/ui/screen_config.cpp` | botón **"Buscar actualización"** (ya está tras el PIN). `msgbox` con `lv_bar` movido por el callback de progreso. Ejecutar la OTA fuera del handler LVGL (flag + atención en `loop`/`ui_tick`). |
| `src/main.cpp` | chequeo en boot **justo tras conectar WiFi y antes de cargar pantallas pesadas** (heap más alto; TLS necesita ~40 KB contiguos con LVGL cargado). |
| `.github/workflows/release.yml` | copia, `PIO_ENV: esp32-2432S028R`, **sin secrets** (WiFi viene de microSD/NVS) |
| `include/secrets.h` | en CI no existe → `WIFI_SSID/PASS = ""`; el binario publicado lee la red real de la microSD/NVS en runtime. ✔ |
| `CHANGELOG.md` | **nuevo** — `0.4.0 — OTA vía GitHub Releases` |

Riesgo a vigilar: heap con LVGL + WiFi + TLS. Mitigación: chequear temprano en
boot; el botón manual sólo cuando el usuario lo pide (pantalla de config, sin
gráficas). El módulo aborta si `getFreeHeap() < 45 KB`.

### 5.3 `nodeIO` (nodo de campo — LoRa, sin WiFi normalmente)

**Fase 1 (ya):** flasheo **por USB** en la visita de mantenimiento (son 2 nodos y
ahora mismo se están manipulando para cablear sensores). Añadir igualmente el
`release.yml` + `versionControl.py` para que existan los binarios versionados y
el `CHANGELOG.md`.

**Fase 2 (OTA sin cable):** *OTA disparada por comando LoRa + WiFi de
mantenimiento*.

| Archivo | Cambio |
|---|---|
| `src/node_config.{h,cpp}` | `CFG_MAGIC` +1; nuevos campos `char otaSsid[33]`, `char otaPass[65]` (red de mantenimiento) |
| `src/lora_proto.cpp` | comando de aprovisionamiento **`OTA`** (como `DISC`/`ROLLCALL`, salta el filtro de dirección; dirigido por MAC o addr). Al recibirlo: marca "OTA pendiente" en NVS y `ESP.restart()`. |
| `src/main.cpp` | al arrancar, si "OTA pendiente": levantar WiFi STA contra `otaSsid`, `ota::run({"asdrubalfuentes","nodeIO",FW_SEMVER}, otaOled)`, limpiar el flag, `ESP.restart()`. Si la WiFi no conecta en ~30 s → limpiar flag y seguir normal. |
| `src/ota_update.{h,cpp}` | **nuevo** — copia |
| `nodeIO_master` | comando web/portal "Actualizar nodo N" → envía `OTA` por LoRa |
| `.github/workflows/release.yml`, `versionControl.py`, `CHANGELOG.md` | como los otros |

*Descartado:* OTA sobre LoRa puro (~1.3 MB a ~5 kbps ≈ 35-45 min, bloquea la red).

---

## 6. CI y secrets

- Cada repo: `.github/workflows/release.yml` desde `tools/ota/release.yml`,
  ajustando `PIO_ENV`.
- **Secrets:** ninguno para `nodeIO` / `nodeIO_master` / `miHMI` (WiFi en runtime).
  Sólo `LoraSenderAysafi` mantiene `WIFI_SSID` / `WIFI_PASSWORD`.
- Repos GitHub: `asdrubalfuentes/nodeIO`, `asdrubalfuentes/nodeIO_master`,
  `asdrubalfuentes/miHMI` (este ya existe).
- Primer release de cada uno: `git tag v1.0.0 && git push --tags` (o
  `versionControl.py`) sobre `main` limpio.

---

## 7. Plan de acción (estado)

1. ✅ **`LoraSenderAysafi`:** fix de redirects aplicado en `board_def.h` (los 3
   GET usan `WiFiClientSecure::setInsecure()` + `setFollowRedirects(STRICT)` +
   `setTimeout(15000)`). Compila. **Falta:** publicar `vX.Y.(Z+1)` y validar
   end-to-end con un equipo. ⚠️ Flash al **84 %** del slot OTA de 1.25 MB
   (`default.csv`): el próximo binario no puede crecer mucho — evaluar un último
   flasheo con `board_build.partitions = min_spiffs.csv` (slots de 1.9 MB).
2. ✅ **Módulo `ota_update.{h,cpp}`** en `ORCHESTRATION/tools/ota/` + copiado a
   `nodeIO_master/src/` y `nodeIO/src/`.
3. ✅ **`nodeIO_master` (§5.1):** módulo + wiring en `main.cpp` (chequeo al
   conectar WiFi y cada 6 h), `FW_SEMVER 1.2.0`, `release.yml`, `CHANGELOG.md`,
   botón **OTA** por nodo en el portal (`masterOtaTrigger`). Compila
   (Flash 31 %). **Falta:** push + tag `v1.2.0`.
4. ✅ **`nodeIO` (§5.3):** comando LoRa `OTA,<mac>` + `runOtaModeIfPending()` en
   boot + `otaSsid`/`otaPass` en `node_config` (magic 106) y en el portal +
   `release.yml` + `CHANGELOG.md`. Compila (Flash 30 %). **Falta:** push + tag
   `v1.3.0`; configurar la WiFi de mantenimiento en cada nodo antes de instalar.
5. ✅ **`miHMI` (§5.2):** `src/net/ota_update.{h,cpp}` + `src/net/ota_hmi.{h,cpp}`
   (progreso con TFT_eSPI a pantalla completa, no compite con LVGL). Botón
   *Buscar actualización* en *Configuración* (tras PIN) + chequeo silencioso cada
   6 h. `APP_VERSION` es el canal OTA (`FW_VERSION_OVERRIDE` del CI).
   `platformio.ini` con `${sysenv.EXTRA_BUILD_FLAGS}`, `release.yml`,
   `CHANGELOG.md`. Compila (Flash 73.6 % del slot de 1.875 MB). **Falta:** push +
   tag `v0.4.0`.
6. ⏳ **Gestión de flota:** panel que liste qué equipo está en qué versión;
   releases canary antes del rollout completo.

> **Regla de campo:** el **último flasheo por USB** de cada equipo debe llevar ya
> el cliente OTA (nodeIO_master ≥ 1.2.0, nodeIO ≥ 1.3.0 **con WiFi de
> mantenimiento configurada**, LoraSenderAysafi con el fix). A partir de ahí se
> actualizan sin cable.

---

## 8. Checklist por repo

- [ ] `ota_update.{h,cpp}` copiados a `src/`
- [ ] `FW_SEMVER` / `APP_VERSION` en formato `X.Y.Z` + soporte `FW_VERSION_OVERRIDE`
- [ ] `platformio.ini`: `${sysenv.EXTRA_BUILD_FLAGS}` en `build_flags`
- [ ] `ota::run(...)` llamado tras conectar WiFi (boot) y desde el botón manual
- [ ] callback de progreso conectado (OLED / LVGL)
- [ ] `.github/workflows/release.yml` con el `PIO_ENV` correcto
- [ ] `versionControl.py` adaptado
- [ ] `CHANGELOG.md` con la entrada de la versión
- [ ] `pio run` local OK; compila en CI con credenciales vacías
- [ ] tag `vX.Y.Z` sobre `main` → Release "latest" con 3 assets
- [ ] equipo real: sube de `X.Y.Z` a `X.Y.Z+1` y reinicia solo
