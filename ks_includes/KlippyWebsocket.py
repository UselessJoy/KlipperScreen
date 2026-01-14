#!/usr/bin/python

import threading
import json
import logging
import gi
import websocket
gi.require_version("Gtk", "3.0")
from gi.repository import GLib
from ks_includes.KlippyGcodes import KlippyGcodes

class KlippyWebsocket(threading.Thread):
    _req_id = 0
    connected = False
    connecting = True
    callback_table = {}
    reconnect_count = 0
    max_retries = 4

    def __init__(self, screen, callback, host, port):
        threading.Thread.__init__(self)
        self._wst = None
        self.ws_url = None
        self._screen = screen
        self._callback = callback
        self.klippy = MoonrakerApi(self)
        self.ws = None
        self.closing = False
        self.host = host
        self.port = port

    @property
    def _url(self):
        return f"{self.host}:{self.port}"

    @property
    def ws_proto(self):
        return "wss" if int(self.port) in {443, 7130} else "ws"

    def retry(self):
        self.reconnect_count = 0
        self.connecting = True
        self.initial_connect()

    def initial_connect(self):
        if self.connect() is not False:
            GLib.timeout_add_seconds(10, self.reconnect)

    def reconnect(self):
        if self.reconnect_count > self.max_retries:
            logging.debug("Stopping reconnections")
            self.connecting = False
            self._screen.printer_initializing(
                _("Cannot connect to Moonraker")
                + f'\n\n{self._screen.apiclient.status}')
            return False
        return self.connect()

    def connect(self):
        if self.connected:
            logging.debug("Already connected")
            return False
        logging.debug("Attempting to connect")
        self.reconnect_count += 1
        try:
            state = self._screen.apiclient.get_server_info()
            if state is False:
                if self.reconnect_count > 2:
                    self._screen.printer_initializing(
                        _("Cannot connect to Moonraker") + '\n\n'
                        + _("Retrying") + f' #{self.reconnect_count}'
                    )
                return True
            token = self._screen.apiclient.get_oneshot_token()
        except Exception as e:
            logging.debug(f"Unable to get oneshot token {e}")
            return True

        self.ws_url = f"{self.ws_proto}://{self._url}/websocket?token={token}"
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_close=self.on_close, on_error=self.on_error, on_message=self.on_message, on_open=self.on_open
        )
        self._wst = threading.Thread(target=self.ws.run_forever, daemon=True)
        try:
            logging.debug("Starting websocket thread")
            self._wst.start()
        except Exception as e:
            logging.debug(f"Error starting web socket {e}")
            return True
        return False

    def close(self):
        self.closing = True
        self.connecting = False
        if self.ws is not None:
            self.ws.close()

    def on_message(self, *args):
        message = args[1] if len(args) == 2 else args[0]
        response = json.loads(message)
        if "id" in response and response['id'] in self.callback_table:
            args = (response,
                    self.callback_table[response['id']][1],
                    self.callback_table[response['id']][2],
                    *self.callback_table[response['id']][3])
            GLib.idle_add(self.callback_table[response['id']][0], *args, priority=GLib.PRIORITY_HIGH_IDLE)
            self.callback_table.pop(response['id'])
            return

        if "method" in response and "on_message" in self._callback:
            args = (response['method'], response['params'][0] if "params" in response else {})
            GLib.idle_add(self._callback['on_message'], *args, priority=GLib.PRIORITY_HIGH_IDLE)
        return

    def send_method(self, method, params=None, callback=None, *args):
        # logging.info(f"sending:\n method: {method}, params: {params}, callback: {callback}, args: {args}")
        if not self.connected:
            return False
        if params is None:
            params = {}

        self._req_id += 1
        if callback is not None:
            self.callback_table[self._req_id] = [callback, method, params, [*args]]
        if method == "printer.gcode.script":
            if self._screen.printer.get_stat("heaters", "is_waiting"):
                self.send_method(
                    "printer.open_message",
                    {
                      'message_type': "warning",
                      'message': "on_wait_temperature"
                    },
                    None
                )
        data = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._req_id
        }
        self.ws.send(json.dumps(data))
        return True

    def on_open(self, *args):
        logging.info("Moonraker Websocket Open")
        self.connected = True
        self.connecting = False
        self._screen.reinit_count = 0
        self.reconnect_count = 0
        if "on_connect" in self._callback:
            GLib.idle_add(self._callback['on_connect'], priority=GLib.PRIORITY_HIGH_IDLE)

    def on_close(self, *args):
        # args: ws, status, message
        # sometimes ws is not passed due to bugs
        message = args[2] if len(args) == 3 else args[1]
        if message is not None:
            logging.info(f"{message}")
        if not self.connected:
            logging.debug("Connection already closed")
            return
        if self.closing:
            logging.debug("Closing websocket")
            self.ws.keep_running = False
            self.close()
            self.closing = False
            return
        if "on_close" in self._callback:
            GLib.idle_add(self._callback['on_close'],
                          _("Lost Connection to Moonraker"),
                          priority=GLib.PRIORITY_HIGH_IDLE)
        logging.info("Moonraker Websocket Closed")
        self.connected = False

    @staticmethod
    def on_error(*args):
        error = args[1] if len(args) == 2 else args[0]
        logging.debug(f"Websocket error: {error}")

class MoonrakerApi:
    def __init__(self, ws):
        self._ws = ws

    def emergency_stop(self):
        logging.info("Sending printer.emergency_stop")
        return self._ws.send_method(
            "printer.emergency_stop"
        )

    def gcode_script(self, script, callback=None, *args):
        logging.debug(f"Sending printer.gcode.script: {script}")
        return self._ws.send_method(
            "printer.gcode.script",
            {"script": script},
            callback,
            *args
        )

    def get_file_dir(self, path='gcodes', callback=None, *args):
        logging.debug(f"Sending server.files.directory {path}")
        return self._ws.send_method(
            "server.files.list",
            {"path": path},
            callback,
            *args
        )

    def get_file_list(self, callback=None, *args):
        logging.debug("Sending server.files.list")
        return self._ws.send_method(
            "server.files.list",
            {},
            callback,
            *args
        )

    def get_dir_info(self, callback=None, directory='gcodes', *args):
        logging.debug(f"Sending server.files.get_directory  {directory}")
        return self._ws.send_method(
            "server.files.get_directory",
            {"path": directory},
            callback,
            *args
        )

    def get_file_metadata(self, filename, callback=None, *args):
        return self._ws.send_method(
            "server.files.metadata",
            {"filename": filename},
            callback,
            *args
        )

    def object_subscription(self, updates):
        logging.debug("Sending printer.objects.subscribe")
        return self._ws.send_method(
            "printer.objects.subscribe",
            updates
        )

    def power_device_off(self, device, callback=None, *args):
        logging.debug(f"Sending machine.device_power.off: {device}")
        return self._ws.send_method(
            "machine.device_power.off",
            {device: False},
            callback,
            *args
        )

    def power_device_on(self, device, callback=None, *args):
        logging.debug(f"Sending machine.device_power.on {device}")
        return self._ws.send_method(
            "machine.device_power.on",
            {device: False},
            callback,
            *args
        )

    def print_cancel(self, callback=None, *args):
        logging.debug("Sending printer.print.cancel")
        return self._ws.send_method(
            "printer.print.cancel",
            {},
            callback,
            *args
        )

    def print_pause(self, callback=None, *args):
        logging.debug("Sending printer.print.pause")
        return self._ws.send_method(
            "printer.print.pause",
            {},
            callback,
            *args
        )

    def print_resume(self, callback=None, *args):
        logging.debug("Sending printer.print.resume")
        return self._ws.send_method(
            "printer.print.resume",
            {},
            callback,
            *args
        )

    def print_start(self, filename, callback=None, *args):
        logging.debug("Sending printer.print.start")
        return self._ws.send_method(
            "printer.print.start",
            {
                "filename": filename
            },
            callback,
            *args
        )
   
    def set_bed_temp(self, target, callback=None, *args):
        logging.debug(f"Sending set_bed_temp: {KlippyGcodes.set_bed_temp(target)}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.set_bed_temp(target)
            },
            callback,
            *args
        )

    def set_heater_temp(self, heater, target, callback=None, *args):
        logging.debug(f"Sending heater {heater} to temp: {target}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.set_heater_temp(heater, target)
            },
            callback,
            *args
        )
    
    def turn_off_all_heaters(self, callback=None, *args):
        logging.debug(f"Sending heater turn_off_all_heaters")
        return self._ws.send_method(
            "printer.turn_off_heaters",
            {},
            callback,
            *args
      )

    def set_temp_fan_temp(self, temp_fan, target, callback=None, *args):
        logging.debug(f"Sending temperature fan {temp_fan} to temp: {target}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.set_temp_fan_temp(temp_fan, target)
            },
            callback,
            *args
        )

    def set_tool_temp(self, tool, target, callback=None, *args):
        logging.debug(f"Sending set_tool_temp: {KlippyGcodes.set_ext_temp(target, tool)}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.set_ext_temp(target, tool)
            },
            callback,
            *args
        )

    def restart(self):
        logging.debug("Sending printer.restart")
        return self._ws.send_method(
            "printer.restart"
        )

    def restart_firmware(self):
        logging.debug("Sending printer.firmware_restart")
        return self._ws.send_method(
            "printer.firmware_restart"
        )

    def load_backup_config(self):
        logging.debug("Sending printer.load_backup_config")
        return self._ws.send_method(
            "printer.load_backup_config"
        )
    
    def check_backup(self, callback=None):
        logging.debug("Sending printer.check_backup")
        return self._ws.send_method(
            "printer.check_backup",
            {},
            callback
        )

    ####      NEW      ####
    def print_rebuild(self, callback=None, *args):
        logging.debug("Sending printer.print.rebuild")
        return self._ws.send_method(
            "printer.print.rebuild",
            {},
            callback,
            *args
        )

    def print_remove(self, callback=None, *args):
        logging.debug("Sending printer.print.remove")
        return self._ws.send_method(
            "printer.print.remove",
            {},
            callback,
            *args
        )

    def set_safety(self, safety, callback=None, *args):
        logging.debug("Sending printer.setSafetyPrinting")
        return self._ws.send_method(
            "printer.setSafetyPrinting",
            {
                "safety_enabled": safety
            },
            callback,
            *args
        )
    
    def set_nozzle_diameter(self, nozzle_diameter, callback=None, *args):
        logging.debug("Sending printer.set_nozzle_diameter")
        return self._ws.send_method(
            "printer.set_nozzle_diameter",
            {
                "nozzle_diameter": nozzle_diameter
            },
            callback,
            *args
        )

    def set_quite_mode(self, stepper, quite_mode, callback=None, *args):
        logging.debug("Sending printer.setQuiteMode")
        return self._ws.send_method(
            "printer.setQuiteMode",
            {
              'stepper': stepper,
              'quite_mode': quite_mode
            },
            callback,
            *args
        )

    def set_watch_bed_mesh(self, watch_bed_mesh, callback=None, *args):
        logging.debug("Sending printer.setWatchBedMesh")
        return self._ws.send_method(
            "printer.setWatchBedMesh",
            {
                "watch_bed_mesh": watch_bed_mesh
            },
            callback,
            *args
        )

    def set_autoload_bed_mesh(self, autoload_bed_mesh, callback=None, *args):
        logging.debug("Sending printer.setAutoloadBedMesh")
        return self._ws.send_method(
            "printer.setAutoloadBedMesh",
            {
                "autoload_bed_mesh": autoload_bed_mesh
            },
            callback,
            *args
        )
        
    def repeat_update(self, callback=None, *args):
        logging.debug("Sending printer.fixing.repeat_update")
        return self._ws.send_method(
            "printer.fixing.repeat_update",
            {},
            callback,
            *args
        )
    
    def send_logs(self, n, p, e, sn, d, callback=None, *args):
      logging.debug("Sending server.bot.send_logs")
      return self._ws.send_method(
            "server.bot.send_logs",
            {
              'name': n,
              'phone': p,
              'email': e,
              'serial_number': sn,
              'description': d
            },
            callback,
            *args
      )

    def close_dialog(self, callback=None, *args):
        logging.debug("Sending printer.fixing.close_dialog")
        return self._ws.send_method(
            "printer.fixing.close_dialog",
            {},
            callback,
            *args
        )

    def get_old_frames(self, callback=None, *args):
      logging.debug("Sending machine.timelapse.old_frames")
      return self._ws.send_method(
          "machine.timelapse.old_frames",
          {},
          callback,
          *args
      )
    
    def update_webcam(self, webcam, callback=None, *args):
      logging.debug("Sending machine.webcams.post_item")
      return self._ws.send_method(
          "server.webcams.post_item",
          webcam,
          callback,
          *args
      )
    
    def timelapse_set_settings(self, settings, callback=None, *args):
      logging.debug("Sending machine.timelapse.post_settings")
      return self._ws.send_method(
        "machine.timelapse.post_settings",
        settings,
        callback,
        *args
      )
      
    def run_timelapse_method(self, method, callback=None, *args):
      logging.debug(f"Sending machine.timelapse.{method}")
      return self._ws.send_method(
        f"machine.timelapse.{method}",
        {},
        callback,
        *args
      )
    
    def set_neopixel_color(self, name, r, g, b, callback=None, *args):
        logging.debug(f"Sending set_led: {KlippyGcodes.set_led(name, r, g, b)}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.set_led(name, r, g, b)
            },
            callback,
            *args
        )

    def save_default_neopixel_color(self, name, r, g, b, callback=None, *args):
        logging.debug(f"Sending save_default_neopixel_color: {KlippyGcodes.save_default_neopixel_color(name, r, g, b)}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.save_default_neopixel_color(name, r, g, b)
            },
            callback,
            *args
        )

    def turn_off_led(self, callback=None, *args):
        logging.debug(f"Sending turn_off_led: {KlippyGcodes.turn_off_led()}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.turn_off_led()
            },
            callback,
            *args
        )

    def turn_on_led(self, callback=None, *args):
        logging.debug(f"Sending turn_off_led: {KlippyGcodes.turn_on_led()}")
        return self._ws.send_method(
            "printer.gcode.script",
            {
                "script": KlippyGcodes.turn_on_led()
            },
            callback,
            *args
        )

    def get_neopixel_color(self, name, callback=None, *args):
        logging.debug(f"Sending get_neopixel_color")
        return self._ws.send_method(
            "printer.get-neopixel-color",
            {
                "neopixel": name
            },
            callback,
            *args
        )

    def cancel_autooff(self, callback=None, *args):
        logging.debug(f"Sending printer.offautooff")
        return self._ws.send_method(
            "printer.offautooff",
            {},
            callback,
            *args
        )

    def set_autooff(self, autooff, callback=None, *args):
        logging.debug(f"Sending printer.setautooff")
        return self._ws.send_method(
            "printer.setautooff",
            {
                "autoOff_enable" : autooff
            },
            callback,
            *args
    )

    def close_message(self, callback=None, *args):
        logging.debug(f"Sending printer.close_message")
        return self._ws.send_method(
            "printer.close_message",
            {},
            callback,
            *args
    )

    def send_message(self, message_type, message, callback=None, *args):
        logging.debug(f"Sending printer.open_message")
        return self._ws.send_method(
            "printer.open_message",
            {"message_type": message_type,
             "message": message},
            callback,
            *args
    )
  
    def run_async_command(self, command, callback=None, *args):
        return self._ws.send_method(
            "printer.gcode.async_command",
            {
                "command": command
            },
            callback,
            *args
        )

    def stop_pid_calibrate(self, callback=None, *args):
        return self._ws.send_method(
            "printer.pid_calibrate.stop_pid_calibrate",
            {},
            callback,
            *args
        )

    def timelapse_old_frames(self, callback=None, *args):
        return self._ws.send_method(
            "machine.timelapse.old_frames",
            {},
            callback,
            *args
        )
    
    def test_heating(self, heater, callback=None, *args):
        return self._ws.send_method(
            "printer.heaters.test_temperature",
            {
              "heater": heater
            },
            callback,
            *args
        )
        
    def test_magnet_probe(self, callback=None, *args):
        return self._ws.send_method(
            "printer.magnet_probe.test_magnet_probe",
            {},
            callback,
            *args
        )

    def set_serial_number(self, serial_number, callback=None, *args):
        return self._ws.send_method(
            "printer.serial.set_serial",
            {
                "serial_number": serial_number
            },
            callback,
            *args
        )