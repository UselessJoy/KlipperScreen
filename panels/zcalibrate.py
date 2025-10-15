import contextlib
import gi
from ks_includes.widgets.distgrid import DistGrid
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
import logging

class Panel(ScreenPanel):
    widgets = {}

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.probe = self._printer.get_probe()
        self.z_offset = None
        self.last_z_result = None
        self.manual_active = False
        self.tool = 'endstop'
        logging.info(f"Z offset: {self.z_offset}")

        self.widgets['zposition'] = Gtk.Label("?")
        self.widgets['savedoffset'] = Gtk.Label("?")
        self.widgets['zoffset'] = Gtk.Label("?")
        self.widgets['probe_z_result'] = Gtk.Label()

        self.z_buttons = {
            'z-': self._gtk.Button('z-farther', _("Raise Nozzle"), 'color4'),
            'z+': self._gtk.Button('z-closer', _("Lower Nozzle"), 'color1'),
        }
        self.z_buttons['z-'].connect("clicked", self.move, "-")
        self.z_buttons['z+'].connect("clicked", self.move, "+")

        self.control_buttons = {
            'start': self._screen.gtk.Button("complete", _("Start"), "color4"),
            'abort': self._screen.gtk.Button("cancel", _("Cancel"), "color2"),
            'accept': self._screen.gtk.Button("complete", _("Accept"), "color4"),
        }
        self.control_buttons['start'].connect('clicked', self.start)
        self.control_buttons['accept'].connect('clicked', self.end, KlippyGcodes.ACCEPT)
        self.control_buttons['abort'].connect('clicked', self.end, KlippyGcodes.ABORT)

        info_button = self._gtk.Button("info", style="round_button")#, scale=0.7)
        info_button.set_halign(Gtk.Align.END)
        info_button.set_valign(Gtk.Align.START)
        info_button.connect("clicked", self.show_help_overlay)

        self.z_move_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.z_move_box.add(self.z_buttons['z-'])
        self.z_move_box.add(self.z_buttons['z+'])
        self.z_move_box.set_sensitive(False)
        self.tools_grid = self._gtk.HomogeneousGrid()
        self.tools_buttons = [
          self._gtk.Button(None, _("Endstop"), "active-disabled"),
          self._gtk.Button(None, _("Probe"), "active-disabled")
        ]
        self.on_tool_changed(self.tools_buttons[0], self.tool, self.tools_buttons[1])
        for btn in self.tools_buttons:
          btn.set_vexpand(False)
          btn.set_size_request(1, 50)
        self.tools_buttons[0].connect("clicked", self.on_tool_changed, "endstop", self.tools_buttons[1])
        self.tools_buttons[1].connect("clicked", self.on_tool_changed, "probe", self.tools_buttons[0])
        for btn in self.tools_buttons:
          self.tools_grid.add(btn)

        offset_grid = self._gtk.HomogeneousGrid()
        offset_grid.set_row_spacing(20)
        offset_grid.set_vexpand(True)
        offset_grid.set_valign(Gtk.Align.CENTER)
        offset_grid.attach(Gtk.Label("Z:"), 0, 0, 1, 1)
        offset_grid.attach(self.widgets['zposition'], 1, 0, 1, 1)
        offset_grid.attach(Gtk.Label(_("Saved")), 0, 2, 1, 1)
        offset_grid.attach(self.widgets['savedoffset'], 1, 2, 1, 1)
        offset_grid.attach(self.widgets['probe_z_result'], 0, 3, 2, 1)
        offset_grid.attach(Gtk.Label(_("New")), 0, 4, 1, 1)
        offset_grid.attach(self.widgets['zoffset'], 1, 4, 1, 1)

        tool_data_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tool_data_box.add(self.tools_grid)
        tool_data_box.add(offset_grid)

        control_button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for btn in self.control_buttons:
            self.control_buttons[btn].set_no_show_all(True)
            control_button_box.add(self.control_buttons[btn])
            self.control_buttons[btn].set_vexpand(False)
            self.control_buttons[btn].set_size_request(self._screen.width * 0.15, self._screen.height * 0.15)
        self.control_buttons['start'].show()
        self.control_buttons['accept'].hide()
        self.control_buttons['abort'].hide()

        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        control_box.add(info_button)
        control_box.add(control_button_box)

        offset_content_box = Gtk.Box()
        offset_content_box.add(self.z_move_box)
        offset_content_box.add(tool_data_box)
        offset_content_box.add(control_box)
        self.distgrid = DistGrid(screen, ['.01', '.05', '.1', '.5', '1', '5'])
        for btn in self.distgrid:
            btn.set_vexpand(False)
            btn.set_size_request(1, self._screen.height * 0.25)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.add(offset_content_box)
        main_box.add(self.distgrid)
        self.overlay = Gtk.Overlay()
        self.overlay.add_overlay(main_box)
        self.content.add(self.overlay)

    def show_help_overlay(self, widget):
        self.overlayBox = Gtk.Box()
        close_help_overlay_button = self._gtk.Button("back_overlay", scale=self.bts, position=Gtk.PositionType.RIGHT)
        close_help_overlay_button.set_vexpand(False)
        close_help_overlay_button.set_hexpand(True)
        close_help_overlay_button.set_alignment(1., 0.)
        close_help_overlay_button.get_style_context().add_class("overlay_close_button")
        close_help_overlay_button.connect("clicked", self.close_help_overlay)
        self.overlayBox.pack_start(close_help_overlay_button, False, True, 0)
        self.scroll = self._gtk.ScrolledWindow()

        msg_label = Gtk.Label(label=_(
"Калибровка концевика:\n"
"1. нажать на кнопку \"Концевик\" и после нажать на кнопку \"Начать\";\n"
"2. кнопками \"Поднять стол\" и \"Опустить стол\" довести стол до положения, когда между ним и соплом зазор будет равен нулю*;\n"
"3. нажать кнопку \"Применить\";\n"
"\n"
"Калибровка пробы:\n"
"1. нажать на кнопку \"Проба\" и после нажать на кнопку \"Начать\". Принтер определит координату \
срабатывания магнитной пробы по оси Z (по тройному срабатыванию пробы в центре стола), вернет пробу \
и переместит экструдер в центр стола;\n"
"2. кнопками \"Поднять стол\" и \"Опустить стол\" довести стол до положения, когда между ним и соплом зазор будет равен нулю**;\n"
"3. нажать кнопку \"Применить\";\n"
"\n"
"*Если сложно визуально оценить зазор, то можно положить между столом и соплом сложенный пополам лист офисной бумаги \
и довести стол до положения, когда при движении листа начнет ощущаться небольшое сопротивление. Это будет означать, что \
зазор между столом и соплом составляет ≈0.2 мм. Вытащить лист бумаги, поднять стол на 0.2 мм, получив тем самым нулевой зазор.\n"
"**Если калибровка концевика была выполнена корректно, то значение координаты по оси Z при нулевом зазоре между столом и соплом на этапе \
калибровки пробы будет совпадать со значением, полученным на этапе калибровки концевика."))
        msg_label.set_line_wrap(True)
        msg_label.set_valign(Gtk.Align.START)

        self.scroll.add(msg_label)
        self.scroll.set_vexpand(False)
        self.scroll.set_hexpand(True)
        self.scroll.set_halign(Gtk.Align.FILL)
        self.scroll.set_min_content_width(self._gtk.content_width / 1.2)
        self.scroll.get_style_context().add_class("overlay_background")
        self.overlayBox.pack_start(self.scroll, True, True, 0)
        self.overlayBox.set_vexpand(False)
        self.overlayBox.set_hexpand(True)
        self.overlayBox.show_all()
        for child in self.overlay:
            child.set_opacity(0.2)
            child.set_sensitive(False)
        self.overlay.add_overlay(self.overlayBox)
        self.scroll.show_all()

    def close_help_overlay(self, widget=None):
        self.overlay.remove(self.overlayBox)
        for child in self.overlayBox:
            self.overlayBox.remove(child)
        self.overlayBox = None
        for child in self.scroll:
            self.scroll.remove(child)
        self.scroll = None
        for child in self.overlay:
            child.set_opacity(1)
            child.set_sensitive(True)
        self.overlayBox = None

    def popup_popdown(self, widget, popup):
      popup.popdown()
    
    def show_info_popover(self, widget, popup):
      popup.popup()
      popup.show_all()

    def start(self, widget):
      self._screen.gtk.Button_busy(self.control_buttons['start'], True)
      if self.tool == "probe":
          self._screen._ws.klippy.gcode_script(KlippyGcodes.PROBE_CALIBRATE, self.on_gcode_script)
      elif self.tool  == "endstop":
          self._screen._ws.klippy.gcode_script(KlippyGcodes.Z_ENDSTOP_CALIBRATE, self.on_gcode_script)

    def on_gcode_script(self, *args):
        self._screen.gtk.Button_busy(self.control_buttons['start'], False)

    def end(self, widget, gcode:str):
        self._screen._ws.klippy.gcode_script(gcode)
  
    def widgets_on_start(self):
        self.tools_buttons[self.tool == 'endstop'].get_style_context().remove_class("active-disabled")
        self.tools_buttons[self.tool == 'endstop'].set_sensitive(False)
        for btn in self.tools_buttons:
            btn.get_style_context()
            btn.set_sensitive(False)
        self.z_move_box.set_sensitive(True)
        self.control_buttons['start'].hide()
        self.control_buttons['accept'].show()
        self.control_buttons['abort'].show()
        self._screen.base_panel.control['back'].set_sensitive(False)
        self._screen.base_panel.control['home'].set_sensitive(False)
        self._screen.base_panel.control['shortcut'].set_sensitive(False)

    def widgets_on_end(self):
        self.tools_buttons[self.tool == 'endstop'].get_style_context().add_class("active-disabled")
        self.tools_buttons[self.tool == 'endstop'].set_sensitive(True)
        endstop_calibrated = 0 if self.tool == 'endstop' else 1
        if endstop_calibrated:
          self.tools_buttons[False].set_sensitive(False)

        self.z_move_box.set_sensitive(False)
        self.widgets['zoffset'].set_text("?")
        self.control_buttons['accept'].hide()
        self.control_buttons['abort'].hide()
        self.control_buttons['start'].show()
        self._screen.base_panel.control['back'].set_sensitive(True)
        self._screen.base_panel.control['home'].set_sensitive(True)
        self._screen.base_panel.control['shortcut'].set_sensitive(True)

    def on_tool_changed(self, widget, tool, activate_tool):
        widget.set_sensitive(False)
        activate_tool.set_sensitive(True)
        self.tool = tool.lower()
        if self.tool == "probe":
            self.z_offset =  float(self._screen.apiclient.send_request("printer/objects/query?probe")['result']['status']['probe']['last_z_result'])
            saved_offset = float(self._screen.apiclient.send_request("printer/objects/query?probe")['result']['status']['probe']['z_offset'])
            self.widgets['savedoffset'].set_text(f"{saved_offset:.2f}")
        elif self.tool == "endstop":
            self.z_offset = float(self._screen.apiclient.send_request("printer/objects/query?manual_probe")['result']['status']['manual_probe']['z_position_endstop'])
            self.widgets['savedoffset'].set_text(f"{self.z_offset:.2f}")

    def move(self, widget, direction):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.testz_move(f"{direction}{self.distgrid.get_distance()}"))

    def update_position(self, position):
        self.widgets['zposition'].set_text(f"{position[2]:.3f}")
        if self.z_offset:
            if self.widgets['probe_z_result'].get_text() == "":
                self.widgets['zoffset'].set_text(f"{(self.z_offset - position[2]):.3f}")
            elif self.last_z_result:
                self.widgets['zoffset'].set_text(f"{(self.last_z_result - position[2]):.3f}")

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
            self.widgets['zposition'].set_text("?")
        elif "gcode_move" in data:
            if "gcode_position" in data['gcode_move']:
                self.update_position(data['gcode_move']['gcode_position'])
        if 'manual_probe' in data:
            if 'z_position_endstop' in data['manual_probe']:
                self.z_offset = data['manual_probe']['z_position_endstop']
            if 'is_active' in data['manual_probe']:
                self.manual_active = data['manual_probe']['is_active']
                if self.manual_active:
                  self.widgets_on_start()
                else:
                  self.widgets_on_end()
            if 'command' in data['manual_probe']:
                if data['manual_probe']['command'] == 'Z_ENDSTOP_CALIBRATE':
                    self.widgets['savedoffset'].set_text(f"{self.z_offset:.3f}")
                    self.widgets['probe_z_result'].set_text("")
                elif data['manual_probe']['command'] == 'PROBE_CALIBRATE':
                    self.z_offset = float(self.probe['z_offset'])
                    self.widgets['savedoffset'].set_text(f"{self.z_offset:.3f}")
                    self.widgets['probe_z_result'].set_text("Проба сработала на Z = ?")
                if data['manual_probe']['command'] == None:
                    self.on_tool_changed(self.tools_buttons[not self.tool == 'endstop'], self.tool, self.tools_buttons[self.tool == 'endstop'])
        if 'probe' in data and 'last_z_result' in data['probe']:
            if data['probe']['last_z_result']:
                self.last_z_result = data['probe']['last_z_result']
        if self.widgets['probe_z_result'].get_text() != "" and self.manual_active:
            self.widgets['probe_z_result'].show()
            self.widgets['probe_z_result'].set_text("Проба сработала на Z = %.3f" % self.last_z_result)
        else:
            self.widgets['probe_z_result'].hide()
        if action == "notify_gcode_response":
            lower_data = data.lower()
            if "out of range" in lower_data:
                self._screen.show_popup_message(data)
            elif "fail" in lower_data and "use testz" in lower_data:
                self._screen.show_popup_message(_("Failed, adjust position first"))