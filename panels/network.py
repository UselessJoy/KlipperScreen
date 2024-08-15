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
                {'content': InterfaceConfiguration(self._screen, "eth0"), 'label': _("Ethernet")},
                {'content': APConfiguration(self._screen), 'label': _("Access Point")},
            ]
        self.cur_page = None
        self.notebook = self._gtk.VerticalNotebook(self.pages)
        self.wifi_mode = None
        self.notebook.connect("switch-page", self.on_change_page)
        # self.notebook.connect("button-release-event", self.on_click)
        # self.notebook.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        
        
        self.content.add(self.notebook)
        self.content.show_all()
    
    def on_change_page(self, notebook, page, page_num):
        self._screen.remove_keyboard()
        self._screen.remove_numpad()
        self.cur_page = page
        notebook.grab_focus()
        if hasattr(self.cur_page, "reinit"):
            self.cur_page.reinit()
        
        if hasattr(self.cur_page, "show_according_wifi_mode"):
            self.cur_page.show_according_wifi_mode(self.wifi_mode)
            
            
    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'wifi_mode' in data and 'wifiMode' in data['wifi_mode']:
                self.wifi_mode = data['wifi_mode']['wifiMode']
                if hasattr(self.cur_page, "show_according_wifi_mode"):
                    self.cur_page.show_according_wifi_mode(data['wifi_mode']['wifiMode'])
                        
                        
    
    # def on_click(self, event, gdata):
    #     logging.info(f"this event {event}")
    #     logging.info(f"this data {gdata}")
    
                        
    def back(self):
        if hasattr(self.cur_page, "back"):
            return self.cur_page.back()
        return False
            
        
    