import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.colorWheel = Gtk.HSV()
        self.colorWheel.set_metrics(self._gtk.content_width/3,self._gtk.content_width/30)
        self.colors = self.get_default_color()
        hsv = Gtk.rgb_to_hsv(self.colors[0], self.colors[1], self.colors[2])
        self.colorWheel.set_color(hsv[0], hsv[1], hsv[2])
        self.enabled: bool = self._printer.get('led_control', 'enabled', False)
        self.colorWheel.set_sensitive(self.enabled)
        self.labels['set_default'] = self._gtk.Button("complete", _("Set Default"), "color1")
        self.labels['set_default'].set_sensitive(self.enabled)
        self.labels['set_default'].connect("clicked", self.set_default_color)
        self.labels['turn_off_led'] = self._gtk.Button("shutdown", _("Turn off"), "color2")
        self.labels['turn_off_led'].set_label(_("Turn on neopixel") if self.enabled else _("Turn off neopixel"))
        self.labels['turn_off_led'].connect("clicked", self.turn_off_led)
        self.colorWheel.connect("changed", self.color_changed)
        self.labels['actions'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.labels['actions'].set_hexpand(True)
        self.labels['actions'].set_vexpand(True)
        self.labels['actions'].set_halign(Gtk.Align.END)
        self.labels['actions'].set_homogeneous(True)
        self.labels['actions'].set_size_request(self._gtk.content_width, -1)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main.pack_start(self.colorWheel, True, True, 8)
        main.pack_end(self.labels['actions'], True, False, 8)
        self.neopixel = self.get_neopixel()
        self.content.add(main)
        if self._screen.initialized:
            self.labels['actions'].add(self.labels['set_default'])
            self.labels['actions'].add(self.labels['turn_off_led'])
        self.content.show_all()
        
    def color_changed(self, widget):
        self.colors = self.colorWheel.get_color()
        self.colors = self.colorWheel.to_rgb(self.colors[0], self.colors[1], self.colors[2])
        if not self.colorWheel.is_adjusting():
            self._screen._ws.klippy.set_neopixel_color(self.neopixel, self.colors[0], self.colors[1], self.colors[2])
    
    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'led_control' in data and 'enabled' in data['led_control']:
                self.update_power_button(data['led_control']['enabled'])
    
    def get_neopixel(self):
        return self._printer.get_neopixels()[0][9:]

    def get_default_color(self):
        colors = {}
        colors[0] = float(self._printer.config['neopixel my_neopixel']['initial_red'])
        colors[1] = float(self._printer.config['neopixel my_neopixel']['initial_green'])
        colors[2] = float(self._printer.config['neopixel my_neopixel']['initial_blue'])
        return colors

    def set_default_color(self, widget):
        self._screen._ws.klippy.save_default_neopixel_color(self.get_neopixel(), str("%.1f" % (self.colors[0])), str("%.1f" % (self.colors[1])), str("%.1f" % (self.colors[2])))

    def update_power_button(self, enabled):
        self.enabled = enabled
        if self.enabled:
            self.labels['turn_off_led'].set_label(_("Turn off neopixel"))
        else:
            self.labels['turn_off_led'].set_label(_("Turn on neopixel"))
        self.labels['turn_off_led'].set_sensitive(True)
        self.labels['set_default'].set_sensitive(self.enabled)
        self.colorWheel.set_sensitive(self.enabled)
    
    def turn_off_led(self, widget):
        if not self.enabled:
            self._screen._ws.klippy.turn_on_led()
            
        else:
            self._screen._ws.klippy.turn_off_led()
            self.labels['set_default'].set_sensitive(False)
            self.colorWheel.set_sensitive(False)
        self.labels['turn_off_led'].set_sensitive(False)
        return