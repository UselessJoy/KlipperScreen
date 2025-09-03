import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib



class PopupMessage(Gtk.Popover):
  __MESSAGE_STYLE = {1: "message_popup_echo", 2: "message_popup_warning", 3: "message_popup_error",  10: "message_popup_suggestion"}
  def __init__(self, relative_to, position = Gtk.PositionType.BOTTOM, message="", level=3, timeout=5, autoclose=True, width = 0, height = 0, close_cb=None):
    super().__init__()
    self.set_relative_widget(relative_to, position)
    self.timer = None
    self.close_cb = close_cb
    self.next: PopupMessage = None
    self.is_autoclose = autoclose
    self.timeout = timeout
    msg = Gtk.Button(label=f"{message}")
    msg.get_style_context().add_class("message_popup")
    msg.set_hexpand(True)
    msg.set_vexpand(True)
    msg.get_child().set_line_wrap(True)
    msg.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    msg.get_child().set_max_width_chars(40)
    msg.connect("clicked", self.popdown)
    msg.get_style_context().add_class(self.__MESSAGE_STYLE[level])
    self.connect("closed", self.on_close)
    self.get_style_context().add_class("message_popup_popover")
    if width and height:
      self.set_size_request(width, height)
    self.set_halign(Gtk.Align.CENTER)
    self.add(msg)

  def set_relative_widget(self, relative_to, position=Gtk.PositionType.BOTTOM):
    self.set_relative_to(relative_to)
    self.set_position(position)

  def on_close(self, widget):
    if self.timer is not None:
        GLib.source_remove(self.timer)
        self.timer = None
    if self.close_cb:
        self.close_cb(self)

  def popup(self):
    super().popup()
    self.show_all()
    if self.is_autoclose:
      self.timer = GLib.timeout_add_seconds(self.timeout, self.popdown)

  def popdown(self, widget=None):
    super().popdown()
    return False
      
          