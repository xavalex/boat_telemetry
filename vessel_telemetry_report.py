import asyncio
import re
import sys
import requests
import json
import tinytuya

from victron_ble.exceptions import AdvertisementKeyMissingError
from victron_ble.scanner import Scanner

# --- MASTER CONFIGURATION ---
BOT_TOKEN = "8694739414:AAFWpNk2rKENyrYbEndh0eN1TuLdGaCZQYg"
CHAT_ID = "6071049012"
SBMS_IP = "192.168.1.186"

DEVICE_ID = "bffcf32e83ea5301a7vu9j"
LOCAL_KEY = "K$Izl;w{#U&$P$6S"
IP_ADDRESS = "192.168.1.241"

DEVICE_MAC = "f0:50:7d:7e:4b:80"
ENCRYPTION_KEY = "2bd66038933d98e74c0ca53f5da5c5ab"

# Global dictionary to capture the single decrypted packet data
latest_mppt_data = {}


# --- VICTRON BLE SCANNER ARCHITECTURE ---
class SinglePacketScanner(Scanner):
    """Listens for exactly one valid decrypted MPPT packet, then stops."""

    def __init__(self, key_map, stop_event):
        super().__init__(key_map)
        self.stop_event = stop_event

    def callback(self, ble_device, raw_data, advertisement):
        if ble_device.address.lower() != DEVICE_MAC.lower():
            return

        try:
            device = self.get_device(ble_device, raw_data)
            mppt_data = device.parse(raw_data)

            global latest_mppt_data
            latest_mppt_data = {
                "voltage": mppt_data.get_battery_voltage(),
                "current": mppt_data.get_battery_charging_current(),
                "power": mppt_data.get_solar_power(),
                "state": mppt_data.get_charge_state().name,
                "yield": mppt_data.get_yield_today(),
            }
            # Break the blocking loop
            self.stop_event.set()

        except AdvertisementKeyMissingError:
            return
        except Exception as e:
            print(f"⚠️ BLE Parser Error: {e}", file=sys.stderr)


async def get_solar_telemetry():
    """Runs the BLE scanner until an MPPT advertisement is captured or times out."""
    stop_event = asyncio.Event()
    scanner = SinglePacketScanner({DEVICE_MAC: ENCRYPTION_KEY}, stop_event)

    await scanner.start()
    try:
        # Wait up to 10 seconds for the MPPT to cycle an advertisement broadcast
        await asyncio.wait_for(stop_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        print("⚠️ BLE Scan Timeout: No Victron broadcast intercepted.")
    finally:
        await scanner.stop()


# --- ELECTRODACUS SBMS HTTP PARSER ---
def decode_sbms_char(char):
    return ord(char) - 35


def get_sbms_data(ip_address):
    """Connects to the ElectroDacus SSE stream, extracts the first valid data frame, and returns it."""
    url = f"http://{ip_address}/eData"
    try:
        # Open a streaming connection to catch the Server-Sent Events
        with requests.get(url, stream=True, timeout=5) as response:
            for line in response.iter_lines():
                if not line:
                    continue

                # Decode the raw byte line into text
                decoded_line = line.decode("utf-8").strip()

                # Look for the line starting with 'data:'
                if decoded_line.startswith("data:"):
                    json_str = decoded_line.replace("data:", "").strip()

                    # Skip empty data lines safely
                    if not json_str:
                        continue

                    try:
                        # Load it into a Python dictionary
                        sbms_json = json.loads(json_str)

                        # Extract values directly
                        soc = sbms_json.get("soc")
                        temp_int = sbms_json.get("tempInt")
                        cells_mv = sbms_json.get("cellsMV", [])

                        # Map your 4 active cells (Channels 1, 2, 7, 8) converting mV to V
                        c1 = (
                            round(cells_mv[0] / 1000.0, 3)
                            if len(cells_mv) > 0
                            else 0.0
                        )
                        c2 = (
                            round(cells_mv[1] / 1000.0, 3)
                            if len(cells_mv) > 1
                            else 0.0
                        )
                        c3 = (
                            round(cells_mv[6] / 1000.0, 3)
                            if len(cells_mv) > 6
                            else 0.0
                        )
                        c4 = (
                            round(cells_mv[7] / 1000.0, 3)
                            if len(cells_mv) > 7
                            else 0.0
                        )
                        cell_voltages = [c1, c2, c3, c4]

                        total_voltage = round(sum(cell_voltages), 2)

                        # Extract current data and convert mA to A
                        current_data = sbms_json.get("currentMA", {})
                        battery_ma = current_data.get("battery", 0)
                        net_current = round(battery_ma / 1000.0, 2)

                        return {
                            "total_voltage": total_voltage,
                            "cell_voltages": cell_voltages,
                            "soc": soc,
                            "temperature": temp_int,
                            "net_current": net_current,
                            "error": None,
                        }
                    except json.JSONDecodeError:
                        # If a line has invalid JSON data, ignore it and wait for the next line
                        continue

        return {"error": "Stream closed before receiving a data frame."}

    except Exception as e:
        return {"error": f"BMS SSE Parser error: {str(e)}"}


# --- FANELITE DEHUMIDIFIER TELEMETRY FUNCTION ---
def get_dehumidifier_status():
    """Connects to Fanelite over LAN and extracts live environmental conditions."""
    try:
        # Connect directly to the appliance over local Wi-Fi
        d = tinytuya.OutletDevice(DEVICE_ID, address=IP_ADDRESS, local_key=LOCAL_KEY)
        d.set_version(3.4) 
        
        payload = d.status()
        
        if payload and 'dps' in payload:
            current_humidity = payload['dps'].get('6')
            is_on = payload['dps'].get('1')
            
            power_status = "ON" if is_on else "OFF"
            return f"💧 Boat Humidity: {current_humidity}% (Dehumidifier: {power_status})\n"
        else:
            return "💧 Boat Humidity: <i>Error (Unable to parse data points)</i>\n"
                        
    except Exception:
        return "💧 Boat Humidity: <i>Error (Device Unreachable)</i>\n"

# --- PI ZERO TEMPERATURE
def get_pi_cpu_temperature():
    """Reads the Raspberry Pi internal CPU thermal sensor directly from the system zone."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            # The system returns the temp in millidegrees Celsius (e.g., 43500)
            millidegrees = float(f.read().strip())
            return round(millidegrees / 1000.0, 1)
    except Exception as e:
        # Fallback if the file path isn't readable
        return None

# --- TELEGRAM DISPATCH ---
def send_telegram_update(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False


# --- RUN COROUTINE CONTROLLER ---
async def main():
    # 1. Gather SBMS data over local IP via standard synchronous execution
    metrics = get_sbms_data(SBMS_IP)

    # 2. Gather Victron data asynchronously from the BLE radio stream
    await get_solar_telemetry()

    # 3. Gather local Dehumidifier/Saloon Humidity telemetry
    humidity_msg = get_dehumidifier_status()

    # 4. Get P{i Zero temperature
    pi_temp = get_pi_cpu_temperature()

    # 5. Build the unified text payload
    if not metrics or metrics.get("error"):
        error_reason = (
            metrics["error"] if metrics else "Unknown critical parser failure."
        )
        alert_msg = f"🚨 Telemetry Error: {error_reason}"
    else:
        direction = "🟢" if metrics["net_current"] >= 0 else "🔴"

        alert_msg = (
            "<b>⚠️ Katharina House Bank Report</b>\n"
            "---------------------------------\n"
            "🔋 State of Charge: {}%\n"
            "⚡ Total Voltage: {} V\n"
            "{} Net Current: {} A\n"
            "🌡️ BMS Temp: {} °C\n"
            "{}"  # <-- This is where your live humidity text seamlessly slides into place
            "---------------------------------\n"
            "Individual Cell Levels:\n"
            "  ▪️ Cell 1: {} V\n"
            "  ▪️ Cell 2: {} V\n"
            "  ▪️ Cell 3: {} V\n"
            "  ▪️ Cell 4: {} V\n"
            "---------------------------------\n".format(
                metrics["soc"],
                metrics["total_voltage"],
                direction,
                metrics["net_current"],
                metrics["temperature"],
                humidity_msg,  # Inserts the cleanly formatted humidity string
                metrics["cell_voltages"][0],
                metrics["cell_voltages"][1],
                metrics["cell_voltages"][2],
                metrics["cell_voltages"][3],
            )
        )

        # Append the latest Victron dataset if captured cleanly
        if latest_mppt_data:
            victron_msg = (
                "<b>☀️ Solar MPPT 100/50</b>\n"
                "  ▪️ Battery: {} V\n"
                "  ▪️ Charge Current: {} A\n"
                "  ▪️ Array Power: {} W\n"
                "  ▪️ Charge State: {}\n"
                "  ▪️ Yield Today: {} Wh\n"
                "---------------------------------".format(
                    latest_mppt_data["voltage"],
                    latest_mppt_data["current"],
                    latest_mppt_data["power"],
                    latest_mppt_data["state"],
                    latest_mppt_data["yield"],
                )
            )
            alert_msg += victron_msg
        else:
            alert_msg += "☀️ Solar Data: <i>Unavailable (BLE Timeout)</i>\n---------------------------------\n"

        # Append Pi Zero temperature
        # If the Pi temperature reading is valid, add it cleanly to the string
        if pi_temp is not None:
            alert_msg += f"\n🧠 *Pi Zero Tmep: {pi_temp}°C\n"

        alert_msg += f"-----------------------------------\n"

    # 5. Ship the combined report out to Telegram
    send_telegram_update(BOT_TOKEN, CHAT_ID, alert_msg)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess aborted manually.")
