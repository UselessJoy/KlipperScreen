import re
import gi
import logging
from ks_includes.widgets.typed_entry import TypedEntry, NumberRule, TextView
from ks_includes.screen_panel import ScreenPanel
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib, Gdk

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        try:
          serial_number = str(screen.apiclient.send_request("printer/serial/get_serial")['result']['serial_number'])
        except Exception as e:
            serial_number = ''
            logging.error(f"Can't load serial number from klipper: {e}")
           
        self.labels['form'] = {
            'fullname': TypedEntry(text="", hexpand=True),
            'phone' : TypedEntry(text="", hexpand=True, entry_rule=NumberRule),
            'serial_number' : TypedEntry(text=serial_number, entry_rule=NumberRule, hexpand=True, placeholder_text=_("Necessary")),
            'email' : TypedEntry(text="", hexpand=True, placeholder_text=_("Necessary")),
            'description':TextView(placeholder_text=_("Necessary"))
        }

        self.popups = []
        self.labels['form']['description'].get_style_context().add_class("textview_logs")
        self.labels['form']['description'].set_size_request(50, 50)
        form_grid = Gtk.Grid(column_homogeneous = True, vexpand = False, row_spacing = 8)
        scroll = self._gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class("p-10px")
        for i, lbl in enumerate(self.labels['form']):
          self.labels['form'][lbl].connect("button-press-event", self.on_change_entry)
          form_grid.attach(Gtk.Label(label = _(lbl.capitalize().replace('_', ' ')), hexpand=True, halign=Gtk.Align.START), 0, i, 1, 1)
          form_grid.attach(self.labels['form'][lbl], 1, i, 3, 1)
        
        self.send_log_button = self._screen.gtk.Button("complete", _("Send logs"), "color1")
        self.send_log_button.set_hexpand(True)
        self.send_log_button.set_vexpand(True)
        self.send_log_button.set_valign(Gtk.Align.END)
        self.send_log_button.set_halign(Gtk.Align.END)
        self.send_log_button.set_resize_mode(False)
        self.send_log_button.set_size_request((self._screen.width) * 0.25, self._screen.height * 0.2)
        self.send_log_button.connect('clicked', self.send_logs)
        main_content_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        main_content_box.add(form_grid)
        main_content_box.add(self.send_log_button)
        scroll.add(main_content_box)
        self.content.add(scroll)

    def send_logs(self, widget):
      has_errors = False
      for field in self.labels['form']:
        if field not in ['fullname', 'phone']:
          if not self.labels['form'][field].get_text():
            self.add_error_popup(self.labels['form'][field], "Cannot be empty")
            has_errors = True
          elif field == 'serial_number':
            if len(self.labels['form'][field].get_text()) != 6:
              self.add_error_popup(self.labels['form'][field], "Must contain only 6 numbers")
              has_errors = True
      if not has_errors and not re.match(r"^\w+([.-]?\w+)*@\w+([.-]?\w+)*(\.\w{2,3})+$", self.labels['form']['email'].get_text()):
        self.add_error_popup(self.labels['form']['email'], "Not valid email")
        has_errors = True
      if has_errors:
          GLib.timeout_add_seconds(5, self.close_preheat_popups)
          return
      n = self.labels['form']['fullname'].get_text()
      p = self.labels['form']['phone'].get_text()
      e = self.labels['form']['email'].get_text()
      sn = self.labels['form']['serial_number'].get_text()
      d = self.labels['form']['description'].get_text()
      self._gtk.Button_busy(self.send_log_button, True)
      self._screen._ws.klippy.send_logs(n, p, e, sn, d, self.on_send_logs)
      return

    def add_error_popup(self, relative, error):
        popup = Gtk.Popover.new(relative)
        popup.get_style_context().add_class("message_popup_error")
        popup.set_position(Gtk.PositionType.BOTTOM)
        popup.set_halign(Gtk.Align.CENTER)
        msg = Gtk.Button(label=_(error))
        msg.set_hexpand(True)
        msg.set_vexpand(True)
        msg.get_child().set_line_wrap(True)
        msg.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        popup.add(msg)
        msg.connect("clicked", self.popup_popdown, popup)
        popup.popup()
        popup.show_all()
        self.popups.append(popup)

    def close_preheat_popups(self):
        for child in self.popups:
            child.popdown()   
        self.popups.clear()

    def popup_popdown(self, widget, popup):
        popup.popdown()

    def on_send_logs(self, result, method, params):
        self._gtk.Button_busy(self.send_log_button, False)
        if 'error' in result:
            logging.debug(result['error'])
            res: str = result['error']['message']
            if res.find('Cannot connect to host api.telegram.org'):
              res = _("Can't send message: connection lost. Please, check your internet access")
            self._screen.show_popup_message(res, just_popup=True)
            return
        else:
          self._screen.show_popup_message(_("Message sended"), level=1)
    #       self.save_data()
    # # Можно доабвить автоматическую вставку данных пользователя после первого заполнения формы
    # def save_data():
    #   return

    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self.on_accept_keyboard_dutton)
        self._screen.keyboard.change_entry(entry=entry)
        
    def on_accept_keyboard_dutton(self):
        self._screen.remove_keyboard()