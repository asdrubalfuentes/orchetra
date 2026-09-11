#!/usr/bin/env python3
"""
mapa_a_verify.py - Compara el MAPA A crudo (pasarela) contra lo que el LOGO! 9
importo por Network Input, campo a campo, para las estaciones 0 y 1.

No sustituye a mapb_check.py (ese verifica el contrato PUBLICADO, HR0-105).
Este script mira ademas la zona de scratch interno (VW400.., no publicada) que
mapb_check no conoce.

Formulas (PLC_REGISTER_RECIPE.md SS2, REGISTER_MAP.md SS3.1), para estacion s (0 o 1):
  Pasarela (FC04, Input Registers), base b = s*16:
    b+0 AI1 (nivel crudo)   b+1 AI2 (caudal crudo)
    b+4 DI bitfield         b+5 Reles bitfield       b+6 Enlace
    b+7 RSSI                b+8 Antiguedad           b+9 Direccion LoRa

  LOGO! (FC03, Holding Registers = VW/2), por bloque:
    NI-*a (eco escalado): HR (2 + s*32), (3 + s*32)      <- VW4/6 (s=0), VW68/70 (s=1)
    NI-*b (scratch, NO publicado): HR (200 + s*16) .. +2 <- VW400/402/404 (s=0), VW432/434/436 (s=1)
    NI-*c (eco):          HR (10 + s*32) .. +2           <- VW20/22/24 (s=0), VW84/86/88 (s=1)

Uso:
  pip install -r requirements.txt
  python mapa_a_verify.py --gw-host 192.168.1.50 --logo-host 192.168.1.56 --logo-port 503
"""
import argparse
import sys

from pymodbus.client import ModbusTcpClient


def rd(cli, fn, addr, count, unit):
    if fn == "ir":
        r = cli.read_input_registers(addr, count=count, slave=unit)
    else:
        r = cli.read_holding_registers(addr, count=count, slave=unit)
    if r.isError():
        return None
    return list(r.registers)


def s16(v):
    return v - 65536 if v >= 32768 else v


def check(label, gw_vals, logo_vals, names):
    ok = True
    if gw_vals is None or logo_vals is None:
        print(f"  [FAIL] {label}: no se pudo leer (gw={gw_vals} logo={logo_vals})")
        return False
    for n, g, l in zip(names, gw_vals, logo_vals):
        marca = "OK " if g == l else "FAIL"
        if g != l:
            ok = False
        print(f"  [{marca}] {n:<22} pasarela={g:<6} logo={l:<6}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="Compara MAPA A (pasarela) vs. lo importado en el LOGO!")
    ap.add_argument("--gw-host", required=True, help="IP del nodeIO_master (gateway)")
    ap.add_argument("--gw-port", type=int, default=502)
    ap.add_argument("--gw-unit", type=int, default=1)
    ap.add_argument("--logo-host", required=True, help="IP del LOGO! 9 / PLC-SIM")
    ap.add_argument("--logo-port", type=int, default=502)
    ap.add_argument("--logo-unit", type=int, default=1)
    ap.add_argument("--stations", type=int, default=2, help="cuantas estaciones probar (0 y 1 por defecto)")
    args = ap.parse_args()

    gw = ModbusTcpClient(args.gw_host, port=args.gw_port, timeout=3)
    logo = ModbusTcpClient(args.logo_host, port=args.logo_port, timeout=3)
    if not gw.connect():
        sys.exit(f"No conecta a la pasarela {args.gw_host}:{args.gw_port}")
    if not logo.connect():
        sys.exit(f"No conecta al LOGO!/PLC-SIM {args.logo_host}:{args.logo_port}")

    all_ok = True
    for s in range(args.stations):
        b = s * 16
        print(f"\n=== Estacion {s} ===")

        # a) escalado: AI1/AI2 crudo
        gw_a = rd(gw, "ir", b + 0, 2, args.gw_unit)
        logo_a = rd(logo, "hr", 2 + s * 32, 2, args.logo_unit)
        all_ok &= check("NI-%da (escalado)" % s, gw_a, logo_a, ["nivel_crudo", "caudal_crudo"])

        # b) scratch: DI / Reles / Enlace  (NO esta en el contrato publicado)
        gw_b = rd(gw, "ir", b + 4, 3, args.gw_unit)
        logo_b = rd(logo, "hr", 200 + s * 16, 3, args.logo_unit)
        all_ok &= check("NI-%db (scratch)" % s, gw_b, logo_b, ["DI_bitfield", "Reles_bitfield", "Enlace"])

        # c) eco: RSSI / antiguedad / direccion LoRa
        gw_c = rd(gw, "ir", b + 7, 3, args.gw_unit)
        logo_c = rd(logo, "hr", 10 + s * 32, 3, args.logo_unit)
        if gw_c and logo_c:
            gw_c = [s16(gw_c[0])] + gw_c[1:]   # RSSI es int16
            logo_c = [s16(logo_c[0])] + logo_c[1:]
        all_ok &= check("NI-%dc (eco)" % s, gw_c, logo_c, ["RSSI_dBm", "antiguedad_s", "dir_LoRa"])

    gw.close()
    logo.close()
    print("\n" + ("TODO OK" if all_ok else "HAY DIFERENCIAS - revisar arriba"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
