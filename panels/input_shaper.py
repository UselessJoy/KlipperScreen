import logging
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

# X and Y frequencies
XY_FREQ = [
    {'name': 'X', 'config': 'shaper_freq_x', 'min': 0, 'max': 133},
    {'name': 'Y', 'config': 'shaper_freq_y', 'min': 0, 'max': 133},
]
SHAPERS = ['zv', 'mzv', 'zvd', 'ei', '2hump_ei', '3hump_ei']

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.freq_xy_adj = {}
        self.freq_xy_combo = {}
        self.calibrate_btn = self._gtk.Button("move", _('Auto-calibrate'), "color1")
        self.calibrate_btn.connect("clicked", self.on_popover_clicked)
        self.calibrate_btn.set_vexpand(False)
        self.calibrate_btn.set_sensitive(True)
        self.calibrating_axis = None
        self.calibrating_axis = None
        self.stop_shaper_btn = self._gtk.Button(label=_("Stop"))
        self.stop_shaper_btn.set_sensitive(False)
        self.stop_shaper_btn.connect("clicked", self.stop_shaper)

        auto_calibration_label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        auto_calibration_label.set_markup('<big><b>%s</b></big>' % _("Auto Calibration"))
        
        auto_grid = Gtk.Grid()
        auto_grid.attach(auto_calibration_label, 0, 0, 1, 1)
        auto_grid.attach(self.calibrate_btn, 1, 0, 1, 1)
        input_grid = Gtk.Grid()

        for i, dim_freq in enumerate(XY_FREQ):
            axis_lbl = Gtk.Label()
            axis_lbl.set_markup(f"<b>{dim_freq['name']}</b>")
            axis_lbl.set_hexpand(False)

            self.freq_xy_adj[dim_freq['config']] = Gtk.Adjustment(0, dim_freq['min'], dim_freq['max'], 0.1)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, adjustment=self.freq_xy_adj[dim_freq['config']])
            scale.set_digits(1)
            scale.set_has_origin(True)
            scale.get_style_context().add_class("option_slider")
            scale.connect("button-release-event", self.set_opt_value, dim_freq['config'])

            shaper_slug = dim_freq['config'].replace('_freq_', '_type_')
            self.freq_xy_combo[shaper_slug] = Gtk.ComboBoxText()
            for shaper in SHAPERS:
                self.freq_xy_combo[shaper_slug].append(shaper, shaper)
                self.freq_xy_combo[shaper_slug].set_active(0)

            input_grid.attach(axis_lbl, 0, i + 2, 1, 1)
            input_grid.attach(scale, 1, i + 2, 1, 1)
            input_grid.attach(self.freq_xy_combo[shaper_slug], 2, i + 2, 1, 1)
        
        scroll_grid = Gtk.Grid()
        self.sw = Gtk.ScrolledWindow()
        self.sw.set_max_content_height(screen.gtk.content_height * 0.4)
        self.sw.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.AUTOMATIC)
        self.sw.set_vexpand(True)
        self.sw.set_hexpand(True)
        self.tb = Gtk.TextBuffer()
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_buffer(self.tb)
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.connect("size-allocate", self._autoscroll)
        self.sw.add(tv)
        scroll_grid.attach(self.sw, 0, 0, 1, 1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add(auto_grid)
        box.add(input_grid)
        lbl = Gtk.Label(label=_("Don't touch the printer until calibration end"), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        lbl.get_style_context().add_class("label_chars")
        box.add(lbl)
        box.add(scroll_grid)
        self.content.add(box)

        self.pobox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        test_x = self._gtk.Button(label=_("Measure X"))
        test_x.connect("clicked", self.start_calibration, "x")
        self.pobox.pack_start(test_x, True, True, 5)
        test_y = self._gtk.Button(label=_("Measure Y"))
        test_y.connect("clicked", self.start_calibration, "y")
        self.pobox.pack_start(test_y, True, True, 5)
        test_both = self._gtk.Button(label=_("Measure Both"))
        test_both.connect("clicked", self.start_calibration, "both")
        self.pobox.pack_start(test_both, True, True, 5)
        self.pobox.pack_start(self.stop_shaper_btn, True, True, 5)
        self.labels['popover'] = Gtk.Popover()
        self.labels['popover'].add(self.pobox)
        self.labels['popover'].set_position(Gtk.PositionType.LEFT)

    def on_popover_clicked(self, widget):
        self.labels['popover'].set_relative_to(widget)
        self.labels['popover'].show_all()

    def stop_shaper(self, widget):
      self.labels['popover'].popdown()
      self._screen._ws.klippy.run_async_command('ASYNC_STOP_SHAPER')

    def start_calibration(self, widget, method):
        self.labels['popover'].popdown()
        self.calibrating_axis = method
        if method == "x":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE AXIS=X')
        if method == "y":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE AXIS=Y')
        if method == "both":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE')

        # self.calibrate_btn.set_label(_('Calibrating') + '...')
        # self.calibrate_btn.set_sensitive(False)

    def set_opt_value(self, widget, opt, *args):
        shaper_freq_x = self.freq_xy_adj['shaper_freq_x'].get_value()
        shaper_freq_y = self.freq_xy_adj['shaper_freq_y'].get_value()
        shaper_type_x = self.freq_xy_combo['shaper_type_x'].get_active_text()
        shaper_type_y = self.freq_xy_combo['shaper_type_y'].get_active_text()

        self._screen._ws.klippy.gcode_script(
            f'SET_INPUT_SHAPER '
            f'SHAPER_FREQ_X={shaper_freq_x} '
            f'SHAPER_TYPE_X={shaper_type_x} '
            f'SHAPER_FREQ_Y={shaper_freq_y} '
            f'SHAPER_TYPE_Y={shaper_type_y}'
        )

    def activate(self):
        # This will return the current values
        self._screen._ws.klippy.gcode_script('SET_INPUT_SHAPER')

    def _autoscroll(self, *args):
        adj = self.sw.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())

    def process_update(self, action, data):
        if action == "notify_status_update":
          if 'resonance_tester' in data:
            if 'shaping' in data['resonance_tester']:
              for child in self.pobox:
                child.set_sensitive(not data['resonance_tester']['shaping'])
              self.stop_shaper_btn.set_sensitive(data['resonance_tester']['shaping'])
              #Эта хуйня расширяет дисплей в высоту в 2 раза - не спрашивайте
              # if data['resonance_tester']['shaping']:
              #   self.calibrate_btn.set_label(_('Calibrating') + '...')
              # else:
              #   self.calibrate_btn.set_label(_('Auto-calibrate'))
          return
        elif action != "notify_gcode_response":
            return
        if data.startswith("(warning)"):
          data = data[10:]
        self.tb.insert_markup(
            self.tb.get_end_iter(),
            f"\n<span >{data.replace('shaper_', '').replace('damping_', '').replace('// ', '')}</span>", -1)
        data: str = data.lower()
        # if 'got 0' in data:
        #     self.calibrate_btn.set_label(_('Check ADXL Wiring'))
        #     self.calibrate_btn.set_sensitive(False)
        # if 'unknown command:"accelerometer_query"' in data:
        #     self.calibrate_btn.set_label(_('ADXL Not Configured'))
        #     self.calibrate_btn.set_sensitive(False)
        # if 'adxl345 values' in data or 'axes noise' in data:
        #     self.calibrate_btn.set_sensitive(True)
            # self.calibrate_btn.set_label(_('Auto-calibrate'))
        # Recommended shaper_type_y = ei, shaper_freq_y = 48.4 Hz
        if 'recommended shaper_type_' in data:
            results = re.search(r'shaper_type_(?P<axis>[xy])\s*=\s*(?P<shaper_type>.*?), shaper_freq_.\s*=\s*('
                                r'?P<shaper_freq>[0-9.]+)', data)
            if results:
                results = results.groupdict()
                self.freq_xy_adj['shaper_freq_' + results['axis']].set_value(float(results['shaper_freq']))
                self.freq_xy_combo['shaper_type_' + results['axis']].set_active(SHAPERS.index(results['shaper_type']))
                # if self.calibrating_axis == results['axis'] or (self.calibrating_axis == "both" and results['axis'] == 'y'):
                #     self.calibrate_btn.set_sensitive(True)
                #     self.calibrate_btn.set_label(_('Calibrated'))
        # shaper_type_y:ei shaper_freq_y:48.400 damping_ratio_y:0.100000
        if 'shaper_type_' in data:
            results = re.search(r'shaper_type_(?P<axis>[xy]):(?P<shaper_type>.*?) shaper_freq_.:('
                                r'?P<shaper_freq>[0-9.]+)', data)
            if results:
                results = results.groupdict()
                self.freq_xy_adj['shaper_freq_' + results['axis']].set_value(float(results['shaper_freq']))
                self.freq_xy_combo['shaper_type_' + results['axis']].set_active(SHAPERS.index(results['shaper_type']))
