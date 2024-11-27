import gi
import subprocess
from datetime import datetime
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class Timepicker(Gtk.Box):
    def __init__(self, screen, change_value_cb, change_switch_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._screen = screen
        self.change_value_cb = change_value_cb
        self.change_switch_cb = change_switch_cb
        now = datetime.now()
        hours = int(f'{now:%H}')
        minutes = int(f'{now:%M}')
        adjustmentH = Gtk.Adjustment(upper=23, step_increment=1, page_increment=1)
        adjustmentM = Gtk.Adjustment(upper=59, step_increment=1, page_increment=1)
        self.spin_hours = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_hours.connect("value-changed", self.on_change_value, 'hours')
        self.spin_hours.set_size_request(screen.width / 5, screen.height / 4)
        self.spin_hours.set_adjustment(adjustmentH)
        self.spin_hours.set_numeric(True)
        self.spin_hours.set_value(hours)
        self.spin_minutes = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_minutes.connect("value-changed", self.on_change_value, 'minutes')
        self.spin_minutes.set_size_request(screen.width / 5, screen.height / 4)
        self.spin_minutes.set_adjustment(adjustmentM)
        self.spin_minutes.set_numeric(True)
        self.spin_minutes.set_value(minutes)
        
        
        switchbox = Gtk.Box()
        switchbox.set_hexpand(True)
        switchbox.set_vexpand(True)
        switchbox.set_valign(Gtk.Align.END)
        switchbox.set_halign(Gtk.Align.START)
        self.switch_button_ntp = Gtk.Switch()
        self.switch_button_ntp.connect("notify::active", self.on_change_switch)
    
        switchbox.pack_start(Gtk.Label(label=_("Synchronize time")), False, False, 5)
        switchbox.pack_end(self.switch_button_ntp, False, False, 5)

        grid = Gtk.Grid()
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "systemd-timesyncd.service"])
        self.switch_button_ntp.set_active(True if stat == 0 else False)
        self.spin_minutes.set_sensitive(not self.switch_button_ntp.get_active())
        self.spin_hours.set_sensitive(not self.switch_button_ntp.get_active())
        label = {
            'title': Gtk.Label(label=_("Set new time")),
            'separator': Gtk.Label(label=":")}
        grid.attach(label['title'], 0, 0, 3, 1)
        grid.attach(self.spin_hours, 0, 1, 1, 1)
        grid.attach(label['separator'], 1, 1, 1, 1)
        grid.attach(self.spin_minutes, 2, 1, 1, 1)
        
        self.pack_start(grid, True, True, 15)
        self.pack_end(switchbox, True, True, 15)
        
        
        
    def on_change_value(self, spinbutton, name):
        value = int(spinbutton.get_value())
        self.change_value_cb(name, value)
        
    def  on_change_switch(self, switch, gdata):
        switch_status = switch.get_active()
        if switch_status:
            self.spin_minutes.set_sensitive(not switch_status)
            self.spin_hours.set_sensitive(not switch_status)
        else:
            self.spin_minutes.set_sensitive(not switch_status)
            self.spin_hours.set_sensitive(not switch_status)
        self.change_switch_cb(switch_status)
