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
        self.pid_scroll.set_min_content_height(self._gtk.content_height * 0.65)
        self.pid_scroll.set_min_content_width(self._gtk.content_width * .3)
        self.pid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        pid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
        pid_box.add(self.rows_box)
        
        pid_box.add(self.add_button)
        self.pid_scroll.add(pid_box)
        
        self.update_temp_grid()
        
        self.heater_box = self._gtk.HomogeneousGrid()
        
        
        h_buttons = [
          self._gtk.Button(None, _("extruder"), "active-disabled"),
          self._gtk.Button(None, _("heater_bed"), "active-disabled")
        ]
        for btn in h_buttons:
          btn.set_size_request(1, 50)
        h_buttons[0].set_sensitive(False)
        h_buttons[0].connect("clicked", self.on_heater_changed, "extruder", h_buttons[1])
        h_buttons[1].connect("clicked", self.on_heater_changed, "heater_bed", h_buttons[0])
        for btn in h_buttons:
          self.heater_box.add(btn)
        self.temperatures_grid = self._gtk.HomogeneousGrid()

        self.left_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, valign = Gtk.Align.START)
        self.left_box.add(self.heater_box)
        self.left_box.add(self.pid_scroll)

        self.heater_image = self._gtk.Image('extruder', self._gtk.content_width * .3, self._gtk.content_height * .3)
        # self.heater_image.set_margin_bottom(10)
        self.temp_label = Gtk.Label(label="--- °C")
        self.temp_label.get_style_context().add_class("label_chars")
        self.temp_label.set_size_request(-1, 35)
        
        temp_label_align = Gtk.Alignment.new(0.5, 0.5, 0, 0)
        temp_label_align.add(self.temp_label)
        
        image_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        image_box.pack_start(self.heater_image, False, False, 0)
        image_box.pack_start(temp_label_align, False, False, 0)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.right_box.add(image_box)
        self.calibrate_button = self._gtk.Button(None, _("Calibrate"), "color4")
        self.calibrate_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        self.calibrate_button.set_valign(Gtk.Align.END)
        self.calibrate_button.set_halign(Gtk.Align.END)
        self.calibrate_button.connect("clicked", self.pid_calibrate)

        self.main_box = Gtk.Box(spacing = 15)

        self.main_box.add(self.left_box)
        self.main_box.add(self.right_box)
        cb = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        cb.add(self.main_box)
        cb.add(self.calibrate_button)
        self.content.add(cb)

    def on_heater_changed(self, widget, heater, neighbour):
      self.temperatures = []
      widget.set_sensitive(False)
      neighbour.set_sensitive(True)
      self.active_heater, img_name = ('heater_bed', 'bed') if self.active_heater == 'extruder' else ('extruder', 'extruder')
      self._screen.gtk.update_image(self.heater_image, img_name, self._gtk.content_width * .2, self._gtk.content_height * .4)
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
        temps = self._config.get_default_heater_preheats(self.active_heater)
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
      temp_text = f"{int(cur_temp):3}" if cur_temp else "---"
      if cur_target:
          temp_text += f"/{int(cur_target)}"
      self.temp_label.set_label(temp_text + " °C")