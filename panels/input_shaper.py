import logging
from ks_includes.widgets.combo_box import KSComboBox
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
        self.freq_xy_adj      = {}
        self.freq_xy_combo    = {}
        self.old_values       = {}
        self.old_active       = {}
        self.calibrating_axis = None
        self.calibrating_axis = None
        self.manual_dialog    = None

        self.auto_calibrate_btn = self._gtk.Button(None, _('Auto-calibrate'), "color1")
        self.auto_calibrate_btn.connect("clicked", self.on_popover_clicked)
        self.auto_calibrate_btn.set_vexpand(False)

        # self.stop_shaper_btn = self._gtk.Button(label=_("Stop"))
        # self.stop_shaper_btn.set_sensitive(False)
        # self.stop_shaper_btn.connect("clicked", self.stop_shaper)

        self.manual_calibrate_btn = self._gtk.Button(None, _('Manual Calibration'), "color2")
        self.manual_calibrate_btn.connect("clicked", self.show_manual_calibrate_dialog)
        self.manual_calibrate_btn.set_vexpand(False)

        self.input_grid = Gtk.Grid()
        for i, dim_freq in enumerate(XY_FREQ):
            axis_lbl = Gtk.Label()
            axis_lbl.set_markup(f"<b>{dim_freq['name']}</b>")
            axis_lbl.set_hexpand(False)

            self.freq_xy_adj[dim_freq['config']] = Gtk.Adjustment(0, dim_freq['min'], dim_freq['max'], 0.1)
            self.old_values[dim_freq['config']] = self.freq_xy_adj[dim_freq['config']].get_value()
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, adjustment=self.freq_xy_adj[dim_freq['config']])
            scale.set_digits(1)
            scale.set_has_origin(True)
            scale.get_style_context().add_class("option_slider")
            scale.connect("button-release-event", self.on_change_manual_parameter)
            shaper_slug = dim_freq['config'].replace('_freq_', '_type_')

            self.freq_xy_combo[shaper_slug] = KSComboBox(self._screen)
            self.freq_xy_combo[shaper_slug].set_halign(Gtk.Align.END)
            self.freq_xy_combo[shaper_slug].set_size_request(150, 1)
            # self.freq_xy_combo[shaper_slug].button.set_hexpand(False)
            for shaper in SHAPERS:
                self.freq_xy_combo[shaper_slug].append(shaper)
            self.freq_xy_combo[shaper_slug].set_active_num(0)
            self.freq_xy_combo[shaper_slug].connect("selected", self.on_change_manual_parameter)
            self.old_active[shaper_slug] = self.freq_xy_combo[shaper_slug].get_text()

            self.input_grid.attach(axis_lbl, 0, i + 2, 1, 1)
            self.input_grid.attach(scale, 1, i + 2, 1, 1)
            self.input_grid.attach(self.freq_xy_combo[shaper_slug], 2, i + 2, 1, 1)

        auto_grid = self._gtk.HomogeneousGrid()
        auto_grid.set_size_request(1, screen.gtk.content_height * 0.2)
        auto_grid.attach(self.manual_calibrate_btn, 0, 0, 1, 1)
        auto_grid.attach(self.auto_calibrate_btn, 1, 0, 1, 1)

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
        # self.pobox.pack_start(self.stop_shaper_btn, True, True, 5)
        self.labels['popover'] = Gtk.Popover()
        self.labels['popover'].add(self.pobox)
        self.labels['popover'].set_position(Gtk.PositionType.LEFT)

    def on_popover_clicked(self, widget):
        self.labels['popover'].set_relative_to(widget)
        self.labels['popover'].show_all()

    def show_manual_calibrate_dialog(self, *args):
        buttons = [
            {"name": _("Set"), "response": Gtk.ResponseType.OK, "style": "color1"},
            {"name": _("Close"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
        ]

        for dim_freq in XY_FREQ:
            self.freq_xy_adj[dim_freq['config']].set_value(self.old_values[dim_freq['config']])
            shaper_slug = dim_freq['config'].replace('_freq_', '_type_')
            self.freq_xy_combo[shaper_slug].set_active_text(self.old_active[shaper_slug])

        self.manual_dialog = self._gtk.Dialog(buttons, self.input_grid, "", self.close_manual_calibrate_dialog, on_realize=self.on_realize)
        return False

    def on_realize(self, dialog):
      b = dialog.get_widget_for_response(Gtk.ResponseType.OK)
      if b:
        b.set_sensitive(False)

    def on_change_manual_parameter(self, *args):
      if not self.manual_dialog:
         return
      b = self.manual_dialog.get_widget_for_response(Gtk.ResponseType.OK)
      if not b:
         return
      
      for dim_freq in XY_FREQ:
         shaper_slug = dim_freq['config'].replace('_freq_', '_type_')
         if self.old_values[dim_freq['config']] != self.freq_xy_adj[dim_freq['config']].get_value() or \
            self.old_active[shaper_slug] != self.freq_xy_combo[shaper_slug].get_text():
              b.set_sensitive(True)

    def close_manual_calibrate_dialog(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.set_opt_value()
            self.manual_dialog.get_widget_for_response(Gtk.ResponseType.OK).set_sensitive(False)
            self._screen.show_popup_message(_("Parameters setted"), just_popup=True, level=1, 
                                            relative_to = self.input_grid,#self.manual_dialog.get_widget_for_response(Gtk.ResponseType.CANCEL), 
                                            position_type = Gtk.PositionType.TOP)
        else:
            # Рабочий метод, если не хочется каждый раз пересоздавать виджеты
            if self.input_grid.get_parent():
                self.input_grid.get_parent().remove(self.input_grid)
            self._gtk.remove_dialog(dialog)

    # def stop_shaper(self, widget):
    #   self.labels['popover'].popdown()
    #   self._screen._ws.klippy.run_async_command('ASYNC_STOP_SHAPER')

    def start_calibration(self, widget, method):
        self.labels['popover'].popdown()
        self.calibrating_axis = method
        if method == "x":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE AXIS=X')
        if method == "y":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE AXIS=Y')
        if method == "both":
            self._screen._ws.klippy.gcode_script('SHAPER_CALIBRATE')

    def set_opt_value(self):
        shaper_freq_x = self.freq_xy_adj['shaper_freq_x'].get_value()
        self.old_values['shaper_freq_x'] = shaper_freq_x
        shaper_freq_y = self.freq_xy_adj['shaper_freq_y'].get_value()
        self.old_values['shaper_freq_y'] = shaper_freq_y
        shaper_type_x = self.freq_xy_combo['shaper_type_x'].get_text()
        self.old_active['shaper_type_x'] = shaper_type_x
        shaper_type_y = self.freq_xy_combo['shaper_type_y'].get_text()
        self.old_active['shaper_type_y'] = shaper_type_y

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
              self.auto_calibrate_btn.set_sensitive(not data['resonance_tester']['shaping'])
              self.manual_calibrate_btn.set_sensitive(not data['resonance_tester']['shaping'])
              # for child in self.pobox:
              #   child.set_sensitive(not data['resonance_tester']['shaping'])
              # self.stop_shaper_btn.set_sensitive(data['resonance_tester']['shaping'])
          return
        elif action != "notify_gcode_response":
            return
        if data.startswith("(warning)"):
          data = data[10:]
        self.tb.insert_markup(
            self.tb.get_end_iter(),
            f"\n<span >{data.replace('shaper_', '').replace('damping_', '').replace('// ', '')}</span>", -1)
        data: str = data.lower()
        # Recommended shaper_type_y = ei, shaper_freq_y = 48.4 Hz
        if 'recommended shaper_type_' in data:
            results = re.search(r'shaper_type_(?P<axis>[xy])\s*=\s*(?P<shaper_type>.*?), shaper_freq_.\s*=\s*('
                                r'?P<shaper_freq>[0-9.]+)', data)
            self.set_new_data(results)
        # shaper_type_y:ei shaper_freq_y:48.400 damping_ratio_y:0.100000
        if 'shaper_type_' in data:
            results = re.search(r'shaper_type_(?P<axis>[xy]):(?P<shaper_type>.*?) shaper_freq_.:('
                                r'?P<shaper_freq>[0-9.]+)', data)
            self.set_new_data(results)
        
    def set_new_data(self, results):
        if results:
            results = results.groupdict()
            self.freq_xy_adj['shaper_freq_' + results['axis']].set_value(float(results['shaper_freq']))
            self.old_values['shaper_freq_' + results['axis']] = float(results['shaper_freq'])
            self.freq_xy_combo['shaper_type_' + results['axis']].set_active_num(SHAPERS.index(results['shaper_type']))
            self.old_active['shaper_type_' + results['axis']] = self.freq_xy_combo['shaper_type_' + results['axis']].get_text()
