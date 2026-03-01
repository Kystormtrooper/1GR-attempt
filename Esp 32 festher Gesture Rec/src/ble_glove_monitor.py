import asyncio
import datetime as dt
from pathlib import Path

from bleak import BleakClient, BleakScanner

DEVICE_NAME = "GLOVE-ESP32"

SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # notify from ESP32 -> PC

# --- Gesture memory ---
last_action = None


def now_stamp() -> str:
    return dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def decode_payload(data: bytearray) -> str:
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception: 
        return repr(bytes(data))


async def find_device_by_name(name: str, timeout: float = 10.0):
    print(f"[{now_stamp()}] Scanning for '{name}' ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if (d.name or "").strip() == name:
            print(f"[{now_stamp()}] Found: {d.name}  address={d.address}")
            return d
    return None


def try_parse_elev_action(line: str):
    """
    Expects your ESP32 line to end like: ..., pitch, elev, action
    Returns (elev, action) or (None, None) if it can't parse.
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None, None

    elev = parts[-2]
    action = parts[-1]

    # Optional sanity: only accept known elev labels
    if elev not in {"LOW", "MID", "HIGH", "OTHER"}:
        return None, None

    if not action:
        return None, None

    return elev, action


async def main():
    log_path = Path("glove_ble_log.csv")
    do_log = True

    device = await find_device_by_name(DEVICE_NAME, timeout=12.0)
    if not device:
        print(f"[{now_stamp()}] Not found. Tips:")
        print("  - Make sure ESP32 is advertising (power-cycle it).")
        print("  - Close other BLE apps (Bluetooth LE Explorer, etc.).")
        return

    buffer = ""

    def handle_notify(_, data: bytearray):
        global last_action
        nonlocal buffer

        text = decode_payload(data)
        buffer += text

        # --- Print complete lines (preferred) ---
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            print(f"[{now_stamp()}] {line}")
            if do_log:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")

            # --------- YOUR CUSTOM GESTURES GO HERE ---------
            elev, action = try_parse_elev_action(line)
            if elev is None:
                continue

            # Gesture 1: LOW + TWIST_FIST (rapid twist while watching)
            if elev == "LOW" and action == "TWIST_FIST":
                print(f"[{now_stamp()}] 🔥 GESTURE_1: LOW + TWIST_FIST")

            # Gesture 2: HIGH + (FIST -> POINT) transition
            if elev == "HIGH" and last_action == "FIST" and action == "POINT":
                print(f"[{now_stamp()}] ✨ GESTURE_2: HIGH FIST → POINT")

            last_action = action
            # ------------------------------------------------

        # --- If ESP32 doesn't include '\n', treat big chunks as a "line" ---
        if "\n" not in text and "," in text and len(text) > 20:
            pseudo_line = text.strip()
            print(f"[{now_stamp()}] {pseudo_line}")
            if do_log:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(pseudo_line + "\n")

            elev, action = try_parse_elev_action(pseudo_line)
            if elev is not None:
                if elev == "LOW" and action == "TWIST_FIST":
                    print(f"[{now_stamp()}] 🔥 GESTURE_1: LOW + TWIST_FIST")

                if elev == "HIGH" and last_action == "FIST" and action == "POINT":
                    print(f"[{now_stamp()}] ✨ GESTURE_2: HIGH FIST → POINT")

                last_action = action

    print(f"[{now_stamp()}] Connecting to {device.address}...")
    async with BleakClient(device) as client:
        if not client.is_connected:
            print(f"[{now_stamp()}] Failed to connect.")
            return

        print(f"[{now_stamp()}] Connected ✅")
        print(f"[{now_stamp()}] Subscribing to notifications on {TX_CHAR_UUID} ...")

        await client.start_notify(TX_CHAR_UUID, handle_notify)

        print(f"[{now_stamp()}] Listening... (Ctrl+C to stop)")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            print(f"\n[{now_stamp()}] Stopping...")
        finally:
            await client.stop_notify(TX_CHAR_UUID)

    print(f"[{now_stamp()}] Disconnected.")
    if do_log:
        print(f"[{now_stamp()}] Log saved to: {log_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())