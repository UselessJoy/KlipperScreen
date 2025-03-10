import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Services")
        super().__init__(screen, title)
        self.labels = {}
        self.update_status = None
        self.service_row = {}
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.content.add(self.scroll)

    def get_services(self):
        info = self._screen.apiclient.send_request("machine/system_info")
        system_info = {}
        if info and 'result' in info and 'system_info' in info['result']:
          system_info = info['result']['system_info']
        service_state = system_info["service_state"]
        available_services = system_info["available_services"]

        return [{"name": name, "state": service_state[name] or None} for name in available_services if name not in ['klipper-mcu']]
    
    def activate(self):
      logging.info("activate")
      services = self.get_services()
      service_grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
      for i,service in enumerate(services):
        label_name = Gtk.Label(hexpand=True, halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END)
        label_name.set_markup(f"<b>{service['name']}</b>")
        label_name.get_style_context().add_class("updater-item")

        buttons = {}
        if service['state']['active_state'] != 'active':
            buttons['start'] = (self._gtk.Button("load", _("Start service"), "color4", scale=self.bts))
            buttons['start'].connect("clicked", self.start, service['name'])
        else:
            buttons['restart'] = (self._gtk.Button("refresh", _("Restart service"), "color3",scale=self.bts))
            buttons['restart'].connect("clicked", self.restart, service['name'])
        if service['name'] != 'KlipperScreen':
          buttons['stop'] = (self._gtk.Button("stop", _("Stop service"), "color4", scale=self.bts))
          buttons['stop'].set_sensitive(service['state']['active_state'] == "active")
          buttons['stop'].connect("clicked", self.stop, service['name'])
        button_grid = Gtk.Grid(column_homogeneous=True)
        button_grid.set_hexpand(True)
        button_grid.set_halign(Gtk.Align.END)
        for j, b in enumerate(buttons):
            buttons[b].set_size_request(self._screen.width * 0.33, 1)
            button_grid.attach(buttons[b], j, 0, 1, 1)
        service_grid.attach(label_name, 1, i, 1, 1)
        service_grid.attach(button_grid, 2, i, 1, 1)
        self.service_row[service['name']] = {
           'button_grid': button_grid
        }
        for button_name in buttons:
            self.service_row[service['name']][button_name] = buttons[button_name]
      self.scroll.add(service_grid)
      self.scroll.show_all()

    def restart(self, widget, service):
        self._screen._confirm_send_action(
              widget,
              f'{_("Are you sure?")}\n\n' f'{_("Restart service")}: {service}',
              "machine.services.restart",
              {"service": service},
              callback=self.on_restart_service
        )
        self._gtk.Button_busy(self.service_row[service]['restart'], True)
    
    def on_restart_service(self, result, method, params):
      self._gtk.Button_busy(self.service_row[params['service']]['restart'], False)

    def start(self, widget, service):
        self._screen._confirm_send_action(
                widget,
                f'{_("Are you sure?")}\n\n' f'{_("Start service")}: {service}',
                "machine.services.start",
                {"service": service},
                callback=self.on_start_service
        )
        self._gtk.Button_busy(self.service_row[service]['start'], True)
    
    def on_start_service(self, result, method, params):
      self._gtk.Button_busy(self.service_row[params['service']]['start'], False)

    def stop(self, widget, service):
        self._screen._confirm_send_action(
                widget,
                f'{_("Are you sure?")}\n\n' f'{_("Stop service")}: {service}',
                "machine.services.stop",
                {"service": service},
                callback=self.on_stop_service
        )
        self._gtk.Button_busy(self.service_row[service]['stop'], True)

    def on_stop_service(self, result, method, params):
      self._gtk.Button_busy(self.service_row[params['service']]['stop'], False)