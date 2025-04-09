import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Services")
        super().__init__(screen, title)
        image = self._gtk.Image("qr_bot", self._gtk.content_width * .95, self._gtk.content_height * .95)
        box = Gtk.Box(vexpand=True, hexpand=True, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        box.add(image)
        self.content.add(box)