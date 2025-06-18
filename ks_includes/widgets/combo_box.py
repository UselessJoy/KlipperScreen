import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GObject

class KSComboBox(Gtk.Box):
  __gsignals__ = {
        'selected': (GObject.SIGNAL_RUN_LAST, None,
                      (str,))
  }
  def __init__(self, screen, text = ""):
    super().__init__()
    self.button = screen.gtk.Button("triangle-down", _(text), position = Gtk.PositionType.RIGHT, scale=0.65)
    self.add(self.button)
    self.popover = KSPopover(self, screen)
    self.button.connect("clicked", self.open_popover)

  def open_popover(self, widget):
    self.popover.show_all()
    return Gdk.EVENT_STOP

  def set_active_text(self, text):
    self.button.set_label(_(text))
    self.emit("selected", text)

  def set_active_num(self, num):
    fields = self.popover.get_fields()
    for i, child in enumerate(fields):
      if num == i:  
        self.button.set_label(_(fields[i]))
        self.emit("selected", fields[i])
        break
    
  def get_text(self):
    return self.button.get_label()

  def remove_all(self):
    self.popover.clear_content()

  def append(self, field):
    self.popover.add_field(field)

class KSPopover(Gtk.Popover):
  def __init__(self, relative_to, screen, position = Gtk.PositionType.BOTTOM):
    super().__init__()
    self.get_style_context().add_class("popup")
    self.set_relative_to(relative_to)
    self.set_position(position)
    self.relative_to = relative_to
    scroll = screen.gtk.ScrolledWindow()
    scroll.set_hexpand(True)
    scroll.set_min_content_height(screen.gtk.content_height * 0.3)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
    self.content_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, spacing = 6)
    scroll.add(self.content_box)
    self.add(scroll)

  def clear_content(self):
    for ch in self.content_box:
      self.content_box.remove(ch)

  def add_field(self, field):
    field_label = Gtk.Button(label = _(field), hexpand = True, vexpand = True)
    field_label.get_style_context().add_class("hide_button")
    field_label.connect("clicked", self.on_field_select, field)
    self.content_box.add(field_label)

  def get_fields(self):
    return [ch.get_label() for ch in self.content_box]

  def on_field_select(self, btn, field):
    self.relative_to.set_active_text(field)
    self.popdown()
