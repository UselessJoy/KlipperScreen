import logging
import gi
from ks_includes.wifi_nm import WifiManager
gi.require_version("Gtk", "3.0")
from ks_includes.widgets.interface_configuration import InterfaceConfiguration
from ks_includes.widgets.wifi_connection import WiFiConnection
from ks_includes.widgets.AP_configuration import APConfiguration
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    initialized = False

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self._screen = screen
        self.pages = [
                {'content': WiFiConnection(self._screen), 'label': _("WiFi")}, 
                {'content': InterfaceConfiguration(self._screen), 'label': _("Ethernet")},
                {'content': APConfiguration(self._screen), 'label': _("Access Point")},
            ]
        self.cur_page = None
        self.is_access_point_active = False
        self.notebook = self._gtk.VerticalNotebook(self.pages)
        self.wifi_dev: WifiManager = self._screen.base_panel.get_wifi_dev()
        ssid = self.wifi_dev.get_connected_ssid()
        self.wifi_dev.add_callback("connected", self.on_connected)
        self.wifi_dev.add_callback("disconnected", self.on_disconnected)
        if ssid:
          self.is_access_point_active = self.wifi_dev.get_network_info(ssid)['is_hotspot']
          logging.info(f"Ssid access point is {self.is_access_point_active}")
        self.notebook.connect("switch-page", self.on_change_page)
        self.content.add(self.notebook)
        self.content.show_all()
    
    def on_connected(self, ssid, prev_ssid):
        self.is_access_point_active = self.wifi_dev.get_network_info(ssid)['is_hotspot']
        logging.info(f"connected: access point is {self.is_access_point_active}")
        self.page_print()

    def on_disconnected(self, msg):
        self.is_access_point_active = False
        self.page_print()

    def on_change_page(self, notebook, page, page_num):
        self._screen.remove_keyboard()
        self._screen.remove_numpad()
        self.cur_page = page
        notebook.grab_focus()
        self.page_print()
    
    
    def page_print(self):
        if hasattr(self.cur_page, "print_network_mode"):
            self.cur_page.print_network_mode(self.is_access_point_active)

    def back(self):
        if hasattr(self.cur_page, "back"):
            return self.cur_page.back()
        return False