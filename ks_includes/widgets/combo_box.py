import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GObject, GLib

class KSComboBox(Gtk.Box):
  __gsignals__ = {
        'selected': (GObject.SIGNAL_RUN_LAST, None,
                      (str,))
  }
  def __init__(self, screen, text = ""):
    super().__init__()
    self.button = screen.gtk.Button_with_box("triangle-down", _(text), position = Gtk.PositionType.RIGHT, scale=0.65)
    self.label = self.get_inside_label()
    self.add(self.button)
    self.popover = KSPopover(self, screen)
    self.button.connect("clicked", self.open_popover)

  # Очень неудобное обращение к label у такого Button - такой Button желательно вывести в отдельный класс с наследованием от Button
  def get_inside_label(self):
    for ch in self.button:
      if isinstance(ch, Gtk.Box):
        for c in ch:
          if isinstance(c, Gtk.Label):
            return c

  def open_popover(self, widget):
    self.popover.show_all()
    return Gdk.EVENT_STOP

  def set_active_text(self, text):
    self.label.set_label(_(text))
    self.emit("selected", text)

  def set_active_num(self, num):
    fields = self.popover.get_fields()
    if num >= len(fields):
        logging.error(f"{num} >= {len(fields)} - set_active_num stop")
        return
    self.label.set_label(fields[num])
    self.emit("selected", fields[num])

  def get_text(self):
    return self.label.get_label()

  def remove_all(self):
    self.popover.clear_content()

  def append(self, field):
    self.popover.add_field(field)

  def rename(self, old, new):
    if self.label.get_label() == old:
      self.label.set_label(new)
      self.button.show_all()
    self.popover.rename_field(old, new)

class KSPopover(Gtk.Popover):
  def __init__(self, relative_to: KSComboBox, screen, position = Gtk.PositionType.BOTTOM):
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
  
  def delete_by_name(self, name):
      for i, ch in enumerate(self.content_box):
        if name == ch.get_label():
          self.content_box.remove(ch)
          if self.relative_to.get_text() == name:
            self.relative_to.set_active_num((i + 1) % len(self.content_box))
          break
  
  def rename_field(self, old_name, new_name):
    if old_name == self.relative_to.get_text():
      self.relative_to.label.set_label(new_name)
    for ch in self.content_box:
        if old_name == ch.get_label():
          ch.set_label(new_name)
          break

  def add_field(self, field):
    field_label = Gtk.Button(label = field, hexpand = True, vexpand = True)
    field_label.get_style_context().add_class("hide_button")
    field_label.connect("clicked", self.on_field_select, field)
    self.content_box.add(field_label)

  def get_fields(self):
    return [ch.get_label() for ch in self.content_box]

  def on_field_select(self, btn, field):
    self.relative_to.set_active_text(field)
    self.popdown()
