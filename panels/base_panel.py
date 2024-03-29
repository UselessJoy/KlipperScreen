# -*- coding: utf-8 -*-
import contextlib
import logging
import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango
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
        self.titlebar_items = []
        self.titlebar_name_type = None
        self.last_time_message = None
        self.buttons_showing = {
            'macros_shortcut': False,
            'printer_select': len(self._config.get_printers()) > 1,
        }
        self.hours = None
        self.minutes = None
        self.current_extruder = None
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
            self.wifi.add_callback("popup", self.popup_callback)
        ####    END NEW    ####

        if len(self._config.get_printers()) > 1:
            self.control['printer_select'] = self._gtk.Button('shuffle', scale=abscale)
            self.control['printer_select'].connect("clicked", self._screen.show_printer_select)

        self.control['macros_shortcut'] = self._gtk.Button('custom-script', scale=abscale)
        self.control['macros_shortcut'].connect("clicked", self.menu_item_clicked, "gcode_macros", {
            "name": "Macros",
            "panel": "gcode_macros"
        })

        self.control['estop'] = self._gtk.Button('emergency', scale=abscale)
        self.control['estop'].connect("clicked", self.emergency_stop)
        
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
        self.show_back(False)
        if self.buttons_showing['printer_select']:
            self.action_bar.add(self.control['printer_select'])
        self.show_macro_shortcut(self._config.get_main_config().getboolean('side_macro_shortcut', True))
        self.action_bar.add(self.control['estop'])
        self.action_bar.add(self.control['power'])
        self.show_estop(False)

        # Titlebar

        # This box will be populated by show_heaters
        self.control['temp_box'] = Gtk.Box(spacing=10)
        
        self.control['network_box'] = Gtk.Box(spacing=15)
        self.control['network_box'].set_margin_start(15)
        #img_size = self._gtk.img_scale * self.bts
        self.network_status_image = self._gtk.Image()#self._gtk.Image('lan_status_none', img_size, img_size)
        self.control['network_box'].add(self.network_status_image)
        
        self.titlelbl = Gtk.Label() 
        self.titlelbl.set_hexpand(True)
        self.titlelbl.set_halign(Gtk.Align.CENTER)
        self.titlelbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.set_title(title)

        self.control['time'] = Gtk.Label("00:00 AM")
        self.control['time_box'] = Gtk.EventBox()
        self.control['time_box'].set_halign(Gtk.Align.END)
        self.control['time_box'].add(self.control['time'])#, True, True, 10
        self.control['time_box'].connect("button-release-event", self.create_time_modal)
        self.titlebar = Gtk.Box(spacing=5)
        self.titlebar.get_style_context().add_class("title_bar")
        self.titlebar.set_valign(Gtk.Align.CENTER)
        self.titlebar.add(self.control['temp_box'])
        self.titlebar.add(self.control['network_box'])
        self.titlebar.add(self.titlelbl)
        self.titlebar.add(self.control['time_box'])

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
        

    def create_time_modal(self, widget, event):
        
        buttons = [
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL},
                    {"name": _("Resume"), "response": Gtk.ResponseType.OK}
                ]
        now = datetime.now()
        self.hours = int(f'{now:%H}')
        self.minutes = int(f'{now:%M}')
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "systemd-timesyncd.service"])
        self.is_timesync = True if stat == 0 else False
        timepicker = Timepicker(self._screen, self.on_change_value, self.on_change_timesync)
        dialog = self._gtk.Dialog(self._screen, buttons, timepicker, self.close_time_modal, width=1, height=1)
        dialog.set_title(_("Time"))
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
    def get_width_action_bar(self):
        return self.action_bar.get_allocation().width
    
    def get_height_titlebar(self):
        return self.titlebar.get_allocation().height
        
    def show_power_dialog(self, widget):
        buttons = [
                    {"name": _("Restart"), "response": Gtk.ResponseType.YES, "style": "color1"},
                    {"name": _("Shutdown"), "response": Gtk.ResponseType.OK, "style": "color2"},
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color3"},
                ]
        grid = self._gtk.HomogeneousGrid()
        grid.attach(Gtk.Label(label=_("Select action")), 0, 0, 1, 1)
        dialog = self._gtk.Dialog(self._screen, buttons, grid, self.close_power_modal, width = 1, height = 1)
        dialog.set_title(_("Power Manager"))
    
    def close_power_modal(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            os.system("systemctl poweroff")
        elif response_id == Gtk.ResponseType.YES: 
            os.system("systemctl reboot")
        self._gtk.remove_dialog(dialog)
    
    
    # def on_properties_changed_callback(self, ap_status):
    #     # Update status only for connected ssid
    #     if ap_status['ssid'] == self.wifi.get_connected_ssid():
    #         if 'Strength' in ap_status['properties']: 
    #             self.update_connected_network_status()
                
    # Callback only from wireless interface
    def connecting_callback(self, msg):
        logging.info("connecting...")
        self.is_connecting_to_network = True
        self.update_connected_network_status()
    
    def connected_callback(self, ssid, prev_ssid):
        logging.info("connected!")
        self.is_connecting_to_network = False
    
    def popup_callback(self, msg):
        logging.info("exception connect!")
        self.is_connecting_to_network = False
    
    def update_connected_network_status(self):
        img_size = self._gtk.img_scale * self.bts
        if not self.is_connecting_to_network:
            try:
                connected_ssid = self.wifi.get_connected_ssid()
                if not connected_ssid:
                    raise Exception("Connected ssid not found")
                netinfo = self.wifi.get_network_info(connected_ssid)
                # get_wifi_hotspot not needed, may add "mode" prop in get_connected_ssid (like "mode": ap.Mode)
                if self._printer.get_wifi_hotspot() == connected_ssid:
                    self.network_status_image = self._gtk.Image(f"access_point", img_size, img_size)
                elif "signal_level_dBm" in netinfo:
                    self.network_status_image = self.signal_strength(int(netinfo["signal_level_dBm"]), img_size)
            except Exception as e:
                data: bytes = subprocess.check_output(["nmcli", "networking", "connectivity"])
                data = data.decode("utf-8").strip()
                self.network_status_image = self._gtk.Image(f"lan_status_{data}", img_size, img_size) if data != 'none' else self._gtk.Image()
            finally:
                for child in self.control['network_box']:
                    self.control['network_box'].remove(child)
                self.control['network_box'].add(self.network_status_image)
                self.control['network_box'].show_all() 
                return True
        else:
            # pass if already spinner
            if isinstance(self.network_status_image, Gtk.Spinner):
                return True
            self.network_status_image = Gtk.Spinner()
            self.network_status_image.set_size_request(img_size, img_size)
            self.network_status_image.start()
        for child in self.control['network_box']:
                self.control['network_box'].remove(child)
        self.control['network_box'].add(self.network_status_image)
        self.control['network_box'].show_all() 
        return True
    
    def signal_strength(self, signal_level, img_size):
        # networkmanager uses percentage not dbm
        # the bars of nmcli are aligned near this breakpoints
        exc = 77 if self.use_network_manager else -50
        good = 60 if self.use_network_manager else -60
        fair = 35 if self.use_network_manager else -70
        if signal_level > exc:
            return self._gtk.Image('wifi_excellent', img_size, img_size)
        elif signal_level > good:
            return self._gtk.Image('wifi_good', img_size, img_size)
        elif signal_level > fair:
            return self._gtk.Image('wifi_fair', img_size, img_size)
        else:
            return self._gtk.Image('wifi_weak', img_size, img_size)    
        
        
    def show_heaters(self, show=True):
        try:
            for child in self.control['temp_box'].get_children():
                self.control['temp_box'].remove(child)
            if not show or self._printer.get_temp_store_devices() is None:
                return

            img_size = self._gtk.img_scale * self.bts
            for device in self._printer.get_temp_store_devices():
                self.labels[device] = Gtk.Label(label="100º")
                self.labels[device].set_ellipsize(Pango.EllipsizeMode.START)

                self.labels[f'{device}_box'] = Gtk.Box()
                icon = self.get_icon(device, img_size)
                if icon is not None:
                    self.labels[f'{device}_box'].pack_start(icon, False, False, 3)
                self.labels[f'{device}_box'].pack_start(self.labels[device], False, False, 0)

            # Limit the number of items according to resolution
            nlimit = int(round(log(self._screen.width, 10) * 5 - 10.5))

            n = 0
            if self._printer.get_tools():
                self.current_extruder = self._printer.get_stat("toolhead", "extruder")
                if self.current_extruder and f"{self.current_extruder}_box" in self.labels:
                    self.control['temp_box'].add(self.labels[f"{self.current_extruder}_box"])
                    n += 1

            if self._printer.has_heated_bed():
                self.control['temp_box'].add(self.labels['heater_bed_box'])
                n += 1

            # Options in the config have priority
            for device in self._printer.get_temp_store_devices():
                # Users can fill the bar if they want
                if n >= nlimit + 1:
                    break
                name = device.split()[1] if len(device.split()) > 1 else device
                for item in self.titlebar_items:
                    if name == item:
                        self.control['temp_box'].add(self.labels[f"{device}_box"])
                        n += 1
                        break

            # If there is enough space fill with heater_generic
            for device in self._printer.get_temp_store_devices():
                if n >= nlimit:
                    break
                if device.startswith("heater_generic"):
                    self.control['temp_box'].add(self.labels[f"{device}_box"])
                    n += 1
            self.control['temp_box'].show_all()
            self.control['network_box'].show_all()
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
        if action == "notify_update_response":
            if self.update_dialog is None:
                self.show_update_dialog()
            with contextlib.suppress(KeyError):
                self.labels['update_progress'].set_text(
                    f"{self.labels['update_progress'].get_text().strip()}\n"
                    f"{data['message']}\n")
            with contextlib.suppress(KeyError):
                if data['complete']:
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
        if action != "notify_status_update" or self._screen.printer is None:
            return
        devices = self._printer.get_temp_store_devices()
        if devices is not None:
            for device in devices:
                temp = self._printer.get_dev_stat(device, "temperature")
                if temp is not None and device in self.labels:
                    name = ""
                    if not (device.startswith("extruder") or device.startswith("heater_bed")):
                        if self.titlebar_name_type == "full":
                            name = device.split()[1] if len(device.split()) > 1 else device
                            name = f'{name.capitalize().replace("_", " ")}: '
                        elif self.titlebar_name_type == "short":
                            name = device.split()[1] if len(device.split()) > 1 else device
                            name = f"{name[:1].upper()}: "
                    self.labels[device].set_label(f"{name}{int(temp)}°")

        with contextlib.suppress(Exception):
            if data["toolhead"]["extruder"] != self.current_extruder:
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
            # Interrput dialog showing from screen.py
            # elif data['virtual_sdcard']['show_interrupt'] == True:
            #     self.show_interrupt_dialog()
        with contextlib.suppress(Exception):
            if "is_open" in data["messages"]:
                if data["messages"]["is_open"]:
                    msg = self._printer.get_message()
                    if msg["message"] != "":
                        lvl = 1 if msg['message_type'] == 'success' else 2 if msg['message_type'] != 'error' else 3
                        self._screen.show_popup_message(msg['message'], level=lvl, just_popup=True)
            elif "last_message_eventtime" in data["messages"]:
                msg = self._printer.get_message()
                if msg["is_open"] and  msg["message"] != "":
                    lvl = 1 if msg['message_type'] == 'success' else 2 if msg['message_type'] != 'error' else 3
                    self._screen.show_popup_message(msg['message'], level=lvl, just_popup=True)
                    
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
        
        self.autooff_dialog = self._gtk.Dialog(self._screen, buttons, grid, self.close_autooff_dialog, width = 1, height= self._screen.height / 3)
        self.autooff_dialog.get_style_context().add_class("autoclose_dialog")
        self.autooff_dialog.set_title(_("Autooff after print"))
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
        
        self.interrupt_dialog = self._gtk.Dialog(self._screen, buttons, grid, self.close_interrupt_dialog, width = 1, height = self._screen.height / 3)
        self.interrupt_dialog.get_style_context().add_class("autoclose_dialog")
        self.interrupt_dialog.set_title(_("Interrupted printing"))
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

    def show_back(self, show=True):
        if show:
            self.control['back'].set_sensitive(True)
            self.control['home'].set_sensitive(True)
            return
        self.control['back'].set_sensitive(False)
        self.control['home'].set_sensitive(False)

    def show_macro_shortcut(self, show=True):
        if show is True and self.buttons_showing['macros_shortcut'] is False:
            self.action_bar.add(self.control['macros_shortcut'])
            if self.buttons_showing['printer_select'] is False:
                self.action_bar.reorder_child(self.control['macros_shortcut'], 2)
            else:
                self.action_bar.reorder_child(self.control['macros_shortcut'], 3)
            self.control['macros_shortcut'].show()
            self.buttons_showing['macros_shortcut'] = True
        elif show is False and self.buttons_showing['macros_shortcut'] is True:
            self.action_bar.remove(self.control['macros_shortcut'])
            self.buttons_showing['macros_shortcut'] = False

    def show_printer_select(self, show=True):
        if show and self.buttons_showing['printer_select'] is False:
            self.action_bar.add(self.control['printer_select'])
            self.action_bar.reorder_child(self.control['printer_select'], 2)
            self.buttons_showing['printer_select'] = True
            self.control['printer_select'].show()
        elif show is False and self.buttons_showing['printer_select']:
            self.action_bar.remove(self.control['printer_select'])
            self.buttons_showing['printer_select'] = False

    def set_title(self, title):
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

    def show_estop(self, show=True):
        if show:
            self.control['estop'].set_sensitive(True)
            return
        self.control['estop'].set_sensitive(False)

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
        self.labels['update_progress'] = Gtk.Label()
        self.labels['update_progress'].set_halign(Gtk.Align.START)
        self.labels['update_progress'].set_valign(Gtk.Align.START)
        self.labels['update_progress'].set_ellipsize(Pango.EllipsizeMode.END)
        self.labels['update_scroll'] = self._gtk.ScrolledWindow()
        self.labels['update_scroll'].set_property("overlay-scrolling", True)
        self.labels['update_scroll'].add(self.labels['update_progress'])
        self.labels['update_scroll'].connect("size-allocate", self._autoscroll)
        dialog = self._gtk.Dialog(self._screen, button, self.labels['update_scroll'], self.finish_updating)
        dialog.connect("delete-event", self.close_update_dialog)
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).hide()
        dialog.set_title(_("Updating"))
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
