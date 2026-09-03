#!/usr/bin/env python3
"""
mapb_check.py  -  Verificador de conformidad del MAPA B (contrato CONTRACT_VERSION 1).

Se conecta por Modbus TCP a un endpoint MAPA B (el PLC-SIM de modbusMaster ahora,
el LOGO! 9 real despues) y comprueba estructura, coherencia y semantica de
comandos contra ../REGISTER_MAP.md.

  python mapb_check.py --host 127.0.0.1 --port 502
  python mapb_check.py --host 192.168.1.50 --write --station 0

Codigo de salida: 0 = todo OK, 1 = alguna comprobacion FAIL.
"""
import argparse
import sys
import time

from pymodbus.client import ModbusTcpClient

CONTRACT_VERSION = 1
MAPB_MARK        = 0x0B01
HR_STRIDE, DI_STRIDE, CO_STRIDE = 32, 16, 16

# --- offsets HR dentro del bloque de estacion ---
HR_LEVEL, HR_FLOW, HR_LEVEL_RAW, HR_FLOW_RAW = 0, 1, 2, 3
HR_DAY_W0, HR_DAY_W1, HR_MON_W0, HR_MON_W1   = 4, 5, 6, 7
HR_STATUS, HR_ALARMS, HR_RSSI, HR_AGE        = 8, 9, 10, 11
HR_LINK_ADDR, HR_RDERR                       = 12, 13
HR_SCALE_BASE = 20   # +20..+31: lvl(rmin,rmax,emin,emax) flw(rmin,rmax,emin,emax) u_lvl u_flw filt stamp

# --- coils / discrete inputs ---
CO_SIREN_MANUAL, CO_SIREN_AUTO, CO_SILENCE = 0, 1, 2
CO_RESET_DAY, CO_RESET_MONTH               = 3, 4
CO_APPLY_SCALE, CO_ARM_RESET               = 8, 9

DI_PRESOSTATO, DI_VOLT_LOCAL, DI_TAMPER, DI_SPARE4 = 0, 1, 2, 3
DI_LORA_OK, DI_IN_ALARM, DI_SIREN_ON, DI_FRESH     = 4, 5, 6, 7

# --- bloque global (input registers) ---
IR_G_MARK, IR_G_NSTATIONS, IR_G_ONLINE, IR_G_ALARM_OR = 2000, 2001, 2002, 2003
IR_G_HEARTBEAT, IR_G_UPTIME_W0, IR_G_UPTIME_W1        = 2004, 2005, 2006
IR_G_ORIGIN, IR_G_LOGIC_VER, IR_G_CONTRACT            = 2007, 2008, 2009

ST_BITS = [(1 << 0, "presostato"), (1 << 1, "volt_local"), (1 << 2, "tamper"),
           (1 << 3, "spare4"), (1 << 4, "sirena_on"), (1 << 5, "link_ok"),
           (1 << 6, "en_alarma"), (1 << 7, "sirena_auto")]
ALM_BITS = [(1 << 0, "Nivel alto"), (1 << 1, "Nivel bajo"), (1 << 2, "Nivel muy bajo"),
            (1 << 3, "Sin caudal"), (1 << 4, "Falla presostato"), (1 << 5, "Perdida voltaje"),
            (1 << 6, "Tamper"), (1 << 7, "Perdida enlace LoRa"), (1 << 8, "Dato obsoleto"),
            (1 << 9, "Escala invalida"), (1 << 10, "Sobre-rango")]
UNITS_LEVEL = ["%", "m", "cm", "mca"]
UNITS_FLOW  = ["L/s", "m3/h", "L/min", "GPM"]


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def u32_hi_first(w0, w1):
    return ((w0 & 0xFFFF) << 16) | (w1 & 0xFFFF)


def bits_txt(val, table):
    return ", ".join(n for m, n in table if val & m) or "-"


class Checker:
    def __init__(self, cli, unit):
        self.c, self.u = cli, unit
        self.fail = self.warn = 0

    def ok(self, cond, msg):
        print(f"  [{'OK  ' if cond else 'FAIL'}] {msg}")
        if not cond:
            self.fail += 1
        return cond

    def note(self, msg):
        print(f"  [i]   {msg}")

    def warning(self, msg):
        print(f"  [!]   {msg}")
        self.warn += 1

    # lecturas (None si error)
    def hr(self, a, n):
        r = self.c.read_holding_registers(a, n, slave=self.u)
        return None if r.isError() else list(r.registers)

    def ir(self, a, n):
        r = self.c.read_input_registers(a, n, slave=self.u)
        return None if r.isError() else list(r.registers)

    def di(self, a, n):
        r = self.c.read_discrete_inputs(a, n, slave=self.u)
        return None if r.isError() else list(r.bits[:n])

    def co(self, a, n):
        r = self.c.read_coils(a, n, slave=self.u)
        return None if r.isError() else list(r.bits[:n])

    # ---------------------------------------------------------------
    def check_global(self):
        print("\n== Bloque global (IR 2000..2009) ==")
        g = self.ir(IR_G_MARK, 10)
        if not self.ok(g is not None, "responde IR 2000..2009"):
            return 2
        self.ok(g[0] == MAPB_MARK, f"marca de protocolo = 0x{g[0]:04X} (esperado 0x0B01)")
        self.ok(g[IR_G_CONTRACT - IR_G_MARK] == CONTRACT_VERSION,
                f"CONTRACT_VERSION = {g[IR_G_CONTRACT - IR_G_MARK]} (esperado {CONTRACT_VERSION})")
        origin = g[IR_G_ORIGIN - IR_G_MARK]
        self.ok(origin in (0, 1), f"origen = {origin}")
        self.note(f"origen: {'LOGO! real' if origin == 1 else 'PLC-SIM'} | "
                  f"logica v{g[IR_G_LOGIC_VER - IR_G_MARK]}")
        n = g[IR_G_NSTATIONS - IR_G_MARK]
        self.ok(1 <= n <= 16, f"nro de estaciones = {n}")
        self.note(f"online_bits=0b{g[IR_G_ONLINE - IR_G_MARK]:016b}  "
                  f"alarma_general=[{bits_txt(g[IR_G_ALARM_OR - IR_G_MARK], ALM_BITS)}]")

        hb0 = g[IR_G_HEARTBEAT - IR_G_MARK]
        up0 = u32_hi_first(g[IR_G_UPTIME_W0 - IR_G_MARK], g[IR_G_UPTIME_W1 - IR_G_MARK])
        self.note(f"latido={hb0}  uptime={up0}s  (esperando 2.5 s para ver el latido avanzar...)")
        time.sleep(2.5)
        g2 = self.ir(IR_G_MARK, 10)
        hb1 = g2[IR_G_HEARTBEAT - IR_G_MARK] if g2 else hb0
        self.ok(hb1 != hb0, f"latido avanza ({hb0} -> {hb1})")
        return n

    # ---------------------------------------------------------------
    def check_station(self, s):
        print(f"\n== Estacion {s} (HR {s*HR_STRIDE}..{s*HR_STRIDE+31}) ==")
        hr = self.hr(s * HR_STRIDE, 32)
        di = self.di(s * DI_STRIDE, 8)
        co = self.co(s * CO_STRIDE, 16)
        if not self.ok(hr is not None, "responde el bloque HR"):
            return
        if not self.ok(di is not None, "responde el bloque DI"):
            di = [False] * 8
        if not self.ok(co is not None, "responde el bloque de coils"):
            co = [False] * 16

        level = hr[HR_LEVEL] / 100.0
        flow  = hr[HR_FLOW] / 100.0
        day   = u32_hi_first(hr[HR_DAY_W0], hr[HR_DAY_W1]) / 10.0
        mon   = u32_hi_first(hr[HR_MON_W0], hr[HR_MON_W1]) / 10.0
        st    = hr[HR_STATUS]
        alm   = hr[HR_ALARMS]
        self.note(f"Nivel={level:.2f}  Caudal={flow:.2f}  crudos=({hr[HR_LEVEL_RAW]},{hr[HR_FLOW_RAW]})")
        self.note(f"Acum dia={day:.1f} m3  mes={mon:.1f} m3  RSSI={s16(hr[HR_RSSI])} dBm  "
                  f"edad={hr[HR_AGE]} s  addr={hr[HR_LINK_ADDR]}  rderr={hr[HR_RDERR]}")
        self.note(f"STATUS=[{bits_txt(st, ST_BITS)}]")
        self.note(f"ALARMS=[{bits_txt(alm, ALM_BITS)}]")

        # coherencia DI <-> HR_STATUS
        pairs = [(DI_PRESOSTATO, 1 << 0, "presostato"), (DI_VOLT_LOCAL, 1 << 1, "volt_local"),
                 (DI_TAMPER, 1 << 2, "tamper"), (DI_LORA_OK, 1 << 5, "link_ok"),
                 (DI_IN_ALARM, 1 << 6, "en_alarma"), (DI_SIREN_ON, 1 << 4, "sirena_on")]
        for dbit, sbit, nm in pairs:
            self.ok(bool(di[dbit]) == bool(st & sbit), f"DI[{dbit}] coincide con STATUS.{nm}")

        # bloque de escala hb+20..31
        sc = hr[HR_SCALE_BASE:HR_SCALE_BASE + 12]
        lv = dict(rmin=sc[0], rmax=sc[1], emin=s16(sc[2]), emax=s16(sc[3]))
        fl = dict(rmin=sc[4], rmax=sc[5], emin=s16(sc[6]), emax=s16(sc[7]))
        u_lv, u_fl, filt, stamp = sc[8], sc[9], sc[10], sc[11]
        self.note(f"escala Nivel : raw {lv['rmin']}..{lv['rmax']}  eng {lv['emin']/100:.2f}..{lv['emax']/100:.2f}  "
                  f"unidad={UNITS_LEVEL[u_lv] if u_lv < 4 else u_lv}  filtro={filt}  sello={stamp}")
        self.note(f"escala Caudal: raw {fl['rmin']}..{fl['rmax']}  eng {fl['emin']/100:.2f}..{fl['emax']/100:.2f}  "
                  f"unidad={UNITS_FLOW[u_fl] if u_fl < 4 else u_fl}")
        self.ok(lv["rmax"] > lv["rmin"], "escala Nivel: raw_max > raw_min")
        self.ok(fl["rmax"] > fl["rmin"], "escala Caudal: raw_max > raw_min")
        self.ok(lv["emax"] != lv["emin"], "escala Nivel: eng_max != eng_min")
        self.ok(u_lv < 4 and u_fl < 4, "codigos de unidad en rango 0..3")
        if alm & (1 << 9):
            self.warning("alarma 'Escala invalida' activa en esta estacion")

    # ---------------------------------------------------------------
    def write_tests(self, s):
        print(f"\n== Pruebas de escritura (estacion {s}) ==")
        base_co = s * CO_STRIDE

        # 1) coil de silenciar se auto-limpia
        self.c.write_coil(base_co + CO_SILENCE, True, slave=self.u)
        time.sleep(1.5)
        c = self.co(base_co, 16)
        self.ok(c is not None and not c[CO_SILENCE],
                "coil 'silenciar' (cb+2) se auto-limpia tras el pulso")

        # 2) aplicar el bloque de escala (mismos valores) cambia el sello
        hr = self.hr(s * HR_STRIDE + HR_SCALE_BASE, 12)
        if not self.ok(hr is not None, "lee el bloque de escala"):
            return
        stamp_before = hr[11]
        self.c.write_registers(s * HR_STRIDE + HR_SCALE_BASE, hr, slave=self.u)
        self.c.write_coil(base_co + CO_APPLY_SCALE, True, slave=self.u)
        time.sleep(1.5)
        hr2 = self.hr(s * HR_STRIDE + HR_SCALE_BASE, 12)
        c2 = self.co(base_co, 16)
        self.ok(c2 is not None and not c2[CO_APPLY_SCALE],
                "coil 'aplicar escala' (cb+8) se auto-limpia")
        self.ok(hr2 is not None and hr2[11] != stamp_before,
                f"el sello de config cambia al aplicar ({stamp_before} -> {hr2[11] if hr2 else '?'})")
        self.ok(hr2 is not None and hr2[0:11] == hr[0:11],
                "los valores de escala quedan intactos (se escribieron los mismos)")


def main():
    ap = argparse.ArgumentParser(description="Verificador de conformidad del MAPA B (contrato v1)")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--stations", type=int, default=0,
                    help="nro de estaciones a revisar (0 = leerlo de IR 2001)")
    ap.add_argument("--write", action="store_true",
                    help="ejecuta pruebas de escritura (silenciar + aplicar escala con los mismos valores)")
    ap.add_argument("--station", type=int, default=0, help="estacion para las pruebas de escritura")
    args = ap.parse_args()

    cli = ModbusTcpClient(args.host, port=args.port, timeout=3)
    if not cli.connect():
        print(f"ERROR: no conecta a {args.host}:{args.port}")
        return 2
    print(f"Conectado a {args.host}:{args.port}  (Unit ID {args.unit})")

    chk = Checker(cli, args.unit)
    try:
        n = chk.check_global()
        n_stations = args.stations or (n if isinstance(n, int) and n > 0 else 2)
        for s in range(n_stations):
            chk.check_station(s)
        if args.write:
            chk.write_tests(args.station)
    finally:
        cli.close()

    print(f"\n=== Resultado: {chk.fail} FAIL, {chk.warn} avisos ===")
    return 1 if chk.fail else 0


if __name__ == "__main__":
    sys.exit(main())
