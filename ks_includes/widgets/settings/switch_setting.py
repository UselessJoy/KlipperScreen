import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class SwitchSetting(Gtk.Box):
  def __init__(self, name, is_active, update_callback, setting=""):
      super().__init__(hexpand = True, vexpand = False, valign = Gtk.Align.CENTER)
      self.update_callback, self.setting = update_callback, setting
      switch = Gtk.Switch(active=is_active)
      switch.connect("notify::active", self.on_switch_active)
      self.pack_start(Gtk.Label(label=name), False, False, 0)
      self.pack_end(switch, False, False, 0)
  
  def on_switch_active(self, switch, gdata):
      self.update_callback(switch, switch.get_active(), self.setting)