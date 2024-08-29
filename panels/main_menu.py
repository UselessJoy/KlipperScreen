import logging
import contextlib
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from panels.menu import Panel as MenuPanel
from ks_includes.widgets.heatergraph import HeaterGraph
from ks_includes.widgets.keypad import Keypad

class Panel(MenuPanel):
    def __init__(self, screen, title, items=None):
        super().__init__(screen, title, items)
        self.left_panel = None
        self.is_active = False
        self.rows_box = None
        self.calibrate_button = None
        self.temperatures = []
        self.pid_scroll = self._screen.gtk.ScrolledWindow()
        self.pid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.menu_labels = None
        self.devices = {}
        self.graph_update = None
        self.active_heater = None
        self.h = self.f = 0
        self.main_menu = self._gtk.HomogeneousGrid()
        self.main_menu.set_hexpand(True)
        self.main_menu.set_vexpand(True)
        scroll = self._gtk.ScrolledWindow()
        self.numpad_visible = False
        self.labels['print_interrupt'] = None
        
        logging.info("### Making MainMenu")

        stats = self._printer.get_printer_status_data()["printer"]
        
        if stats["temperature_devices"]["count"] > 0 or stats["extruders"]["count"] > 0:
            self._gtk.reset_temp_color()
            self.main_menu.attach(self.create_left_panel(), 0, 0, 1, 1)
        self.columns = 2
        if self._screen.vertical_mode:
            self.columns = 3
            self.labels['menu'] = self.arrangeMenuItems(items, self.columns, True)
            scroll.add(self.labels['menu'])
            self.main_menu.attach(scroll, 0, 1, 1, 1)
        else:
            self.labels['menu'] = self.arrangeMenuItems(items, self.columns, True)
            scroll.add(self.labels['menu'])
            self.main_menu.attach(scroll, 1, 0, 1, 1)
        self.main_menu.show_all()
        self.content.add(self.main_menu)

    def update_graph_visibility(self):
        if self.left_panel is None:
            logging.info("No left panel")
            return
        count = 0   
        for device in self.devices:
            visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}",
                                                           device, fallback=True)
            self.devices[device]['visible'] = visible
            self.labels['da'].set_showing(device, visible)
            if visible:
                count += 1
                self.devices[device]['name'].get_style_context().add_class("graph_label")
                if self._printer.device_has_target(device):
                    self.devices[device]['temp'].get_style_context().add_class("graph_label_temp")
            else:
                self.devices[device]['name'].get_style_context().remove_class("graph_label")
                self.devices[device]['temp'].get_style_context().remove_class("graph_label_temp")
        if count > 0:
            if self.labels['da'] not in self.left_panel:
                self.left_panel.add(self.labels['da'])
            self.labels['da'].queue_draw()
            self.labels['da'].show()
            if self.graph_update is None:
                # This has a high impact on load
                self.graph_update = GLib.timeout_add_seconds(5, self.update_graph)
        elif self.labels['da'] in self.left_panel:
            self.left_panel.remove(self.labels['da'])
            if self.graph_update is not None:
                GLib.source_remove(self.graph_update)
                self.graph_update = None
        return False

    def activate(self):
        if not self._printer.tempstore:
            self._screen.init_tempstore()
        self.update_graph_visibility()

    def deactivate(self):
        if self.graph_update is not None:
            GLib.source_remove(self.graph_update)
            self.graph_update = None
        if self.active_heater is not None:
            self.hide_numpad()

    def add_device(self, device):

        logging.info(f"Adding device: {device}")

        temperature = self._printer.get_dev_stat(device, "temperature")
        if temperature is None:
            return False

        devname = device.split()[1] if len(device.split()) > 1 else device
        # Support for hiding devices by name
        if devname.startswith("_"):
            return False

        if device.startswith("extruder"):
            if self._printer.extrudercount > 1:
                image = f"extruder-{device[8:]}" if device[8:] else "extruder-0"
            else:
                image = "extruder"
            class_name = f"graph_label_{device}"
            dev_type = "extruder"
        elif device == "heater_bed":
            image = "bed"
            # devname = "Heater Bed"
            class_name = "graph_label_heater_bed"
            dev_type = "bed"
        elif device.startswith("heater_generic"):
            self.h += 1
            image = "heater"
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"
        elif device.startswith("temperature_fan"):
            self.f += 1
            image = "fan"
            class_name = f"graph_label_fan_{self.f}"
            dev_type = "fan"
        elif self._config.get_main_config().getboolean("only_heaters", False):
            return False
        else:
            self.h += 1
            image = "heat-up"
            lang = self._config.get_main_config().get("language", "en")
            if f"locale_{lang}" in self._printer.config[device]:
                devname = self._printer.config[device][f"locale_{lang}"]
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"

        rgb = self._gtk.get_temp_color(dev_type)

        can_target = self._printer.device_has_target(device)
        self.labels['da'].add_object(device, "temperatures", rgb, False, False)
        if can_target:
            self.labels['da'].add_object(device, "targets", rgb, False, True)
        if self._show_heater_power and self._printer.device_has_power(device):
            self.labels['da'].add_object(device, "powers", rgb, True, False)

        name = self._gtk.Button(image, _(devname), None, self.bts, Gtk.PositionType.LEFT, 1)
        name.connect("clicked", self.toggle_visibility, device)
        name.set_alignment(0, .5)
        name.get_style_context().add_class(class_name)
        visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}", device, fallback=True)
        temp = self._gtk.Button(label="", lines=1)
        if visible:
            name.get_style_context().add_class("graph_label")
        self.labels['da'].set_showing(device, visible)
        if can_target:
            temp.connect("clicked", self.show_numpad, device)
            temp.get_style_context().add_class(f"{class_name}_temp")
        else:
            temp.set_sensitive(False)
            temp.get_style_context().add_class("unused_temp_button")

        self.devices[device] = {
            "class": class_name,
            "name": name,
            "temp": temp,
            "can_target": can_target,
            "visible": visible
        }

        devices = sorted(self.devices)
        pos = devices.index(device) + 1

        self.labels['devices'].insert_row(pos)
        self.labels['devices'].attach(name, 0, pos, 1, 1)
        self.labels['devices'].attach(temp, 1, pos, 1, 1)
        self.labels['devices'].show_all()
        return True

    def toggle_visibility(self, widget, device):
        self.devices[device]['visible'] ^= True
        logging.info(f"Graph show {self.devices[device]['visible']}: {device}")

        section = f"graph {self._screen.connected_printer}"
        if section not in self._config.get_config().sections():
            self._config.get_config().add_section(section)
        self._config.set(section, f"{device}", f"{self.devices[device]['visible']}")
        self._config.save_user_config_options()

        self.update_graph_visibility()

    def change_target_temp(self, temp):
        temp = self.verify_temp(temp)
        if temp is False:
            return
        if self.is_active:
            self.rows_box.add(self.add_tempearture(temp))
            self.rows_box.show_all()
            return
        name = self.active_heater.split()[1] if len(self.active_heater.split()) > 1 else self.active_heater
        if self.active_heater.startswith('extruder'):
            self._screen._ws.klippy.set_tool_temp(self._printer.get_tool_number(self.active_heater), temp)
        elif self.active_heater == "heater_bed":
            self._screen._ws.klippy.set_bed_temp(temp)
        elif self.active_heater.startswith('heater_generic '):
            self._screen._ws.klippy.set_heater_temp(name, temp)
        elif self.active_heater.startswith('temperature_fan '):
            self._screen._ws.klippy.set_temp_fan_temp(name, temp)
        else:
            logging.info(f"Unknown heater: {self.active_heater}")
            self._screen.show_popup_message(_("Unknown Heater") + " " + self.active_heater)
        self._printer.set_dev_stat(self.active_heater, "target", temp)
    
    def verify_temp(self, temp):
        temp = int(temp)
        max_temp = int(float(self._printer.get_config_section(self.active_heater)['max_temp']))
        min_temp = int(float(self._printer.get_config_section(self.active_heater)['min_temp']))
        logging.debug(f"{temp}/{max_temp}")
        if temp > max_temp:
            self._screen.show_popup_message(_("Can't set above the maximum:") + f' {max_temp}')
            return False
        elif temp < min_temp:
            self._screen.show_popup_message(_("Can't set below the minimum:") + f' {min_temp}')
            return False
        elif temp in self.temperatures:
            self._screen.show_popup_message(_("Temperature already exist") + f' {temp}')
            return False
        return max(temp, 0)    
        
    def pid_calibrate(self, widget=None):
        self.temperatures.sort()
        str_temps = re.compile('[\[\]]').sub('', re.sub(' ', '', str(self.temperatures)))
        script = {"script": f"CALIBRATE_HEATER_PID HEATER={self.active_heater} TEMPERATURES={str_temps}"}
        self._screen._confirm_send_action(
            None,
            _("Initiate a PID calibration for") + f" {_(self.active_heater)}{_('а.')} {_('Choosen temps:')} {str_temps} °C" 
            + "\n\n" + _("It may take more than 5 minutes depending on the heater power."),
            "printer.gcode.script",
            script
        )
        self.main_menu.set_sensititve(True)
        self.close_left_pid_panel()
            
    def switch_left_pid_panel(self, temper, is_active):
        self.is_active = is_active
        # Добавлять в scroll контейнер, содержащий rows
        if is_active:
            self.create_left_pid_panel()
        else:
            self.close_left_pid_panel()
        
    
    def create_left_pid_panel(self):
        if self.active_heater == "extruder":
          temps = [215, 235, 240]
        elif self.active_heater == "heater_bed":
          temps = [65, 85, 90, 110]
        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
        for temp in temps:
            row_temp = self.add_tempearture(temp)
            self.rows_box.add(row_temp)
        pid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
        pid_box.add(self.rows_box)

        self.calibrate_button = self._gtk.Button("heat-up", _("Calibrate"), "color3")
        self.calibrate_button.connect("clicked", self.pid_calibrate)
        self.calibrate_button.set_vexpand(False)
        self.calibrate_button.set_hexpand(False)
        
        pid_box.add(self.calibrate_button)
        self.pid_scroll.add(pid_box)
        self.main_menu.remove(self.left_panel)
        self.main_menu.attach(self.pid_scroll, 0, 0, 1, 1)
        self.main_menu.show_all()
        
    def close_left_pid_panel(self):
        self.labels["keypad"].set_active(False)
        self.temperatures = []
        self.is_active = False
        if self.rows_box:
            for child in self.rows_box.get_children():
                self.rows_box.remove(child)
            self.rows_box = None
            self.calibrate_button = None
            for child in self.pid_scroll.get_children():
                self.pid_scroll.remove(child)
            self.main_menu.remove(self.pid_scroll)
        self.main_menu.attach(self.left_panel, 0, 0, 1, 1)
        self.main_menu.show_all()
        
    def add_tempearture(self, temp=0):
        # Здесь в контейнер, содержащий rows надо добавлять (возвращать None)
        label = Gtk.Label(label=_("Temperature") + f"       {temp}")
        self.temperatures.append(temp)
        delete_button = self._gtk.Button("delete", None, None, .66)
        delete_button.set_hexpand(False)
        delete_button.set_vexpand(False)
        # self._gtk.Button(image, _(devname), None, self.bts, Gtk.PositionType.LEFT, 1)
        row_temp = Gtk.Box(spacing = 15)
        row_temp.pack_start(label, False, False, 0)
        row_temp.pack_end(delete_button, False, False, 0)
        delete_button.connect("clicked", self.delete_temperature, row_temp, temp)
        return row_temp
            
    def delete_temperature(self, widget, row, temp):
        if self.rows_box and row in self.rows_box:
            self.temperatures.remove(temp)
            self.rows_box.remove(row)
        self.rows_box.show_all()
            
    def create_left_panel(self):
        self.labels['devices'] = Gtk.Grid()
        self.labels['devices'].get_style_context().add_class('heater-grid')
        self.labels['devices'].set_vexpand(False)

        name = Gtk.Label("")
        temp = Gtk.Label(_("Temp (°C)"))
        temp.get_style_context().add_class("heater-grid-temp")

        self.labels['devices'].attach(name, 0, 0, 1, 1)
        self.labels['devices'].attach(temp, 1, 0, 1, 1)

        self.labels['da'] = HeaterGraph(self._screen, self._printer, self._gtk.font_size)
        #self.labels['da'].set_vexpand(True)

        scroll = self._gtk.ScrolledWindow(steppers=False)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class('heater-list')
        scroll.add(self.labels['devices'])

        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.left_panel.add(scroll)

        for d in self._printer.get_temp_devices():
            self.add_device(d)

        return self.left_panel

    def hide_numpad(self, widget=None):
        self.close_left_pid_panel()
        self.devices[self.active_heater]['temp'].get_style_context().remove_class("button_active")
        self.active_heater = None

        if self._screen.vertical_mode:
            self.main_menu.remove_row(1)
            self.main_menu.attach(self.labels['menu'], 0, 1, 1, 1)
        else:
            self.main_menu.remove_column(1)
            self.main_menu.attach(self.labels['menu'], 1, 0, 1, 1)
        self.main_menu.show_all()
        self.numpad_visible = False
        self._screen.base_panel.set_control_sensitive(False, control='back')

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        for x in self._printer.get_temp_devices():
            if x in data:
                self.update_temp(
                    x,
                    self._printer.get_dev_stat(x, "temperature"),
                    self._printer.get_dev_stat(x, "target"),
                    self._printer.get_dev_stat(x, "power"),
                )
        with contextlib.suppress(KeyError):
          if self.calibrate_button:
            self.calibrate_button.set_sensitive(data['pid_calibrate']['is_calibrating'])
        with contextlib.suppress(Exception):
            if data['virtual_sdcard']['has_interrupted_file'] == True:
                if 'print' in self.labels:
                    logging.info("Has interrupt")
                    if not self.labels['print_interrupt']:
                        print_item = {'icon': None, 'style': None}
                        print_position = 0
                        for i in range(len(self.items)):
                            if list(self.items[i])[0] == 'print':
                                print_item = self.items[i]['print']
                                print_position = i
                                break
                        self.labels['print_interrupt'] = self._gtk.Button(print_item['icon'], _("Print (Interrupt)"), (print_item['style'] if print_item['style'] else f"color{(print_position % 4) + 1}"))
                        self.labels['print_interrupt'].connect("clicked", self._screen.base_panel.show_interrupt_dialog)
                        col = print_position % self.columns
                        row = int(print_position / self.columns)
                        self.labels['menu'].remove(self.labels['print'])
                    self.labels['menu'].attach(self.labels['print_interrupt'], col, row, 2, 1)
            else:
                if 'print' in self.labels:
                    logging.info("Not interrupt")
                    if self.labels['print_interrupt']:
                        self.labels['menu'].remove(self.labels['print_interrupt'])
                        self.labels['print_interrupt'] = None
                    print_item = {'icon': None, 'style': None}
                    print_position = 0
                    for i in range(len(self.items)):
                        if list(self.items[i])[0] == 'print':
                            print_item = self.items[i]['print']
                            print_position = i
                            break
                    col = print_position % self.columns
                    row = int(print_position / self.columns)
                    self.labels['menu'].attach(self.labels['print'], col, row, 2, 1)
            self.labels['menu'].show_all()
        return False

    def show_numpad(self, widget, device):
        if self.active_heater is not None:
            self.devices[self.active_heater]['temp'].get_style_context().remove_class("button_active")
        self.active_heater = device
        self.devices[self.active_heater]['temp'].get_style_context().add_class("button_active")

        if "keypad" not in self.labels:
            self.labels["keypad"] = Keypad(self._screen, self.change_target_temp, self.switch_left_pid_panel, self.hide_numpad)
        can_pid = self._printer.state not in ("printing", "paused") \
            and self._screen.printer.config[self.active_heater]['control'] == 'pid'
        self.labels["keypad"].show_pid(can_pid)
        self.labels["keypad"].clear()

        if self._screen.vertical_mode:
            self.main_menu.remove_row(1)
            self.main_menu.attach(self.labels["keypad"], 0, 1, 1, 1)
        else:
            self.main_menu.remove_column(1)
            self.main_menu.attach(self.labels["keypad"], 1, 0, 1, 1)
        self.main_menu.show_all()
        self.numpad_visible = True
        self._screen.base_panel.set_control_sensitive(True, control='back')


    def update_graph(self):
        self.labels['da'].queue_draw()
        return True

    def back(self):
        if self.numpad_visible:
            self.close_left_pid_panel()
            self.hide_numpad()
            return True
        return False
