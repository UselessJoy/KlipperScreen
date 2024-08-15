import contextlib
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
import logging

class Panel(ScreenPanel):
    widgets = {}
    distances = ['.01', '.05', '.1', '.5', '1', '5']
    distance = distances[-2]

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.probe = self._printer.get_probe()
        self.z_offset = None
        self.last_z_result = None
        self.manual_active = False
        logging.info(f"Z offset: {self.z_offset}")
        self.widgets['zposition'] = Gtk.Label("Z: ?")
        self.widgets['whichoffset'] = Gtk.Label()
        self.widgets['savedoffset'] = Gtk.Label("?")
        self.widgets['zoffset'] = Gtk.Label("?")
        self.widgets['probe_z_result'] = Gtk.Label()
        self.z_pos_grid = self._gtk.HomogeneousGrid()
        self.z_pos_grid.attach(self.widgets['zposition'], 0, 1, 2, 1)
        self.z_pos_grid.attach(self.widgets['whichoffset'] , 0, 2, 2, 1)
        self.z_pos_grid.attach(self.widgets['probe_z_result'], 0, 3, 2, 1)
        self.z_pos_grid.attach(Gtk.Label(_("Saved")), 0, 4, 1, 1)
        self.z_pos_grid.attach(Gtk.Label(_("New")), 1, 4, 1, 1)
        self.z_pos_grid.attach(self.widgets['savedoffset'], 0, 5, 1, 1)
        self.z_pos_grid.attach(self.widgets['zoffset'], 1, 5, 1, 1)
        
        self.buttons = {
            'zpos': self._gtk.Button('z-farther', _("Raise Nozzle"), 'color4'),
            'zneg': self._gtk.Button('z-closer', _("Lower Nozzle"), 'color1'),
            'start': self._gtk.Button('resume', _("Start"), 'color3'),
            'complete': self._gtk.Button('complete', _('Accept'), 'color3'),
            'cancel': self._gtk.Button('cancel', _('Abort'), 'color2'),
        }
        self.buttons['zpos'].connect("clicked", self.move, "-")
        self.buttons['zneg'].connect("clicked", self.move, "+")
        self.buttons['complete'].connect("clicked", self.accept)
        self.buttons['cancel'].connect("clicked", self.abort)

        functions = []
        pobox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if "Z_ENDSTOP_CALIBRATE" in self._printer.available_commands:
            self._add_button(_("Endstop"), "endstop", pobox)
            functions.append("endstop")
        if "PROBE_CALIBRATE" in self._printer.available_commands:
            self._add_button(_("Probe"), "probe", pobox)
            functions.append("probe")
        if "BED_MESH_CALIBRATE" in self._printer.available_commands and "probe" not in functions:
            # This is used to do a manual bed mesh if there is no probe
            self._add_button(_("Bed mesh"), "mesh", pobox)
            functions.append("mesh")
        if "DELTA_CALIBRATE" in self._printer.available_commands:
            if "probe" in functions:
                self._add_button(_("Delta Automatic"), "delta", pobox)
                functions.append("delta")
            # Since probes may not be accturate enough for deltas, always show the manual method
            self._add_button(_("Delta Manual"), "delta_manual", pobox)
            functions.append("delta_manual")

        logging.info(f"Available functions for calibration: {functions}")

        self.labels['popover'] = Gtk.Popover()
        self.labels['popover'].add(pobox)
        self.labels['popover'].set_position(Gtk.PositionType.BOTTOM)

        if len(functions) > 1:
            self.buttons['start'].connect("clicked", self.on_popover_clicked)
        else:
            self.buttons['start'].connect("clicked", self.start_calibration, functions[0])

        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            self.widgets[i] = self._gtk.Button(label=i)
            self.widgets[i].set_direction(Gtk.TextDirection.LTR)
            self.widgets[i].connect("clicked", self.change_distance, i)
            ctx = self.widgets[i].get_style_context()
            if (self._screen.lang_ltr and j == 0) or (not self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_top")
            elif (not self._screen.lang_ltr and j == 0) or (self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.distance:
                ctx.add_class("distbutton_active")
            distgrid.attach(self.widgets[i], j, 0, 1, 1)

        self.widgets['move_dist'] = Gtk.Label(_("Move Distance (mm)"))
        distances = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        distances.pack_start(self.widgets['move_dist'], True, True, 0)
        distances.pack_start(distgrid, True, True, 0)

        grid = Gtk.Grid()
        #grid.set_row_homogeneous(True)
        if self._screen.vertical_mode:
            grid.attach(self.buttons['zpos'], 0, 1, 1, 1)
            grid.attach(self.buttons['zneg'], 0, 2, 1, 1)
            grid.attach(self.buttons['start'], 0, 0, 1, 1)
            grid.attach(self.z_pos_grid, 1, 0, 1, 1)
            grid.attach(self.buttons['complete'], 1, 1, 1, 1)
            grid.attach(self.buttons['cancel'], 1, 2, 1, 1)
            grid.attach(distances, 0, 3, 2, 1)
        else:
            grid.attach(self.buttons['zpos'], 0, 0, 1, 1)
            grid.attach(self.buttons['zneg'], 0, 1, 1, 1)
            grid.attach(self.buttons['start'], 1, 0, 1, 1)
            grid.attach(self.z_pos_grid, 1, 1, 1, 1)
            grid.attach(self.buttons['complete'], 2, 0, 1, 1)
            grid.attach(self.buttons['cancel'], 2, 1, 1, 1)
            grid.attach(distances, 0, 2, 3, 1)
        self.content.add(grid)

    def _add_button(self, label, method, pobox):
        popover_button = self._gtk.Button(label=label)
        popover_button.connect("clicked", self.start_calibration, method)
        pobox.pack_start(popover_button, True, True, 5)

    def on_popover_clicked(self, widget):
        self.labels['popover'].set_relative_to(widget)
        self.labels['popover'].show_all()

    def start_calibration(self, widget, method):
        self.labels['popover'].popdown()
        
        if method == "probe":
            self.z_offset = float(self.probe['z_offset'])
            self.widgets['whichoffset'].set_text(_("Probe Offset"))
            self.widgets['savedoffset'].set_text(f"{self.z_offset:.2f}")
            self.widgets['probe_z_result'].set_text("Проба сработала на Z = ?")
            #self._move_to_position()
            self._screen._ws.klippy.gcode_script(KlippyGcodes.PROBE_CALIBRATE)
        elif method == "mesh":
            self._screen._ws.klippy.gcode_script("BED_MESH_CALIBRATE")
        elif method == "delta":
            self._screen._ws.klippy.gcode_script("DELTA_CALIBRATE")
        elif method == "delta_manual":
            self._screen._ws.klippy.gcode_script("DELTA_CALIBRATE METHOD=manual")
        elif method == "endstop":
            self.z_offset = float(self._printer.get_config_section("stepper_z")['position_endstop'])
            self.widgets['whichoffset'].set_text(_("Endstop Offset"))
            self.widgets['savedoffset'].set_text(f"{self.z_offset:.2f}")
            self._screen._ws.klippy.gcode_script(KlippyGcodes.Z_ENDSTOP_CALIBRATE)

    def _move_to_position(self):
        x_position = y_position = None
        z_hop = speed = None
        # Get position from config
        if self.ks_printer_cfg is not None:
            x_position = self.ks_printer_cfg.getfloat("calibrate_x_position", None)
            y_position = self.ks_printer_cfg.getfloat("calibrate_y_position", None)
        if self.probe:
            if "sample_retract_dist" in self.probe:
                z_hop = self.probe['sample_retract_dist']
            if "speed" in self.probe:
                speed = self.probe['speed']

        # Use safe_z_home position
        if ("safe_z_home" in self._printer.get_config_section_list() and
                "Z_ENDSTOP_CALIBRATE" not in self._printer.available_commands):
            safe_z = self._printer.get_config_section("safe_z_home")
            safe_z_xy = safe_z['home_xy_position']
            safe_z_xy = [str(i.strip()) for i in safe_z_xy.split(',')]
            if x_position is None:
                x_position = float(safe_z_xy[0])
                logging.debug(f"Using safe_z x:{x_position}")
            if y_position is None:
                y_position = float(safe_z_xy[1])
                logging.debug(f"Using safe_z y:{y_position}")
            if 'z_hop' in safe_z:
                z_hop = safe_z['z_hop']
            if 'z_hop_speed' in safe_z:
                speed = safe_z['z_hop_speed']

        speed = 15 if speed is None else speed
        z_hop = 5 if z_hop is None else z_hop
        self._screen._ws.klippy.gcode_script(f"G91\nG0 Z{z_hop} F{float(speed) * 60}")
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")

        if x_position is not None and y_position is not None:
            logging.debug(f"Configured probing position X: {x_position} Y: {y_position}")
            self._screen._ws.klippy.gcode_script(f'G0 X{x_position} Y{y_position} F3000')
        elif "delta" in self._printer.get_config_section("printer")['kinematics']:
            logging.info("Detected delta kinematics calibrating at 0,0")
            self._screen._ws.klippy.gcode_script('G0 X0 Y0 F3000')
        else:
            self._calculate_position()

    def _calculate_position(self):
        logging.debug("Position not configured, probing the middle of the bed")
        try:
            xmax = float(self._printer.get_config_section("stepper_x")['position_max'])
            ymax = float(self._printer.get_config_section("stepper_y")['position_max'])
        except KeyError:
            logging.error("Couldn't get max position from stepper_x and stepper_y")
            return
        x_position = xmax / 2
        y_position = ymax / 2
        logging.info(f"Center position X:{x_position} Y:{y_position}")

        # Find probe offset
        x_offset = y_offset = None
        if self.probe:
            if "x_offset" in self.probe:
                x_offset = float(self.probe['x_offset'])
            if "y_offset" in self.probe:
                y_offset = float(self.probe['y_offset'])
        logging.info(f"Offset X:{x_offset} Y:{y_offset}")
        if x_offset is not None:
            x_position = x_position - x_offset
        if y_offset is not None:
            y_position = y_position - y_offset

        logging.info(f"Moving to X:{x_position} Y:{y_position}")
        self._screen._ws.klippy.gcode_script(f'G0 X{x_position} Y{y_position} F3000')

    def process_busy(self, busy):
        for button in self.buttons:
            self.buttons[button].set_sensitive((not busy))

    def process_update(self, action, data):
        if action == "notify_status_update":
            if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
                self.widgets['zposition'].set_text("Z: ?")
            elif "gcode_move" in data and "gcode_position" in data['gcode_move']:
                self.update_position(data['gcode_move']['gcode_position'])
            if 'manual_probe' in data:
                if 'is_active' in data['manual_probe']:
                    self.manual_active = data['manual_probe']['is_active']
                if 'command' in data['manual_probe']:
                    if data['manual_probe']['command'] == 'Z_ENDSTOP_CALIBRATE':
                        self.z_offset = float(self._printer.get_config_section("stepper_z")['position_endstop'])
                        self.widgets['whichoffset'].set_text(_("Endstop Offset"))
                        self.widgets['savedoffset'].set_text(f"{self.z_offset:.2f}")
                        self.widgets['probe_z_result'].set_text("")
                    elif data['manual_probe']['command'] == 'PROBE_CALIBRATE':
                        self.z_offset = float(self.probe['z_offset'])
                        self.widgets['whichoffset'].set_text(_("Probe Offset"))
                        self.widgets['savedoffset'].set_text(f"{self.z_offset:.2f}")
                        self.widgets['probe_z_result'].set_text("Проба сработала на Z = ?")  
            if 'probe' in data and 'last_z_result' in data['probe']:
                if data['probe']['last_z_result']:
                    self.last_z_result = data['probe']['last_z_result']
            with contextlib.suppress(Exception):
                if 'probe' in data['configfile']['save_config_pending_items']:
                    self.save_config()
                elif 'stepper_z' in data['configfile']['save_config_pending_items']:
                    self.save_config()
            if self.widgets['probe_z_result'].get_text() != "" and self.manual_active:
                self.widgets['probe_z_result'].show()
                self.widgets['probe_z_result'].set_text("Проба сработала на Z = %.2f" % self.last_z_result)
            else:
                self.widgets['probe_z_result'].hide()
        if action == "notify_gcode_response":
            lower_data = data.lower()
            if "out of range" in lower_data:
                self._screen.show_popup_message(data)
            elif "fail" in lower_data and "use testz" in lower_data:
                self._screen.show_popup_message(_("Failed, adjust position first"))

    def update_position(self, position):
        self.widgets['zposition'].set_text(f"Z: {position[2]:.3f}")
        if self.z_offset:
            if self.widgets['probe_z_result'].get_text() == "": #Если концевик
                self.widgets['zoffset'].set_text(f"{(self.z_offset - position[2]):.3f}")
            # Если проба
            elif self.last_z_result:
                self.widgets['zoffset'].set_text(f"{(self.last_z_result - position[2]):.3f}")

    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.widgets[f"{self.distance}"].get_style_context().remove_class("distbutton_active")
        self.widgets[f"{distance}"].get_style_context().add_class("distbutton_active")
        self.distance = distance

    def move(self, widget, direction):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.testz_move(f"{direction}{self.distance}"))

    def abort(self, widget):
        logging.info("Aborting calibration")
        self._screen._ws.klippy.gcode_script(KlippyGcodes.ABORT)
        # self.buttons_not_calibrating()
        self._screen._menu_go_back()

    def accept(self, widget):
        logging.info("Accepting Z position")
        # self.buttons_calibrating()
        self._screen._ws.klippy.gcode_script(KlippyGcodes.ACCEPT)

    def save_config(self):

        script = {"script": "SAVE_CONFIG"}
        self._screen._confirm_send_action(
            None,
            _("Save configuration?") + "\n\n" + _("Klipper will reboot"),
            "printer.gcode.script",
            script
        )
        
    def buttons_calibrating(self):
        self.buttons['start'].get_style_context().remove_class('color3')
        self.buttons['start'].set_sensitive(False)

        self.buttons['zpos'].set_sensitive(True)
        self.buttons['zpos'].get_style_context().add_class('color4')
        self.buttons['zneg'].set_sensitive(True)
        self.buttons['zneg'].get_style_context().add_class('color1')
        self.buttons['complete'].set_sensitive(True)
        self.buttons['complete'].get_style_context().add_class('color3')
        self.buttons['cancel'].set_sensitive(True)
        self.buttons['cancel'].get_style_context().add_class('color2')

    def buttons_not_calibrating(self):
        self.buttons['start'].get_style_context().add_class('color3')
        self.buttons['start'].set_sensitive(True)

        self.buttons['zpos'].set_sensitive(False)
        self.buttons['zpos'].get_style_context().remove_class('color4')
        self.buttons['zneg'].set_sensitive(False)
        self.buttons['zneg'].get_style_context().remove_class('color1')
        self.buttons['complete'].set_sensitive(False)
        self.buttons['complete'].get_style_context().remove_class('color3')
        self.buttons['cancel'].set_sensitive(False)
        self.buttons['cancel'].get_style_context().remove_class('color2')

    # def activate(self):
    #     # This is only here because klipper doesn't provide a method to detect if it's calibrating
    #     self._screen._ws.klippy.gcode_script(KlippyGcodes.testz_move("+0.001"))
