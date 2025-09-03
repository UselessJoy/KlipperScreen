import gi
from ks_includes.widgets.combo_box import KSComboBox
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class ComboBoxSetting(Gtk.Box):
  def __init__(self, name, screen, values=[], current_value = "", update_callback = None, setting=""):
    super().__init__()
    self.set_halign(Gtk.Align.FILL)
    self.combo_box = KSComboBox(screen, current_value)
    self.combo_box.button.get_style_context().add_class('color3')
    for val in values:
      self.combo_box.append(val)
    self.combo_box.set_hexpand(True)
    self.combo_box.set_halign(Gtk.Align.END)
    self.combo_box.connect("selected", update_callback, setting)
    label = Gtk.Label(label=name, hexpand=True, halign=Gtk.Align.START)
    self.pack_start(label, True, True, 0)
    self.pack_end(self.combo_box, False, True, 0)
