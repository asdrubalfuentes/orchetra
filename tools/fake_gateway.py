#!/usr/bin/env python3
"""
fake_gateway.py  -  Pasarela LoRa falsa: sirve el MAPA A del contrato por Modbus
TCP para probar el PLC-SIM (o el LOGO! real) y el HMI sin hardware LoRa.

  python fake_gateway.py --port 1602 --scenario normal
  python fake_gateway.py --port 1602 --scenario lowlevel   # dispara alarmas de nivel
  python fake_gateway.py --port 1602 --scenario tamper

Estructura (contrato Seccion 3): por nodo i, base i*16, Input Registers:
  b+0..3 AI1..AI4  ·  b+4 DI bitfield  ·  b+5 rele bitfield  ·  b+6 link
  b+7 RSSI(int16)  ·  b+8 edad s  ·  b+9 addr LoRa  ·  b+10 fw
Discrete Inputs b+0..3 = DI1..4, b+4 = link. Coils b+0..3 consigna de rele.
Global Input Reg 900 = 0x0203, 901 nodeCount, 902 online.
"""
import argparse
import asyncio
import math
import time

from pymodbus.datastore import (ModbusSequentialDataBlock, ModbusServerContext,
                                ModbusSlaveContext)
from pymodbus.server import StartAsyncTcpServer

NODE_STRIDE = 16
GLOBAL_BASE = 900

# escenarios: (ai1_base, ai2_base, di_bits)   di bit0 presostato, bit1 volt, bit2 tamper
SCEN = {
    "normal":   (2400, 1500, 0b0011),
    "lowlevel": (600,  0,    0b0010),
    "highlevel":(3900, 1800, 0b0011),
    "tamper":   (2400, 1500, 0b0111),
    "noflow":   (2400, 5,    0b0001),
    "novolt":   (2400, 0,    0b0000),
}


def build_context(nodes):
    ir = [0] * (GLOBAL_BASE + 16)
    for i in range(nodes):
        b = i * NODE_STRIDE
        ir[b + 6] = 1                     # link
        ir[b + 7] = (-70 - i * 8) & 0xFFFF  # rssi
        ir[b + 8] = 1                     # edad
        ir[b + 9] = 11 + i               # addr LoRa
        ir[b + 10] = 8                   # fw
    ir[GLOBAL_BASE + 0] = 0x0203
    ir[GLOBAL_BASE + 1] = nodes
    ir[GLOBAL_BASE + 2] = nodes
    slave = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * 256),
        co=ModbusSequentialDataBlock(0, [0] * 256),
        hr=ModbusSequentialDataBlock(0, [0] * 16),
        ir=ModbusSequentialDataBlock(0, ir),
        zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


async def animate(ctx, nodes, scenario):
    ai1_0, ai2_0, di = SCEN[scenario]
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        for i in range(nodes):
            b = i * NODE_STRIDE
            ph = i * 1.7
            ai1 = max(0, min(4095, int(ai1_0 + 250 * math.sin(t / 20 + ph))))
            ai2 = max(0, min(4095, int(ai2_0 + (120 * math.sin(t / 7 + ph) if ai2_0 else 0))))
            ctx[0].setValues(4, b + 0, [ai1, ai2, 0, 0, di])
            ctx[0].setValues(2, b + 0, [bool(di & 1), bool(di & 2), bool(di & 4), False, True])
            # eco de la consigna de rele (coil b+0) en el bitfield de reles (b+5)
            relay = ctx[0].getValues(1, b + 0, 4)
            rb = sum((1 << k) for k in range(4) if relay[k])
            ctx[0].setValues(4, b + 5, [rb])
        await asyncio.sleep(0.5)


async def main():
    ap = argparse.ArgumentParser(description="Pasarela LoRa falsa (MAPA A por Modbus TCP)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=1602)
    ap.add_argument("--nodes", type=int, default=2)
    ap.add_argument("--scenario", choices=list(SCEN), default="normal")
    args = ap.parse_args()

    ctx = build_context(args.nodes)
    print(f"fake_gateway: MAPA A en {args.host}:{args.port}  ·  {args.nodes} nodo(s)  ·  escenario '{args.scenario}'")
    asyncio.create_task(animate(ctx, args.nodes, args.scenario))
    await StartAsyncTcpServer(context=ctx, address=(args.host, args.port))


if __name__ == "__main__":
    asyncio.run(main())
