# -*- coding: utf-8 -*-
import contextlib
import logging
import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango, Gdk, GdkPixbuf
from jinja2 import Environment
from datetime import datetime
from math import log
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.timepicker import Timepicker
import netifaces
from ks_includes.KlippyGcodes import KlippyGcodes
# from subprocess import run, STDOUT, PIPE

# Брать информацию о соединении из коллбэка NetworkManager, а не по таймеру
# По клику на значок интерфейса видеть его название
class BasePanel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.current_panel = None
        self.time_min = -1
        self.time_format = self._config.get_main_config().getboolean("24htime", True)
        self.time_update = None
        self.autooff_dialog = None
        self.power_dialog = None
        self.titlebar_items = []
        self.check_temp = False
        self.titlebar_name_type = None
        self.last_time_message = None
        self.wifi_mode = None
        self.hours = None
        self.minutes = None
        self.current_extruder = None
        self.last_usage_report = datetime.now()
        self.usage_report = 0
        # Action bar buttons
        abscale = self.bts * 1.1
        self.control['back'] = self._gtk.Button('back', scale=abscale)
        self.control['back'].connect("clicked", self.back)
        self.control['home'] = self._gtk.Button('main', scale=abscale)
        self.control['home'].connect("clicked", self._screen._menu_go_back, True)
        ####      NEW      ####
        self.network_interfaces = netifaces.interfaces()
        self.wireless_interfaces = [iface for iface in self.network_interfaces if iface.startswith('w')]
        self.is_connecting_to_network = False
        self.use_network_manager = os.system('systemctl is-active --quiet NetworkManager.service') == 0
        if len(self.wireless_interfaces) > 0:
            logging.info(f"Found wireless interfaces: {self.wireless_interfaces}")
            if self.use_network_manager:
                logging.info("Using NetworkManager")
                from ks_includes.wifi_nm import WifiManager
            else:
                logging.info("Using wpa_cli")
                from ks_includes.wifi import WifiManager
            self.wifi = WifiManager(self.wireless_interfaces[0])
            #self.wifi.add_callback("strength_changed", self.on_properties_changed_callback)
            self.wifi.add_callback("connecting", self.connecting_callback)
            self.wifi.add_callback("connected", self.connected_callback)
            self.wifi.add_callback("disconnected", self.disconnected_callback)
            self.wifi.add_callback("popup", self.popup_callback)
        ####    END NEW    ####
        
        for control in self.control:
            self.set_control_sensitive(False, control)
        self.control['estop'] = self._gtk.Button('emergency', scale=abscale)
        self.control['estop'].connect("clicked", self.emergency_stop)
        # self.control['estop'].set_no_show_all(True)
        # self.shutdown = {
        #     "name": None,
        #     "panel": "shutdown",
        #     "icon": "shutdown",
        # }
        # self.control['shutdown'] = self._gtk.Button('shutdown', scale=abscale)
        # self.control['shutdown'].connect("clicked", self.menu_item_clicked, self.shutdown)
        # self.control['shutdown'].set_no_show_all(True)
        self.control['printer_select'] = self._gtk.Button('shuffle', scale=abscale)
        self.control['printer_select'].connect("clicked", self._screen.show_printer_select)
        self.control['printer_select'].set_no_show_all(True)

        self.shorcut = {
            "name": "Macros",
            "panel": "gcode_macros",
            "icon": "custom-script",
        }
        self.control['shortcut'] = self._gtk.Button(self.shorcut['icon'], scale=abscale)
        self.control['shortcut'].connect("clicked", self.menu_item_clicked, self.shorcut)
        self.control['shortcut'].set_no_show_all(True)
        
        self.control['power'] = self._gtk.Button('shutdown_red', scale=abscale)
        self.control['power'].connect("clicked", self.show_power_dialog)

        # Any action bar button should close the keyboard
        for item in self.control:
            self.control[item].connect("clicked", self._screen.remove_keyboard)

        # Action bar
        self.action_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        if self._screen.vertical_mode:
            self.action_bar.set_hexpand(True)
            self.action_bar.set_vexpand(False)
        else:
            self.action_bar.set_hexpand(False)
            self.action_bar.set_vexpand(True)
        self.action_bar.get_style_context().add_class('action_bar')
        self.action_bar.set_size_request(self._gtk.action_bar_width, self._gtk.action_bar_height)
        self.action_bar.add(self.control['back'])
        self.action_bar.add(self.control['home'])
        self.action_bar.add(self.control['printer_select'])
        self.action_bar.add(self.control['shortcut'])
        self.action_bar.add(self.control['estop'])
        # self.action_bar.add(self.control['shutdown'])
        self.action_bar.add(self.control['power'])
        self.show_printer_select(len(self._config.get_printers()) > 1)
        # Titlebar
        self.img_titlebar_size = self._gtk.img_scale * self.bts
        # This box will be populated by show_heaters
        self.control['temp_box'] = Gtk.Box(spacing=10)
        
        self.network_status_image = self._gtk.Image()
        self.network_status_image.set_margin_left(15)
        self.network_status_image.hide()

        self.magnet_probe_image = self._gtk.Image()
        self.magnet_probe_image.set_margin_left(15)
        self.magnet_probe_image.hide()

        
        self.on_connecting_spinner = Gtk.Spinner()
        self.on_connecting_spinner.set_size_request(self.img_titlebar_size, self.img_titlebar_size)
        self.on_connecting_spinner.hide()
        
        self.unsaved_config_box = Gtk.EventBox()
        self.unsaved_config_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.unsaved_config_box.add_events(Gdk.EventMask.TOUCH_MASK)
        self.unsaved_config_box.connect("button_release_event", self.on_popover_clicked)
        # self.unsaved_config_box.connect('touch-event', self.on_popover_clicked)
        
        self.on_unsaved_config = Gtk.Image()
        self.on_unsaved_config.set_margin_left(15)
        self.unsaved_config_box.add(self.on_unsaved_config)
        
        self.unsaved_config_popover = Gtk.Popover()
        self.unsaved_config_popover.get_style_context().add_class("message_popup")
        self.unsaved_config_popover.set_halign(Gtk.Align.CENTER)
        self.unsaved_config_popover.add(Gtk.Label(label=_("Have unsaved options")))
        self.unsaved_config_popover.set_relative_to(self.unsaved_config_box)
        self.unsaved_config_popover.set_position(Gtk.PositionType.BOTTOM)
        
        self.stop_pid_button = Gtk.Button(label=_("Stop PID"), hexpand=True, halign=Gtk.Align.CENTER)
        self.stop_pid_button.get_style_context().add_class('stop_pid')
        self.stop_pid_button.connect('clicked', self.send_stop_pid)
        self.stop_pid_button.set_no_show_all(True)
        self.stop_pid_button.hide()

        self.titlelbl = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER, ellipsize=Pango.EllipsizeMode.END)
        self.control['time'] = Gtk.Label("00:00 AM")
        self.control['time_box'] = Gtk.EventBox(halign=Gtk.Align.END)
        self.control['time_box'].add(self.control['time'])#, True, True, 10
        self.control['time_box'].connect("button-release-event", self.create_time_modal)
        self.titlebar = Gtk.Box(spacing=5, valign=Gtk.Align.CENTER)
        self.titlebar.get_style_context().add_class("title_bar")
        self.titlebar.add(self.control['temp_box'])
        self.titlebar.add(self.network_status_image)
        self.titlebar.add(self.on_connecting_spinner)
        self.titlebar.add(self.unsaved_config_box)
        self.titlebar.add(self.magnet_probe_image)
        self.titlebar.add(self.titlelbl)
        self.titlebar.add(self.stop_pid_button)
        self.titlebar.add(self.control['time_box'])
        self.set_title(title)

        # Main layout
        self.main_grid = Gtk.Grid()
        if self._screen.vertical_mode:
            self.main_grid.attach(self.titlebar, 0, 0, 1, 1)
            self.main_grid.attach(self.content, 0, 1, 1, 1)
            self.main_grid.attach(self.action_bar, 0, 2, 1, 1)
            self.action_bar.set_orientation(orientation=Gtk.Orientation.HORIZONTAL)
        else:
            self.main_grid.attach(self.action_bar, 0, 0, 1, 2)
            self.main_grid.attach(self.titlebar, 0, 0, 2, 1)
            self.main_grid.attach(self.content, 1, 1, 1, 1)
            self.action_bar.set_orientation(orientation=Gtk.Orientation.VERTICAL)
        self.update_time()
        GLib.timeout_add_seconds(1, self.update_connected_network_status)

    def on_popover_clicked(self, widget, event):
        self.unsaved_config_popover.show_all()
    
    def create_time_modal(self, widget, event):
        
        buttons = [
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color2"},
                    {"name": _("Resume"), "response": Gtk.ResponseType.OK, "style": "color4"}
                ]
        now = datetime.now()
        self.hours = int(f'{now:%H}')
        self.minutes = int(f'{now:%M}')
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "systemd-timesyncd.service"])
        self.is_timesync = True if stat == 0 else False
        timepicker = Timepicker(self._screen, self.on_change_value, self.on_change_timesync)
        dialog = self._gtk.Dialog(buttons, timepicker, _("Time"), self.close_time_modal, width=1, height=1)
        dialog.get_action_area().set_layout(Gtk.ButtonBoxStyle.EXPAND)
        dialog.show_all()
    
    def close_time_modal(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            if not self.is_timesync:
                subprocess.call(["systemctl", "stop", "systemd-timesyncd.service"])
                subprocess.call(["systemctl", "disable", "systemd-timesyncd.service"])
                os.system(f"timedatectl set-time {self.hours}:{self.minutes}:00")
                logging.info(f"set time to {self.hours}:{self.minutes}")
            else:
                subprocess.call(["systemctl", "start", "systemd-timesyncd.service"])
                subprocess.call(["systemctl", "enable", "systemd-timesyncd.service"])
                logging.info("time synchromized")
        self.update_time()
            
    
    def on_change_timesync(self, switch_status):
        self.is_timesync = switch_status
    
            
    def on_change_value(self, name, value):
        logging.info(f'in on_change name is {name} value is {value}')
        if name == 'hours':
            self.hours = value
        else:
            self.minutes = value

    ####      NEW      ####
        
    def show_power_dialog(self, widget=None):
        buttons = [
                    {"name": _("Restart"), "response": Gtk.ResponseType.YES, "style": "color1"},
                    {"name": _("Shutdown"), "response": Gtk.ResponseType.OK, "style": "color2"},
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color3"},
                ]
        grid = self._gtk.HomogeneousGrid()
        button_grid = self._gtk.HomogeneousGrid()
        button_grid.set_margin_top(20)
        b = []
        for i, button in enumerate(buttons):
          b.append(self._gtk.Button(None, button['name'], button['style']))
          
          button_grid.attach(b[i], i, 0, 1, 1)
        last_btn = self._gtk.Button(None, _("Shutdown on cooling"), "color2")
        last_btn.set_size_request(1, self._screen.height / 4)
        button_grid.attach(last_btn, 1, 1, 1, 1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add(grid)
        box.add(button_grid)
        # grid.attach(button, 0, 1, 1, 1)
        self.power_dialog = self._gtk.Dialog([], box, _("Power Manager"), self.close_power_dialog, width = 1, height = 1)
        for i, button in enumerate(b):
          button.connect("clicked", self.close_power_dialog, self.power_dialog, buttons[i]['response'])
        last_btn.connect("clicked", self.close_power_dialog, self.power_dialog, Gtk.ResponseType.APPLY)
        
    def close_power_dialog(self, widget, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            os.system("systemctl poweroff")
        elif response_id == Gtk.ResponseType.YES: 
            os.system("systemctl reboot")
        elif response_id == Gtk.ResponseType.APPLY: 
          self._screen.show_popup_message(_("Shutdown on cooling"), level=1, timeout=0)
          self.check_temp = True
        self._gtk.remove_dialog(self.power_dialog)
        self.power_dialog = None
    
    # def on_properties_changed_callback(self, ap_status):
    #     # Update status only for connected ssid
    #     if ap_status['ssid'] == self.wifi.get_connected_ssid():
    #         if 'Strength' in ap_status['properties']: 
    #             self.update_connected_network_status()
    
    def get_wifi_dev(self):
        return self.wifi
    # Callback only from wireless interface
    def connecting_callback(self, msg):
        logging.info("connecting...")
        self.is_connecting_to_network = True
        self.update_connected_network_status()
    
    def connected_callback(self, ssid, prev_ssid):
        logging.info("connected!")
        self.is_connecting_to_network = False
        self.update_connected_network_status()
        
    def disconnected_callback(self, msg):
        logging.info("disconnected!")
        self.is_connecting_to_network = False
        self.update_connected_network_status()
        
    def popup_callback(self, msg):
        logging.exception("exception connect!")
        self.is_connecting_to_network = False
        self.update_connected_network_status()
    
    def update_connected_network_status(self):
        try:
            if not self.is_connecting_to_network:
                if self.on_connecting_spinner.get_visible():
                    self.on_connecting_spinner.hide()
                    self.on_connecting_spinner.stop()
                if not self.network_status_image.get_visible():
                    self.network_status_image.show()
                connected_ssid = self.wifi.get_connected_ssid()
                if not connected_ssid:
                    # connectivity в объекте нетворк манагера херово работает (он показывает 4, а команда напрямую показывает full)
                    data: bytes = subprocess.check_output(["nmcli", "networking", "connectivity"])
                    data = data.decode("utf-8").strip()
                    if data != 'none':
                      self._screen.gtk.update_image(self.network_status_image, f"lan_status_{data}", self.img_titlebar_size, self.img_titlebar_size)
                    else:
                      self.network_status_image.set_from_pixbuf(None)
                else:
                    netinfo: dict = self.wifi.get_network_info(connected_ssid)
                    if not "is_hotspot" in netinfo:
                        netinfo["is_hotspot"] = False
                        logging.warning("Cannot get hotspot info")
                    if not "signal_level_dBm" in netinfo:
                        netinfo["signal_level_dBm"] = 0
                        logging.warning("Cannot get signal strehgth info")
                    if self.wifi_mode:
                        self._screen.gtk.update_image(self.network_status_image, "access_point", self.img_titlebar_size, self.img_titlebar_size)
                        #logging.info("showing access_point")
                    else:
                        self._screen.gtk.update_image(self.network_status_image, self.signal_strength(netinfo["signal_level_dBm"]), self.img_titlebar_size, self.img_titlebar_size)
                        #logging.info("showing wifi with signal")     
            else:
                if self.network_status_image.get_visible():
                    self.network_status_image.hide()
                if not self.on_connecting_spinner.get_visible():
                    self.on_connecting_spinner.show()
                    self.on_connecting_spinner.start()
        except Exception as e:
            logging.exception(f"Error on update network status:\n{e}")
        return True
                
    def signal_strength(self, signal_level):
        # networkmanager uses percentage not dbm
        # the bars of nmcli are aligned near this breakpoints
        exc = 77 if self.use_network_manager else -50
        good = 60 if self.use_network_manager else -60
        fair = 35 if self.use_network_manager else -70
        if signal_level > exc:
            return "wifi_excellent"
        elif signal_level > good:
            return "wifi_good"
        elif signal_level > fair:
            return "wifi_fair"
        else:
            return "wifi_weak"   
        
        
    def show_heaters(self, show=True):
        try:
            for child in self.control['temp_box'].get_children():
                self.control['temp_box'].remove(child)
            devices = self._printer.get_temp_devices()
            if not show or not devices:
                return

            img_size = self._gtk.img_scale * self.bts
            for device in devices:
                self.labels[device] = Gtk.Label(ellipsize=Pango.EllipsizeMode.START)

                self.labels[f'{device}_box'] = Gtk.Box()
                icon = self.get_icon(device, img_size)
                if icon is not None:
                    self.labels[f'{device}_box'].pack_start(icon, False, False, 3)
                self.labels[f'{device}_box'].pack_start(self.labels[device], False, False, 0)

            # Limit the number of items according to resolution
            nlimit = int(round(log(self._screen.width, 10) * 5 - 10.5))

            n = 0
            if len(self._printer.get_tools()) > (nlimit - 1):
                self.current_extruder = self._printer.get_stat("toolhead", "extruder")
                if self.current_extruder and f"{self.current_extruder}_box" in self.labels:
                    self.control['temp_box'].add(self.labels[f"{self.current_extruder}_box"])
            else:
                self.current_extruder = False
            for device in devices:
                if n >= nlimit:
                    break
                if device.startswith("extruder") and self.current_extruder is False:
                    self.control['temp_box'].add(self.labels[f"{device}_box"])
                    n += 1
                elif device.startswith("heater"):
                    self.control['temp_box'].add(self.labels[f"{device}_box"])
                    n += 1

            for device in devices:
                # Users can fill the bar if they want
                if n >= nlimit + 1:
                    break
                name = device.split()[1] if len(device.split()) > 1 else device
                for item in self.titlebar_items:
                    if name == item:
                        self.control['temp_box'].add(self.labels[f"{device}_box"])
                        n += 1
                        break
            self.control['temp_box'].show_all()
        except Exception as e:
            logging.debug(f"Couldn't create heaters box: {e}")

    def get_icon(self, device, img_size):
        if device.startswith("extruder"):
            if self._printer.extrudercount > 1:
                if device == "extruder":
                    device = "extruder0"
                return self._gtk.Image(f"extruder-{device[8:]}", img_size, img_size)
            return self._gtk.Image("extruder", img_size, img_size)
        elif device.startswith("heater_bed"):
            return self._gtk.Image("bed", img_size, img_size)
        # Extra items
        elif self.titlebar_name_type is not None:
            # The item has a name, do not use an icon
            return None
        elif device.startswith("temperature_fan"):
            return self._gtk.Image("fan", img_size, img_size)
        elif device.startswith("heater_generic"):
            return self._gtk.Image("heater", img_size, img_size)
        else:
            return self._gtk.Image("heat-up", img_size, img_size)

    def activate(self):
        if self.time_update is None:
            self.time_update = GLib.timeout_add_seconds(1, self.update_time)

    def add_content(self, panel):
        printing = self._printer and self._printer.state in {"printing", "paused"}
        connected = self._printer and self._printer.state not in {'disconnected', 'startup', 'shutdown', 'error'}
        # self.control['estop'].set_visible(printing)
        # self.control['shutdown'].set_visible(not printing)
        self.show_shortcut(connected)
        self.show_heaters(connected)
        for control in ('back', 'home'):
            self.set_control_sensitive(len(self._screen._cur_panels) > 1, control=control)
        self.current_panel = panel
        self.set_title(panel.title)
        self.content.add(panel.content)

    def back(self, widget=None):
        if self.current_panel is None:
            return
        self._screen.remove_keyboard()
        if hasattr(self.current_panel, "back") \
                and not self.current_panel.back() \
                or not hasattr(self.current_panel, "back"): 
            self._screen._menu_go_back()

    def process_update(self, action, data):
        if action == "notify_proc_stat_update":
            cpu = data["system_cpu_usage"]["cpu"]
            memory = (data["system_memory"]["used"] / data["system_memory"]["total"]) * 100
            error = "message_popup_error"
            ctx = self.titlebar.get_style_context()
            msg = f"CPU: {cpu:2.0f}%    RAM: {memory:2.0f}%"
            if cpu > 80 or memory > 85:
                if self.usage_report < 3:
                    self.usage_report += 1
                    return
                self.last_usage_report = datetime.now()
                if not ctx.has_class(error):
                    ctx.add_class(error)
                self._screen.log_notification(f"{self._screen.connecting_to_printer}: {msg}", 2)
                self.titlelbl.set_label(msg)
            elif ctx.has_class(error):
                if (datetime.now() - self.last_usage_report).seconds < 5:
                    self.titlelbl.set_label(msg)
                    return
                self.usage_report = 0
                ctx.remove_class(error)
                self.titlelbl.set_label(f"{self._screen.connecting_to_printer}")
            return
        if action == "notify_update_response":
            if self.update_dialog is None:
                self.show_update_dialog()
            if 'message' in data:
                self.labels['update_progress'].set_text(
                    f"{self.labels['update_progress'].get_text().strip()}\n"
                    f"{data['message']}\n")
            if 'complete' in data and data['complete']:
                logging.info("Update complete")
                if self.update_dialog is not None:
                    try:
                        self.update_dialog.set_response_sensitive(Gtk.ResponseType.OK, True)
                        self.update_dialog.get_widget_for_response(Gtk.ResponseType.OK).show()
                    except AttributeError:
                        logging.error("error trying to show the updater button the dialog might be closed")
                        self._screen.updating = False
                        for dialog in self._screen.dialogs:
                            self._gtk.remove_dialog(dialog)
            return
        if action != "notify_status_update" or self._screen.printer is None:
            return
        if 'power_button' in data:
          if 'state' in data['power_button']:
            if data['power_button']['state']:
                if not self.power_dialog:
                  self.show_power_dialog()
        if 'probe' in data:
            if 'is_using_magnet_probe' in data['probe']:
                if data['probe']['is_using_magnet_probe']:
                    if not self.magnet_probe_image.get_pixbuf():
                      self._screen.gtk.update_image(self.magnet_probe_image, "magnetOn", self.img_titlebar_size, self.img_titlebar_size)
                    self.magnet_probe_image.show()
                else:
                    self.magnet_probe_image.hide()
        if 'pid_calibrate' in data:
            if 'is_calibrating' in data['pid_calibrate']:
                if data['pid_calibrate']['is_calibrating']:
                    self.stop_pid_button.show()
                else:
                    self.stop_pid_button.hide()
        if 'configfile' in data:
                if 'save_config_pending' in data['configfile']:
                    if data['configfile']['save_config_pending'] == True:
                        if not self.on_unsaved_config.get_pixbuf():
                            self._screen.gtk.update_image(self.on_unsaved_config, "unsaved_config", self.img_titlebar_size, self.img_titlebar_size)
                        self.on_unsaved_config.show()
                    else:
                        self.on_unsaved_config.hide()
        if 'wifi_mode' in data and 'wifiMode' in data['wifi_mode']:
            self.wifi_mode = True if data['wifi_mode']['wifiMode'] == 'AP' else False
        for device in self._printer.get_temp_devices():
            temp = self._printer.get_dev_stat(device, "temperature")
            if temp is not None and device in self.labels:
                name = ""
                if not (device.startswith("extruder") or device.startswith("heater_bed")):
                    if self.titlebar_name_type == "full":
                        name = device.split()[1] if len(device.split()) > 1 else device
                        name = f'{self.prettify(name)}: '
                    elif self.titlebar_name_type == "short":
                        name = device.split()[1] if len(device.split()) > 1 else device
                        name = f"{name[:1].upper()}: "
                self.labels[device].set_label(f"{name}{int(temp)}°")
                if self.check_temp:
                  if device.startswith("extruder") and temp < 90:
                    os.system("systemctl poweroff")

        if (self.current_extruder and 'toolhead' in data and 'extruder' in data['toolhead']
                and data["toolhead"]["extruder"] != self.current_extruder):
            self.control['temp_box'].remove(self.labels[f"{self.current_extruder}_box"])
            self.current_extruder = data["toolhead"]["extruder"]
            self.control['temp_box'].pack_start(self.labels[f"{self.current_extruder}_box"], True, True, 3)
            self.control['temp_box'].reorder_child(self.labels[f"{self.current_extruder}_box"], 0)
            self.control['temp_box'].show_all()
                
        with contextlib.suppress(Exception):
                if self.autooff_dialog is not None and data['autooff']['autoOff'] == False:
                    self._gtk.remove_dialog(self.autooff_dialog)
                    self.autooff_dialog = None
                elif data['autooff']['autoOff'] == True:
                    self.show_autooff_dialog()
        with contextlib.suppress(Exception):
            if self.interrupt_dialog is not None and data['virtual_sdcard']['show_interrupt'] == False:
                self._gtk.remove_dialog(self.interrupt_dialog)
                self.interrupt_dialog = None
        with contextlib.suppress(Exception):
          if 'messages' in data:
            msg = data['messages']
            if msg['is_open']:
              if msg["message"] != "" and msg['message_type'] != "":
                  lvl = 1 if msg['message_type'] == 'success' else 2 if msg['message_type'] != 'error' else 3
                  self._screen.show_popup_message(msg['message'], level=lvl, just_popup=True)
        return False
                    
    def show_autooff_dialog(self):
        buttons = [
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color1"},
            {"name": _("Poweroff now"), "response": Gtk.ResponseType.OK, "style": "color2"}
        ]
        grid = self._gtk.HomogeneousGrid()
        label = Gtk.Label(label=_("Printing is finished. The printer will be turned off after cooling the extruder"))
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(40)
        label.set_hexpand(True)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        label.set_justify(Gtk.Justification.CENTER)
        grid.attach(label, 0, 0, 1, 1)
        
        self.autooff_dialog = self._gtk.Dialog(buttons, grid, _("Autooff after print"), self.close_autooff_dialog, width = 1, height= self._screen.height / 3)
        self.autooff_dialog.get_style_context().add_class("autoclose_dialog")
        self.autooff_dialog.show_all()
        return False
    
    def close_autooff_dialog(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        self.autooff_dialog = None
        if response_id == Gtk.ResponseType.OK:
            self._screen._ws.send_method("machine.shutdown")
        else:
            self._screen._ws.klippy.cancel_autooff()
    
    def show_interrupt_dialog(self, widget=None):
        buttons = [
            {"name": _("Continue Print"), "response": Gtk.ResponseType.OK, "style": "color1"},
            {"name": _("Later"), "response": Gtk.ResponseType.APPLY, "style": "color2"},
            {"name": _("Delete Print"), "response": Gtk.ResponseType.CANCEL, "style": "color3"}
        ]
        grid = self._gtk.HomogeneousGrid()
        label = Gtk.Label(label=_("Printing was interrupted\nDid you want to continue print?"))
        label.set_hexpand(True)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        label.set_justify(Gtk.Justification.CENTER)
        grid.attach(label, 0, 0, 1, 1)
        
        self.interrupt_dialog = self._gtk.Dialog(buttons, grid, _("Interrupted printing"), self.close_interrupt_dialog, width = 1, height = self._screen.height / 3)
        self.interrupt_dialog.get_style_context().add_class("autoclose_dialog")
        self.interrupt_dialog.show_all()
        return False
        
    def close_interrupt_dialog(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        self.autooff_dialog = None
        if response_id == Gtk.ResponseType.OK:
            self._screen._ws.klippy.print_rebuild()
        elif response_id == Gtk.ResponseType.APPLY:
            self._screen._ws.klippy.gcode_script(KlippyGcodes.pass_interrupt())
        else:
            self._screen._ws.klippy.print_remove()
    
    def remove(self, widget):
        self.content.remove(widget)

    def set_control_sensitive(self, value=True, control='shortcut'):
        self.control[control].set_sensitive(value)

    def show_shortcut(self, show=True):
        show = (
            show
            and self._config.get_main_config().getboolean('side_macro_shortcut', True)
            and self._printer.get_printer_status_data()["printer"]["gcode_macros"]["count"] > 0
        )
        self.control['shortcut'].set_visible(show)
        # self.set_control_sensitive(self._screen._cur_panels[-1] != self.shutdown['panel'], control='shutdown')
        
    def show_printer_select(self, show=True):
        self.control['printer_select'].set_visible(show)

    def set_title(self, title):
        self.titlebar.get_style_context().remove_class("message_popup_error")
        if not title:
            self.titlelbl.set_label(f"{self._screen.connecting_to_printer}")
            return
        try:
            env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
            env.install_gettext_translations(self._config.get_lang())
            j2_temp = env.from_string(title)
            title = j2_temp.render()
        except Exception as e:
            logging.debug(f"Error parsing jinja for title: {title}\n{e}")

        self.titlelbl.set_label(f"{self._screen.connecting_to_printer} | {title}")

    def update_time(self):
        now = datetime.now()
        confopt = self._config.get_main_config().getboolean("24htime", True)
        if now.minute != self.time_min or self.time_format != confopt:
            if confopt:
                self.control['time'].set_text(f'{now:%H:%M }')
            else:
                self.control['time'].set_text(f'{now:%I:%M %p}')
            self.time_min = now.minute
            self.time_format = confopt
        return True

    def set_ks_printer_cfg(self, printer):
        ScreenPanel.ks_printer_cfg = self._config.get_printer_config(printer)
        if self.ks_printer_cfg is not None:
            self.titlebar_name_type = self.ks_printer_cfg.get("titlebar_name_type", None)
            titlebar_items = self.ks_printer_cfg.get("titlebar_items", None)
            if titlebar_items is not None:
                self.titlebar_items = [str(i.strip()) for i in titlebar_items.split(',')]
                logging.info(f"Titlebar name type: {self.titlebar_name_type} items: {self.titlebar_items}")
            else:
                self.titlebar_items = []

    def show_update_dialog(self):
        if self.update_dialog is not None:
            return
        button = [{"name": _("Finish"), "response": Gtk.ResponseType.OK}]
        self.labels['update_progress'] = Gtk.Label(hexpand=True, vexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.labels['update_scroll'] = self._gtk.ScrolledWindow(steppers=False)
        self.labels['update_scroll'].set_property("overlay-scrolling", True)
        self.labels['update_scroll'].add(self.labels['update_progress'])
        self.labels['update_scroll'].connect("size-allocate", self._autoscroll)
        dialog = self._gtk.Dialog(button, self.labels['update_scroll'], _("Updating"), self.finish_updating)
        dialog.connect("delete-event", self.close_update_dialog)
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).hide()
        self.update_dialog = dialog
        self._screen.updating = True

    def finish_updating(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            return
        logging.info("Finishing update")
        self._screen.updating = False
        self._gtk.remove_dialog(dialog)
        self._screen._menu_go_back(home=True)

    def close_update_dialog(self, *args):
        logging.info("Closing update dialog")
        if self.update_dialog in self._screen.dialogs:
            self._screen.dialogs.remove(self.update_dialog)
        self.update_dialog = None
        self._screen._menu_go_back(home=True)

    def send_stop_pid(self, widget):
        self._screen._ws.klippy.stop_pid_calibrate()