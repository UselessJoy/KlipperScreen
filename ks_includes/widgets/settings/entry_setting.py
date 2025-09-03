import gi
from ks_includes.widgets.keyboard import Keyboard
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.widgets.typed_entry import TypedEntry, BaseRule

class EntrySetting(Gtk.Box):
    def __init__(self, label, text="", entry_rule=BaseRule, update_callback=None, setting="", size_x = 200, size_y = 35, screen=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.screen = screen
        self.update_callback = update_callback
        self.setting = setting
        label_widget = Gtk.Label(label=_(label), hexpand=True, halign=Gtk.Align.START)
        self.entry = TypedEntry(entry_rule, self.on_change_entry, text=text, hexpand=True)
        self.entry.set_size_request(size_x, size_y)
        self.entry.set_halign(Gtk.Align.END)
        self.pack_start(label_widget, True, True, 0)
        self.pack_end(self.entry, False, True, 0)

    def on_change_entry(self, entry):
        if not self.update_callback:
            return
        self.update_callback(entry, entry.get_text(), self.setting)