import logging
import contextlib
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.heatergraph import HeaterGraph
from ks_includes.widgets.keypad import Keypad

class Panel(ScreenPanel):
    graph_update = None
    active_heater = None

    def __init__(self, screen, title, extra=None):
        super().__init__(screen, title)
        self.popover_timeout = None
        self.left_panel = None
        self.is_active = False
        self.rows_box = None
        self.calibrate_button = None
        self.temperatures = []
        self.pid_scroll = self._screen.gtk.ScrolledWindow()
        self.pid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.menu_labels = None
        self.popover_device = None
        self.h = self.f = 0
        self.tempdeltas = ["1", "5", "10", "25"]
        self.tempdelta = self.tempdeltas[-2]
        self.show_preheat = False
        self.preheat_options = self._screen._config.get_preheat_options()
        self.grid = self._gtk.HomogeneousGrid()
        self._gtk.reset_temp_color()
        self.grid.attach(self.create_left_panel(), 0, 0, 1, 1)

        # When printing start in temp_delta mode and only select tools
        selection = []
        if self._printer.state not in ("printing", "paused"):
            self.show_preheat = True
            selection.extend(self._printer.get_temp_devices())
        elif extra:
            selection.append(extra)

        # Select heaters
        for h in selection:
            if h.startswith("temperature_sensor "):
                continue
            name = h.split()[1] if len(h.split()) > 1 else h
            # Support for hiding devices by name
            if name.startswith("_"):
                continue
            if h not in self.active_heaters:
                self.select_heater(None, h)

        if self._screen.vertical_mode:
            self.grid.attach(self.create_right_panel(), 0, 1, 1, 1)
        else:
            self.grid.attach(self.create_right_panel(), 1, 0, 1, 1)

        self.content.add(self.grid)

    def create_right_panel(self):
        cooldown = self._gtk.Button('cool-down', _('Cooldown'), "color4", self.bts, Gtk.PositionType.LEFT, 1)
        adjust = self._gtk.Button('fine-tune', None, "color3", self.bts * 1.4, Gtk.PositionType.LEFT, 1)
        cooldown.connect("clicked", self.set_temperature, "cooldown")
        adjust.connect("clicked", self.switch_preheat_adjust)

        right = self._gtk.HomogeneousGrid()
        right.attach(cooldown, 0, 0, 2, 1)
        right.attach(adjust, 2, 0, 1, 1)
        if self.show_preheat:
            right.attach(self.preheat(), 0, 1, 3, 3)
        else:
            right.attach(self.delta_adjust(), 0, 1, 3, 3)
        return right

    def switch_preheat_adjust(self, widget):
        self.show_preheat ^= True
        if self._screen.vertical_mode:
            self.grid.remove_row(1)
            self.grid.attach(self.create_right_panel(), 0, 1, 1, 1)
        else:
            self.grid.remove_column(1)
            self.grid.attach(self.create_right_panel(), 1, 0, 1, 1)
        self.grid.show_all()

    def preheat(self):
        self.labels["preheat_grid"] = self._gtk.HomogeneousGrid()
        i = 0
        for option in self.preheat_options:
            if option != "cooldown":
                self.labels[option] = self._gtk.Button(label=option, style=f"color{(i % 4) + 1}")
                self.labels[option].connect("clicked", self.set_temperature, option)
                self.labels['preheat_grid'].attach(self.labels[option], (i % 2), int(i / 2), 1, 1)
                i += 1
        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels["preheat_grid"])
        return scroll

    def delta_adjust(self):
        deltagrid = self._gtk.HomogeneousGrid()
        self.labels["increase"] = self._gtk.Button("increase", None, "color1")
        self.labels["increase"].connect("clicked", self.change_target_temp_incremental, "+")
        self.labels["decrease"] = self._gtk.Button("decrease", None, "color3")
        self.labels["decrease"].connect("clicked", self.change_target_temp_incremental, "-")

        tempgrid = Gtk.Grid()
        for j, i in enumerate(self.tempdeltas):
            self.labels[f'deg{i}'] = self._gtk.Button(label=i)
            self.labels[f'deg{i}'].connect("clicked", self.change_temp_delta, i)
            ctx = self.labels[f'deg{i}'].get_style_context()
            if j == 0:
                ctx.add_class("distbutton_top")
            elif j == len(self.tempdeltas) - 1:
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.tempdelta:
                ctx.add_class("distbutton_active")
            tempgrid.attach(self.labels[f'deg{i}'], j, 0, 1, 1)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.pack_start(Gtk.Label(_("Temperature") + " (°C)"), False, False, 8)
        vbox.pack_end(tempgrid, True, True, 2)

        vsize = 2 if self._screen.vertical_mode else 3
        deltagrid.attach(self.labels["decrease"], 0, 0, 1, vsize)
        deltagrid.attach(self.labels["increase"], 1, 0, 1, vsize)
        deltagrid.attach(vbox, 0, vsize, 2, 2)
        return deltagrid

    def change_temp_delta(self, widget, tempdelta):
        logging.info(f"### tempdelta {tempdelta}")
        self.labels[f"deg{self.tempdelta}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"deg{tempdelta}"].get_style_context().add_class("distbutton_active")
        self.tempdelta = tempdelta

    def change_target_temp_incremental(self, widget, direction):

        if len(self.active_heaters) == 0:
            self._screen.show_popup_message(_("Nothing selected"))
        else:
            for heater in self.active_heaters:
                target = self._printer.get_dev_stat(heater, "target")
                name = heater.split()[1] if len(heater.split()) > 1 else heater
                if direction == "+":
                    target += int(self.tempdelta)
                    max_temp = int(float(self._printer.get_config_section(heater)['max_temp']))
                    if target > max_temp:
                        target = max_temp
                        self._screen.show_popup_message(_("Can't set above the maximum:") + f' {target}')

                else:
                    target -= int(self.tempdelta)
                    target = max(target, 0)
                if heater.startswith('extruder'):
                    self._screen._ws.klippy.set_tool_temp(self._printer.get_tool_number(heater), target)
                elif heater.startswith('heater_bed'):
                    self._screen._ws.klippy.set_bed_temp(target)
                elif heater.startswith('heater_generic '):
                    self._screen._ws.klippy.set_heater_temp(name, target)
                elif heater.startswith("temperature_fan "):
                    self._screen._ws.klippy.set_temp_fan_temp(name, target)
                else:
                    logging.info(f"Unknown heater: {heater}")
                    self._screen.show_popup_message(_("Unknown Heater") + " " + heater)
                self._printer.set_dev_stat(heater, "target", int(target))
                logging.info(f"Setting {heater} to {target}")

    def update_graph_visibility(self):
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

    def select_heater(self, widget, device):
        if self.active_heater is None and device in self.devices and self.devices[device]["can_target"]:
            if device in self.active_heaters:
                self.active_heaters.remove(device)
                self.devices[device]['name'].get_style_context().remove_class("button_active")
                self.devices[device]['select'].set_label(_("Select"))
                logging.info(f"Deselecting {device}")
                return
            else:
                self.active_heaters.append(device)
            self.devices[device]['name'].get_style_context().add_class("button_active")
            self.devices[device]['select'].set_label(_("Deselect"))
            logging.info(f"Selecting {device}")
        return

    def set_temperature(self, widget, setting):
        if len(self.active_heaters) == 0:
            self._screen.show_popup_message(_("Nothing selected"))
        else:
            for heater in self.active_heaters:
                target = None
                max_temp = float(self._printer.get_config_section(heater)['max_temp'])
                name = heater.split()[1] if len(heater.split()) > 1 else heater
                with contextlib.suppress(KeyError):
                    for i in self.preheat_options[setting]:
                        logging.info(f"{self.preheat_options[setting]}")
                        if i == name:
                            # Assign the specific target if available
                            target = self.preheat_options[setting][name]
                            logging.info(f"name match {name}")
                        elif i == heater:
                            target = self.preheat_options[setting][heater]
                            logging.info(f"heater match {heater}")
                if target is None and setting == "cooldown" and not heater.startswith('temperature_fan '):
                    target = 0
                if heater.startswith('extruder'):
                    if self.validate(heater, target, max_temp):
                        self._screen._ws.klippy.set_tool_temp(self._printer.get_tool_number(heater), target)
                elif heater.startswith('heater_bed'):
                    if target is None:
                        with contextlib.suppress(KeyError):
                            target = self.preheat_options[setting]["bed"]
                    if self.validate(heater, target, max_temp):
                        self._screen._ws.klippy.set_bed_temp(target)
                elif heater.startswith('heater_generic '):
                    if target is None:
                        with contextlib.suppress(KeyError):
                            target = self.preheat_options[setting]["heater_generic"]
                    if self.validate(heater, target, max_temp):
                        self._screen._ws.klippy.set_heater_temp(name, target)
                elif heater.startswith('temperature_fan '):
                    if target is None:
                        with contextlib.suppress(KeyError):
                            target = self.preheat_options[setting]["temperature_fan"]
                    if self.validate(heater, target, max_temp):
                        self._screen._ws.klippy.set_temp_fan_temp(name, target)
            # This small delay is needed to properly update the target if the user configured something above
            # and then changed the target again using preheat gcode
            GLib.timeout_add(250, self.preheat_gcode, setting)

    def validate(self, heater, target=None, max_temp=None):
        if target is not None and max_temp is not None:
            if 0 <= target <= max_temp:
                self._printer.set_dev_stat(heater, "target", target)
                return True
            elif target > max_temp:
                self._screen.show_popup_message(_("Can't set above the maximum:") + f' {max_temp}')
                return False
        logging.debug(f"Invalid {heater} Target:{target}/{max_temp}")
        return False

    def preheat_gcode(self, setting):
        with contextlib.suppress(KeyError):
            self._screen._ws.klippy.gcode_script(self.preheat_options[setting]['gcode'])
        return False

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
            if "locale" in self._printer.config[device]:
                devname = self._printer.config[device]['locale']
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"

        rgb = self._gtk.get_temp_color(dev_type)

        name = self._gtk.Button(image, _(devname), None, self.bts, Gtk.PositionType.LEFT, 1)
        name.set_alignment(0, .5)
        name.get_style_context().add_class(class_name)
        visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}", device, fallback=True)
        temp = self._gtk.Button(label="", lines=1)
        if visible:
            name.get_style_context().add_class("graph_label")

        can_target = self._printer.device_has_target(device)
        self.labels['da'].add_object(device, "temperatures", rgb, False, False)
        if can_target:
            self.labels['da'].add_object(device, "targets", rgb, False, True)
            name.connect('button-press-event', self.name_pressed, device)
            name.connect('button-release-event', self.name_released, device)
        else:
            name.connect("clicked", self.toggle_visibility, device)
        if self._show_heater_power and self._printer.device_has_power(device):
            self.labels['da'].add_object(device, "powers", rgb, True, False)
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

        if self.devices[device]["can_target"]:
            self.devices[device]['select'] = self._gtk.Button(label=_("Select"))
            self.devices[device]['select'].connect('clicked', self.select_heater, device)

        devices = sorted(self.devices)
        pos = devices.index(device) + 1

        self.labels['devices'].insert_row(pos)
        self.labels['devices'].attach(name, 0, pos, 1, 1)
        self.labels['devices'].attach(temp, 1, pos, 1, 1)
        self.labels['devices'].show_all()
        return True

    def name_pressed(self, widget, event, device):
        self.popover_timeout = GLib.timeout_add(300, self.popover_popup, widget, device)

    def name_released(self, widget, event, device):
        if self.popover_timeout is not None:
            GLib.source_remove(self.popover_timeout)
            self.popover_timeout = None
        if not self.popover_device:
            self.select_heater(None, device)

    def toggle_visibility(self, widget, device=None):
        if device is None:
            device = self.popover_device
        self.devices[device]['visible'] ^= True
        logging.info(f"Graph show {self.devices[device]['visible']}: {device}")

        section = f"graph {self._screen.connected_printer}"
        if section not in self._config.get_config().sections():
            self._config.get_config().add_section(section)
        self._config.set(section, f"{device}", f"{self.devices[device]['visible']}")
        self._config.save_user_config_options()

        self.update_graph_visibility()
        if self.devices[device]['can_target']:
            self.popover_populate_menu()
            self.labels['popover'].show_all()

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
        self.grid.set_sensititve(True)
        self.close_left_pid_panel()
        
    def switch_left_pid_panel(self, temper, is_active):
        self.is_active = is_active
        # Добавлять в scroll контейнер, содержащий rows
        if is_active:
            self.create_left_pid_panel()
        else:
            self.close_left_pid_panel()
    
    def create_left_pid_panel(self):
        temps = [215, 235, 240]
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
        self.grid.remove(self.left_panel)
        self.grid.attach(self.pid_scroll, 0, 0, 1, 1)
        self.grid.show_all()
        
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
            self.grid.remove(self.pid_scroll)
        self.grid.attach(self.left_panel, 0, 0, 1, 1)
        self.grid.show_all()
        
    def add_tempearture(self, temp=0):
        # Здесь в контейнер, содержащий rows надо добавлять (возвращать None)
        label = Gtk.Label(label=_("Temperature") + f"       {temp}")
        self.temperatures.append(temp)
        delete_button = self._gtk.Button("delete", None, None, .66)
        delete_button.set_hexpand(False)
        delete_button.set_vexpand(False)
        # self._gtk.Button(image, _(devname), None, self.bts, Gtk.PositionType.LEFT, 1)
        row_temp = Gtk.Box(spacing = 5)
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
        self.labels['da'].set_vexpand(True)

        scroll = self._gtk.ScrolledWindow(steppers=False)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class('heater-list')
        scroll.add(self.labels['devices'])

        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.left_panel.add(scroll)

        self.labels['graph_settemp'] = self._gtk.Button(label=_("Set Temp"))
        self.labels['graph_settemp'].connect("clicked", self.show_numpad)
        self.labels['graph_hide'] = self._gtk.Button(label=_("Hide"))
        self.labels['graph_hide'].connect("clicked", self.toggle_visibility)
        self.labels['graph_show'] = self._gtk.Button(label=_("Show"))
        self.labels['graph_show'].connect("clicked", self.toggle_visibility)

        popover = Gtk.Popover()
        self.labels['popover_vbox'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popover.add(self.labels['popover_vbox'])
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.connect('closed', self.popover_closed)
        self.labels['popover'] = popover

        for d in self._printer.get_temp_devices():
            self.add_device(d)

        return self.left_panel

    def popover_closed(self, widget):
        self.popover_device = None

    def popover_popup(self, widget, device):
        self.popover_device = device
        po = self.labels['popover']
        po.set_relative_to(widget)
        self.popover_populate_menu()
        po.show_all()

    def popover_populate_menu(self):
        pobox = self.labels['popover_vbox']
        for child in pobox.get_children():
            pobox.remove(child)

        if self.labels['da'].is_showing(self.popover_device):
            pobox.pack_start(self.labels['graph_hide'], True, True, 5)
        else:
            pobox.pack_start(self.labels['graph_show'], True, True, 5)
        if self.devices[self.popover_device]["can_target"]:
            pobox.pack_start(self.labels['graph_settemp'], True, True, 5)
            pobox.pack_end(self.devices[self.popover_device]['select'], True, True, 5)

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        with contextlib.suppress(KeyError):
          if self.calibrate_button:
            self.calibrate_button.set_sensitive(data['pid_calibrate']['is_calibrating'])
        for x in self._printer.get_temp_devices():
            if x in data:
                self.update_temp(
                    x,
                    self._printer.get_dev_stat(x, "temperature"),
                    self._printer.get_dev_stat(x, "target"),
                    self._printer.get_dev_stat(x, "power"),
                )

    def show_numpad(self, widget, device=None):
        for d in self.active_heaters:
            self.devices[d]['temp'].get_style_context().remove_class("button_active")
            self.devices[d]['name'].get_style_context().remove_class("button_active")
        if self.active_heater:
            self.devices[self.active_heater]['temp'].get_style_context().remove_class("button_active")
        self.active_heater = self.popover_device if device is None else device
        self.devices[self.active_heater]['temp'].get_style_context().add_class("button_active")

        if "keypad" not in self.labels:
            self.labels["keypad"] = Keypad(self._screen, self.change_target_temp, self.switch_left_pid_panel, self.hide_numpad)
        can_pid = self._printer.state not in ("printing", "paused") \
            and self._screen.printer.config[self.active_heater]['control'] == 'pid'
        self.labels["keypad"].show_pid(can_pid)
        self.labels["keypad"].clear()

        if self._screen.vertical_mode:
            self.grid.remove_row(1)
            self.grid.attach(self.labels["keypad"], 0, 1, 1, 1)
        else:
            self.grid.remove_column(1)
            self.grid.attach(self.labels["keypad"], 1, 0, 1, 1)
        self.grid.show_all()

        self.labels['popover'].popdown()
    
    def hide_numpad(self, widget=None):
        self.close_left_pid_panel()
        for d in self.active_heaters:
            self.devices[d]['name'].get_style_context().add_class("button_active")
        self.devices[self.active_heater]['temp'].get_style_context().remove_class("button_active")
        self.active_heater = None

        if self._screen.vertical_mode:
            self.grid.remove_row(1)
            self.grid.attach(self.create_right_panel(), 0, 1, 1, 1)
        else:
            self.grid.remove_column(1)
            self.grid.attach(self.create_right_panel(), 1, 0, 1, 1)
        self.grid.show_all()

    def update_graph(self):
        self.labels['da'].queue_draw()
        return True
