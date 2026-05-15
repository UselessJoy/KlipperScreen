import logging
import gi
import subprocess
from ks_includes.widgets.combo_box import KSComboBox
from datetime import datetime
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class Timepicker(Gtk.Box):
    def __init__(self, screen):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._screen = screen
        now = datetime.now()
        self.cur_hours = int(f'{now:%H}')
        self.cur_minutes = int(f'{now:%M}')
        adjustmentH = Gtk.Adjustment(upper=23, step_increment=1, page_increment=1)
        adjustmentM = Gtk.Adjustment(upper=59, step_increment=1, page_increment=1)
        self.spin_hours = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_hours.connect("value-changed", self.on_change_hour)
        self.spin_hours.set_size_request(screen.width * 0.2, 0)
        self.spin_hours.set_adjustment(adjustmentH)
        self.spin_hours.set_numeric(True)
        self.spin_hours.set_value(self.cur_hours)
        self.spin_minutes = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_minutes.connect("value-changed", self.on_change_minute)
        self.spin_minutes.set_size_request(screen.width * 0.2, 0)
        self.spin_minutes.set_adjustment(adjustmentM)
        self.spin_minutes.set_numeric(True)
        self.spin_minutes.set_value(self.cur_minutes)

        switchbox = Gtk.Box()
        switchbox.set_hexpand(True)
        switchbox.set_vexpand(True)
        switchbox.set_valign(Gtk.Align.END)
        switchbox.set_halign(Gtk.Align.START)
        self.switch_button_ntp = Gtk.Switch()
        self.switch_button_ntp.connect("notify::active", self.on_change_switch)

        switchbox.pack_start(Gtk.Label(label=_("Synchronize time")), False, False, 5)
        switchbox.pack_end(self.switch_button_ntp, False, False, 5)

        list_timezones = subprocess.check_output("timedatectl list-timezones", universal_newlines=True, shell=True).split('\n')
        self.cur_timezone = subprocess.check_output("timedatectl status | grep -i 'Time zone:' | awk '{print $3}'", universal_newlines=True, shell=True)
        self.cur_region, cur_sep, self.cur_city = self.cur_timezone.partition('/')
        self.cur_city = self.cur_city.rstrip('\n')
        regions_combo_box = KSComboBox(self._screen, _(self.cur_region))
        cities_combo_box = KSComboBox(self._screen, _(self.cur_city))
        if not self.cur_city:
          cities_combo_box.set_sensitive(False)
        self.timezones = {} 
        self.regions = self.cities = {}
        for timezone in list_timezones:
          region, sep, city = timezone.partition('/')
          if region not in self.timezones and region:
            self.timezones[region] = []
            regions_combo_box.append(_(region))
            self.regions[_(region)] = region
          if region:
            self.timezones[region].append(_(city))
            self.cities[_(city)] = city
          if region == self.cur_region:
            cities_combo_box.append(_(city))
        regions_combo_box.connect("selected", self.on_region_changed, cities_combo_box)
        cities_combo_box.connect("selected", self.on_city_changed, regions_combo_box)
        
        timezoneBox = Gtk.Box()
        timezoneBox.set_size_request(50, 50)
        timezoneBox.add(regions_combo_box)
        timezoneBox.add(cities_combo_box)
        grid = Gtk.Grid()
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", "systemd-timesyncd.service"],
                timeout=2
            )
            self.is_timesync = (result.returncode == 0)
        except subprocess.TimeoutExpired:
            self.is_timesync = False
        except FileNotFoundError:
            self.is_timesync = False

        self.switch_button_ntp.set_active(self.is_timesync)
        self.spin_minutes.set_sensitive(not self.switch_button_ntp.get_active())
        self.spin_hours.set_sensitive(not self.switch_button_ntp.get_active())
        label = {
            'title': Gtk.Label(label=_("Set new time")),
            'separator': Gtk.Label(label=":")}
        grid.attach(label['title'], 0, 0, 3, 1)
        grid.attach(self.spin_hours, 0, 1, 1, 1)
        grid.attach(label['separator'], 1, 1, 1, 1)
        grid.attach(self.spin_minutes, 2, 1, 1, 1)
        
        self.pack_start(grid, True, True, 5)
        self.pack_start(timezoneBox, True, True, 5)
        self.pack_end(switchbox, True, True, 5)
        
    def on_region_changed(self, widget, region, cities_combo_box):
      cities_combo_box.remove_all()
      self.cur_region = self.regions[region]
      for city in self.timezones[self.cur_region]:
        cities_combo_box.append(_(city))
      if self.cur_city and self.cur_city in self.timezones[self.cur_region]:
        cities_combo_box.set_active_text(self.cur_city)
      else:
        cities_combo_box.set_active_num(0)
      cities_combo_box.set_sensitive(True)

    def on_city_changed(self, widget, city, combo_regions):
      self.cur_city = self.cities[city]
      if self.cur_region == "UTC":
        self.cur_timezone = self.cur_region
      else:
        self.cur_timezone = f"{self.cur_region}/{self.cur_city}"

    def on_change_hour(self, spinbutton, gdata):
        self.cur_hours = int(spinbutton.get_value())

    def on_change_minute(self, spinbutton, gdata):
        self.cur_minutes = int(spinbutton.get_value())
        
    def on_change_switch(self, switch, gdata):
        self.is_timesync = switch.get_active()
        if self.is_timesync:
            self.spin_minutes.set_sensitive(not self.is_timesync)
            self.spin_hours.set_sensitive(not self.is_timesync)
        else:
            self.spin_minutes.set_sensitive(not self.is_timesync)
            self.spin_hours.set_sensitive(not self.is_timesync)
