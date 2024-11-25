import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.movement_area import MovementArea

class Panel(ScreenPanel):
    distances = ['.1', '.5', '1', '5', '10', '25', '50']
    distance = distances[-2]
    
    def __init__(self, screen, title):
        super().__init__(screen, title)
        
        # Флаги состояния
        self.is_homing = False
        # Заполнение панели
        self.labels['move_menu'] = Gtk.Grid()
        self.movement_area = MovementArea(screen, self._printer)
        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            self.labels[i] = self._gtk.Button(label=i)
            self.labels[i].set_direction(Gtk.TextDirection.LTR)
            self.labels[i].connect("clicked", self.change_distance, i)
            ctx = self.labels[i].get_style_context()
            if (self._screen.lang_ltr and j == 0) or (not self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_top")
            elif (not self._screen.lang_ltr and j == 0) or (self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.distance:
                ctx.add_class("distbutton_active")
            distgrid.attach(self.labels[i], j, 0, 1, 1)
        self.buttons = {
            'x+': self._gtk.Button("arrow-right", None, "color1"),
            'x-': self._gtk.Button("arrow-left", None, "color1"),
            'y+': self._gtk.Button("arrow-up", None, "color1"),
            'y-': self._gtk.Button("arrow-down", None, "color1"),
            'z+': self._gtk.Button("z-farther", None, "color3"),
            'z-': self._gtk.Button("z-closer", None, "color3"),
            'home': self._gtk.Button("home", _("All"), "color4"),
            'home_x': self._gtk.Button("home", _("X"), "color4"),
            'home_y': self._gtk.Button("home", _("Y"), "color4"),
            'motors_off': self._gtk.Button("motor-off", _("Off"), "color4"),
            'home_z': self._gtk.Button("home", _("Z"), "color4"),
            'mode' : self._gtk.Button("Z-axis", None, "color2")
        }
        self.buttons['x+'].connect("clicked", self.move, "X", "+")
        self.buttons['x-'].connect("clicked", self.move, "X", "-")
        self.buttons['y+'].connect("clicked", self.move, "Y", "+")
        self.buttons['y-'].connect("clicked", self.move, "Y", "-")
        self.buttons['z+'].connect("clicked", self.move, "Z", "-")
        self.buttons['z-'].connect("clicked", self.move, "Z", "+")
        self.buttons['home'].connect("clicked", self.home)
        self.buttons['home_x'].connect("clicked", self.homex)
        self.buttons['home_y'].connect("clicked", self.homey)
        self.buttons['home_z'].connect("clicked", self.homez)
        self.buttons['mode'].connect("clicked", self.movement_area.change_axis)
        script = {"script": "M18"}
        self.buttons['motors_off'].connect("clicked", self._screen._confirm_send_action,
                                           _("Are you sure you wish to disable motors?"),
                                           "printer.gcode.script", script)
      
        grid = self._gtk.HomogeneousGrid()
        if self._screen.vertical_mode:
            if self._screen.lang_ltr:
                grid.attach(self.buttons['x+'], 2, 1, 1, 1)
                grid.attach(self.buttons['x-'], 0, 1, 1, 1)
                grid.attach(self.buttons['z+'], 2, 2, 1, 1)
                grid.attach(self.buttons['z-'], 0, 2, 1, 1)
            else:
                grid.attach(self.buttons['x+'], 0, 1, 1, 1)
                grid.attach(self.buttons['x-'], 2, 1, 1, 1)
                grid.attach(self.buttons['z+'], 0, 2, 1, 1)
                grid.attach(self.buttons['z-'], 2, 2, 1, 1)
            grid.attach(self.buttons['y+'], 1, 0, 1, 1)
            grid.attach(self.buttons['y-'], 1, 1, 1, 1)

        else:
            if self._screen.lang_ltr:
                grid.attach(self.buttons['x+'], 2, 1, 1, 1)
                grid.attach(self.buttons['x-'], 0, 1, 1, 1)
            else:
                grid.attach(self.buttons['x+'], 0, 1, 1, 1)
                grid.attach(self.buttons['x-'], 2, 1, 1, 1)
            grid.attach(self.buttons['y+'], 1, 0, 1, 1)
            grid.attach(self.buttons['y-'], 1, 2, 1, 1)
            grid.attach(self.buttons['z+'], 3, 0, 1, 1)
            grid.attach(self.buttons['z-'], 3, 1, 1, 1)
            grid.attach(self.buttons['home'], 1, 1, 1, 1)
            grid.attach_next_to(self.buttons['home_x'], self.buttons['y+'], Gtk.PositionType.LEFT, 1, 1)
            grid.attach_next_to(self.buttons['home_y'], self.buttons['y+'], Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(self.buttons['home_z'], self.buttons['y-'], Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(self.buttons['motors_off'], self.buttons['home_z'], Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(self.buttons['mode'], self.buttons['y-'], Gtk.PositionType.LEFT, 1, 1)
                        
        for p in ('X', 'Y', 'Z'):
            self.labels[p] = Gtk.Label()
            self.labels[p].set_width_chars(8)
        positions_grid = self._gtk.HomogeneousGrid()
        positions_grid.set_direction(Gtk.TextDirection.LTR)
        positions_grid.attach(self.labels['X'], 0, 0, 1, 1)
        positions_grid.attach(self.labels['Y'], 1, 0, 1, 1)
        positions_grid.attach(self.labels['Z'], 2, 0, 1, 1)
        positions_grid.set_resize_mode(False)
        
        self.labels['move_menu'].set_row_spacing(15)
        self.labels['move_menu'].attach(distgrid, 2, 0, 1, 1)
        self.labels['move_menu'].attach(self.movement_area, 0,1,2,1)
        self.labels['move_menu'].attach(grid, 2, 1, 1, 1)
        self.labels['move_menu'].get_style_context().add_class("move_menu")
        self.labels['move_menu'].attach(positions_grid, 0, 0, 2, 1)
        self.content.add(self.labels['move_menu'])
    
    def sensitive_axes(self, axes, sensitive):
      for button in [f"{axes}+", f"{axes}-"]:
          self.buttons[button].set_sensitive(sensitive)
                

    def update_axes(self, axes: str, new_position: list):
        AXIS = {'X': 0, 'Y': 1, 'Z': 2}
        axes_up = axes.upper()
        self.labels[axes_up].set_text(f"{axes_up}: {new_position[AXIS[axes_up]]:.2f}")
        self.sensitive_axes(axes, True)
        self.movement_area.prev_coord[axes_up] = self.movement_area.last_coord[axes_up]
        self.movement_area.last_coord[axes_up] = new_position[AXIS[axes_up]]
            
    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        # gcode_position - это координаты последней поступившей команды движения,
        # либо сюда попадают мусорные координаты при парковке принтера по типу X: 400 и т.д.
        # Такие координаты надо как-то отфильтровать
        # Самое адекватное - получить callback от хоуминга из клиппера (Добавил поле is_homing в klipper и добавил его к объектам KS)
        # Нужна переключалка, которая регает хоуминг: пока она True, мы должны пропускать очередные координаты, а также блокировать поле
        # до тех пор, пока не придет сигнал is_homing = False, при котором, следовательно, продолжаем регать новые координаты
        
        # При хоуминге, вне зависимости от поля, происходит блокировка. Чтобы блокировка срабатывала только при хоуминге осей,
        # используемых активным полем (т.е., чтобы при хоуминге Z не блокировалось поле XY), 
        # необходимо, чтобы в klipper в поле homed_axes сбрасывались оси, которые хоумятся
        if "toolhead" in data:
            if "is_homing" in data["toolhead"]:
                self.is_homing = data["toolhead"]["is_homing"]
            if "homed_axes" in data["toolhead"]:
                if data["toolhead"]["homed_axes"] == "":
                    for axes in "xyz":
                        axes_up = axes.upper()
                        self.labels[axes_up].set_text(f"{axes_up}: ?")
                        self.sensitive_axes(axes, False)
                    if self.movement_area.verified:
                        self.movement_area.deactivate_movement_area()
        if "gcode_move" in data and "gcode_position" in data["gcode_move"]:
            homed_axes = self._printer.get_stat("toolhead", "homed_axes")
            for axes in "xyz":
                if axes in homed_axes:
                    self.update_axes(axes, data['gcode_move']['gcode_position'])
                else:
                    axes_up = axes.upper()
                    self.labels[axes_up].set_text(f"{axes_up}: ?")
                    self.sensitive_axes(axes, False)
            if self.movement_area.init:  
                if not self.is_homing:
                    if self.movement_area.verify_movement_area():
                        if not self.movement_area.verified:
                            self.movement_area.activate_movement_area()
                        # self.buttons['mode'].set_sensitive(False)
                        # for axes in 'xyz':
                        #   self.sensitive_axes(axes, False)
                        self.movement_area.onExternalMove(data['gcode_move']['gcode_position'], self.on_finish_move)
                elif self.movement_area.verified:
                    self.movement_area.deactivate_movement_area()

    def on_finish_move(self):
        return
        # self.buttons['mode'].set_sensitive(True)
        # for axes in 'xyz':
        #   self.sensitive_axes(axes, True)
    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.labels[f"{self.distance}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"{distance}"].get_style_context().add_class("distbutton_active")
        self.distance = distance

    def move(self, widget, axis, direction):
        if self._config.get_config()['main'].getboolean(f"invert_{axis.lower()}", False):
            direction = "-" if direction == "+" else "+"

        dist = f"{direction}{self.distance}"
        config_key = "move_speed_z" if axis == "Z" else "move_speed_xy"
        # speed = self.ks_printer_cfg.getint(config_key, 20)
        # if speed is None:
        speed = self._config.get_config()['main'].getint(config_key, 20)
        speed = 60 * max(1, speed)
        flt_dist = float(dist)
        if flt_dist < 0:
            if self.movement_area.min[axis] > self.movement_area.last_coord[axis] + flt_dist:
                self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\n{KlippyGcodes.MOVE} {axis}{self.movement_area.min[axis]} F{speed}")
            else:
               self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_RELATIVE}\n{KlippyGcodes.MOVE} {axis}{dist} F{speed}") 
        else:
            if self.movement_area.max[axis] < self.movement_area.last_coord[axis] + flt_dist:
                self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\n{KlippyGcodes.MOVE} {axis}{self.movement_area.max[axis]} F{speed}")
            else:
               self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_RELATIVE}\n{KlippyGcodes.MOVE} {axis}{dist} F{speed}")  

        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")

    def home(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME)
    
    def homex(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_X)
    
    def homey(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_Y)
    
    def homez(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_Z)

    def z_tilt(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.Z_TILT)

    def quad_gantry_level(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.QUAD_GANTRY_LEVEL)