import logging
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


def create_panel(*args):
    return InterruptPanel(*args)


class InterruptPanel(ScreenPanel):

    def __init__(self, screen, title):
        super().__init__(screen, title)
        image = self._gtk.Image("klipper", self._gtk.content_width * .2, self._gtk.content_height * .5)
        self.labels['text'] = Gtk.Label(_("Printing was interrupted\n\n"
                                          "Did you want to continue print?"))
        self.labels['text'].set_line_wrap(True)
        self.labels['text'].set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.labels['text'].set_halign(Gtk.Align.CENTER)
        self.labels['text'].set_valign(Gtk.Align.CENTER)

        self.labels['continue'] = self._gtk.Button("refresh", _("Continue Print"), "color1")
        self.labels['continue'].connect("clicked", self.continue_print)
        self.labels['delete'] = self._gtk.Button("refresh", _("Delete Print"), "color2")
        self.labels['delete'].connect("clicked", self.cancel_print)

        self.labels['actions'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.labels['actions'].set_hexpand(True)
        self.labels['actions'].set_vexpand(False)
        self.labels['actions'].set_halign(Gtk.Align.CENTER)
        self.labels['actions'].set_homogeneous(True)
        self.labels['actions'].set_size_request(self._gtk.content_width, -1)

        scroll = self._gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.labels['text'])

        info = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        info.pack_start(image, False, True, 8)
        info.pack_end(scroll, True, True, 8)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main.pack_start(info, True, True, 8)
        main.pack_end(self.labels['actions'], False, False, 0)

        self.show_restart_buttons()

        self.content.add(main)

    def update_text(self, text):
        self.labels['text'].set_label(f"{text}")
        self.show_restart_buttons()

    def clear_action_bar(self):
        for child in self.labels['actions'].get_children():
            self.labels['actions'].remove(child)

    def show_restart_buttons(self):

        self.clear_action_bar()
        if self.ks_printer_cfg is not None and self._screen._ws.connected:
            power_devices = self.ks_printer_cfg.get("power_devices", "")
            if power_devices and self._printer.get_power_devices():
                logging.info(f"Associated power devices: {power_devices}")
                self.add_power_button(power_devices)

        if self._screen.initialized:
            self.labels['actions'].add(self.labels['continue'])
            self.labels['actions'].add(self.labels['delete'])

        if self._screen._ws and not self._screen._ws.connecting or self._screen.reinit_count > self._screen.max_retries:
            self.labels['actions'].add(self.labels['retry'])
        self.labels['actions'].show_all()

    def cancel_print(self, widget):
        self._screen._ws.klippy.print_remove()

    def continue_print(self, widget):
        self._screen._ws.klippy.print_rebuild()
