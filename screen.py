#!/usr/bin/python

import argparse
import gc
import json
import logging
import os
import subprocess
import pathlib
import traceback  # noqa
import locale
import sys
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango
from importlib import import_module
from jinja2 import Environment
from signal import SIGTERM
from datetime import datetime
from ks_includes import functions
from ks_includes.KlippyWebsocket import KlippyWebsocket
from ks_includes.KlippyRest import KlippyRest
from ks_includes.files import KlippyFiles
from ks_includes.KlippyGtk import KlippyGtk
from ks_includes.printer import Printer
from ks_includes.widgets.keyboard import Keyboard
from ks_includes.widgets.numpad import Numpad
from ks_includes.widgets.prompts import Prompt
from ks_includes.config import KlipperScreenConfig
from panels.base_panel import BasePanel

logging.getLogger("urllib3").setLevel(logging.WARNING)

PRINTER_BASE_STATUS_OBJECTS = [
    'autooff',
    'bed_mesh',
    'configfile',
    'display_status',
    'extruder',
    'fan',
    'gcode_move',
    'heater_bed',
    'idle_timeout',
    'pause_resume',
    'print_stats',
    'safety_printing',
    'toolhead',
    'virtual_sdcard',
    'webhooks',
    'motion_report',
    'messages',
    'firmware_retraction',
    'exclude_object',
    'neopixel my_neopixel',
    'led_control',
    'heaters',
    'probe',
    'screws_tilt_adjust',
    'manual_probe',
    'filament_watcher',
    'pid_calibrate',
    'fixing'
]

klipperscreendir = pathlib.Path(__file__).parent.resolve()


def set_text_direction(lang=None):
    rtl_languages = ['he']
    if lang is None:
        for lng in rtl_languages:
            if locale.getlocale()[0].startswith(lng):
                lang = lng
                break
    if lang in rtl_languages:
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        logging.debug("Enabling RTL mode")
        return False
    Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
    return True


def state_execute(callback):
    callback()
    return False


class KlipperScreen(Gtk.Window):
    """ Class for creating a screen for Klipper via HDMI """
    _cur_panels = []
    connecting = False
    connecting_to_printer = None
    connected_printer = None
    files = None
    new_popup_msg = ""
    keyboard = None
    numpad = None
    panels = {}
    popup_message = None
    screensaver = None
    printers = printer = None
    _ws = None
    screensaver_timeout = None
    reinit_count = 0
    max_retries = 4
    initialized = initializing = False
    popup_timeout = None
    wayland = False
    windowed = False
    notification_log = []
    prompt = None
    can_close_message = True

    def __init__(self, args):
        try:
            super().__init__(title="KlipperScreen")
        except Exception as e:
            logging.exception(f"{e}\n\n{traceback.format_exc()}")
            raise RuntimeError from e
        GLib.set_prgname('KlipperScreen')
        self.blanking_time = 600
        self.use_dpms = True
        self.apiclient = None
        self.dialogs = []
        self.confirm = None
        self.last_window_class = ""
        self.last_popup_time = datetime.now()
        # Для просмотра дерева виджетов
        # self.set_interactive_debugging(True)
        configfile = os.path.normpath(os.path.expanduser(args.configfile))
        self._config = KlipperScreenConfig(configfile, self)
        self.lang_ltr = set_text_direction(self._config.get_main_config().get("language", None))
        self.env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
        self.env.install_gettext_translations(self._config.get_lang())

        # self.connect("key-press-event", self._key_press_event)
        self.connect("configure_event", self.update_size)
        display = Gdk.Display.get_default()
        monitor_amount = Gdk.Display.get_n_monitors(display)
        try:
            mon_n = int(args.monitor)
            if not (-1 < mon_n < monitor_amount):
                raise ValueError
        except ValueError:
            mon_n = 0
        logging.info(f"Monitors: {monitor_amount} using number: {mon_n}")
        monitor = display.get_monitor(mon_n)
        self.wayland = display.get_name().startswith('wayland') or display.get_primary_monitor() is None
        logging.info(f"Wayland: {self.wayland} Display name: {display.get_name()}")
        self.width = self._config.get_main_config().getint("width", None)
        self.height = self._config.get_main_config().getint("height", None)
        if 'XDG_CURRENT_DESKTOP' in os.environ:
            logging.warning("Running inside a desktop environment is not recommended")
            if not self.width:
                self.width = max(int(monitor.get_geometry().width * .5), 480)
            if not self.height:
                self.height = max(int(monitor.get_geometry().height * .5), 320)
        if self.width or self.height:
            logging.info("Setting windowed mode")
            if mon_n > 0:
                logging.error("Monitor selection is only supported for fullscreen")
            self.set_resizable(True)
            self.windowed = True
        else:
            self.width = monitor.get_geometry().width
            self.height = monitor.get_geometry().height
            self.fullscreen_on_monitor(self.get_screen(), mon_n)
        self.set_default_size(self.width, self.height)
        self.aspect_ratio = self.width / self.height
        self.vertical_mode = self.aspect_ratio < 1.0
        logging.info(f"Screen resolution: {self.width}x{self.height}")
        self.theme = self._config.get_main_config().get('theme')
        self.show_cursor = self._config.get_main_config().getboolean("show_cursor", fallback=False)
        self.gtk = KlippyGtk(self)
        self.init_style()
        self.set_icon_from_file(os.path.join(klipperscreendir, "styles", "icon.svg"))
        self.base_panel = BasePanel(self, title="Base Panel")
        self.add(self.base_panel.main_grid)
        self.show_all()
        if self.show_cursor:
            self.get_window().set_cursor(
                Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.ARROW))
            os.system("xsetroot  -cursor_name  arrow")
        else:
            self.get_window().set_cursor(
                Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))
            os.system("xsetroot  -cursor ks_includes/emptyCursor.xbm ks_includes/emptyCursor.xbm")
        self.base_panel.activate()
        if self._config.errors:
            self.show_error_modal("Invalid config file", self._config.get_errors())
            # Prevent this dialog from being destroyed
            self.dialogs = []
        self.set_screenblanking_timeout(self._config.get_main_config().get('screen_blanking'))
        self.log_notification("KlipperScreen Started", 1)
        self.initial_connection()
        if sys.version_info == (3, 7):
            GLib.timeout_add_seconds(2, self.show_popup_message,
                                     _("Warning") + f" Python 3.7\n"
                                     + _("Ended official support in June 2023") + "\n"
                                     + _("KlipperScreen will drop support in June 2024"), 2)

    def initial_connection(self):
        self.printers = self._config.get_printers()
        state_callbacks = {
            "disconnected": self.state_disconnected,
            "error": self.state_error,
            "paused": self.state_paused,
            "printing": self.state_printing,
            "interrupt": self.state_interrupt,
            "ready": self.state_ready,
            "startup": self.state_startup,
            "shutdown": self.state_shutdown
        }
        for printer in self.printers:
            printer["data"] = Printer(state_execute, state_callbacks)
        default_printer = self._config.get_main_config().get('default_printer')
        logging.debug(f"Default printer: {default_printer}")
        if [True for p in self.printers if default_printer in p]:
            self.connect_printer(default_printer)
        elif len(self.printers) == 1:
            pname = list(self.printers[0])[0]
            self.connect_printer(pname)
        else:
            self.base_panel.show_printer_select(True)
            self.show_printer_select()

    def connect_printer(self, name):
        self.connecting_to_printer = name
        if self.files:
            self.files.__init__(self)
        gc.collect()
        if self._ws is not None and self._ws.connected:
            self._ws.close()
            self.connected_printer = None
            self.printer.state = "disconnected"
        self.connecting = True
        self.initialized = False

        logging.info(f"Connecting to printer: {name}")
        ind = next(
            (
                self.printers.index(printer)
                for printer in self.printers
                if name == list(printer)[0]
            ),
            0,
        )
        self.printer = self.printers[ind]["data"]
        self.apiclient = KlippyRest(
            self.printers[ind][name]["moonraker_host"],
            self.printers[ind][name]["moonraker_port"],
            self.printers[ind][name]["moonraker_api_key"],
        )

        self.printer_initializing(_("Connecting to %s") % name, remove=True)

        self._ws = KlippyWebsocket(self,
                                   {
                                       "on_connect": self.init_printer,
                                       "on_message": self._websocket_callback,
                                       "on_close": self.websocket_disconnected
                                   },
                                   self.printers[ind][name]["moonraker_host"],
                                   self.printers[ind][name]["moonraker_port"],
                                   )
        if self.files is None:
            self.files = KlippyFiles(self)
        self._ws.initial_connect()

    def ws_subscribe(self):
        requested_updates = {
            "objects": {
                "autooff": ["autoOff_enable", "autoOff"],
                "safety_printing": ["safety_enabled", "is_doors_open", "is_hood_open", "luft_timeout", "luft_overload"],
                "power_button": ["state"],
                "tmc2209 stepper_x": ["quite_mode"],
                "resonance_tester": ["shaping"],
                "bed_mesh": ["profile_name", "mesh_max", "mesh_min", "probed_matrix", "profiles", "unsaved_profiles", "is_calibrating", "group_bed_mesh_len", "group_current_mesh", "is_preheating"],
                "configfile": ["config", "save_config_pending", "save_config_pending_items"],
                "display_status": ["progress", "message"],
                "fan": ["speed"],
                "gcode_move": ["extrude_factor", "gcode_position", "homing_origin", "speed_factor", "speed"],
                "idle_timeout": ["state"],
                "pause_resume": ["is_paused"],
                "print_stats": ["print_duration", "total_duration", "filament_used", "filename", "state", "message",
                                "info"],
                "toolhead": ["homed_axes", "estimated_print_time", "print_time", "position", "extruder",
                             "max_accel", "minimum_cruise_ratio", "max_velocity", "square_corner_velocity", "is_homing"],
                "virtual_sdcard": ["file_position", "is_active", "progress", "interrupted_file", "has_interrupted_file", "show_interrupt", "watch_bed_mesh", "autoload_bed_mesh"],
                "webhooks": ["state", "state_message"],
                "firmware_retraction": ["retract_length", "retract_speed", "unretract_extra_length", "unretract_speed"],
                "motion_report": ["live_position", "live_velocity", "live_extruder_velocity"],
                "messages": ["last_message_eventtime", "message", "message_type", "is_open"],
                "exclude_object": ["current_object", "objects", "excluded_objects"],
                "neopixel my_neopixel": ["color_data"],
                "led_control": ["led_status", "enabled"],
                "heaters": ["is_waiting"],
                "probe": ["is_using_magnet_probe", "last_z_result", "is_adjusting"],
                "screws_tilt_adjust": ["results", "base_screw", "calibrating_screw", "is_calibrating"],
                "manual_probe": ["is_active", "command", "z_position_endstop"],
                "pid_calibrate": ["is_calibrating"],
                "filament_watcher": ['filament_type', 'show_message'],
                "fixing": ['has_uninstalled_updates', 'open_dialog', 'dialog_message', 'require_internet', 'can_reboot']
            }
        }
        for extruder in self.printer.get_tools():
            requested_updates['objects'][extruder] = [
                "target", "temperature", "pressure_advance", "smooth_time", "power", "nozzle_diameter"]
        for h in self.printer.get_heaters():
            requested_updates['objects'][h] = ["target", "temperature", "power"]
        for t in self.printer.get_temp_sensors():
            requested_updates['objects'][t] = ["temperature"]
        for f in self.printer.get_temp_fans():
            requested_updates['objects'][f] = ["target", "temperature"]
        for f in self.printer.get_fans():
            requested_updates['objects'][f] = ["speed"]
        for f in self.printer.get_filament_sensors():
            requested_updates['objects'][f] = ["enabled", "filament_detected"]
        for p in self.printer.get_output_pins():
            requested_updates['objects'][p] = ["value"]
        for led in self.printer.get_leds():
            requested_updates['objects'][led] = ["color_data"]

        self._ws.klippy.object_subscription(requested_updates)
    
    @staticmethod
    def _load_panel(panel):
        logging.debug(f"Loading panel: {panel}")
        panel_path = os.path.join(os.path.dirname(__file__), 'panels', f"{panel}.py")
        if not os.path.exists(panel_path):
            logging.error(f"Panel {panel} does not exist")
            raise FileNotFoundError(os.strerror(2), "\n" + panel_path)
        return import_module(f"panels.{panel}")

    def show_panel(self, panel, title, remove_all=False, panel_name=None, **kwargs):
        if panel_name is None:
            panel_name = panel
        try:
            if remove_all:
                self._remove_all_panels()
                self.panels_reinit = list(self.panels)
            else:
                self._remove_current_panel()
            if panel_name not in self.panels:
                try:
                    self.panels[panel_name] = self._load_panel(panel).Panel(self, title, **kwargs)
                except Exception as e:
                    self.show_error_modal(f"Unable to load panel {panel}", f"{e}\n\n{traceback.format_exc()}")
                    return
            elif panel_name in self.panels_reinit:
                logging.info("Reinitializing panel")
                self.panels[panel_name].__init__(self, title, **kwargs)
                self.panels_reinit.remove(panel_name)
            self._cur_panels.append(panel_name)
            self.attach_panel(panel_name)
        except Exception as e:
            logging.exception(f"Error attaching panel:\n{e}\n\n{traceback.format_exc()}")
    
    def attach_panel(self, panel):
        self.set_can_close_message(True)
        self.base_panel.add_content(self.panels[panel])
        logging.debug(f"Current panel hierarchy: {' > '.join(self._cur_panels)}")
        if hasattr(self.panels[panel], "process_update"):
            self.process_update("notify_status_update", self.printer.data)
        if hasattr(self.panels[panel], "activate"):
            self.panels[panel].activate()
        self.base_panel.content.show_all()
        
        
    def log_notification(self, message, level=0):
        time = datetime.now().strftime("%H:%M:%S")
        log_entry = {"message": message, "level": level, "time": time}
        if len(self.notification_log) > 999:
            del self.notification_log[0]
        self.notification_log.append(log_entry)
        self.process_update("notify_log", log_entry)
        
    def show_popup_message(self, message, level=3, just_popup=False, timeout=5):
        self.last_popup_time = datetime.now()
        self.close_screensaver()
        self.close_popup_message()
        self.log_notification(message, level)
        msg = Gtk.Button(label=f"{message}")
        msg.set_hexpand(True)
        msg.set_vexpand(True)
        msg.get_child().set_line_wrap(True)
        msg.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        msg.get_child().set_max_width_chars(40)
        msg.connect("clicked", self.close_popup_message)
        msg.get_style_context().add_class("message_popup")
        if level == 1:
            msg.get_style_context().add_class("message_popup_echo")
        elif level == 2:
            msg.get_style_context().add_class("message_popup_warning")
            if not just_popup:
                self.remove_window_classes(self.base_panel.main_grid.get_style_context())
                self.base_panel.main_grid.get_style_context().add_class("window-warning")
        elif level == 10:
          msg.get_style_context().add_class("message_popup_suggestion")
        else:
            msg.get_style_context().add_class("message_popup_error")
            if not just_popup:
                self.remove_window_classes(self.base_panel.main_grid.get_style_context())
                self.base_panel.main_grid.get_style_context().add_class("window-error")

        
        
        popup = Gtk.Popover.new(self.base_panel.titlebar)
        popup.connect("closed", self.on_close_popup_message)
        popup.get_style_context().add_class("message_popup_popover")
        popup.set_size_request(self.width * .7, self.height * .2)
        popup.set_halign(Gtk.Align.CENTER)
        popup.add(msg)
        popup.popup()

        self.popup_message = popup
        self.popup_message.show_all()

        if self._config.get_main_config().getboolean('autoclose_popups', True):
            if self.popup_timeout is not None:
                GLib.source_remove(self.popup_timeout)
                self.popup_timeout = None
            if timeout != -1:
              self.popup_timeout = GLib.timeout_add_seconds(timeout, self.close_popup_message)
        return False
    
    def on_close_popup_message(self, widget):
        if self.popup_message is not None:
            self.popup_message = None
        if self.popup_timeout is not None:
            GLib.source_remove(self.popup_timeout)
            self.popup_timeout = None
        self._ws.klippy.close_message()  # Fallback
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        self.base_panel.main_grid.get_style_context().add_class(self.last_window_class if self.last_window_class is not None else "window-ready")
        

    def set_can_close_message(self, can_close):
        self.can_close_message = can_close

    def close_popup_message(self, widget=None):
        if self.can_close_message:
          if self.popup_message is not None:
              self.popup_message.popdown()
        return False

    def show_error_modal(self, err, e=""):
        logging.error(f"Showing error modal: {err} {e}")

        title = Gtk.Label()
        title.set_markup(f"<b>{err}</b>\n")
        title.set_line_wrap(True)
        title.set_line_wrap_mode(Pango.WrapMode.CHAR)
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)

        version = Gtk.Label(label=f"{functions.get_software_version()}")
        version.set_halign(Gtk.Align.END)

        help_msg = _("Provide KlipperScreen.log when asking for help")
        message = Gtk.Label(label=f"{help_msg}\n\n{e}")
        message.set_line_wrap(True)

        scroll = self.gtk.ScrolledWindow(steppers=False)
        scroll.set_vexpand(True)
        if self.vertical_mode:
            scroll.set_size_request(self.gtk.width - 30, self.gtk.height * .6)
        else:
            scroll.set_size_request(self.gtk.width - 30, self.gtk.height * .45)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(message)
        
        grid = Gtk.Grid()
        grid.attach(title, 0, 0, 1, 1)
        grid.attach(version, 1, 0, 1, 1)
        grid.attach(Gtk.Separator(), 0, 1, 2, 1)
        grid.attach(scroll, 0, 2, 2, 1)
        buttons = [
            {"name": _("Go Back"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
        ]
        self.gtk.Dialog(buttons, grid, _("Error"), self.error_modal_response, style="dialog-error")

    def error_modal_response(self, dialog, response_id):
        self.gtk.remove_dialog(dialog)
        self.restart_ks()

    def restart_ks(self, *args):
        logging.debug(f"Restarting {sys.executable} {' '.join(sys.argv)}")
        os.execv(sys.executable, ['python'] + sys.argv)
        self._ws.send_method("machine.services.restart", {"service": "KlipperScreen"})  # Fallback

    def init_style(self):
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-theme-name", "Adwaita")
        settings.set_property("gtk-application-prefer-dark-theme", False)
        css_data = pathlib.Path(os.path.join(klipperscreendir, "styles", "base.css")).read_text()

        with open(os.path.join(klipperscreendir, "styles", "base.conf")) as f:
            style_options = json.load(f)
        # Load custom theme
        theme = os.path.join(klipperscreendir, "styles", self.theme)
        theme_style = os.path.join(theme, "style.css")
        theme_style_conf = os.path.join(theme, "style.conf")

        if os.path.exists(theme_style):
            with open(theme_style) as css:
                css_data += css.read()
        if os.path.exists(theme_style_conf):
            try:
                with open(theme_style_conf) as f:
                    style_options.update(json.load(f))
            except Exception as e:
                logging.error(f"Unable to parse custom template conf file:\n{e}\n\n{traceback.format_exc()}")

        self.gtk.color_list = style_options['graph_colors']

        for i in range(len(style_options['graph_colors']['extruder']['colors'])):
            num = "" if i == 0 else i
            css_data += "\n.graph_label_extruder%s {border-left-color: #%s}" % (
                num,
                style_options['graph_colors']['extruder']['colors'][i]
            )
            css_data += "\n.graph_label_extruder%s_temp {border-right-color: #%s}" % (
                num,
                style_options['graph_colors']['extruder']['colors'][i]
            )
            
            
        for i in range(len(style_options['graph_colors']['bed']['colors'])):
            css_data += "\n.graph_label_heater_bed%s {border-left-color: #%s}" % (
                "" if i == 0 else i + 1,
                style_options['graph_colors']['bed']['colors'][i]
            )
            css_data += "\n.graph_label_heater_bed%s_temp {border-right-color: #%s}" % (
                "" if i == 0 else i + 1,
                style_options['graph_colors']['bed']['colors'][i]
            )
            
            
        for i in range(len(style_options['graph_colors']['fan']['colors'])):
            css_data += "\n.graph_label_fan_%s {border-left-color: #%s}" % (
                i + 1,
                style_options['graph_colors']['fan']['colors'][i]
            )
            css_data += "\n.graph_label_fan_%s_temp {border-right-color: #%s}" % (
                i + 1,
                style_options['graph_colors']['fan']['colors'][i]
            )
            
            
        for i in range(len(style_options['graph_colors']['sensor']['colors'])):
            css_data += "\n.graph_label_sensor_%s {border-left-color: #%s}" % (
                i + 1,
                style_options['graph_colors']['sensor']['colors'][i]
            )
            css_data += "\n.graph_label_sensor_%s_temp {border-right-color: #%s}" % (
                i + 1,
                style_options['graph_colors']['sensor']['colors'][i]
            )
            
            

        css_data = css_data.replace("KS_FONT_SIZE", f"{self.gtk.font_size}")

        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css_data.encode())

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _go_to_submenu(self, widget, name):
        logging.info(f"#### Go to submenu {name}")
        # Find current menu item
        if "main_menu" in self._cur_panels:
            menu = "__main"
        elif "splash_screen" in self._cur_panels:
            menu = "__splashscreen"
        else:
            menu = "__print"

        logging.info(f"#### Menu {menu}")
        disname = self._config.get_menu_name(menu, name)
        menuitems = self._config.get_menu_items(menu, name)
        if len(menuitems) != 0:
            self.show_panel("menu", disname, panel_name=name, items=menuitems)
        else:
            logging.info("No items in menu")

    def _remove_all_panels(self):
        for _ in self.base_panel.content.get_children():
            self.base_panel.content.remove(_)
        # for dialog in self.dialogs:
        #     self.gtk.remove_dialog(dialog)
        for panel in list(self.panels):
            if hasattr(self.panels[panel], "deactivate"):
                self.panels[panel].deactivate()
        self._cur_panels.clear()
        self.close_screensaver()

    def _remove_current_panel(self):
        self.base_panel.remove(self.panels[self._cur_panels[-1]].content)
        if hasattr(self.panels[self._cur_panels[-1]], "deactivate"):
            self.panels[self._cur_panels[-1]].deactivate()

    def _menu_go_back(self, widget=None, home=False):
        logging.info(f"#### Menu go {'home' if home else 'back'}")
        self.remove_keyboard()
        self.remove_numpad()
        while len(self._cur_panels) > 1:
            self._remove_current_panel()
            del self._cur_panels[-1]
            if not home:
                break
        if len(self._cur_panels) < 1:
            self.reload_panels()
            return
        self.attach_panel(self._cur_panels[-1])
        if self._cur_panels[-1] == 'main_menu':
          self.base_panel.check_system_fix_dialog()

    def reset_screensaver_timeout(self, *args):
        if self.screensaver_timeout is not None:
            GLib.source_remove(self.screensaver_timeout)
            self.screensaver_timeout = None
        if not self.use_dpms and self._config.get_main_config().get('screen_blanking') != "off":
            self.screensaver_timeout = GLib.timeout_add_seconds(self.blanking_time, self.show_screensaver)

    def show_screensaver(self):
        logging.debug("Showing Screensaver")
        if self.screensaver is not None:
            self.close_screensaver()
        self.remove_keyboard()
        self.remove_numpad()
        self.close_popup_message()
        for dialog in self.dialogs:
            logging.debug("Hiding dialog")
            dialog.hide()

        close = Gtk.Button()
        close.connect("clicked", self.close_screensaver)

        box = Gtk.Box(halign=Gtk.Align.CENTER, width_request=self.width, height_request=self.height)
        box.pack_start(close, True, True, 0)
        box.get_style_context().add_class("screensaver")
        self.remove(self.base_panel.main_grid)
        self.add(box)

        # Avoid leaving a cursor-handle
        close.grab_focus()
        self.screensaver = box
        self.screensaver.show_all()
        self.power_devices(None, self._config.get_main_config().get("screen_off_devices", ""), on=False)
        if self.screensaver_timeout is not None:
            GLib.source_remove(self.screensaver_timeout)
            self.screensaver_timeout = None
        return False


    def close_screensaver(self, widget=None):
        if self.screensaver is None:
            return False
        logging.debug("Closing Screensaver")
        self.remove(self.screensaver)
        self.screensaver = None
        self.add(self.base_panel.main_grid)
        if self.use_dpms:
            self.wake_screen()
        else:
            self.reset_screensaver_timeout()
        for dialog in self.dialogs:
            logging.info(f"Restoring Dialog {dialog}")
            dialog.show()
        self.show_all()
        self.power_devices(None, self._config.get_main_config().get("screen_on_devices", ""), on=True)

    def check_dpms_state(self):
        if not self.use_dpms:
            return False
        state = functions.get_DPMS_state()
        if state == functions.DPMS_State.Fail:
            logging.info("DPMS State FAIL: Stopping DPMS Check")
            self.set_dpms(False)
            return False
        elif state != functions.DPMS_State.On:
            if self.screensaver is None:
                self.show_screensaver()
        return True

    def wake_screen(self):
        # Wake the screen (it will go to standby as configured)
        if self._config.get_main_config().get('screen_blanking') != "off":
            logging.debug("Screen wake up")
            if not self.wayland:
                os.system("xset -display :0 dpms force on")


    ####      NEW      ####
    def set_autooff(self, autooff_enable):
        self._ws.klippy.set_autooff(autooff_enable)

    def set_nozzle_diameter(self, value: str):
        self._ws.klippy.set_nozzle_diameter(value)

    def set_safety(self, safety):
        self._ws.klippy.set_safety(safety)
    
    def set_quite_mode(self, quite_mode):
        self._ws.klippy.set_quite_mode("stepper_x", quite_mode)
        self._ws.klippy.set_quite_mode("stepper_y", quite_mode)
        
    def set_watch_bed_mesh(self, watch_bed_mesh):
        self._ws.klippy.set_watch_bed_mesh(watch_bed_mesh)
      
    def set_autoload_bed_mesh(self, autoload_bed_mesh):
        self._ws.klippy.set_autoload_bed_mesh(autoload_bed_mesh)
    
    # def get_stat(self, stat, substat=None):
    #     if self.data is None or stat not in self.data:
    #         return {}
    #     if substat is not None:
    #         return self.data[stat][substat] if substat in self.data[stat] else {}
    #     return self.data[stat]
    ####    END NEW    ####
    
    def set_dpms(self, use_dpms):
        self.use_dpms = use_dpms
        logging.info(f"DPMS set to: {self.use_dpms}")
        self.set_screenblanking_timeout(self._config.get_main_config().get('screen_blanking'))

    def set_screenblanking_timeout(self, time):
        if not self.wayland:
            os.system("xset -display :0 s off")
        self.use_dpms = self._config.get_main_config().getboolean("use_dpms", fallback=True)

        if time == "off":
            logging.debug(f"Screen blanking: {time}")
            if self.screensaver_timeout is not None:
                GLib.source_remove(self.screensaver_timeout)
                self.screensaver_timeout = None
            if not self.wayland:
                os.system("xset -display :0 dpms 0 0 0")
            return

        self.blanking_time = abs(int(time))
        logging.debug(f"Changing screen blanking to: {self.blanking_time}")
        if self.use_dpms and functions.dpms_loaded is True:
            if not self.wayland:
                os.system("xset -display :0 +dpms")
            if functions.get_DPMS_state() == functions.DPMS_State.Fail:
                logging.info("DPMS State FAIL")
                self.show_popup_message(_("DPMS has failed to load"))
                self._config.set("main", "use_dpms", "False")
                self._config.save_user_config_options()
            else:
                logging.debug("Using DPMS")
                if not self.wayland:
                    os.system(f"xset -display :0 dpms 0 {self.blanking_time} 0")
                GLib.timeout_add_seconds(1, self.check_dpms_state)
                return
        # Without dpms just blank the screen
        logging.debug("Not using DPMS")
        if not self.wayland:
            os.system("xset -display :0 dpms 0 0 0")
        self.reset_screensaver_timeout()
        return

    def show_printer_select(self, widget=None):
        self.base_panel.show_heaters(False)
        self.show_panel("printer_select", _("Printer Select"), remove_all=True)

    def websocket_disconnected(self, msg):
        logging.debug("### websocket_disconnected")
        self.printer_initializing(msg, remove=True)
        self.printer.state = "disconnected"
        self.connecting = True
        self.connected_printer = None
        self.initialized = False
        self.connect_printer(self.connecting_to_printer)
    ####      NEW      ####
    def state_interrupt(self):
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        self.base_panel.main_grid.get_style_context().add_class("window-interrupt")
        self.show_panel("main_menu", None, remove_all=True, items=self._config.get_menu_items("__main"))
        self.base_panel.show_interrupt_dialog()
    ####    END NEW    ####


    def state_disconnected(self):
        self.printer.stop_tempstore_updates()
        ####      NEW      ####
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        ####    END NEW    ####
        self.base_panel.main_grid.get_style_context().add_class("window-disconnected")
        logging.debug("### Going to disconnected")
        self.close_screensaver()
        self.initialized = False
        self.reinit_count = 0
        self._init_printer(_("Klipper has disconnected"), remove=True)

    def state_error(self):
        ####      NEW      ####
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        ####    END NEW    ####
        self.base_panel.main_grid.get_style_context().add_class("window-error")
        self.close_screensaver()
        msg = _("Klipper has encountered an error.") + "\n"
        state = self.printer.get_stat("webhooks", "state_message")
        if "FIRMWARE_RESTART" in state:
            msg += _("A FIRMWARE_RESTART may fix the issue.") + "\n"
        elif "micro-controller" in state:
            msg += _("Please recompile and flash the micro-controller.") + "\n"
        self.printer_initializing(msg + "\n" + state, remove=True)

    def state_paused(self):
        self.close_screensaver()
        self.show_panel("job_status", _("Printing"), remove_all=True)
        if self._config.get_main_config().getboolean("auto_open_extrude", fallback=True):
            self.show_panel("extrude", _("Extrude"))
        ####      NEW      ####
        self.last_window_class = "window-paused"
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        self.base_panel.main_grid.get_style_context().add_class("window-paused")
        ####    END NEW    ####

    def state_printing(self):
        self.close_screensaver()
        self.show_panel("job_status", _("Printing"), remove_all=True)
        ####      NEW      ####
        self.last_window_class = "window-printing"
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        self.base_panel.main_grid.get_style_context().add_class("window-printing")
        ####    END NEW    ####


    def state_ready(self, wait = True):
        # Do not return to main menu if completing a job, timeouts/user input will return
        if "job_status" in self._cur_panels and wait:
            return
        if not self.initialized:
            logging.debug("Printer not initialized yet")
            self.printer.state = "not ready"
            return
        self.files.refresh_files()
        ####      NEW      ####
        self.last_window_class = "window-ready"
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        self.base_panel.main_grid.get_style_context().add_class("window-ready")
        ####    END NEW    ####
        self.show_panel("main_menu", None, remove_all=True, items=self._config.get_menu_items("__main"))
        self.base_panel.check_system_fix_dialog()

    def state_startup(self):
        self.last_window_class = "window-ready"
        ####      NEW      ####
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        ####    END NEW    ####
        self.base_panel.main_grid.get_style_context().add_class("window-startup")
        self.printer_initializing(_("Klipper is attempting to start"))

    def state_shutdown(self):
        self.printer.stop_tempstore_updates()
        ####      NEW      ####
        self.remove_window_classes(self.base_panel.main_grid.get_style_context())
        ####    END NEW    ####
        self.base_panel.main_grid.get_style_context().add_class("window-shutdown")
        self.close_screensaver()
        msg = self.printer.get_stat("webhooks", "state_message")
        msg = msg if "ready" not in msg else ""
        self.printer_initializing(_("Klipper has shutdown") + "\n\n" + msg, remove=True)


    def remove_window_classes(self, context):
        window_classes = (i for i in context.list_classes() if i.startswith("window-"))
        for j in window_classes:
            context.remove_class(j)

    def toggle_shortcut(self, show):
        if show and not self.printer.get_printer_status_data()["printer"]["gcode_macros"]["count"] > 0:
            self.show_popup_message(
                _("No elegible macros:") + "\n" #no locale
                + _("macros with a name starting with '_' are hidden") + "\n" #no locale
                + _("macros that use 'rename_existing' are hidden") + "\n" #no locale
                + _("LOAD_FILAMENT/UNLOAD_FILAMENT are hidden and shold be used from extrude") + "\n" #no locale
            )
        self.base_panel.show_shortcut(show)

    def change_language(self, widget, lang):
        self._config.install_language(lang)
        self.lang_ltr = set_text_direction(lang)
        self.env.install_gettext_translations(self._config.get_lang())
        self._config._create_configurable_options(self)
        self._config.set('main', 'language', lang)
        self._config.save_user_config_options()
        self.reload_panels()

    def reload_panels(self, *args):
        if "printer_select" in self._cur_panels:
            self.show_printer_select()
            return
        self._remove_all_panels()
        if self.printer is not None:
            self.printer.change_state(self.printer.state)

    def _websocket_callback(self, action, data):
        if self.connecting:
            return
        if action == "notify_klippy_disconnected":
            self.printer.process_update({'webhooks': {'state': "disconnected"}})
            return
        elif action == "notify_klippy_shutdown":
            self.printer.process_update({'webhooks': {'state': "shutdown"}})
            return
        elif action == "notify_klippy_ready":
            if not self.initialized:
                self.reinit_count = 0
                self._init_printer(_("Reconnecting"), klipper=True)
                return
            self.printer.process_update({'webhooks': {'state': "ready"}})
            return
        elif action == "notify_status_update" and self.printer.state != "shutdown":
            self.printer.process_update(data)
        elif action == "notify_filelist_changed":
            if self.files is not None:
                self.files.process_update(data)
            return
        elif action == "notify_metadata_update":
            self.files.request_metadata(data['filename'])
            return
        elif action == "notify_update_response":
            if 'message' in data and 'error' in data['message'].lower():
                logging.error(f"{action}:{data['message']}")
                self.show_popup_message(data['message'], 3)
                if "KlipperScreen" in data['message']:
                    self.restart_ks()
        elif action == "notify_power_changed":
            logging.debug("Power status changed: %s", data)
            self.printer.process_power_update(data)
            self.panels['splash_screen'].check_power_status()
        elif action == "notify_gcode_response" and self.printer.state not in ["error", "shutdown"]:
            if not (data.startswith("B:") or data.startswith("T:")):
                if data.startswith("// action:"):
                    action = data[10:]
                    if action.startswith('prompt_begin'):
                        if self.prompt is not None:
                            self.prompt.end()
                        self.prompt = Prompt(self)
                    if self.prompt is None:
                        return
                    self.prompt.decode(action)
                # elif data.startswith("echo: "):
                #     self.show_popup_message(data[6:], 1)
                # elif data.startswith("(suggestion) "):
                #   self.show_popup_message(data[13:], 10)
                elif data.startswith("!! "):
                  self.new_popup_msg = data[3:]
                  if len(self.dialogs):
                    GLib.timeout_add(300, self.new_popup)
                  else:
                    self.new_popup()
                elif "unknown" in data.lower() and \
                        not ("TESTZ" in data or "MEASURE_AXES_NOISE" in data or "ACCELEROMETER_QUERY" in data):
                    self.show_popup_message(data)
        self.process_update(action, data)

    def new_popup(self, *args):
      self.show_popup_message(self.new_popup_msg, 3, True)
      return False
    
    def process_update(self, *args):
        self.base_panel.process_update(*args)
        if self._cur_panels and hasattr(self.panels[self._cur_panels[-1]], "process_update"):
            self.panels[self._cur_panels[-1]].process_update(*args)
            
    def _confirm_send_action(self, widget, text, method, params=None, callback=None):
        buttons = [
            {"name": _("Continue"), "response": Gtk.ResponseType.OK, "style": "color4"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
        ]

        try:
            j2_temp = self.env.from_string(text)
            text = j2_temp.render()
        except Exception as e:
            logging.debug(f"Error parsing jinja for confirm_send_action\n{e}\n\n{traceback.format_exc()}")

        label = Gtk.Label()
        label.set_markup(text)
        label.set_hexpand(True)
        label.set_halign(Gtk.Align.CENTER)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        if self.confirm is not None:
            self.gtk.remove_dialog(self.confirm)
        self.confirm = self.gtk.Dialog(buttons, label, "KlipperScreen", self._confirm_send_action_response, method, params, callback)

    def _confirm_send_action_response(self, dialog, response_id, method, params, callback=None):
        self.gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self._send_action(None, method, params, callback)

    def _send_action(self, widget, method, params, callback=None):
        logging.info(f"{method}: {params}")
        self._ws.send_method(method, params, callback)

    def printer_initializing(self, msg, remove=False):
        if 'splash_screen' not in self.panels or remove:
            self.show_panel("splash_screen", None, remove_all=True)
        self.panels['splash_screen'].update_text(msg)
        self.log_notification(msg, 0)

    def search_power_devices(self, devices):
        found_devices = []
        if self.connected_printer is None or not devices:
            return found_devices
        devices = [str(i.strip()) for i in devices.split(',')]
        power_devices = self.printer.get_power_devices()
        if power_devices:
            found_devices = [dev for dev in devices if dev in power_devices]
            logging.info(f"Found {found_devices}", )
        return found_devices

    def _init_printer(self, msg, remove=False, klipper=False):
        self.printer_initializing(msg, remove)
        self.initializing = False
        if klipper:
            GLib.timeout_add_seconds(3, self.init_klipper)
        else:
            GLib.timeout_add_seconds(3, self.init_printer)
    
    def power_devices(self, widget=None, devices=None, on=False):
        devs = self.search_power_devices(devices)
        for dev in devs:
            if on:
                self._ws.klippy.power_device_on(dev)
            else:
                self._ws.klippy.power_device_off(dev)
    
    def init_printer(self):
        if self.initializing:
            logging.info("Already Initializing")
            return False
        self.initializing = True
        if self.reinit_count > self.max_retries or 'printer_select' in self._cur_panels:
            logging.info("Stopping Retries")
            self.initializing = False
            return False
        state = self.apiclient.get_server_info()
        if state is False:
            logging.info("Moonraker not connected")
            self.initializing = False
            return False
        self.connecting = not self._ws.connected
        self.connected_printer = self.connecting_to_printer
        self.base_panel.set_ks_printer_cfg(self.connected_printer)

        self.init_server(state["result"])
        # Moonraker is ready, set a loop to init the printer
        return self.init_klipper(state["result"])
        
    def init_server(self, server_info):
        popup = ''
        level = 2
        if server_info["warnings"]:
            popup += '\nMoonraker warnings:\n'
            for warning in server_info["warnings"]:
                warning = warning.replace('<br>', '').replace('<br/>', '\n').replace('</br>', '\n').replace(':', ':\n')
                popup += f"{warning}\n"
        if server_info["failed_components"]:
            popup += '\nMoonraker failed components:\n'
            for failed in server_info["failed_components"]:
                popup += f'[{failed}]\n'
        if server_info["missing_klippy_requirements"]:
            popup += '\nMissing Klipper configuration:\n'
            for missing in server_info["missing_klippy_requirements"]:
                popup += f'[{missing}]\n'
                level = 3
        if popup:
            self.show_popup_message(popup, level)
        if "webcam" in server_info["components"]:
            cameras = self.apiclient.send_request("server/webcams/list")
            if cameras is not False:
                self.printer.configure_cameras(cameras['result']['webcams'])
        if "spoolman" in server_info["components"]:
            self.printer.enable_spoolman()
                
    def init_klipper(self, server_info=None):
        if self.reinit_count > self.max_retries or 'printer_select' in self._cur_panels:
            logging.info("Stopping Retries")
            return False
        if not server_info:
            server_info = self.apiclient.get_server_info()["result"]
        #logging.info(f"Moonraker info {server_info}")

        self.reinit_count += 1

        if server_info['klippy_connected'] is False:
            logging.info("Klipper not connected")
            msg = _("Moonraker: connected") + "\n\n"
            msg += f"Klipper: {server_info['klippy_state']}" + "\n\n"
            if self.reinit_count <= self.max_retries:
                msg += _("Retrying") + f' #{self.reinit_count}'
            return self._init_printer(msg, klipper=True)
        printer_info = self.apiclient.get_printer_info()
        if printer_info is False:
            return self._init_printer(_("Unable to get printer info from moonraker"))
        config = self.apiclient.send_request("printer/objects/query?configfile")
        if config is False:
            return self._init_printer(_("Error getting printer configuration"))
        #logging.debug(config['result']['status'])
        # Reinitialize printer, in case the printer was shut down and anything has changed.
        self.printer.reinit(printer_info['result'], config['result']['status'])
        self.printer.available_commands = self.apiclient.get_gcode_help()['result']
        info = self.apiclient.send_request("machine/system_info")
        if info and 'result' in info and 'system_info' in info['result']:
            self.printer.system_info = info['result']['system_info']

        self.ws_subscribe()
        extra_items = (self.printer.get_tools()
                       + self.printer.get_heaters()
                       + self.printer.get_temp_sensors()
                       + self.printer.get_fans()
                       + self.printer.get_temp_fans()
                       + self.printer.get_filament_sensors()
                       + self.printer.get_output_pins()
                       + self.printer.get_leds()
                       )

        data = self.apiclient.send_request("printer/objects/query?" + "&".join(PRINTER_BASE_STATUS_OBJECTS +
                                                                               extra_items))
        if data is False:
            return self._init_printer(_("Error getting printer object data with extra items"))

        self.files.set_gcodes_path()
        self.init_spoolman()
        logging.info("Printer initialized")
        self.initialized = True
        self.reinit_count = 0
        self.initializing = False
        self.printer.process_update(data['result']['status'])
        self.log_notification("Printer Initialized", 1)
        return False

    def init_tempstore(self):
        if len(self.printer.get_temp_devices()) == 0:
            return
        tempstore = self.apiclient.send_request("server/temperature_store")
        if tempstore and 'result' in tempstore and tempstore['result']:
            self.printer.init_temp_store(tempstore['result'])
            if hasattr(self.panels[self._cur_panels[-1]], "update_graph_visibility"):
                self.panels[self._cur_panels[-1]].update_graph_visibility()
        else:
            logging.error(f'Tempstore not ready: {tempstore} Retrying in 5 seconds')
            GLib.timeout_add_seconds(5, self.init_tempstore)
            return
        if set(self.printer.tempstore) != set(self.printer.get_temp_devices()):
            GLib.timeout_add_seconds(5, self.init_tempstore)
            return
        server_config = self.apiclient.send_request("server/config")
        if server_config:
            try:
                self.printer.tempstore_size = server_config["result"]["config"]["data_store"]["temperature_store_size"]
                logging.info(f"Temperature store size: {self.printer.tempstore_size}")
            except KeyError:
                logging.error("Couldn't get the temperature store size")
                return False

    def init_spoolman(self):
        server_config = self.apiclient.send_request("server/config")
        if server_config:
            try:
                server_config["result"]["config"]["spoolman"]
                self.printer.enable_spoolman()
            except KeyError:
                logging.warning("Not using Spoolman")

        return False

    def show_keyboard(self, entry=None, event=None, accept_function=None, backspace_function=None, reject_function=None):
        if self.keyboard is not None:
            return
        if entry is None:
            logging.debug("Error: no entry provided for keyboard")
            return
        if not reject_function:
          reject_function = self.remove_keyboard
        self.keyboard = Keyboard(self, reject_function, accept_function, entry=entry, backspace_cb=backspace_function)
        self.base_panel.content.pack_end(self.keyboard, True, True, 5)
        self.base_panel.content.show_all()

    def remove_keyboard(self, widget=None, event=None):
        if self.keyboard is None:
            return
        if 'process' in self.keyboard:
            os.kill(self.keyboard['process'].pid, SIGTERM)
        self.base_panel.content.remove(self.keyboard)
        self.keyboard = None

    def show_numpad(self, entry=None, event=None, accept_function=None): 
        if self.numpad is not None:
                return
        if entry is None:
            logging.debug("Error: no entry provided for keyboard")
            return
        self.numpad = Numpad(self, accept_function, entry=entry)
        self.base_panel.content.pack_end(self.numpad, True, True, 5)
        self.base_panel.content.show_all()

    def remove_numpad(self, widget=None, event=None):
        if self.numpad is None:
            return
        self.base_panel.content.remove(self.numpad)
        self.numpad = None   
    
    def _show_matchbox_keyboard(self, box):
        env = os.environ.copy()
        usrkbd = os.path.expanduser("~/.matchbox/keyboard.xml")
        if os.path.isfile(usrkbd):
            env["MB_KBD_CONFIG"] = usrkbd
        else:
            env["MB_KBD_CONFIG"] = "ks_includes/locales/keyboard.xml"
        p = subprocess.Popen(["matchbox-keyboard", "--xid"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        xid = int(p.stdout.readline())
        logging.debug(f"XID {xid}")
        logging.debug(f"PID {p.pid}")

        keyboard = Gtk.Socket()
        box.get_style_context().add_class("keyboard_matchbox")
        box.pack_start(keyboard, True, True, 0)
        self.base_panel.content.pack_end(box, False, False, 0)

        self.show_all()
        keyboard.add_id(xid)

        self.keyboard = {
            "box": box,
            "process": p,
            "socket": keyboard
        }
        return

    # def _key_press_event(self, widget, event):
    #     keyval_name = Gdk.keyval_name(event.keyval)
    #     if keyval_name == "Escape":
    #         self._menu_go_back(home=True)
    #     elif keyval_name == "BackSpace" and len(self._cur_panels) > 1 and self.keyboard is None:
    #         self.base_panel.back()

    def update_size(self, *args):
        width, height = self.get_size()
        if width != self.width or height != self.height:
            logging.info(f"Size changed: {self.width}x{self.height}")
        self.width, self.height = width, height
        new_ratio = self.width / self.height
        new_mode = new_ratio < 1.0
        ratio_delta = abs(self.aspect_ratio - new_ratio)
        if ratio_delta > 0.1 and self.vertical_mode != new_mode:
            self.reload_panels()
            self.vertical_mode = new_mode
            self.aspect_ratio = new_ratio
            logging.info(f"Vertical mode: {self.vertical_mode}")



def main():
    minimum = (3, 7)
    if not sys.version_info >= minimum:
        logging.error(f"python {sys.version_info.major}.{sys.version_info.minor} "
                      f"does not meet the minimum requirement {minimum[0]}.{minimum[1]}")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="KlipperScreen - A GUI for Klipper")
    homedir = os.path.expanduser("~")

    parser.add_argument(
        "-c", "--configfile",
        default="", metavar='<configfile>',
        help="Location of KlipperScreen configuration file"
    )
    logdir = os.path.join(homedir, "printer_data", "logs")
    if not os.path.exists(logdir):
        logdir = "/tmp"
    parser.add_argument(
        "-l", "--logfile", default=os.path.join(logdir, "KlipperScreen.log"), metavar='<logfile>',
        help="Location of KlipperScreen logfile output"
    )
    parser.add_argument(
        "-m", "--monitor", default="0", metavar='<monitor>',
        help="Number of the monitor, that will show Klipperscreen (default: 0)"
    )
    args = parser.parse_args()

    functions.setup_logging(os.path.normpath(os.path.expanduser(args.logfile)))
    functions.patch_threading_excepthook()
    if not Gtk.init_check():
        logging.critical("Failed to initialize Gtk")
        raise RuntimeError
    try:
        win = KlipperScreen(args)
    except Exception as e:
        logging.exception(f"Failed to initialize window\n{e}\n\n{traceback.format_exc()}")
        raise RuntimeError from e
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.exception(f"Fatal error in main loop:\n{ex}\n\n{traceback.format_exc()}")
        sys.exit(1)
