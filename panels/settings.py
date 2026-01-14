import gi
import logging
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.widgets.typed_entry import SerialNumberRule, TypedEntry
from ks_includes.widgets.keyboard import Keyboard
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.printers = self.settings = self.langs = self.entries = {}
        self.menu = ['settings_menu']
        options = self._config.get_configurable_options().copy()
        # options.append({"printers": {
        #     "name": _("Printer Connections"),
        #     "type": "menu",
        #     "menu": "printers"
        # }})
        options.append({"lang": {
            "name": _("Language"),
            "type": "menu",
            "menu": "lang"
        }})
        
        self.options_data = {}
        self.labels['settings_menu'] = self._gtk.ScrolledWindow()
        self.labels['settings'] = Gtk.Grid()
        self.labels['settings_menu'].add(self.labels['settings'])
        for option in options:
            name = list(option)[0]
            self.add_option('settings', self.settings, name, option[name])
        
        self.labels['lang_menu'] = self._gtk.ScrolledWindow()
        self.labels['lang'] = Gtk.Grid()
        self.labels['lang_menu'].add(self.labels['lang'])
        for lang in self._config.lang_list:
            self.langs[lang] = {
                "name": lang,
                "type": "lang",
            }
            self.add_option("lang", self.langs, lang, self.langs[lang])

        self.labels['printers_menu'] = self._gtk.ScrolledWindow()
        self.labels['printers'] = Gtk.Grid()
        self.labels['printers_menu'].add(self.labels['printers'])
        for printer in self._config.get_printers():
            pname = list(printer)[0]
            self.printers[pname] = {
                "name": pname,
                "section": f"printer {pname}",
                "type": "printer",
                "moonraker_host": printer[pname]['moonraker_host'],
                "moonraker_port": printer[pname]['moonraker_port'],
            }
            self.add_option("printers", self.printers, pname, self.printers[pname])

        try:
            serial_number = screen.apiclient.send_request("printer/serial/get_serial")
            opts = {
            "name": _("Serial number"),
            "text": serial_number['result']['serial_number'],
            "type": "entry",
            "on_accept": self.on_accept_serial
            }
            self.add_option("settings", self.entries, opts['name'], opts)
        except Exception as e:
            logging.error(f"Can't load serial number from klipper: {e}")
        
        self.content.add(self.labels['settings_menu'])

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        
        if 'autooff' in data:
            if 'autoOff_enable' in data['autooff']:
                logging.info(f"autooff changed to {data['autooff']['autoOff_enable']}")
                for child in self.options_data['autooff_enable']['row']:
                    if hasattr(child, "set_active"):
                        child.set_active(data['autooff']['autoOff_enable'])
                    
        if 'safety_printing' in data:
            if 'safety_enabled' in data['safety_printing']:
                logging.info(f"safety_printing changed to {data['safety_printing']['safety_enabled']}")
                for child in self.options_data['safety_printing']['row']:
                    if hasattr(child, "set_active"):
                        child.set_active(data['safety_printing']['safety_enabled'])
        
        if 'tmc2209 stepper_x' in data:
          if 'quite_mode' in data['tmc2209 stepper_x']:
            for child in self.options_data['quite_mode']['row']:
              if hasattr(child, "set_active"):
                  child.set_active(data['tmc2209 stepper_x']['quite_mode'])
        
        if 'virtual_sdcard' in data:
            if 'watch_bed_mesh' in data['virtual_sdcard']:
                logging.info(f"watch_bed_mesh changed to {data['virtual_sdcard']['watch_bed_mesh']}")
                for child in self.options_data['watch_bed_mesh']['row']:
                    if hasattr(child, "set_active"):
                        child.set_active(data['virtual_sdcard']['watch_bed_mesh'])
            if 'autoload_bed_mesh' in data['virtual_sdcard']:
                logging.info(f"autoload_bed_mesh changed to {data['virtual_sdcard']['autoload_bed_mesh']}")
                for child in self.options_data['autoload_bed_mesh']['row']:
                    if hasattr(child, "set_active"):
                        child.set_active(data['virtual_sdcard']['autoload_bed_mesh'])
        if 'extruder' in data:
          if 'nozzle_diameter' in data['extruder']:
            logging.info(f"nozzle_diameter changed to {data['extruder']['nozzle_diameter']}")
            for child in self.options_data['nozzle_diameter']['row']:
              if hasattr(child, "get_model"):
                found_value = False
                model = child.get_model()
                i = 0
                for _, value in model:
                  logging.info(f"{int(float(value) * 100)} == {int(float(data['extruder']['nozzle_diameter']) * 100)}")
                  if int(float(value) * 100) == int(float(data['extruder']['nozzle_diameter']) * 100):
                    child.set_active(i)
                    found_value = True
                    break
                  i += 1
                if not found_value:
                  child.append(str(data['extruder']['nozzle_diameter']), str(data['extruder']['nozzle_diameter']))
                  child.set_active(i)
            child.show_all()
            logging.info(f"{self._printer.get_stat('extruder')}")

    def activate(self):
        while len(self.menu) > 1:
            self.unload_menu()

    def back(self):
        if len(self.menu) > 1:
            self.unload_menu()
            return True
        return False

    def add_option(self, boxname, opt_array, opt_name, option):
        if option['type'] is None:
            return
        name = Gtk.Label()
        name.set_markup(f"<big><b>{option['name']}</b></big>")
        name.set_hexpand(True)
        name.set_vexpand(True)
        name.set_halign(Gtk.Align.START)
        name.set_valign(Gtk.Align.CENTER)
        name.set_line_wrap(True)
        name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        labels.add(name)

        dev = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        dev.get_style_context().add_class("frame-item")
        dev.set_hexpand(True)
        dev.set_vexpand(False)
        dev.set_valign(Gtk.Align.CENTER)

        dev.add(labels)
        if option['type'] == "binary":
            switch = Gtk.Switch()
            switch.set_active(self._config.get_config().getboolean(option['section'], opt_name))
            switch.connect("notify::active", self.switch_config_option, option['section'], opt_name,
                           option['callback'] if "callback" in option else None)
            dev.add(switch)
        elif option['type'] == "dropdown":
            dropdown = Gtk.ComboBoxText()
            for i, opt in enumerate(option['options']):
                dropdown.append(opt['value'], opt['name'])
                if opt['value'] == self._config.get_config()[option['section']].get(opt_name, option['value']):
                    dropdown.set_active(i)
            dropdown.connect("changed", self.on_dropdown_change, option['section'], opt_name,
                             option['callback'] if "callback" in option else None)
            dropdown.set_entry_text_column(0)
            dev.add(dropdown)
        elif option['type'] == "scale":
            dev.set_orientation(Gtk.Orientation.VERTICAL)
            scale = Gtk.Scale.new_with_range(orientation=Gtk.Orientation.HORIZONTAL,
                                             min=option['range'][0], max=option['range'][1], step=option['step'])
            scale.set_hexpand(True)
            scale.set_value(int(self._config.get_config().get(option['section'], opt_name, fallback=option['value'])))
            scale.set_digits(0)
            scale.connect("button-release-event", self.scale_moved, option['section'], opt_name)
            dev.add(scale)
        elif option['type'] == "printer":
            box = Gtk.Box()
            box.set_vexpand(False)
            label = Gtk.Label(f"{option['moonraker_host']}:{option['moonraker_port']}")
            box.add(label)
            dev.add(box)
        elif option['type'] == "menu":
            open_menu = self._gtk.Button("settings", style="color3")
            open_menu.connect("clicked", self.load_menu, option['menu'], option['name'])
            open_menu.set_hexpand(False)
            open_menu.set_halign(Gtk.Align.END)
            dev.add(open_menu)
        elif option['type'] == "lang":
            select = self._gtk.Button("load", style="color3")
            select.connect("clicked", self._screen.change_language, option['name'])
            select.set_hexpand(False)
            select.set_halign(Gtk.Align.END)
            dev.add(select)
        elif option['type'] == 'entry':
            entry = TypedEntry(SerialNumberRule)
            if option['text']:
              entry.set_text(option['text'])
            else:
              entry.set_text('')
            # entry.set_hexpand(True)
            # entry.set_vexpand(False)
            entry.set_size_request(self._screen.width * 0.4, 1)
            entry.connect("button-press-event", self.on_change_entry, option['on_accept'])
            dev.add(entry)

        opt_array[opt_name] = {
            "name": option['name'],
            "row": dev
        }
        self.options_data[opt_name] = opt_array[opt_name]
        # opts = sorted(list(opt_array), key=lambda x: opt_array[x]['name'])
        # pos = opts.index(opt_name)

        self.labels[boxname].insert_row(len(opt_array))
        self.labels[boxname].attach(opt_array[opt_name]['row'], 0, len(opt_array), 1, 1)
        self.labels[boxname].show_all()

    def on_change_entry(self, entry, event, opt_func):
        self._screen.show_keyboard(entry=entry, accept_function=opt_func)
        self._screen.keyboard.change_entry(entry=entry)

    def on_accept_serial(self):
        if self._screen.keyboard:
          self._screen._ws.klippy.set_serial_number(self._screen.keyboard.entry.get_text())
          self._screen.remove_keyboard()
          logging.info("serial number updated")