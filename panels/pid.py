import logging
import contextlib
import re

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.heatergraph import HeaterGraph
from ks_includes.widgets.keypad import Keypad
from ks_includes.widgets.combo_box import KSComboBox

class Panel(ScreenPanel):
    graph_update = None
    active_heater = None

    def __init__(self, screen, title, extra=None):
        super().__init__(screen, title)
        self.active_heater = "extruder"
        self.temperatures = []
        self.numpad = None
        self.is_calibrating = False
        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
        
        self.add_button = self._gtk.Button("heat-up", _("Add"), "color3")
        self.add_button.connect("clicked", self.show_numpad)
        self.add_button.set_vexpand(False)
        self.add_button.set_hexpand(False)
        
        self.pid_scroll = self._screen.gtk.ScrolledWindow()
        self.pid_scroll.set_min_content_height(self._gtk.content_height * 0.9)
        self.pid_scroll.set_min_content_width(self._gtk.content_width * .3)
        self.pid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        
        pid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
        pid_box.add(self.rows_box)
        
        pid_box.add(self.add_button)
        self.pid_scroll.add(pid_box)
        
        self.update_temp_grid()
        
        self.heater_combo_box = KSComboBox(screen, _("extruder"))
        self.heater_combo_box.set_hexpand(False)
        self.heater_combo_box.append(_("extruder"))
        self.heater_combo_box.append(_("heater_bed"))
        self.heater_combo_box.connect("selected", self.on_heater_changed)
        self.temperatures_grid = self._gtk.HomogeneousGrid()

        self.left_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, valign = Gtk.Align.START)
        self.left_box.add(self.heater_combo_box)
        self.left_box.add(self.pid_scroll)

        self.heater_image = self._gtk.Image('extruder', self._gtk.content_width * .3, self._gtk.content_height * .3)
        self.temp_label = Gtk.Label()
        self.temp_label.get_style_context().add_class("label_chars")
        
        image_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        image_box.add(self.heater_image)
        image_box.add(self.temp_label)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_box.add(image_box)
        self.calibrate_button = self._gtk.Button("heat-up", _("Calibrate"), "color3", hexpand=False, vexpand=False)
        self.calibrate_button.connect("clicked", self.pid_calibrate)
        self.calibrate_button.set_valign(Gtk.Align.END)
        self.right_box.add(self.calibrate_button)

        self.main_box = Gtk.Box(spacing = 15)

        self.main_box.add(self.left_box)
        self.main_box.add(self.right_box)
        self.content.add(self.main_box)

    def on_heater_changed(self, widget, heater):
      self.active_heater, img_name = ('heater_bed', 'bed') if self.active_heater == 'extruder' else ('extruder', 'extruder')
      self._screen.gtk.update_image(self.heater_image, img_name, self._gtk.content_width * .2, self._gtk.content_height * .5)
      self.update_temp_grid()

    def pid_calibrate(self, widget=None):
        self.temperatures.sort()
        str_temps = re.compile('[\[\]]').sub('', re.sub(' ', '', str(self.temperatures)))
        script = {"script": f"CALIBRATE_HEATER_PID HEATER={self.active_heater} TEMPERATURES={str_temps}"}
        self._screen._confirm_send_action(
            None,
            # :D
            _("Initiate a PID calibration for") + f" {_(self.active_heater)}{_('а.')} {_('Choosen temps:')} {str_temps} °C" 
            + "\n\n" + _("It may take more than 5 minutes depending on the heater power."),
            "printer.gcode.script",
            script
        )
        self.close_left_pid_panel()

    def update_temp_grid(self):
        if self.active_heater == "extruder":
          temps = [215, 235]
        elif self.active_heater == "heater_bed":
          temps = [65, 85, 110]
        for child in self.rows_box:
          self.rows_box.remove(child)
        for temp in temps:
            row_temp = self.add_tempearture(temp)
            self.rows_box.add(row_temp)
        self.pid_scroll.show_all()

    def add_tempearture(self, temp=0):
        label = Gtk.Label(label=_("Temperature") + f"       {temp}")
        self.temperatures.append(temp)
        delete_button = self._gtk.Button("delete", None, None, .66)
        delete_button.set_hexpand(False)
        delete_button.set_vexpand(False)
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
    
    def show_numpad(self, widget):
        self.numpad = Keypad(self._screen, self.change_target_temp, self.switch_left_pid_panel, self.hide_numpad)
        self.main_box.remove(self.right_box)
        self.main_box.add(self.numpad)
        self.main_box.show_all()
        self.add_button.set_sensitive(False)

    def hide_numpad(self, widget=None):
        self.main_box.remove(self.numpad)
        self.main_box.add(self.right_box)
        self.main_box.show_all()
        self.add_button.set_sensitive(True)

    def change_target_temp(self, temp):
        self.rows_box.add(self.add_tempearture(temp))
        self.rows_box.show_all()

    def switch_left_pid_panel(self, temper, is_active):
        self.is_active = is_active
        if is_active:
            self.create_left_pid_panel()
        else:
            self.close_left_pid_panel()

    def close_left_pid_panel(self):
        self.labels["keypad"].set_active(False)
        self.temperatures = []
        self.is_active = False
        if self.rows_box:
            for child in self.rows_box.get_children():
                self.rows_box.remove(child)
            self.rows_box = None
            for child in self.pid_scroll.get_children():
                self.pid_scroll.remove(child)

    def process_update(self, action, data):
      if action != "notify_status_update":
          return
      with contextlib.suppress(KeyError):
        self.is_calibrating = data['pid_calibrate']['is_calibrating']
      cur_temp = self._printer.get_dev_stat(self.active_heater, "temperature")
      cur_target = self._printer.get_dev_stat(self.active_heater, "target")
      new_label_text = f"{int(cur_temp):3}"
      if cur_target:
        new_label_text += f"/{int(cur_target)}"
      new_label_text += " °C"
      self.temp_label.set_label(new_label_text)