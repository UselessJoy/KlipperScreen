import contextlib
import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib
from typing import Union

class Printer:
    def __init__(self, state_cb, state_callbacks) -> None:
        self.config = {}
        self.data = {}
        self.state = "disconnected"
        self.state_cb = state_cb
        self.state_callbacks = state_callbacks
        self.devices = {}
        self.power_devices = {}
        self.tools = []
        self.extrudercount = 0
        self.tempdevcount = 0
        self.fancount = 0
        self.ledcount = 0
        self.output_pin_count = 0
        self.store_timeout = None
        self.tempstore = {}
        self.tempstore_size = 1200
        self.cameras = []
        self.available_commands = {}
        self.system_info = {}
        self.spoolman = False
        self.temp_devices = self.sensors = None

    def reinit(self, printer_info, data) -> None:
        self.config = data['configfile']['config']
        self.data = data
        self.devices.clear()
        self.tools.clear()
        self.extrudercount = 0
        self.tempdevcount = 0
        self.fancount = 0
        self.ledcount = 0
        self.output_pin_count = 0
        self.tempstore.clear()
        self.tempstore_size = 1200
        self.available_commands.clear()
        self.system_info.clear()
        self.temp_devices = self.sensors = None
        self.stop_tempstore_updates()

        for x in self.config.keys():
            if x[:8] == "extruder":
                self.tools.append(x)
                self.tools = sorted(self.tools)
                self.extrudercount += 1
                if x.startswith('extruder_stepper'):
                    continue
                self.devices[x] = {
                    "temperature": 0,
                    "target": 0
                }
            if x == 'heater_bed' \
                    or x.startswith('heater_generic ') \
                    or x.startswith('temperature_sensor ') \
                    or x.startswith('temperature_fan '):
                self.devices[x] = {"temperature": 0}
                if not x.startswith('temperature_sensor '):
                    self.devices[x]["target"] = 0
                # Support for hiding devices by name
                name = x.split()[1] if len(x.split()) > 1 else x
                if not name.startswith("_"):
                    self.tempdevcount += 1
            if x == 'fan' \
                    or x.startswith('controller_fan ') \
                    or x.startswith('heater_fan ') \
                    or x.startswith('fan_generic '):
                # Support for hiding devices by name
                name = x.split()[1] if len(x.split()) > 1 else x
                if not name.startswith("_"):
                    self.fancount += 1
            if x.startswith('output_pin ') and not x.split()[1].startswith("_"):
                self.output_pin_count += 1
            if x.startswith('bed_mesh '):
                try:
                    r = self.config[x]
                    r['x_count'] = int(r['x_count'])
                    r['y_count'] = int(r['y_count'])
                    r['max_x'] = float(r['max_x'])
                    r['min_x'] = float(r['min_x'])
                    r['max_y'] = float(r['max_y'])
                    r['min_y'] = float(r['min_y'])
                    r['points'] = [[float(j.strip()) for j in i.split(",")] for i in r['points'].strip().split("\n")]
                except KeyError:
                    logging.debug(f"Couldn't load mesh {x}: {self.config[x]}")
            if x.startswith('led') \
                    or x.startswith('neopixel ') \
                    or x.startswith('dotstar ') \
                    or x.startswith('pca9533 ') \
                    or x.startswith('pca9632 '):
                name = x.split()[1] if len(x.split()) > 1 else x
                if not name.startswith("_"):
                    self.ledcount += 1
        self.process_update(data)

        logging.info(f"Klipper version: {printer_info['software_version']}")
        logging.info(f"# Extruders: {self.extrudercount}")
        logging.info(f"# Temperature devices: {self.tempdevcount}")
        logging.info(f"# Fans: {self.fancount}")
        logging.info(f"# Output pins: {self.output_pin_count}")
        logging.info(f"# Leds: {self.ledcount}")

    def stop_tempstore_updates(self) -> None:
        logging.info("Stopping tempstore")
        if self.store_timeout is not None:
            GLib.source_remove(self.store_timeout)
            self.store_timeout = None
            
    def process_update(self, data) -> None:
        if self.data is None:
            return
        for x in (self.get_temp_devices() + self.get_filament_sensors()):
            if x in data:
                for i in data[x]:
                  self.set_dev_stat(x, i, data[x][i])
        for x in data:
            if x == "configfile":
                if not 'save_config_pending' in data[x] or not 'save_config_pending_items' in data[x]:
                    continue
            if x not in self.data:
                self.data[x] = {}
            self.data[x].update(data[x])
        if "webhooks" in data or "print_stats" in data or "idle_timeout" in data:
            self.process_status_update()

    def evaluate_state(self) -> str:
        # webhooks states: startup, ready, shutdown, error
        # print_stats: standby, printing, paused, error, complete
        # idle_timeout: Idle, Printing, Ready
        if self.data['webhooks']['state'] == "ready":
            with contextlib.suppress(KeyError):
                if self.data['print_stats']['state'] == 'interrupt':
                    return "interrupt"
                if self.data['print_stats']['state'] == 'paused':
                    return "paused"
                if self.data['print_stats']['state'] == 'printing':
                    return "printing"
        return self.data['webhooks']['state']

    def process_status_update(self) -> bool:
        state = self.evaluate_state()
        if state != self.state:
            self.change_state(state)
        return False

    def process_power_update(self, data) -> None:
        if data['device'] in self.power_devices:
            self.power_devices[data['device']]['status'] = data['status']

    def change_state(self, state) -> None:
        if state not in list(self.state_callbacks):
            return  # disconnected, startup, ready, shutdown, error, paused, printing
        if state != self.state:
            logging.debug(f"Changing state from '{self.state}' to '{state}'")
            self.state = state
        if self.state_callbacks[state] is not None:
            logging.debug(f"Adding callback for state: {state}")
            GLib.idle_add(self.state_cb, self.state_callbacks[state])

    def configure_power_devices(self, data) -> None:
        self.power_devices = {}

        logging.debug(f"Processing power devices: {data}")
        for x in data['devices']:
            self.power_devices[x['device']] = {
                "status": "on" if x['status'] == "on" else "off"
            }
        logging.debug(f"Power devices: {self.power_devices}")
        
    def configure_cameras(self, data) -> None:
        self.cameras = data
        logging.debug(f"Cameras: {self.cameras}")

    def get_config_section_list(self, search="") -> list:
        if self.config is not None:
            return [i for i in list(self.config) if i.startswith(search)] if hasattr(self, "config") else []
        return []

    def get_config_section(self, section) -> Union[dict, bool]:
        return self.config[section] if section in self.config else False

    def get_macro(self, macro) -> Union[dict, bool]:
        return next(
            (
                self.config[key]
                for key in self.config.keys()
                if key.find(macro) > -1
            ),
            False,
        )

    def get_fans(self, fan_types = ["controller_fan", "fan_generic", "heater_fan"], append_fan = True) -> list:
        fans = []
        if append_fan and self.config_section_exists("fan"):
            fans.append("fan")
        for fan_type in fan_types:
            fans.extend(iter(self.get_config_section_list(f"{fan_type} ")))
        return fans

    def get_output_pins(self) -> list:
        return self.get_config_section_list("output_pin ")

    def get_gcode_macros(self) -> list:
        macros = []
        for macro in self.get_config_section_list("gcode_macro "):
            macro = macro[12:].strip()
            if macro.startswith("_") or macro.upper() in ('LOAD_FILAMENT', 'UNLOAD_FILAMENT'):
                continue
            if self.get_macro(macro) and "rename_existing" in self.get_macro(macro):
                continue
            macros.append(macro)
        return macros

    def get_neopixels(self) -> list:
        neopixels = []
        neopixels.extend(iter(self.get_config_section_list("neopixel ")))
        return neopixels
    
    def get_heaters(self) -> list:
        heaters = self.get_config_section_list("heater_generic ")
        if "heater_bed" in self.devices:
            heaters.insert(0, "heater_bed")
        return heaters

    def get_temp_fans(self) -> list:
        return self.get_config_section_list("temperature_fan")

    def get_temp_sensors(self) -> list:
        return self.get_config_section_list("temperature_sensor")
    
    def get_filament_sensors(self) -> list:
        if self.sensors is None:
            self.sensors = list(self.get_config_section_list("filament_switch_sensor "))
            self.sensors.extend(iter(self.get_config_section_list("filament_motion_sensor ")))
        return self.sensors

    def get_probe(self) -> Union[dict, bool, None]:
        probe_types = ["probe", "bltouch", "smart_effector", "dockable_probe"]
        for probe_type in probe_types:
            if self.config_section_exists(probe_type):
                logging.info(f"Probe type: {probe_type}")
                return self.get_config_section(probe_type)
        return None

    def get_printer_status_data(self) -> dict:
        return {
            "moonraker": {
                "power_devices": {"count": len(self.get_power_devices())},
                "cameras": {"count": len(self.cameras)},
                "spoolman": self.spoolman,
            },
            "printer": {
                "extruders": {"count": self.extrudercount},
                "temperature_devices": {"count": self.tempdevcount},
                "fans": {"count": self.fancount},
                "output_pins": {"count": self.output_pin_count},
                "gcode_macros": {"count": len(self.get_gcode_macros())},
                "leds": {"count": self.ledcount},
                "config_sections": [section for section in self.config.keys()],
            }
        }

    def get_leds(self) -> list:
        return [
            led
            for led_type in ["dotstar", "led", "neopixel", "pca9533", "pca9632"]
            for led in self.get_config_section_list(f"{led_type} ")
            if not led.split()[1].startswith("_")
        ]

    def get_led_color_order(self, led) -> Union[str, None]:
        if led not in self.config or led not in self.data:
            logging.debug(f"Error getting {led} config")
            return None
        elif "color_order" in self.config[led]:
            return self.config[led]["color_order"]
        colors = ''
        for option in self.config[led]:
            if option in ("red_pin", 'initial_RED') and 'R' not in colors:
                colors += 'R'
            elif option in ("green_pin", 'initial_GREEN') and 'G' not in colors:
                colors += 'G'
            elif option in ("blue_pin", 'initial_BLUE') and 'B' not in colors:
                colors += 'B'
            elif option in ("white_pin", 'initial_WHITE') and 'W' not in colors:
                colors += 'W'
        logging.debug(f"Colors in led: {colors}")
        return colors
    
    def get_power_devices(self) -> list:
        return list(self.power_devices)

    def get_power_device_status(self, device) -> Union[None, str]:
        if device not in self.power_devices:
            return
        return self.power_devices[device]['status']

    def get_stat(self, stat, substat=None) -> dict:
        if self.data is None or stat not in self.data:
            return {}
        if substat is not None:
            return self.data[stat][substat] if substat in self.data[stat] else {}
        return self.data[stat]

    def get_dev_stat(self, dev, stat) -> Union[dict, None]:
        if dev in self.devices and stat in self.devices[dev]:
            return self.devices[dev][stat]
        return None

    def get_fan_speed(self, fan="fan") -> float:
        speed = 0
        if fan not in self.config or fan not in self.data:
            logging.debug(f"Error getting {fan} config")
            return speed
        if "speed" in self.data[fan]:
            speed = self.data[fan]["speed"]
        if 'max_power' in self.config[fan]:
            max_power = float(self.config[fan]['max_power'])
            if max_power > 0:
                speed = speed / max_power
        if 'off_below' in self.config[fan]:
            off_below = float(self.config[fan]['off_below'])
            if speed < off_below:
                speed = 0
        return speed

    def get(self, section, option=None, default=None):
        if section in self.data:
            if not option:
              return self.data[section]
            if option in self.data[section]:
              return self.data[section][option] 
        return default
    
    def get_pin_value(self, pin) -> int:
        if pin in self.data:
            return self.data[pin]["value"]
        elif pin in self.config and 'value' in self.config[pin]:
            return self.config[pin]["value"]
        return 0

    def get_temp_store_devices(self) -> list:
        return list(self.tempstore)

    def device_has_target(self, device) -> bool:
        return ("target" in self.devices[device])

    def device_has_power(self, device) -> bool:
        return ("power" in self.devices[device])

    def get_temp_store(self, device, section=False, results=0) -> Union[dict, bool, None]:
        if device not in self.tempstore:
            return False

        if section is not False:
            if section not in self.tempstore[device]:
                return False
            if results == 0 or results >= len(self.tempstore[device][section]):
                return self.tempstore[device][section]
            return self.tempstore[device][section][-results:]

        temp = {}
        for section in self.tempstore[device]:
            if results == 0 or results >= len(self.tempstore[device][section]):
                temp[section] = self.tempstore[device][section]
            temp[section] = self.tempstore[device][section][-results:]
        return temp

    def get_tempstore_size(self) -> int:
        return self.tempstore_size
    
    def get_temp_devices(self) -> list:
        if self.temp_devices is None:
            devices = [
                device
                for device in self.tools
                if not device.startswith('extruder_stepper')
            ]
            self.temp_devices = devices + self.get_heaters() + self.get_temp_sensors() + self.get_temp_fans()
        return self.temp_devices
    
    def get_tools(self) -> list:
        return self.tools

    def get_tool_number(self, tool) -> int:
        return self.tools.index(tool)

    def init_temp_store(self, tempstore) -> None:
        if self.tempstore and set(self.tempstore) != set(tempstore):
            logging.debug("Tempstore has changed")
            self.tempstore = tempstore
            self.change_state(self.state)
        else:
            self.tempstore = tempstore
        for device in self.tempstore:
            for x in self.tempstore[device]:
                length = len(self.tempstore[device][x])
                if length < self.tempstore_size:
                    for _ in range(1, self.tempstore_size - length):
                        self.tempstore[device][x].insert(0, 0)
        logging.info(f"Temp store: {list(self.tempstore)}")
        if not self.store_timeout:
            self.store_timeout = GLib.timeout_add_seconds(1, self._update_temp_store)

    def config_section_exists(self, section) -> bool:
        return section in self.get_config_section_list()

    def set_dev_stat(self, dev, stat, value) -> None:
        if dev not in self.devices:
            return
        self.devices[dev][stat] = value

    def _update_temp_store(self) -> bool:
        if self.tempstore is None:
            return False
        for device in self.tempstore:
            for x in self.tempstore[device]:
                self.tempstore[device][x].pop(0)
                temp = self.get_dev_stat(device, x[:-1])
                if temp is None:
                    temp = 0
                self.tempstore[device][x].append(temp)
        return True
    
    def enable_spoolman(self) -> None:
        logging.info("Enabling Spoolman")
        self.spoolman = True
