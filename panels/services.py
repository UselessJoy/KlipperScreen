import logging
import gi
import os
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Services")
        super().__init__(screen, title)
        self.labels = {}
        self.update_status = None
        self.service_row = {}
        self.buttons = {}
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.content.add(self.scroll)

    def get_services(self):
        info = self._screen.apiclient.send_request("machine/system_info")
        if not info:
          return
        system_info = {}
        if info and 'result' in info and 'system_info' in info['result']:
          system_info = info['result']['system_info']
        service_state = system_info["service_state"]
        available_services: list[str] = system_info["available_services"]
        try:
           available_services.remove('klipper-mcu')
        except:
           pass
        return [{"name": name, "state": service_state[name] or None} for name in available_services]

    def activate(self):
      services = self.get_services()
      if not services:
        self.create_moonraker_shutdown_menu()
        return
      service_grid = Gtk.Grid()
      for i,service in enumerate(services):
        label_name = Gtk.Label(hexpand=True, halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END)
        label_name.set_markup(f"<b>{service['name']}</b>")
        label_name.get_style_context().add_class("updater-item")

        buttons = {
          'start': [self._gtk.Button("load", _("Start service"), "color4", scale=self.bts, hexpand=False, vexpand=False), self.service_method],
          'restart': [self._gtk.Button("refresh", _("Restart service"), "color3",scale=self.bts, hexpand=False, vexpand=False), self.service_method],
          'stop': [self._gtk.Button("stop", _("Stop service"), "color4", scale=self.bts, hexpand=False, vexpand=False), self.service_method]
        }

        for btn in buttons:
          buttons[btn][0].set_no_show_all(True)
          buttons[btn][0].set_halign(Gtk.Align.END)
          buttons[btn][0].connect("clicked", buttons[btn][1], btn, service['name'])

        button_box = Gtk.Box(spacing = 5, halign = Gtk.Align.END)
        
        for b in buttons:
          buttons[b][0].set_size_request(self._screen.width * 0.33, 1)
          button_box.add(buttons[b][0])
        service_grid.attach(label_name, 1, i, 1, 1)
        service_grid.attach(button_box, 2, i, 1, 1)
        self.service_row[service['name']] = {
           'button_box': button_box
        }
        for button_name in buttons:
            self.service_row[service['name']][button_name] = buttons[button_name][0]
        self.show_buttons_for_state(service['state']['active_state'] == 'active', service['name'])
      self.scroll.add(service_grid)
      self.scroll.show_all()

    def create_moonraker_shutdown_menu(self):
      moonraker_box = Gtk.Box(hexpand = True, vexpand = False, valign = Gtk.Align.CENTER)
      self.restart_button = self._gtk.Button("load", _("Start service"), "color4", scale=self.bts)
      self.restart_button.set_size_request(self._screen.width * 0.33, 1)
      self.restart_button.connect("clicked", self.start_moonraker)
      self.restart_button.set_halign(Gtk.Align.END)
      lbl = Gtk.Label(hexpand=True)
      lbl.set_markup("<b>Moonraker</b>")
      moonraker_box.pack_start(lbl, False, False, 0)
      moonraker_box.pack_end(self.restart_button, False, False, 0)
      shutdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 10)
      shutdown_box.add(Gtk.Label(label=_("Moonraker shutdown. Please, reboot moonraker"), hexpand=True, halign=Gtk.Align.CENTER))
      shutdown_box.add(moonraker_box)
      self.scroll.add(shutdown_box)
      self.scroll.show_all()

    def start_moonraker(self, widget):
      os.system(f"echo {self._screen.get_pwd()} | sudo --stdin systemctl restart moonraker")
      GLib.timeout_add_seconds(10, self.check_moonraker_status)
      self._gtk.Button_busy(self.restart_button, True)

    def check_moonraker_status(self):
      error = os.system('systemctl is-active --quiet moonraker')
      if error:
        self._screen.show_popup_message(_("Moonraker load error"), 3, True)
        self._gtk.Button_busy(self.restart_button, False)

    def service_method(self, widget, method: str, service: str):
      method_message = f"{method.capitalize()} service"
      self._screen._confirm_send_action(
          widget,
          f'{_("Are you sure?")}\n\n' f'{_(method_message)}: {service}',
          f"machine.services.{method}",
          {"service": service},
          callback=self.on_callback_service)

    def on_callback_service(self, result: dict, method: str, params: dict):
        if result == Gtk.ResponseType.CANCEL:
            return
        method = method.split('.')[2]
        self._gtk.Button_busy(self.service_row[params['service']][method], True)
        GLib.timeout_add_seconds(5, self.refresh_service_status, params['service'], method)
    
    def refresh_service_status(self, service, method):
        self._gtk.Button_busy(self.service_row[service][method], False)
        has_error = os.system(f"systemctl is-active --quiet {service}")
        if has_error:
           self._screen.show_popup_message(_("Error on launch %s") % service if method != 'stop' else _("Error on stop %s") % service)
        self.show_buttons_for_state(not has_error, service)
        return False

    def show_buttons_for_state(self, is_active, service):
      if is_active:
          self.service_row[service]['start'].hide()
          self.service_row[service]['restart'].show()
          if service not in ['KlipperScreen', 'mooonraker']:
            self.service_row[service]['stop'].show()
      else:
          self.service_row[service]['start'].show()
          self.service_row[service]['restart'].hide()
          self.service_row[service]['stop'].hide()