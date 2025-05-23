import logging
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        image = self._gtk.Image("klipper", self._gtk.content_width * .2, self._gtk.content_height * .5)
        self.labels['text'] = Gtk.Label(_("Initializing printer..."))
        self.labels['text'].set_line_wrap(True)
        self.labels['text'].set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.labels['text'].set_halign(Gtk.Align.CENTER)
        self.labels['text'].set_valign(Gtk.Align.CENTER)

        self.labels['menu'] = self._gtk.Button("settings", _("Menu"), "color4")
        self.labels['menu'].connect("clicked", self._screen._go_to_submenu, "")
        # self.labels['restart'] = self._gtk.Button("refresh", _("Klipper Service Restart"), "color1")
        # self.labels['restart'].connect("clicked", self.restart_klipper)
        self.labels['firmware_restart'] = self._gtk.Button("refresh", _("Firmware Restart"), "color2")
        self.labels['firmware_restart'].connect("clicked", self.firmware_restart)
        self.labels['backup_config'] = self._gtk.Button("backup", _("Load backup config"), "color3")
        self.labels['backup_config'].connect("clicked", self.confirm_backup)
        self.labels['retry'] = self._gtk.Button("load", _('Retry'), "color3")
        self.labels['retry'].connect("clicked", self.retry)

        self.labels['actions'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.labels['actions'].set_hexpand(True)
        self.labels['actions'].set_vexpand(False)
        self.labels['actions'].set_halign(Gtk.Align.CENTER)
        self.labels['actions'].set_homogeneous(True)
        self.labels['actions'].set_size_request(self._gtk.content_width - 30, -1)

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
        # self._screen.gtk.Button_busy(self.labels['restart'], False)
        self._screen.gtk.Button_busy(self.labels['firmware_restart'], False)
        self._screen.gtk.Button_busy(self.labels['backup_config'], False)
        self.clear_action_bar()
        if self.ks_printer_cfg is not None and self._screen._ws.connected:
            power_devices = self.ks_printer_cfg.get("power_devices", "")
            if power_devices and self._printer.get_power_devices():
                logging.info(f"Associated power devices: {power_devices}")
                self.add_power_button(power_devices)
        # self.labels['actions'].add(self.labels['restart'])
        self.labels['actions'].add(self.labels['firmware_restart'])
        self.labels['actions'].add(self.labels['backup_config'])
        self.labels['actions'].add(self.labels['menu'])
        if self._screen._ws and not self._screen._ws.connecting or self._screen.reinit_count > self._screen.max_retries:
            self.labels['actions'].add(self.labels['retry'])
        self.labels['actions'].set_sensitive(True)
        self.labels['actions'].show_all()

    def add_power_button(self, powerdevs):
        self.labels['power'] = self._gtk.Button("shutdown", _("Power On Printer"), "color3")
        self.labels['power'].connect("clicked", self._screen.power_devices, powerdevs, True)
        self.check_power_status()
        self.labels['actions'].add(self.labels['power'])

    def activate(self):
        self.check_power_status()

    def check_power_status(self):
        if 'power' in self.labels:
            devices = self._printer.get_power_devices()
            if devices is not None:
                for device in devices:
                    if self._printer.get_power_device_status(device) == "off":
                        self.labels['power'].set_sensitive(True)
                        break
                    elif self._printer.get_power_device_status(device) == "on":
                        self.labels['power'].set_sensitive(False)

    def firmware_restart(self, widget):
        self._screen._ws.klippy.restart_firmware()
        self._screen.gtk.Button_busy(widget, True)
        GLib.timeout_add_seconds(10, lambda: self._screen.gtk.Button_busy(widget, False))

    def restart_klipper(self, widget):
        self._screen._ws.send_method("machine.services.restart", {"service": "klipper"})
        self._screen.gtk.Button_busy(widget, True)
        GLib.timeout_add_seconds(10, lambda: self._screen.gtk.Button_busy(widget, False))

    def confirm_backup(self, widget):
        self._screen._ws.klippy.check_backup(self.on_check_backup)
    
    def on_check_backup(self, result, method, params):
        if "error" in result:
            logging.debug(result["error"])
            return
        self._screen._confirm_send_action(
            self.labels['backup_config'],
            _("Are you sure you want to download the backup?") +"\n\n" + (_("Will be recover to the latest backup") if result['result']['backup'] else _("Backup not found. Will be recover to the base config")),
            "printer.load_backup_config",
        )

    def retry(self, widget):
        if self._screen._ws and not self._screen._ws.connecting:
            self._screen._ws.retry()
        self._screen.reinit_count = 0
        self._screen._init_printer(_("Connecting to %s") % self._screen.connecting_to_printer)
        self.show_restart_buttons()

    def reboot_poweroff_confirm(self, dialog, response_id, method):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            if method == "reboot":
                os.system("systemctl reboot -i")
            else:
                os.system("systemctl poweroff -i")
        elif response_id == Gtk.ResponseType.APPLY:
            if method == "reboot":
                self._screen._ws.send_method("machine.reboot")
            else:
                self._screen._ws.send_method("machine.shutdown")
