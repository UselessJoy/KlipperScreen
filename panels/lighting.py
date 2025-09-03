import gi
from ks_includes.widgets.color_picker import ColorPicker
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.color_picker = ColorPicker()
        self.color_picker.color_wheel.connect("color-changed", self.on_color_changed)
        colors = self.get_default_color()
        self.color_picker.set_rgb(colors[0], colors[1], colors[2])
        self.enabled: bool = self._printer.get('led_control', 'enabled', False)
        # self.color_picker.set_sensitive(self.enabled)
        self.labels['set_default'] = self._gtk.Button("complete", _("Set Default"), "color1")
        # self.labels['set_default'].set_sensitive(self.enabled)
        self.labels['set_default'].connect("clicked", self.set_default_color)
        self.labels['turn_off_led'] = self._gtk.Button("shutdown", _("Turn off"), "color2")
        self.labels['turn_off_led'].set_label(_("Turn on neopixel") if self.enabled else _("Turn off neopixel"))
        self.labels['turn_off_led'].connect("clicked", self.turn_off_led)
        self.labels['actions'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.labels['actions'].set_hexpand(True)
        self.labels['actions'].set_vexpand(True)
        self.labels['actions'].set_halign(Gtk.Align.END)
        self.labels['actions'].set_homogeneous(True)
        self.labels['actions'].set_size_request(self._gtk.content_width, -1)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main.pack_start(self.color_picker, True, True, 8)
        main.pack_end(self.labels['actions'], True, False, 8)
        self.content.add(main)
        if self._screen.initialized:
            self.labels['actions'].add(self.labels['set_default'])
            self.labels['actions'].add(self.labels['turn_off_led'])
        self.content.show_all()
    
    def on_color_changed(self, widget, r, g, b):
        self._screen._ws.klippy.set_neopixel_color(self.get_neopixel(), r, g, b)
        self.color_picker.color_palette.rgb_label.set_label(f"color = ({int(r*255)},{int(g*255)},{int(b*255)})")
    
    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'led_control' in data and 'enabled' in data['led_control']:
                self.update_power_button(data['led_control']['enabled'])
    
    def get_neopixel(self):
        return self._printer.get_neopixels()[0][9:]

    def get_default_color(self):
      neopixel = self.get_neopixel()
      colors = [
        float(self._printer.config[f"neopixel {neopixel}"]['initial_red']),
        float(self._printer.config[f"neopixel {neopixel}"]['initial_green']),
        float(self._printer.config[f"neopixel {neopixel}"]['initial_blue'])
      ]
      return colors

    def set_default_color(self, widget):
        colors = self.color_picker.color_wheel.get_current_rgb()
        self._screen._ws.klippy.save_default_neopixel_color(self.get_neopixel(), str("%.1f" % (colors[0])), str("%.1f" % (colors[1])), str("%.1f" % (colors[2])))

    def update_power_button(self, enabled):
        self.enabled = enabled
        if self.enabled:
            self.labels['turn_off_led'].set_label(_("Turn off neopixel"))
        else:
            self.labels['turn_off_led'].set_label(_("Turn on neopixel"))
        self.labels['turn_off_led'].set_sensitive(True)
        # self.labels['set_default'].set_sensitive(self.enabled)
        # self.color_picker.set_sensitive(self.enabled)
    
    def turn_off_led(self, widget):
        if not self.enabled:
            self._screen._ws.klippy.turn_on_led()
            
        else:
            self._screen._ws.klippy.turn_off_led()
            # self.labels['set_default'].set_sensitive(False)
            # self.color_picker.set_sensitive(False)
        self.labels['turn_off_led'].set_sensitive(False)
        return