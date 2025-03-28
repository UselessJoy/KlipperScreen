import logging
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.typed_entry import TypedEntry
HIDDEN_MACROS = [
  "CANCEL_PRINT", "GET_TIMELAPSE_SETUP", "HYPERLAPSE", "LOAD_FILAMENT", "M201", "M203", 
  "M205", "M486", "M900", "PAUSE", "RESUME", "SET_PAUSE_AT_LAYER", "SET_PAUSE_NEXT_LAYER", 
  "SET_PRINT_STATS_INFO", "TEST_STREAM_DELAY", "TIMELAPSE_RENDER", "TIMELAPSE_TAKE_FRAME", 
  "UNLOAD_FILAMENT", "_SET_TIMELAPSE_SETUP", "_TIMELAPSE_NEW_FRAME", "_WAIT_TIMELAPSE_TAKE_FRAME", 
  "_HYPERLAPSE_LOOP", "_WAIT_TIMELAPSE_RENDER"
]

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.sort_reverse = False
        self.sort_btn = self._gtk.Button("arrow-up", _("Name"), "color1", self.bts, Gtk.PositionType.RIGHT, 1)
        self.sort_btn.connect("clicked", self.change_sort)
        self.sort_btn.set_hexpand(True)
        self.sort_btn.get_style_context().add_class("buttons_slim")
        self.options = {}
        self.macros = {}
        self.locale_params = {}
        self.menu = ['macros_menu']

        adjust = self._gtk.Button("settings", " " + _("Settings"), "color2", self.bts, Gtk.PositionType.LEFT, 1)
        adjust.get_style_context().add_class("buttons_slim")
        adjust.connect("clicked", self.load_menu, 'options', _("Settings"))
        adjust.set_hexpand(False)

        sbox = Gtk.Box(vexpand=False)
        sbox.pack_start(self.sort_btn, True, True, 5)
        sbox.pack_start(adjust, True, True, 5)

        self.labels['macros_list'] = self._gtk.ScrolledWindow()
        self.labels['macros'] = Gtk.Grid()
        self.labels['macros_list'].add(self.labels['macros'])

        self.labels['macros_menu'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.labels['macros_menu'].pack_start(sbox, False, False, 0)
        self.labels['macros_menu'].pack_start(self.labels['macros_list'], True, True, 0)

        self.content.add(self.labels['macros_menu'])
        self.labels['options_menu'] = self._gtk.ScrolledWindow()
        self.labels['options'] = Gtk.Grid()
        self.labels['options_menu'].add(self.labels['options'])

    def activate(self):
        while len(self.menu) > 1:
            self.unload_menu()
        self.reload_macros()
    
    def add_gcode_macro(self, macro, macro_locale, param_locale_dict):
        section = self._printer.get_macro(macro)
        if section:
            if "rename_existing" in section:
                return
            if "gcode" in section:
                gcode = section["gcode"].split("\n")
            else:
                logging.error(f"gcode not found in {macro}\n{section}")
                return
        else:
            logging.debug(f"Couldn't load {macro}\n{section}")
            return
        name = Gtk.Label(hexpand=True, vexpand=True, halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                         wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        name.set_margin_bottom(10)
        name.set_markup(f"<big><b>{macro if macro_locale == None else macro_locale}</b></big>")

        btn = self._gtk.Button("resume", style="color3")
        btn.connect("clicked", self.run_gcode_macro, macro)
        btn.set_hexpand(False)
        btn.set_vexpand(False)
        btn.set_margin_bottom(10)
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_halign(Gtk.Align.END)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        labels.add(name)

        row = Gtk.Box(spacing=5, margin_bottom=15)
        row.get_style_context().add_class("frame-item")
        row.add(labels)
        row.add(btn)

        self.macros[macro] = {
            "row": row,
            "params": {},
        }
        pattern = r'params\.(?P<param>[a-zA-Z0-9_]+)(?:\s*\|.*\s*default\(\s*(?P<default>[^\)]+)\))?'
        for line in gcode:
            if line.startswith("{") and "params." in line:
                result = re.search(pattern, line)
                if result:
                    result = result.groupdict()
                    default = result["default"] if "default" in result and result['default'] else ""
                    entry = TypedEntry()
                    entry.set_margin_bottom(10)
                    entry.set_text(default)
                    self.macros[macro]["params"].update({result["param"]: entry})

        params_grid = Gtk.Grid(column_homogeneous=True)
        for i, param in enumerate(self.macros[macro]["params"]):
            param_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_right=10)
            if param in param_locale_dict:
                param_box.add(Gtk.Label(label=param_locale_dict[param], hexpand=True, halign=Gtk.Align.CENTER))
            else:
                param_box.add(Gtk.Label(label=param, hexpand=True, halign=Gtk.Align.CENTER))
            param_box.add(self.macros[macro]["params"][param])
            
            self.macros[macro]["params"][param].connect("focus-in-event", self.on_change_entry)
            self.macros[macro]["params"][param].connect("focus-out-event", self._screen.remove_keyboard)
            params_grid.attach(param_box, i % 3, i / 3, 1, 1)    
        labels.add(params_grid)

    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry)
        self._screen.keyboard.change_entry(entry=entry)

    def run_gcode_macro(self, widget, macro):
        params = ""
        for param in self.macros[macro]["params"]:
            value = self.macros[macro]["params"][param].get_text()
            if value:
                params += f'{param}={value} '
        self._screen.show_popup_message(f"{macro} {params}", 1)
        self._screen._ws.klippy.gcode_script(f"{macro} {params}")

    def change_sort(self, widget):
        self.sort_reverse ^= True
        if self.sort_reverse:
            self.sort_btn.set_image(self._gtk.Image("arrow-down", self._gtk.img_scale * self.bts))
        else:
            self.sort_btn.set_image(self._gtk.Image("arrow-up", self._gtk.img_scale * self.bts))
        self.sort_btn.show()

        GLib.idle_add(self.reload_macros)

    def reload_macros(self):
        self.labels['macros'].remove_column(0)
        self.macros = {}
        self.options = {}
        self.labels['options'].remove_column(0)
        self.load_gcode_macros()
        return False

    def load_gcode_macros(self):
        macros = self._printer.get_gcode_macros()
        for macro in macros:
            macro_locale = None
            param_locale_dict: dict = {}
            macro_params = self._printer.get_macro(macro)
            if 'macro_locale' in macro_params:
                macro_locale = macro_params['macro_locale']
            if 'param_locale' in macro_params:
                param_locale: str = macro_params['param_locale']
                param_locale_list: list[str] = param_locale.split(',')
                for pl in param_locale_list:
                    partition_pl = pl.strip().partition('.')
                    param_locale_dict[partition_pl[0]] = partition_pl[2]
            self.options[macro] = {
                "name": macro,
                "section": f"displayed_macros {self._screen.connected_printer}",
            }
            show = self._config.get_config().getboolean(self.options[macro]["section"], macro.lower(), fallback=None)
            if not show:
                show = macro not in HIDDEN_MACROS
            if macro not in self.macros and show:
                self.add_gcode_macro(macro, macro_locale, param_locale_dict)

        for macro in list(self.options):
            if self.options[macro]["name"] in self.locale_params:
                self.add_option('options', self.options, macro, self.options[macro])
            else:
                self.add_option('options', self.options, macro, self.options[macro])
        macros = sorted(self.macros, reverse=self.sort_reverse, key=str.casefold)
        for macro in macros:
            pos = macros.index(macro)
            self.labels['macros'].insert_row(pos)
            self.labels['macros'].attach(self.macros[macro]['row'], 0, pos, 1, 1)
            self.labels['macros'].show_all()

    def add_option(self, boxname, opt_array, opt_name, option):
        name = Gtk.Label(hexpand=True, vexpand=True, halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                         wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        name.set_markup(f"<big><b>{option['name']}</b></big>")

        box = Gtk.Box(vexpand=False)

        active = self._config.get_config().getboolean(option['section'], opt_name, fallback=None)
        if not active:
            active = opt_name not in HIDDEN_MACROS
        switch = Gtk.Switch(hexpand=False, vexpand=False,
                            width_request=round(self._gtk.font_size * 7),
                            height_request=round(self._gtk.font_size * 3.5),
                            active=active)
        switch.connect("notify::active", self.switch_config_option, option['section'], opt_name)
        box.add(switch)

        dev = Gtk.Box(hexpand=True, vexpand=False, valign=Gtk.Align.CENTER)
        dev.get_style_context().add_class("frame-item")
        dev.add(name)
        dev.add(box)

        opt_array[opt_name] = {
            "name": option['name'],
            "row": dev
        }

        opts = sorted(self.options, key=str.casefold)
        pos = opts.index(opt_name)

        self.labels[boxname].insert_row(pos)
        self.labels[boxname].attach(opt_array[opt_name]['row'], 0, pos, 1, 1)
        self.labels[boxname].show_all()

    def back(self):
        if len(self.menu) > 1:
            self.unload_menu()
            self.reload_macros()
            return True
        return False
