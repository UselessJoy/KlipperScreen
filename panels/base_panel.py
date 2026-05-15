# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
import contextlib
import logging
import os
import pathlib
import subprocess
import sys
import threading
import time
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango, Gdk
from jinja2 import Environment
import datetime
from math import log
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.timepicker import Timepicker
import netifaces
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.wifi_nm import WifiManager
import dbus
from dbus.mainloop.glib import DBusGMainLoop

class BasePanel(ScreenPanel):
    NM_STATUS = {0: 'none', 1: 'unknown', 2: 'limited', 3: 'portal', 4: 'full'}

    def __init__(self, screen, title):
        super().__init__(screen, title)
        DBusGMainLoop(set_as_default=True)
        try:
            nm = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
            self.nm_iface = dbus.Interface(nm, 'org.freedesktop.NetworkManager')
        except:
            self.nm_iface = None

        self.current_panel = None
        self.time_min = -1
        self.time_format = self._config.get_main_config().getboolean("24htime", True)
        self.time_update = None
        self.new_popup_msg = ""
        self.new_popup_level = 1
        self.last_time_message = None

        self.interrupt_dialog = None
        self.autooff_dialog = self.autooff_enable = None
        self.disable_dialog = None
        self.power_dialog = None

        self.updating = False

        self.system_fix_dialog_label = self.system_fix_dialog_message = self.system_fix_dialog = self.require_reboot = self.restart_button_grid = self.system_fix_box = None
        self.is_all_updated = self.require_internet = False

        self.missing = self.pip_restart_button_grid = self.pip_tb = self.pip_scroll = self.pip_box = self.pip_dialog = self.packages_thread = None
        self.all_packages_installed = False
        self._packages_lock = threading.Lock()

        self.timepicker = None

        self.tb = None
        self.titlebar_items = []
        self.titlebar_name_type = None

        self.check_temp = False
        self.current_extruder = None

        self.last_usage_report = datetime.datetime.now()
        self.usage_report = 0
        self.timezone = ""
        # Action bar buttons
        abscale = self.bts * 1.1
        self.control['back'] = self._gtk.Button('back', scale=abscale)
        self.control['back'].connect("clicked", self.back)
        self.control['home'] = self._gtk.Button('main', scale=abscale)
        self.control['home'].connect("clicked", self._screen._menu_go_back, True)
        ####      NEW      ####
        self.network_interfaces = netifaces.interfaces()
        self.wireless_interfaces = [iface for iface in self.network_interfaces 
                                  if iface.startswith('w')]
        self.is_connecting_to_network = False
        if len(self.wireless_interfaces) > 0:
            logging.info(f"Found wireless interfaces: {self.wireless_interfaces}")
            self.wifi = WifiManager(self.wireless_interfaces[0])
            self.wifi.add_callback("connecting", self.connecting_callback)
            self.wifi.add_callback("connected", self.connected_callback)
            self.wifi.add_callback("disconnected", self.disconnected_callback)
            self.wifi.add_callback("popup", self.popup_callback)
        ####    END NEW    ####
        for control in self.control:
            self.set_control_sensitive(False, control)
        self.control['estop'] = self._gtk.Button('emergency', scale=abscale)
        self.control['estop'].connect("clicked", self.emergency_stop)
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

        self.unsaved_config_popover = Gtk.Popover()
        self.unsaved_config_popover.get_style_context().add_class("message_popup")
        self.unsaved_config_popover.set_halign(Gtk.Align.CENTER)
        self.unsaved_config_popover.add(Gtk.Label(label=_("Have unsaved options")))
        self.unsaved_config_popover.set_relative_to(self.unsaved_config_box)
        self.unsaved_config_popover.set_position(Gtk.PositionType.BOTTOM)

        self.unsaved_config_box = Gtk.EventBox()
        self.unsaved_config_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.unsaved_config_box.add_events(Gdk.EventMask.TOUCH_MASK)
        self.unsaved_config_box.connect("button_release_event", self.on_unsaved_config_clicked)

        self.on_unsaved_config = Gtk.Image()
        self.on_unsaved_config.set_margin_left(15)
        self.unsaved_config_box.add(self.on_unsaved_config)

        self.uninstalled_updates_box = Gtk.EventBox()
        self.uninstalled_updates_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.uninstalled_updates_box.add_events(Gdk.EventMask.TOUCH_MASK)
        self.uninstalled_updates_box.connect("button_release_event", self.on_uninstalled_updates_clicked)

        self.on_uninstalled_updates = Gtk.Image()
        self.on_uninstalled_updates.set_margin_left(15)
        self.uninstalled_updates_box.add(self.on_uninstalled_updates)

        self.uninstalled_updates_popover = Gtk.Popover()
        self.uninstalled_updates_popover.get_style_context().add_class("message_popup")
        self.uninstalled_updates_popover.set_halign(Gtk.Align.CENTER)
        self.uninstalled_updates_popover.add(Gtk.Label(label=_("System fixes are not fully installed")))
        self.uninstalled_updates_popover.set_relative_to(self.uninstalled_updates_box)
        self.uninstalled_updates_popover.set_position(Gtk.PositionType.BOTTOM)

        self.stop_pid_button = Gtk.Button(label=_("Stop PID"), hexpand=True, halign=Gtk.Align.CENTER)
        self.stop_pid_button.get_style_context().add_class('stop_pid')
        self.stop_pid_button.connect('clicked', self.send_stop_pid)
        self.stop_pid_button.get_children()[0].get_style_context().add_class('pb-06rem') # Кривое решение выравнивания Label (но остальное не работает)
        self.stop_pid_button.set_no_show_all(True)
        self.stop_pid_button.hide()

        self.autooff_enable_button = self._gtk.Button("autooff", scale=0.7, hexpand=False, vexpand=False)
        self.autooff_enable_button.connect('clicked', self.show_disable_autooff_dialog)
        self.autooff_enable_button.set_no_show_all(True)
        self.autooff_enable_button.hide()

        self.stop_shaper_button = self._gtk.Button("input_shaper_stop", scale=0.7, hexpand=False, vexpand=False)
        self.stop_shaper_button.connect('clicked', self.show_stop_shaper_dialog)
        self.stop_shaper_button.set_no_show_all(True)
        self.stop_shaper_button.hide()

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
        self.titlebar.add(self.uninstalled_updates_box)
        self.titlebar.add(self.magnet_probe_image)
        self.titlebar.add(self.titlelbl)
        self.titlebar.add(self.stop_shaper_button)
        self.titlebar.add(self.autooff_enable_button)
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
        GLib.timeout_add_seconds(10, self.update_connected_network_status)

    def on_unsaved_config_clicked(self, widget, event):
        self.unsaved_config_popover.show_all()

    def on_uninstalled_updates_clicked(self, widget, event):
      if not self.is_all_updated and not self.system_fix_dialog:
        self.show_system_fix_dialog()
        self.system_fix_dialog = self._gtk.Dialog([], self.system_fix_box, _("Restart"), None, width = self._gtk.content_width * 0.9, height = self._gtk.content_height * 0.6)

    def create_time_modal(self, widget, event):
        buttons = [
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color2"},
                    {"name": _("Resume"), "response": Gtk.ResponseType.OK, "style": "color4"}
                ]
        self.timepicker = Timepicker(self._screen)
        dialog = self._gtk.Dialog(buttons, self.timepicker, _("Time"), self.close_time_modal, width=1, height=1)
        dialog.get_action_area().set_layout(Gtk.ButtonBoxStyle.EXPAND)
        dialog.show_all()

    def close_time_modal(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            if not self.timepicker.is_timesync:
                subprocess.call(
                    ["systemctl", "stop", "chronyd.service", "disable", "chronyd.service",
                    "stop", "systemd-timesyncd.service", "disable", "systemd-timesyncd.service"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                subprocess.call(
                    ["timedatectl", "set-time", f"{self.timepicker.cur_hours}:{self.timepicker.cur_minutes}:00"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                logging.info(f"set time to {self.timepicker.cur_hours}:{self.timepicker.cur_minutes}")
            else:
                subprocess.call(
                  ["systemctl", "start", "chronyd.service", "enable", "chronyd.service",
                  "start", "systemd-timesyncd.service", "enable", "systemd-timesyncd.service"],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                logging.info("time synchromized")
            if self.timezone:
                subprocess.call(
                  ["timedatectl", "set-timezone", self.timezone],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        self.update_time()
        time.tzset()

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
          self._screen._ws.klippy.turn_off_all_heaters()
          self.check_temp = True
        self._gtk.remove_dialog(self.power_dialog)
        self.power_dialog = None

    def get_wifi_dev(self):
        return self.wifi
    # Callback only from wireless interface
    def connecting_callback(self, msg):
        logging.info("connecting...")
        self.is_connecting_to_network = True
        GLib.idle_add(self.update_connected_network_status)

    def connected_callback(self, ssid, prev_ssid):
        logging.info("connected!")
        self.is_connecting_to_network = False
        GLib.idle_add(self.update_connected_network_status)

    def disconnected_callback(self, msg):
        logging.info("disconnected!")
        self.is_connecting_to_network = False
        GLib.idle_add(self.update_connected_network_status)

    def popup_callback(self, msg):
        logging.exception("exception connect!")
        self.is_connecting_to_network = False
        GLib.idle_add(self.update_connected_network_status)

    def update_connected_network_status(self):
        if not self._screen.initialized:
            return True
        try:
            if not self.is_connecting_to_network:
                if self.on_connecting_spinner.get_visible():
                    self.on_connecting_spinner.hide()
                    self.on_connecting_spinner.stop()
                if not self.network_status_image.get_visible():
                    self.network_status_image.show()
                connected_ssid = self.wifi.get_connected_ssid()
                if not connected_ssid:
                    self._screen.process_update("notify_status_update", {'access_point': {'is_active': False}})
                    # connectivity в объекте нетворк манагера херово работает (он показывает 4, а команда напрямую показывает full)

                    # connectivity_map = {0: 'none', 1: 'unknown', 2: 'limited', 3: 'portal', 4: 'full'}
                    # self._cached_connectivity = connectivity_map.get(self.connectivity, 'unknown')
                    try:
                        status = self.NM_STATUS.get(self.nm_iface.CheckConnectivity(), 'none')
                    except:
                        status = 'none'
                    # data: bytes = subprocess.check_output(["nmcli", "networking", "connectivity"])
                    # data = data.decode("utf-8").strip()
                    if status != 'none':
                      self._screen.gtk.update_image(self.network_status_image, f"lan_status_{status}", self.img_titlebar_size, self.img_titlebar_size)
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
                    self._screen.process_update("notify_status_update", {'access_point': {'is_active': netinfo['is_hotspot']}})
                    if netinfo['is_hotspot']:
                        self._screen.gtk.update_image(self.network_status_image, "access_point", self.img_titlebar_size, self.img_titlebar_size)
                    else:
                        self._screen.gtk.update_image(self.network_status_image, self.signal_strength(netinfo["signal_level_dBm"]), self.img_titlebar_size, self.img_titlebar_size)     
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
        exc = 77
        good = 60
        fair = 35
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
        connected = self._printer and self._printer.state not in {'disconnected', 'startup', 'shutdown', 'error'}
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
            if cpu > 95 or memory > 95:
                if self.usage_report < 3:
                    self.usage_report += 1
                    return
                self.last_usage_report = datetime.datetime.now()
                if not ctx.has_class(error):
                    ctx.add_class(error)
                self._screen.log_notification(f"{self._screen.connecting_to_printer}: {msg}", 2)
                self.titlelbl.set_label(msg)
            elif ctx.has_class(error):
                if (datetime.datetime.now() - self.last_usage_report).seconds < 5:
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
                        self.update_dialog.set_sensitive(True)
                    except AttributeError as e:
                        self.close_update_dialog(None, None, Gtk.ResponseType.OK)
                        self._screen.show_popup_message(f"error trying to show updater button, error is: {e}.\nUpdate dialog closed", 3)
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
        if 'resonance_tester' in data:
            if 'shaping' in data['resonance_tester']:
                if data['resonance_tester']['shaping']:
                    self.stop_shaper_button.show()
                else:
                    self.stop_shaper_button.hide()
        if 'configfile' in data:
                if 'save_config_pending' in data['configfile']:
                    if data['configfile']['save_config_pending']:
                        if not self.on_unsaved_config.get_pixbuf():
                            self._screen.gtk.update_image(self.on_unsaved_config, "unsaved_config", self.img_titlebar_size, self.img_titlebar_size)
                        self.on_unsaved_config.show()
                    else:
                        self.on_unsaved_config.hide()
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

        if 'autooff' in data:
            if 'autoOff_enable' in data['autooff']:
              self.autooff_enable = data['autooff']['autoOff_enable']
            if 'autoOff' in data['autooff']:
                if not self.autooff_dialog and self.autooff_enable and data['autooff']['autoOff']:
                  self.show_autooff_dialog()
                elif self.autooff_dialog:
                  self._gtk.remove_dialog(self.autooff_dialog)
                  self.autooff_dialog = None 
        if 'virtual_sdcard' in data:
            if 'is_active' in data['virtual_sdcard']:
                if data['virtual_sdcard']['is_active'] and self.autooff_enable:
                    self.autooff_enable_button.show()
                else:
                    self.autooff_enable_button.hide()
            if 'show_interrupt' in data['virtual_sdcard']:
               if self.interrupt_dialog and not data['virtual_sdcard']['show_interrupt']:
                  self._gtk.remove_dialog(self.interrupt_dialog)
                  self.interrupt_dialog = None    
        if 'fixing' in data:
            if 'updating' in data['fixing']:
                self.updating = data['fixing']['updating']
                if self.restart_button_grid:
                    self.restart_button_grid.set_sensitive(not self.updating)
            if 'all_updated' in data['fixing']:
              self.is_all_updated = data['fixing']['all_updated']
              if not self.system_fix_dialog and not self.is_all_updated:
                self.show_system_fix_dialog()
              if not self.is_all_updated:
                  if not self.on_uninstalled_updates.get_pixbuf():
                      self._screen.gtk.update_image(self.on_uninstalled_updates, "alert", self.img_titlebar_size, self.img_titlebar_size)
                  self.on_uninstalled_updates.show()
              else:
                  self.on_uninstalled_updates.hide()
                  if self.system_fix_dialog:
                    self.action_area_done_fixing()
            if 'dialog_message' in data['fixing']:
                self.system_fix_dialog_message = data['fixing']['dialog_message']
                if self.tb and self.system_fix_dialog_message:
                    self.tb.insert(self.tb.get_end_iter(), self.system_fix_dialog_message, -1)
            if 'require_internet' in data['fixing']:
              self.require_internet = data['fixing']['require_internet']
              if self.require_internet:
                  if self.system_fix_dialog:
                      self.action_area_require_internet()
            if 'require_reboot' in data['fixing']:
              self.require_reboot = data['fixing']['require_reboot']
              if self.system_fix_dialog:
                self.action_area_done_fixing()
        with contextlib.suppress(Exception):
          if 'messages' in data:
            msg = data['messages']
            if msg['is_open']:
              if msg["message"] != "" and msg['message_type'] != "":
                  lvl = 1 if msg['message_type'] == 'success' else 2 if msg['message_type'] != 'error' else 3
                  self.new_popup_msg = msg["message"]
                  self.new_popup_level = lvl
                  if len(self._screen.dialogs):
                    GLib.timeout_add(300, self.new_popup)
                  else:
                    self.new_popup()
        return False

    def new_popup(self, *args):
      self._screen.show_popup_message(self.new_popup_msg, level=self.new_popup_level, just_popup=True)
      return False

    def action_area_done_fixing(self):
      for ch in self.restart_button_grid.get_children():
        self.restart_button_grid.remove(ch)
      btns =  [
                  {"name": _("Close"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.close_fix_dialog},
              ]
      if self.require_reboot:
        btns.append({"name": _("Restart"), "response": Gtk.ResponseType.OK, "style": "color2", 'callback': self.accept_reboot})
      new_btns = []
      for i, button in enumerate(btns):
        new_btns.append(self._gtk.Button(None, button['name'], button['style']))
        new_btns[i].connect("clicked", button['callback'], self.system_fix_dialog, btns[i]['response'])
        self.restart_button_grid.add(new_btns[i])
      self.restart_button_grid.set_sensitive(not self.updating)
      self.restart_button_grid.show_all()
    
    def action_area_require_internet(self):
      for ch in self.restart_button_grid.get_children():
        self.restart_button_grid.remove(ch)
      btns =  [
                  {"name": _("Close"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.close_fix_dialog},
                  {"name": _("Start Fix"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.repeat},
                  {"name": _("Network Panel"), "response": Gtk.ResponseType.OK, "style": "color2", "callback": self.open_network_panel_fix},
              ]
      new_btns = []
      for i, button in enumerate(btns):
        new_btns.append(self._gtk.Button(None, button['name'], button['style']))
        new_btns[i].connect("clicked", button['callback'], self.system_fix_dialog, btns[i]['response'])
        self.restart_button_grid.add(new_btns[i])
      self.restart_button_grid.set_sensitive(not self.updating)
      self.restart_button_grid.show_all()

    def show_system_fix_dialog(self, widget=None):
        if self.require_internet and not self.is_all_updated:
            btns =  [
                        {"name": _("Close"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.close_fix_dialog},
                        {"name": _("Start Fix"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.repeat},
                        {"name": _("Network Panel"), "response": Gtk.ResponseType.OK, "style": "color2", "callback": self.open_network_panel_fix},
            ]
        else:
            btns =  [{"name": _("Close"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.close_fix_dialog}]
            if self.require_reboot:
                btns.append({"name": _("Restart"), "response": Gtk.ResponseType.OK, "style": "color2", 'callback': self.accept_reboot})
            else:
                btns.append({"name": _("Start Fix"), "response": Gtk.ResponseType.OK, "style": "color2", "callback": self.repeat})
        self.restart_button_grid = Gtk.Grid(valign = Gtk.Align.CENTER, halign=Gtk.Align.CENTER, column_homogeneous=True, sensitive = not self.updating)
        self.restart_button_grid.set_margin_bottom(10)
        self.restart_button_grid.set_margin_left(10)
        self.restart_button_grid.set_margin_right(10)
        restart_buttons = []
        for i, button in enumerate(btns):
          restart_buttons.append(self._gtk.Button(None, button['name'], button['style']))
          restart_buttons[i].connect("clicked", button['callback'], self.system_fix_dialog, btns[i]['response'])
          restart_buttons[i].set_hexpand(False)
          # restart_buttons[i].set_vexpand(False)
          self.restart_button_grid.attach(restart_buttons[i], i, 0, 1, 1)
        self.system_fix_box = Gtk.Box(valign = Gtk.Align.CENTER, halign = Gtk.Align.CENTER, orientation = Gtk.Orientation.VERTICAL, spacing = 5)
        self.tb = Gtk.TextBuffer()
        if self.system_fix_dialog_message:
            self.tb.set_text(self.system_fix_dialog_message, -1)
        tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Pango.WrapMode.WORD_CHAR, 
                          pixels_inside_wrap=5, vexpand=True, margin_left=10)
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_buffer(self.tb)
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.connect("size-allocate", self._autoscroll)
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_margin_top(10)
        self.scroll.set_margin_bottom(10)
        self.scroll.set_margin_left(10)
        self.scroll.set_margin_right(10)
        self.scroll.set_min_content_height(self._gtk.content_height * 0.5)
        self.scroll.set_min_content_width(self._gtk.content_width * 0.8)
        self.scroll.add(tv)
        self.scroll.get_style_context().add_class("scrolled_window_bed_level")
        self.system_fix_box.add(self.scroll)
        self.system_fix_box.add(self.restart_button_grid)
        self.system_fix_box.get_style_context().add_class("fix_dialog")
        self.system_fix_box.set_size_request(self._gtk.content_width * 0.8, self._gtk.content_height * 0.6)

    def show_pip_dialog(self):
        if self.pip_dialog:
            return
        btns =  [
                    {"name": _("Close"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.close_pip_dialog},
                    {"name": _("Start"), "response": Gtk.ResponseType.YES, "style": "color1", "callback": self.update_pip},
                    {"name": _("Network Panel"), "response": Gtk.ResponseType.OK, "style": "color2", "callback": self.open_network_panel_pip},
        ]
        self.pip_restart_button_grid = Gtk.Grid(valign = Gtk.Align.CENTER, halign=Gtk.Align.CENTER, column_homogeneous=True, sensitive = not self.updating)
        self.pip_restart_button_grid.set_margin_bottom(10)
        self.pip_restart_button_grid.set_margin_left(10)
        self.pip_restart_button_grid.set_margin_right(10)
        restart_buttons = []
        for i, button in enumerate(btns):
            restart_buttons.append(self._gtk.Button(None, button['name'], button['style']))
            restart_buttons[i].connect("clicked", button['callback'], self.system_fix_dialog, btns[i]['response'])
            restart_buttons[i].set_hexpand(False)
            self.pip_restart_button_grid.attach(restart_buttons[i], i, 0, 1, 1)
        self.pip_box = Gtk.Box(valign = Gtk.Align.CENTER, halign = Gtk.Align.CENTER, orientation = Gtk.Orientation.VERTICAL, spacing = 5)
        self.pip_tb = Gtk.TextBuffer()
        pip_message = f"KlipperScreen обнаружил ошибку: не установлены следующие пакеты - {self.missing}\n"
        self.pip_tb.set_text(pip_message, -1)
        end_iter = self.pip_tb.get_end_iter()
        warning_tag = self.pip_tb.create_tag("orange_tag", foreground="#FF6600", weight=Pango.Weight.BOLD)
        warning_text = "Пожалуйста, перед установкой проверьте соединение с интернетом\n"
        self.pip_tb.insert_with_tags(end_iter, warning_text, warning_tag)
        end_iter = self.pip_tb.get_end_iter()
        self.pip_tb.insert(end_iter, "После обновления приложение будет перезапущено\n", -1)
        self.pip_tb.set_text(pip_message, -1)
        tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Pango.WrapMode.WORD_CHAR, 
                          pixels_inside_wrap=5, vexpand=True, margin_left=10)
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_buffer(self.pip_tb)
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.connect("size-allocate", self._autoscroll)
        self.pip_scroll = self._gtk.ScrolledWindow()
        self.pip_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pip_scroll.set_margin_top(10)
        self.pip_scroll.set_margin_bottom(10)
        self.pip_scroll.set_margin_left(10)
        self.pip_scroll.set_margin_right(10)
        self.pip_scroll.set_min_content_height(self._gtk.content_height * 0.5)
        self.pip_scroll.set_min_content_width(self._gtk.content_width * 0.8)
        self.pip_scroll.add(tv)
        self.pip_scroll.get_style_context().add_class("scrolled_window_bed_level")
        self.pip_box.add(self.pip_scroll)
        self.pip_box.add(self.pip_restart_button_grid)
        self.pip_box.get_style_context().add_class("fix_dialog")
        self.pip_box.set_size_request(self._gtk.content_width * 0.8, self._gtk.content_height * 0.6)
        if not self.pip_dialog:
            self.pip_dialog = self._gtk.Dialog([], self.pip_box, _("Modules"), None, width = self._gtk.content_width * 0.9, height = self._gtk.content_height * 0.6)
    
    def update_pip(self, btn, dialog, response_id):
        for child in self.pip_restart_button_grid.get_children():
            child.set_sensitive(False)
        self.pip_tb.set_text(f"Начинаю установку пакетов: {', '.join(self.missing)}\n\n", -1)
        thread = threading.Thread(target=self._install_packages_thread, daemon=True)
        thread.start()

    def _install_packages_thread(self):
        """Установка пакетов в фоновом потоке"""
        import sys
        success = []
        failed = []
        def update_gui(text):
            GLib.idle_add(self._append_to_dialog, text)
        
        for pkg in self.missing:
            update_gui(f"Устанавливаю {pkg}...\n")
            
            try:
                process = subprocess.Popen(
                    [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                for line in process.stdout:
                    if line.strip():
                        GLib.idle_add(self._append_to_dialog, f"  {line.strip()}\n")
                process.wait()
                if process.returncode == 0:
                    success.append(pkg)
                    update_gui(f"✓ {pkg} установлен успешно\n\n")
                else:
                    failed.append(pkg)
                    update_gui(f"✗ Ошибка установки {pkg} (код {process.returncode})\n\n")
            except Exception as e:
                failed.append(pkg)
                update_gui(f"✗ Ошибка установки {pkg}: {str(e)}\n\n")
        GLib.idle_add(self._finish_installation, success, failed)

    def _append_to_dialog(self, text):
        """Добавляет текст в диалог (вызывается из основного потока)"""
        try:
            end_iter = self.pip_tb.get_end_iter()
            self.pip_tb.insert(end_iter, text, -1)
            self.pip_scroll.get_vadjustment().set_value(
                self.pip_scroll.get_vadjustment().get_upper()
            )
        except:
            pass
        return False

    def _finish_installation(self, success, failed):
        """Завершает установку и обновляет интерфейс"""
        self.pip_tb.insert(self.pip_tb.get_end_iter(), "\n" + "="*50 + "\n", -1)
        if success:
            msg = f"✓ Успешно установлены: {', '.join(success)}\n"
            self.pip_tb.insert(self.pip_tb.get_end_iter(), msg, -1)
            for child in self.pip_restart_button_grid.get_children():
                    child.set_sensitive(True)
        if failed:
            msg = f"✗ Не удалось установить: {', '.join(failed)}\n"
            self.pip_tb.insert(self.pip_tb.get_end_iter(), msg, -1)
            for child in self.pip_restart_button_grid.get_children():
                    child.set_sensitive(True)
        if not failed:
            self.pip_tb.insert(self.pip_tb.get_end_iter(), 
                          "\nВсе пакеты успешно установлены!\n", -1)
            self._restart_app()
        else:
            with self._packages_lock:
                self.missing = failed
            self.pip_tb.insert(self.pip_tb.get_end_iter(), 
                          "\nНекоторые пакеты не установились. Проверьте подключение к интернету и повторите.\n", -1)
            for child in self.pip_restart_button_grid.get_children():
              child.set_sensitive(True)

    def _restart_app(self, btn=None):
        """Перезапускает приложение"""
        import os
        import sys
        self.pip_dialog.destroy()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def close_pip_dialog(self, btn, dialog, response_id):
        self._gtk.remove_dialog(self.pip_dialog)
        self.pip_dialog = None

    def check_system_fix_dialog(self):
      # После инициализации всего, чтобы диалог не закрывался в процессе загрузки
      if not self.is_all_updated and not self.system_fix_dialog:
        self.show_system_fix_dialog()
        self.system_fix_dialog = self._gtk.Dialog([], self.system_fix_box, _("Restart"), None, width = self._gtk.content_width * 0.9, height = self._gtk.content_height * 0.6)

    def close(self, btn, dialog, response_id):
      self._gtk.remove_dialog(self.system_fix_dialog)

    def close_fix_dialog(self, btn, dialog, response_id):
      self._gtk.remove_dialog(self.system_fix_dialog)
      self.system_fix_dialog = None

    def repeat(self, btn, dialog, response_id):
      self.restart_button_grid.set_sensitive(False)
      self._screen._ws.klippy.start_update(callback = self.on_repeat_fix)

    def on_repeat_fix(self, result, method, params):
      if result and 'updating' in result['result']:
          self.restart_button_grid.set_sensitive(not result['result']['updating'])

    def _read_requirements(self) -> list[str]:
        import re
        klipperscreendir = pathlib.Path(__file__).parent.parent.resolve()
        data = pathlib.Path(os.path.join(klipperscreendir, "scripts", "KlipperScreen-requirements.txt")).read_text()
        modules: list[str] = []
        for line in data.split("\n"):
            line = line.strip()
            if '#' in line:
                line = line[:line.index('#')].strip()
            if ';' in line:
                line = line.split(';')[0].strip()
            match = re.match(r'^([a-zA-Z0-9_\-\.\[\]]+?)(?:[<>!=~@]|$)', line)
            if match:
                pkg = match.group(1).strip()
                if '[' in pkg:
                    pkg = pkg[:pkg.index('[')].strip()
                modules.append(pkg.lower())
        return modules
    
    def _read_venv_requirements(self) -> list[str]:
        try:
            result = subprocess.check_output(
                [sys.executable, '-m', 'pip', 'freeze'],
                universal_newlines=True,
                timeout=30
            )
            installed = []
            for line in result.strip().split('\n'):
                if line and '==' in line:
                    if line.startswith('sdbus-networkmanager'):
                        line = line.replace('-', '_')
                    elif line.startswith('backports-zoneinfo'):
                        line = line.replace('-', '.')
                    pkg = line.split('==')[0].strip().lower()
                    installed.append(pkg)
            return installed
        except subprocess.TimeoutExpired:
            logging.error("pip freeze timed out")
            return []
        except Exception as e:
            logging.error(f"Error getting installed packages: {e}")
            return []

    def check_missing_packages(self):
        show_dialog = False
        with self._packages_lock:
            if self.all_packages_installed:
                return
            if self.missing:
                show_dialog = True
        
        if show_dialog:
            self.show_pip_dialog()
            return
        
        with self._packages_lock:
            if self.packages_thread and self.packages_thread.is_alive():
                return
            self.packages_thread = threading.Thread(
                target=self._check_packages_background, 
                daemon=True,
                name="PackageChecker"
            )
            self.packages_thread.start()

    def _check_packages_background(self):
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                need_future = executor.submit(self._read_requirements)
                have_future = executor.submit(self._read_venv_requirements)
                need = need_future.result(timeout=10)  # Таймаут для result
                have = have_future.result(timeout=10)
            
            show_dialog = False
            with self._packages_lock:
                self.missing = [pkg for pkg in need if pkg not in have]
                self.all_packages_installed = not self.missing
                show_dialog = bool(self.missing)
            
            if show_dialog:
                GLib.idle_add(self.show_pip_dialog)
        except Exception as e:
            logging.error(f"Package check failed: {e}")

    def open_network_panel_pip(self, btn, dialog, response_id):
      self._gtk.remove_dialog(self.pip_dialog)
      self.pip_dialog = None
      self._screen.show_panel("network", _("Network"))

    def open_network_panel_fix(self, btn, dialog, response_id):
      self._gtk.remove_dialog(self.system_fix_dialog)
      self.system_fix_dialog = None
      self._screen.show_panel("network", _("Network"))
    
    def accept_reboot(self, btn, dialog, response_id):
      self._screen._ws.send_method("machine.reboot")

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
        now = datetime.datetime.now()
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
        button_box = Gtk.Box(hexpand=True, halign=Gtk.Align.END)
        button_box.set_margin_top(5)
        btn_end = self._gtk.Button(None, _("Finish"), "color4", hexpand=False)
        btn_end.set_size_request(self._screen.width / 3 - 30, round(self._screen.height / 5))
        button_box.add(btn_end)

        self.labels['update_progress'] = Gtk.Label(hexpand=True, vexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.labels['update_scroll'] = self._gtk.ScrolledWindow(steppers=False)
        self.labels['update_scroll'].set_min_content_height(self._gtk.content_height * 0.7)
        self.labels['update_scroll'].set_property("overlay-scrolling", True)
        self.labels['update_scroll'].add(self.labels['update_progress'])
        self.labels['update_scroll'].connect("size-allocate", self._autoscroll)

        dialog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog_box.add(self.labels['update_scroll'])
        dialog_box.add(button_box)

        btn_end.connect("clicked", self.close_update_dialog, Gtk.ResponseType.OK)
        dialog = self._gtk.Dialog([], dialog_box, _("Updating"), self.close_update_dialog)
        self.update_dialog = dialog
        self.update_dialog.set_sensitive(False)
        dialog.show_all()

    def close_update_dialog(self, widget, response_id):
      if response_id != Gtk.ResponseType.OK:
        return
      if self.update_dialog:
        self._gtk.remove_dialog(self.update_dialog)
        self.update_dialog = None
        self._screen._menu_go_back(home=True)

    def send_stop_pid(self, *args):
        self._screen._ws.klippy.stop_pid_calibrate()
    
    def send_stop_bed_mesh(self, *args):
      self._screen._ws.klippy.run_async_command("ASYNC_STOP_BED_MESH_CALIBRATE")
      return True

    def show_disable_autooff_dialog(self, *args):
        buttons = [
            {"name": _("Cancel autoooff"), "response": Gtk.ResponseType.OK, "style": "color1"},
            {"name": _("Continue print"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
        ]
        grid = self._gtk.HomogeneousGrid()
        label = Gtk.Label(label=_("The printer will be turned off after printing. Cancel auto-shutdown?"))
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(40)
        label.set_hexpand(True)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        label.set_justify(Gtk.Justification.CENTER)
        grid.attach(label, 0, 0, 1, 1)
        
        self.autooff_dialog = self._gtk.Dialog(buttons, grid, _("Autooff after print"), self.close_disable_autooff_dialog, width = 1, height= self._screen.height / 3)
        self.autooff_dialog.get_style_context().add_class("autoclose_dialog")
        self.autooff_dialog.show_all()
        return False

    def close_disable_autooff_dialog(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        self.disable_dialog = None
        if response_id == Gtk.ResponseType.OK:
            self._screen._ws.klippy.set_autooff(False)
            self.autooff_enable_button.hide()

    def show_stop_shaper_dialog(self, *args):
        buttons = [
            {"name": _("Access"), "response": Gtk.ResponseType.OK, "style": "color1", 'width': self._screen.width * 0.3, 'height': 1},
            {"name": _("Go Back"), "response": Gtk.ResponseType.CANCEL, "style": "color2", 'width': self._screen.width * 0.3, 'height': 1},
        ]
        grid = self._gtk.HomogeneousGrid()
        label = Gtk.Label(label=_("Stop shaper calibrate?"))
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(40)
        label.set_hexpand(True)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        label.set_justify(Gtk.Justification.CENTER)
        grid.attach(label, 0, 0, 1, 1)
        self._gtk.Dialog(buttons, grid, _("Stop Shaper"), self.close_stop_shaper_dialog, width = 1, height = self._screen.height / 3).set_layout(Gtk.ButtonBoxStyle.FILL)
        return False

    def close_stop_shaper_dialog(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self._screen._ws.klippy.run_async_command('ASYNC_STOP_SHAPER')
            self.stop_shaper_button.hide()