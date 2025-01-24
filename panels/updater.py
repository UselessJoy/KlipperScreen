import logging
import socket
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.callback_thread import CallbackThread
import ks_includes.widgets.DetailsBoxes as DetailsBoxes
class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Update")
        super().__init__(screen, title)
        self.labels = {}
        self.update_status = None

        self.buttons = {
            "refresh": self._gtk.Button(
                image_name="arrow-down",
                label=_("Refresh"),
                style="color3",
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
        }
        self.main_updates = Gtk.Grid(row_homogeneous=True)
        self.is_details_box = False
        self.buttons["refresh"].connect("clicked", self.refresh_updates)
        self.buttons["refresh"].set_vexpand(False)
        self.top_box = Gtk.Box(vexpand=False)
        self.top_box.pack_start(self.buttons["refresh"], True, True, 0)
        self.update_msg = Gtk.Label(label=_("Checking for updates, please wait..."), vexpand=True)
        self.check_internet_msg = Gtk.Label(label=_("Checking for internet connection, please wait..."), vexpand=True)
        self.no_internet_access_msg = Gtk.Label(label=_("Cannot connect to github.com.\nPlease, check your internet connection"), vexpand=True, max_width_chars=40, wrap=True, wrap_mode = Pango.WrapMode.WORD_CHAR)
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.add(self.check_internet_msg)
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.main_box.pack_start(self.top_box, False, False, 0)
        self.main_box.pack_start(self.scroll, True, True, 0)
        self.content.add(self.main_box)

    def back(self):
      if self.is_details_box:
        self.clear_scroll()
        self.scroll.add(self.main_updates)
        self.top_box.show()
        self.scroll.show_all()
        return True
      return False
    
    def clear_scroll(self):
        for child in self.scroll.get_children():
            self.scroll.remove(child)

    def activate(self):
        GLib.timeout_add(200, self.refresh_updates)

    def refresh_updates(self, widget=None):
        self._gtk.Button_busy(self.buttons["refresh"], True)
        self.clear_scroll()
        self.scroll.add(self.check_internet_msg)
        self.scroll.show_all()
        self.show_on_connection_result(self.inner_has_connection())
       
    def show_on_connection_result(self, has_connection):
        if has_connection:
          self.check_updates()
        else:
          self.show_no_connection_message()

    def inner_has_connection(self):
        try:
          host = socket.gethostbyname("one.one.one.one")
          s = socket.create_connection((host, 80), 3)
          s.close()
          return True
        except Exception as e:
          logging.exception(f"Exception on internet_access: {e}")
        try:
          host = socket.gethostbyname("github.com")
          s = socket.create_connection((host, 80), 3)
          s.close()
          return True
        except Exception as e:
          logging.exception(f"Exception on internet_access: {e}")
        return False

    def show_no_connection_message(self):
      self.clear_scroll()
      self.scroll.add(self.no_internet_access_msg)
      self.scroll.show_all()
      self._gtk.Button_busy(self.buttons["refresh"], False)  

    def check_updates(self):
      self.clear_scroll()
      self.scroll.add(self.update_msg)
      self.scroll.show_all()
      logging.info("Sending machine.update.refresh")
      self._screen._ws.send_method("machine.update.refresh", callback=self.on_updates)

    def show_details(self, widget, DetailsBox, *args):
       self.clear_scroll()
       self.top_box.hide()
       self.scroll.add(DetailsBox(self.update_status['version_info'], *args))
       self.is_details_box = True
       self.scroll.show_all()

    def _all_updated(self):
        v_info = self.update_status['version_info']
        return all(v_info[prog]['vesion'] == v_info[prog]['remote_version'] for prog in v_info if prog != 'system')
    def _any_not_valid(self):
        v_info = self.update_status['version_info']
        return any((not v_info[prog]['is_valid']) for prog in v_info if prog != 'system')
    
    def UpdaterBox(self, updater_label, update_button_label, update_button_callback, DetailsBox, *args):
      updater_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
      updater_label = Gtk.Label(label = updater_label, halign=Gtk.Align.START)
      updater_label.get_style_context().add_class("details_prog_label")
      updater_box.add(updater_label)
      button_box = Gtk.Box()
      if update_button_label:
         update_button = self._gtk.Button(None, update_button_label, "color2", vexpand=False)
         update_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
         update_button.connect("clicked", update_button_callback)
         button_box.add(update_button)
      details_button = self._gtk.Button(None, _("Details"), "color3", vexpand=False)
      details_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
      details_button.connect("clicked", self.show_details, DetailsBox, *args)
      button_box.add(details_button)
      updater_box.add(button_box)
      return updater_box

    def ApplicationBox(self):
      updater_label = update_button_label = ""
      update_button_callback = lambda *args: None
      if self._any_not_valid():
        DetailsBox = DetailsBoxes.DetailsDirty
        updater_label = _("Software: version verification error")
        update_button_label = _("Recover")
        update_button_callback = self.show_recover_dialog     
      elif self._all_updated():
        DetailsBox = DetailsBoxes.DetailsActual
        updater_label = _("Software: actual version")
      else:
        DetailsBox = DetailsBoxes.DetailsUpdates
        updater_label = _("Software: has updates")
        update_button_label = _("Update")
        update_button_callback = self.show_update_dialog
      return self.UpdaterBox(updater_label, update_button_label, update_button_callback, DetailsBox)

    def SystemBox(self):
      updater_label = ( 
        self._printer.system_info["distribution"]["name"] 
        if "distribution" in self._printer.system_info and "name" in self._printer.system_info["distribution"]
        else _("System")
      )
      update_button_label = _("Update") if self.update_status['version_info']['system']['package_count'] != 0 else ""
      update_button_callback = self.show_system_update_dialog
      DetailsBox = DetailsBoxes.DetailsSystemBox
      return self.UpdaterBox(updater_label, update_button_label, update_button_callback, DetailsBox, updater_label)

    def on_updates(self, response, method, params):
        self._gtk.Button_busy(self.buttons["refresh"], False)
        self.update_status = response["result"]
        self.clear_scroll()
        self.main_updates.attach(self.ApplicationBox(), 0, 0, 1, 1)
        if 'system' in self.update_status['version_info']:
          self.main_updates.attach(self.SystemBox(), 0, 1, 1, 1)
        self.scroll.add(self.main_updates)
        self.scroll.show_all()

    def show_recover_dialog(self, widget):
      label = Gtk.Label(label = _("Recover applications?"), wrap=True, vexpand=True)
      recoverybuttons = [
          {
              "name": _("Recover"),
              "response": Gtk.ResponseType.OK,
              "style": "color4",
          },
          {
              "name": _("Cancel"),
              "response": Gtk.ResponseType.CANCEL,
              "style": "color3",
          },
      ]
      self._gtk.Dialog(recoverybuttons, label, _("Recover"), self.recover)
      return

    def show_update_dialog(self, widget):
      v_info = self.update_status["version_info"]
      scroll = self._gtk.ScrolledWindow(steppers=False)
      scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
      labelBox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
      for prog in v_info:
        if prog != 'system':
          if v_info[prog]['version'] != v_info['remote_version']:
            prog_label = Gtk.Label(wrap=True, vexpand=True)
            prog_label.set_markup(
              "<b>"
              + _("%s will be updated to version") % prog.capitalize()
              + f": {v_info[prog]['remote_version']}</b>"
            )
            labelBox.add(prog_label)
      scroll.add(labelBox)
      buttons = [
          {
              "name": _("Update"),
              "response": Gtk.ResponseType.OK,
              "style": "color4",
          },
          {
              "name": _("Cancel"),
              "response": Gtk.ResponseType.CANCEL,
              "style": "color3",
          },
      ]
      self._gtk.Dialog(buttons, scroll, _("Update"), self.update)

    def show_system_update_dialog(self, widget):
      v_packages_count = self.update_status["version_info"]['system']["package_count"]
      label = Gtk.Label(wrap=True, vexpand=True)
      label.set_markup(
                (
                    f'<b>{v_packages_count} '
                    + ngettext(
                        "package will be updated",
                        "packages will be updated",
                        v_packages_count,
                    ) +'</b>'
                )
            )
      buttons = [
          {
              "name": _("Update"),
              "response": Gtk.ResponseType.OK,
              "style": "color4",
          },
          {
              "name": _("Cancel"),
              "response": Gtk.ResponseType.CANCEL,
              "style": "color3",
          },
      ]
      self._gtk.Dialog(buttons, label, _("Update"), self.system_update)

    def update(self, dialog, response_id):
       self._gtk.remove_dialog(dialog)
       if response_id == Gtk.ResponseType.OK:
          self.send_update_method('applications', _("Starting applications updates..."))

    def system_update(self, dialog, response_id):
       self._gtk.remove_dialog(dialog)
       if response_id == Gtk.ResponseType.OK:
        self.send_update_method('system', _("Starting system updates..."))

    def recover(self, dialog, response_id):
       self._gtk.remove_dialog(dialog)
       if response_id == Gtk.ResponseType.OK:
        apps = {}
        v_info = self.update_status['version_info']
        for prog in v_info:
            if prog != 'system':
              prog_info = v_info[prog]
              if not prog_info['is_valid']:
                apps[prog] = {'hard': not not prog_info['git_messages'], 'update_deps': False}
        self.send_update_method('recover_needed', _("Starting recovering..."), apps)

    def send_update_method(self, method, msg, *args):
        if self._screen.updating:
          return
        self._screen.base_panel.show_update_dialog()
        self._screen._websocket_callback(
            "notify_update_response",
            {"message": msg, "complete": False},
        )
        self._screen._ws.send_method(f"machine.update.{method}", *args)