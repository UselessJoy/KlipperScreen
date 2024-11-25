import gi
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
        wifi_dev = self._screen.base_panel.get_wifi_dev()
        ssid = wifi_dev.get_connected_ssid()
        if ssid:
          self.is_access_point_active = wifi_dev.get_network_info(ssid)['is_hotspot']
        self.notebook.connect("switch-page", self.on_change_page)
        self.content.add(self.notebook)
        self.content.show_all()
    
    def on_change_page(self, notebook, page, page_num):
        self._screen.remove_keyboard()
        self._screen.remove_numpad()
        self.cur_page = page
        notebook.grab_focus()
        if hasattr(self.cur_page, "get_access_point_activity"):
            self.cur_page.get_access_point_activity(self.is_access_point_active)
            
    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'access_point' in data and 'is_active' in data['access_point']:
                self.is_access_point_active = data['access_point']['is_active']
                if hasattr(self.cur_page, "get_access_point_activity"):
                    self.cur_page.get_access_point_activity(data['access_point']['is_active'])
   
    def back(self):
        if hasattr(self.cur_page, "back"):
            return self.cur_page.back()
        return False