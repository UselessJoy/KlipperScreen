import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib, Gdk

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
import time

def create_panel(*args):
    return MovePanel(*args)


class MovePanel(ScreenPanel):
    distances = ['.1', '.5', '1', '5', '10', '25', '50']
    distance = distances[-2]
    
    def __init__(self, screen, title):
        super().__init__(screen, title)
        
        self.settings = {}
        self.menu = ['move_menu']
        
        self.init = False
        self.label_put = False
        self.image = self._gtk.Image("big_extruder", self._screen.width*2, self._screen.height*2)
        self.buffer_image = self._gtk.Image("big_extruder_opacity", self._screen.width*2, self._screen.height*2)
        self.label_XY = Gtk.Label(label=_("Must home XY"))
        self.label_Z = Gtk.Label(label=_("Must home Z"))
        self.label_Z.set_lines(2)
        self.label_Z.set_justify(Gtk.Justification.CENTER)
        self.label_XY.set_lines(2)
        self.label_XY.set_justify(Gtk.Justification.CENTER)
        #self.label_XY.set_text(_("Must home axis first"))
        self.movement_area = Gtk.Layout()
        self.movement_area.put(self.image, 0,0)
        self.movement_area.put(self.buffer_image, 0,0)
        self.movement_area.put(self.label_XY, 0,0)
        self.movement_area.put(self.label_Z, 0,0)
        self.movement_area.set_opacity(0)
        #self.movement_area.put(self.text_image, 0,0)
        self.movement_area.set_resize_mode(False)
        self.border_corner = "inside" #value that indicates which boundary or corner we are at
        self.X_GCODE = self.Y_GCODE = self.Z_GCODE = 0
        self.prev_coord = {
                        "X": None,
                        "Y": None,
                        "Z": None
        }
        self.last_coord = {
                            "X": None,
                            "Y": None,
                            "Z": None
        }
        self.max =  {    
                        "X": float(self._printer.get_config_section("stepper_x")['position_max']),
                        "Y": float(self._printer.get_config_section("stepper_y")['position_max']),
                        "Z": float(self._printer.get_config_section("stepper_z")['position_max'])
        }
        self.min =  {    
                        "X": float(self._printer.get_config_section("stepper_x")['position_min']),
                        "Y": float(self._printer.get_config_section("stepper_y")['position_min']),
                        "Z": float(self._printer.get_config_section("stepper_z")['position_min'])
        }
        self.stepper_endstop = {
                                    "X" : float(self._printer.get_config_section("stepper_x")['position_endstop']), 
                                    "Y" : float(self._printer.get_config_section("stepper_y")['position_endstop']), 
                                    "Z" : float(self._printer.get_config_section("stepper_z")['position_endstop']),
        }
        
        
        self.mode = False
        self.clicked = False
        self.moving_timer = None
        self.printing_timer = None
        
        self.move_to_coordinate = False
        self.time = 0
        self.old_x, self.old_y = 0,0
        self.speed_x, self.speed_y = 0,0
        self.query_points = []
        self.point_parameters = []
        self.busy = False
        self.hypot = 0
        self.overflow_x = self.overflow_y = 0
        self.corrective_time = 0
        self.main_gcode = []
        
        self.area_w = 0
        self.area_h = 0
        self.image_width = 0
        self.image_height = 0
        self.cursor_button_width = 0
        self.cursor_button_height = 0
        self.buffer_image_height = 0
        self.labels['move_menu'] = Gtk.Grid()
        self.event_field = Gtk.EventBox()
        self.event_field.add(self.movement_area)
        self.event_field.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(.5,.5,.5,.5))
        self.event_field.connect("motion-notify-event", self.move_to_cursor)
        self.event_field.connect('button-release-event', self.stop_moving)
        self.event_field.connect('button-press-event', self.area_clicked)
        self.event_field.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.event_field.set_resize_mode(False)
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
            'home_xy': self._gtk.Button("home", _("XY"), "color4"),
            'motors_off': self._gtk.Button("motor-off", _("Off"), "color4"),
            'home_z': self._gtk.Button("home", _("Z"), "color4"),
            'mode' : self._gtk.Button("Z-axis", None, "color2")
        }
        self.buttons['x+'].connect("clicked", self.move, "X", "+")
        self.buttons['x-'].connect("clicked", self.move, "X", "-")
        self.buttons['y+'].connect("clicked", self.move, "Y", "+")
        self.buttons['y-'].connect("clicked", self.move, "Y", "-")
        self.buttons['z+'].connect("clicked", self.move, "Z", "+")
        self.buttons['z-'].connect("clicked", self.move, "Z", "-")
        self.buttons['home'].connect("clicked", self.home)
        self.buttons['home_xy'].connect("clicked", self.homexy)
        self.buttons['home_z'].connect("clicked", self.homez)
        self.buttons['mode'].connect("clicked", self.change_axis)
        script = {"script": "M18"}
        self.buttons['motors_off'].connect("clicked", self._screen._confirm_send_action,
                                           _("Are you sure you wish to disable motors?"),
                                           "printer.gcode.script", script)
        
        adjust = self._gtk.Button("settings", None, "color2", 1, Gtk.PositionType.LEFT, 1)
        adjust.connect("clicked", self.load_menu, 'options', _('Settings'))
        adjust.set_hexpand(False)
        
        
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
            grid.attach_next_to(self.buttons['home_xy'], self.buttons['y+'], Gtk.PositionType.LEFT, 1, 1)
            grid.attach_next_to(self.buttons['home_z'], self.buttons['y+'], Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(adjust, self.buttons['y-'], Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(self.buttons['motors_off'], adjust, Gtk.PositionType.RIGHT, 1, 1)
            grid.attach_next_to(self.buttons['mode'], self.buttons['y-'], Gtk.PositionType.LEFT, 1, 1)

        printer_cfg = self._printer.get_config_section("printer")
        # The max_velocity parameter is not optional in klipper config.
        max_velocity = int(float(printer_cfg["max_velocity"]))
        if "max_z_velocity" in printer_cfg:
            max_z_velocity = int(float(printer_cfg["max_z_velocity"]))
        else:
            max_z_velocity = max_velocity

        configurable_options = [
            {"move_speed_xy": {
                "section": "main", "name": _("XY Speed (mm/s)"), "type": "scale", "value": "50",
                "range": [1, max_velocity], "step": 1}},
            {"move_speed_z": {
                "section": "main", "name": _("Z Speed (mm/s)"), "type": "scale", "value": "10",
                "range": [1, max_z_velocity], "step": 1}}
        ]

        self.labels['options_menu'] = self._gtk.ScrolledWindow()
        self.labels['options'] = Gtk.Grid()
        self.labels['options_menu'].add(self.labels['options'])
        for option in configurable_options:
            name = list(option)[0]
            self.add_option('options', self.settings, name, option[name])
            
            
        for p in ('pos_x', 'pos_y', 'pos_z'):
            self.labels[p] = Gtk.Label()
            # self.labels[p].set_ellipsize(Pango.EllipsizeMode.END)
            # self.labels[p].set_halign(Pango.EllipsizeMode.END)
            self.labels[p].set_width_chars(8)
        positions_grid = self._gtk.HomogeneousGrid()
        positions_grid.set_direction(Gtk.TextDirection.LTR)
        positions_grid.attach(self.labels['pos_x'], 0, 0, 1, 1)
        positions_grid.attach(self.labels['pos_y'], 1, 0, 1, 1)
        positions_grid.attach(self.labels['pos_z'], 2, 0, 1, 1)
        positions_grid.set_resize_mode(False)
        
        
        plug = Gtk.Box()
        plug.set_size_request(100,int(self._screen.height/10))
        self.labels['move_menu'].set_row_spacing(15)
        self.event_field.set_vexpand(True)
        self.event_field.set_hexpand(True)
        self.event_field.set_size_request(int(self._screen.width/3.5),int(self._screen.height/1.5))
        
        self.labels['move_menu'].attach(distgrid, 2, 0, 1, 1)
        self.labels['move_menu'].attach(self.event_field, 0,1,2,1)
        self.labels['move_menu'].attach(grid, 2, 1, 1, 1)
        self.labels['move_menu'].get_style_context().add_class("move_menu")
        #self.labels['move_menu'].attach(plug, 0, 2, 1, 1)
        self.labels['move_menu'].attach(positions_grid, 0, 0, 2, 1)
        self.content.add(self.labels['move_menu'])
        GLib.timeout_add(200, self.init_sizes)
    
    def show_popup(self):
        logging.info("clicked")
        return
    
    
    def init_sizes(self):
        self.area_w = self.event_field.get_allocation().width
        self.area_h = self.event_field.get_allocation().height
        self.image_width = self.image.get_allocation().width
        self.image_height = self.image.get_allocation().height
        homed_axes = self._printer.get_stat("toolhead", "homed_axes")
        if self.mode:
            self.cursor_button_width = self.image_width
            self.cursor_button_height = int(self.image_height*0.064)
            self.buffer_image_height = self.cursor_button_height
            if "z" in homed_axes and "gcode_move" in self._printer.data and "gcode_position" in self._printer.data["gcode_move"]:
                self.old_x, self.old_y, image_to_pixel_w, image_to_pixel_h = self.mm_coordinates_to_pixel_coordinates(0,0, self._printer.data['gcode_move']['gcode_position'][2])
                self.init = True
        else:    
            self.cursor_button_width = int(self.image_width*0.032)
            self.cursor_button_height = self.image_height
            if "x" in homed_axes and "y" in homed_axes and "gcode_move" in self._printer.data and "gcode_position" in self._printer.data["gcode_move"]:
                    self.old_x, self.old_y, image_to_pixel_w, image_to_pixel_h = self.mm_coordinates_to_pixel_coordinates(self._printer.data['gcode_move']['gcode_position'][0], self._printer.data['gcode_move']['gcode_position'][1], 0)
                    self.init = True         
        if self.init:
            self.label_XY.set_opacity(0)
            self.label_Z.set_opacity(0)
            self.movement_area.move(self.image, image_to_pixel_w, image_to_pixel_h)
            if not self.mode:
                self.movement_area.move(self.buffer_image, image_to_pixel_w, image_to_pixel_h)
            else:
                buffer_h = self.mm_coordinates_to_pixel_coordinates_buffer(self._printer.data['gcode_move']['gcode_position'][2])
                self.movement_area.move(self.buffer_image, image_to_pixel_w, buffer_h)
            self.event_field.set_sensitive(True) 
            
        else:
            field_center = self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2
            self.movement_area.move(self.image, field_center[0], field_center[1])
            if self.mode:
                self.movement_area.move(self.buffer_image, field_center[0], field_center[1])
                self.label_XY.set_opacity(0)
                self.label_Z.set_opacity(1)
                label_width = self.label_Z.get_allocation().width
                start_pixel_for_center = (self.area_w - label_width) if self.area_w > label_width else 0
                start_pixel_for_center = start_pixel_for_center / 2 if start_pixel_for_center > 0 else start_pixel_for_center
                self.movement_area.put(self.label_Z, start_pixel_for_center, self.area_h/5)
            else:
                self.movement_area.move(self.buffer_image, field_center[0], field_center[1])
                self.label_Z.set_opacity(0)
                self.label_XY.set_opacity(1)
                label_width = self.label_XY.get_allocation().width
                start_pixel_for_center = (self.area_w - label_width) if self.area_w > label_width else 0
                start_pixel_for_center = start_pixel_for_center / 2 if start_pixel_for_center > 0 else start_pixel_for_center
                self.movement_area.put(self.label_XY, start_pixel_for_center, self.area_h/5)
            self.event_field.set_sensitive(False)
        self.movement_area.set_opacity(1)
        return False
    
    def mm_coordinates_to_pixel_coordinates_buffer(self, z):
        z = 0 if z < 0 else z
        cursor_position_h = abs(((z)*(self.area_h - self.buffer_image_height))/self.max["Z"])
        return cursor_position_h
    
    def mm_coordinates_to_pixel_coordinates(self, x, y, z):
        if self.mode:
            cursor_position_w = self.area_w/2
            z = 0 if z < 0 else z
            cursor_position_h = abs(((z)*(self.area_h - self.cursor_button_height))/self.max["Z"])
            image_to_cursor_w = cursor_position_w - self.image_width/2
            image_to_cursor_h = cursor_position_h - self.image_height/2 + self.cursor_button_height/2
            return cursor_position_w, cursor_position_h + self.cursor_button_height/2, image_to_cursor_w, image_to_cursor_h
            
        else:
            cursor_position_w = abs(((x)*(self.area_w - self.cursor_button_width))/self.max["X"])
            cursor_position_h = abs(((y)*(self.area_h - self.cursor_button_height))/self.max["Y"])
            image_to_cursor_w = -self.image_width/2 + cursor_position_w + self.cursor_button_width/2
            image_to_cursor_h = self.area_h - cursor_position_h - self.cursor_button_height
            return cursor_position_w + self.cursor_button_width/2, self.area_h  - self.cursor_button_height/2 - cursor_position_h, image_to_cursor_w, image_to_cursor_h
    
    def change_axis(self, widget):
        self.movement_area.remove(self.image)
        self.movement_area.remove(self.buffer_image)
        self.init = False
        if self.mode:
            self.mode = False
            self.buttons["mode"].set_image(self._gtk.Image("Z-axis"))
            self.image = self._gtk.Image("big_extruder", self._screen.width*2, self._screen.height*2)
            self.buffer_image = self._gtk.Image("big_extruder_opacity", self._screen.width*2, self._screen.height*2)
        else:
            self.mode = True
            self.buttons["mode"].set_image(self._gtk.Image("XY-axis"))
            self.image = self._gtk.Image("heater_bed_lines", self._screen.width/4, self._screen.height*2)
            self.buffer_image = self._gtk.Image("heater_bed_outlines", self._screen.width/4, self._screen.height*2)
        self.movement_area.put(self.image, self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2)
        self.movement_area.put(self.buffer_image,self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2)
        self.movement_area.show_all()
        GLib.timeout_add(100, self.init_sizes)
  
    def in_borders(self, cursor_x, cursor_y):
        borders = [
                    cursor_x + self.cursor_button_width/2 < self.area_w, #right
                    cursor_x - self.cursor_button_width/2 > 0, #left
                    cursor_y + self.cursor_button_height/2 < self.area_h, #bottom
                    cursor_y - self.cursor_button_height/2 > 0, #top
                   ]
        logging.info(str(borders))
        return borders
    
    def correcting_coordinates(self, current_x, current_y):
        if self.mode:
            correct_x = self.area_w/2 - self.cursor_button_width/2
            correct_y = current_y
            self.y = current_y
            borders = self.in_borders(correct_x, correct_y)
            if not False in borders:
                self.border_corner = "inside"
            else:
                correct_x, correct_y = self.border_overflow(borders, correct_x, correct_y)
        else:
            correct_x = current_x
            correct_y = current_y
            self.x = current_x
            self.y = self.area_h - current_y
            borders = self.in_borders(current_x, current_y)
            if not False in borders:
                self.border_corner = "inside"
            #otherwise we have to set the boundary values according to current width/height depending on the overflow of the other
            #if both of them are overflow, then we need to set the corner position depending on width/height
            elif borders.count(False) == 1:
                correct_x, correct_y = self.border_overflow(borders, correct_x, correct_y)
            else:
                self.border_corner = "corner"
                correct_x, correct_y = self.corner_overflow(borders)
        del borders
        return correct_x, correct_y
    
    def border_overflow(self, borders, correct_x, correct_y):
        if self.mode:#Z
            if not borders[3]:
                self.border_corner = "border_top"
                self.Z_GCODE = 0
                return correct_x, self.cursor_button_height/2
            if not borders[2]:
                self.border_corner = "border_bottom"
                self.Z_GCODE = self.max["Z"]
                return correct_x, self.area_h - self.cursor_button_height/2
        else:#XY
            if not borders[3]:
                self.border_corner = "border_top"
                self.Y_GCODE = self.max["Y"]
                return correct_x, self.cursor_button_height/2
            if not borders[2]:
                self.border_corner = "border_bottom"
                self.Y_GCODE = 0
                return correct_x, self.area_h - self.cursor_button_height/2
            if not borders[1]:
                self.border_corner = "border_left"
                self.X_GCODE = 0
                return self.cursor_button_width/2, correct_y
            if not borders[0]:
                self.border_corner = "border_right"
                self.X_GCODE = self.max["X"]
                return self.area_w - self.cursor_button_width/2, correct_y
        return correct_x, correct_y
        
    def corner_overflow(self, borders):
        if not borders[1] and not borders[3]:
            self.X_GCODE = 0
            self.Y_GCODE = self.max["Y"]
            return  self.cursor_button_width/2, self.cursor_button_height/2
        if not borders[0] and not borders[3]:
            self.X_GCODE = self.max["X"]
            self.Y_GCODE = self.max["Y"]
            return self.area_w - self.cursor_button_width/2, self.cursor_button_height/2
        if not borders[1] and not borders[2]:
            self.X_GCODE = 0
            self.Y_GCODE = 0
            return + self.cursor_button_width/2, self.area_h - self.cursor_button_height/2
        if not borders[0] and not borders[2]:
            self.X_GCODE = self.max["X"]
            self.Y_GCODE = 0
            return self.area_w - self.cursor_button_width/2, self.area_h - self.cursor_button_height/2
    
    def area_clicked(self, widget, args):
        self.clicked = True
        self.move_to_cursor(widget, args)
    
    def stop_moving(self, widget, args):
        self.clicked = False
        gcode = '\n'.join(str(g_command) for g_command in self.main_gcode)
        self._screen._ws.klippy.gcode_script(gcode)
        self.main_gcode = []
    
    def move_to_cursor(self, widget, args):
        try:
            correct_x, correct_y = self.correcting_coordinates(args.x, args.y)
            logging.info("from move " + str(args.x) + " " + str(args.y))
            if self.mode:
                center_width = correct_x
                center_height = correct_y - self.image_height/2
            else:
                center_width = correct_x - self.image_width/2 
                center_height = correct_y - self.image_height/2
            self.movement_area.move(self.image, center_width, center_height)
            if self.clicked:
                self.start_moving(correct_x, correct_y)
        except:
            logging.error("Error in load coordinates")
    
    def start_moving(self, correct_x, correct_y):
        config_key = "move_speed_z" if self.mode else "move_speed_xy"
        speed = None if self.ks_printer_cfg is None else self.ks_printer_cfg.getint(config_key, None)
        if speed is None:
            speed = self._config.get_config()['main'].getint(config_key, 20)
        speed = 60 * max(1, speed)
        self.move_from_layout(correct_x, correct_y, speed)
        
    def move_from_layout(self, pixel_x, pixel_y, speed):
        logging.info("corrective from layout " + str(pixel_x) + " " + str(pixel_y))
        self.cursor_coordinates_to_printer_cordinates(pixel_x, pixel_y)
        if self.mode:
            logging.info(str(self.Z_GCODE))
            self.main_gcode.append(f"{KlippyGcodes.MOVE} Z{self.Z_GCODE:.2f} F{speed}")
        else:
            self.main_gcode.append(f"{KlippyGcodes.MOVE} X{self.X_GCODE:.2f} Y{self.Y_GCODE:.2f} F{speed}")
    
    def print_to_cursor(self):
        self.move_to_coordinate = True
        if len(self.point_parameters) == 0:
            self.point_parameters = self.query_points.pop(0)
            logging.info(f"query len {len(self.query_points)}")
            logging.info(f"point parameters {str(self.point_parameters)}")
            
            self.hypot = ((self.old_x - self.point_parameters["to_x"])**2 + (self.old_y - self.point_parameters["to_y"])**2)**0.5
            if not self.mode:
                Ghypot = ((self.point_parameters["Gx"])**2 + (self.point_parameters["Gy"]**2))**0.5
                sin_Gx = (self.point_parameters["Gx"])/(Ghypot)
                sin_Gy = -1*(self.point_parameters["Gy"])/(Ghypot)
                self.speed_x, self.speed_y = self.speed_mm_to_speed_pixel(self.point_parameters["speed"], sin_Gx, sin_Gy)
            else:
                self.speed_x, self.speed_y = self.speed_mm_to_speed_pixel(self.point_parameters["speed"])
            self.corrective_time = time.time()
        time_now = time.time() - self.corrective_time
        now_x = self.old_x + time_now * self.speed_x
        now_y = self.old_y + time_now * self.speed_y
        dist_now = ((self.old_x - now_x)**2 + (self.old_y - now_y)**2)**0.5
        if self.hypot - dist_now <= 0:
            self.old_x, self.old_y = self.point_parameters["to_x"], self.point_parameters["to_y"]
            self.move_to_coordinate = False
            if self.mode:
                self.movement_area.move(self.buffer_image, self.point_parameters["to_x"] - self.cursor_button_width/2, self.point_parameters["to_y"] - self.cursor_button_height/2)
            else:
                self.movement_area.move(self.buffer_image, self.point_parameters["to_x"] - self.image_width/2, self.point_parameters["to_y"] - self.cursor_button_height/2)
            self.point_parameters = []
            self.corrective_time = time.time()
        if self.move_to_coordinate:
            if self.mode:
                center_width = now_x - self.cursor_button_width/2
                center_height = now_y - self.buffer_image_height/2
            else:
                center_width = now_x - self.image_width/2
                center_height = now_y - self.cursor_button_height/2
            self.movement_area.move(self.buffer_image, center_width, center_height)
        elif len(self.query_points) == 0:
            logging.info("im out from query")
            if self.printing_timer is not None:
                self.corrective_time = 0
                GLib.source_remove(self.printing_timer)
                self.printing_timer = None
        return True
            
    
    def speed_mm_to_speed_pixel(self, speed, sin_x=0, sin_y=0, x=False, y=False):
        mm_speed = ((speed)/60)
        mm_speed_x = mm_speed * sin_x
        mm_speed_y = mm_speed * sin_y
        
        if self.mode:
            speed_pixel_x = 0
            speed_pixel_y = ((mm_speed)*(self.area_h - self.cursor_button_height))/self.max["Z"]
        else:
            speed_pixel_x = ((mm_speed_x)*(self.area_w - self.cursor_button_width))/self.max["X"]
            speed_pixel_y = ((mm_speed_y)*(self.area_h - self.cursor_button_height))/self.max["Y"]
        return speed_pixel_x, speed_pixel_y
    
    def cursor_coordinates_to_printer_cordinates(self, pixel_x, pixel_y):
        logging.info("to printer coordinate " + str(pixel_x) + " " +str(pixel_y))
        if self.mode:
            #if not self.border_corner.endswith("top") and not self.border_corner.endswith("bottom"):
            self.calculate_z_pixels_to_z_mm(pixel_y)
        else:
            if self.border_corner == "corner":
                return
            self.calculate_xy_pixels_to_xy_mm(pixel_x, pixel_y)
    
    def calculate_z_pixels_to_z_mm(self, pixel_y):
        logging.info("calculate " +str(pixel_y))
        self.Z_GCODE = abs(((pixel_y - self.cursor_button_height/2)*self.max["Z"])/(self.area_h - self.cursor_button_height))
        logging.info("calculated Gcode" +str(self.Z_GCODE))
        
    def calculate_xy_pixels_to_xy_mm(self, pixel_x, pixel_y):
        if self.border_corner.startswith("border"):
            if self.border_corner.endswith("left") or self.border_corner.endswith("right"):
                self.Y_GCODE = abs(((self.area_h - pixel_y - self.cursor_button_height/2)*self.max["Y"])/(self.area_h - self.cursor_button_height))
            elif self.border_corner.endswith("top") or self.border_corner.endswith("bottom"):
                self.X_GCODE = abs(((pixel_x - self.cursor_button_width/2)*self.max["X"])/(self.area_w - self.cursor_button_width))
        else:
           self.X_GCODE = abs(((pixel_x - self.cursor_button_width/2)*self.max["X"])/(self.area_w - self.cursor_button_width))
           self.Y_GCODE = abs(((self.area_h - pixel_y - self.cursor_button_height/2)*self.max["Y"])/(self.area_h - self.cursor_button_height))
           
           
    def process_busy(self, busy):
        buttons = ("home", "home_xy", "home_z", "mode")
        self.busy = bool(busy)
        for button in buttons:
                self.buttons[button].set_sensitive(not busy)
    
    def sensitive_axes(self, axes, sensitive):
        buttons = ("x+", "x-", "y+", "y-", "z+", "z-")
        for button in buttons:
            if button.startswith(axes):
                self.buttons[button].set_sensitive(sensitive)

    def process_update(self, action, data):
        change_coord = [False, False, False]
        if action == "notify_busy":
            self.process_busy(data)
            return
        if action != "notify_status_update":
            return
        homed_axes = self._printer.get_stat("toolhead", "homed_axes")
        if "x" in homed_axes:
            if "gcode_move" in data and "gcode_position" in data["gcode_move"]:
                self.labels['pos_x'].set_text(f"X: {data['gcode_move']['gcode_position'][0]:.2f}")
                self.sensitive_axes("x", True)
                if self.last_coord["X"] != data['gcode_move']['gcode_position'][0]:
                    self.prev_coord["X"] = self.last_coord["X"]
                    self.last_coord["X"] = data['gcode_move']['gcode_position'][0]
                    change_coord[0] = True
        else:
            self.labels['pos_x'].set_text("X: ?")
            self.sensitive_axes("x", False)
            self.sensitive_axes("y", False)
            if not self.mode:
                self.init = False
                self.init_sizes()
        if "y" in homed_axes:
            if "gcode_move" in data and "gcode_position" in data["gcode_move"]:
                self.labels['pos_y'].set_text(f"Y: {data['gcode_move']['gcode_position'][1]:.2f}")
                self.sensitive_axes("y", True)
                if self.last_coord["Y"] != data['gcode_move']['gcode_position'][1]:
                    self.prev_coord["Y"] = self.last_coord["Y"]
                    self.last_coord["Y"] = data['gcode_move']['gcode_position'][1]
                    change_coord[1] = True
        else:
            self.labels['pos_y'].set_text("Y: ?")
            self.sensitive_axes("y", False)
            self.sensitive_axes("x", False)
            if not self.mode:
                self.init = False
                self.init_sizes()
        if "z" in homed_axes:
            if "gcode_move" in data and "gcode_position" in data["gcode_move"]:
                self.labels['pos_z'].set_text(f"Z: {data['gcode_move']['gcode_position'][2]:.2f}")
                self.sensitive_axes("z", True)
                if self.last_coord["Z"] != data['gcode_move']['gcode_position'][2]:
                    self.prev_coord["Z"] = self.last_coord["Z"]
                    self.last_coord["Z"] = data['gcode_move']['gcode_position'][2]
                    change_coord[2] = True
        else:
            self.labels['pos_z'].set_text("Z: ?")
            self.sensitive_axes("z", False)
            if self.mode:
                self.init = False
                self.init_sizes()
        if ("x" in homed_axes and "y" in homed_axes or "z" in homed_axes) and "gcode_move" in data and "gcode_position" in data["gcode_move"]:
            if not self.init and self.in_home_position(data):
                self.init_sizes()
            elif self.init and True in change_coord:
                new_x, new_y, new_position_w, new_position_h = self.mm_coordinates_to_pixel_coordinates(data['gcode_move']['gcode_position'][0], 
                                                         data['gcode_move']['gcode_position'][1],
                                                         data['gcode_move']['gcode_position'][2])
                if not self.mode:
                    if change_coord[0] and change_coord[1]:
                        cathet_x = data['gcode_move']['gcode_position'][0] - self.prev_coord["X"]
                        cathet_y = data['gcode_move']['gcode_position'][1] - self.prev_coord["Y"]
                    elif change_coord[0]:
                        cathet_x = data['gcode_move']['gcode_position'][0] - self.prev_coord["X"]
                        cathet_y = 0
                    else:
                        cathet_x = 0
                        cathet_y = data['gcode_move']['gcode_position'][1] - self.prev_coord["Y"]
                    point_tuple = {"to_x" : new_x, "to_y" : new_y, 
                                    "speed" : self._printer.data['gcode_move']['speed'], "Gy": cathet_y, "Gx": cathet_x}
                else:
                    speed = self._printer.data['gcode_move']['speed']
                    if change_coord[2] and data['gcode_move']['gcode_position'][2] - self.prev_coord["Z"] < 0:
                        speed = speed * -1
                    point_tuple = {"to_x" : new_x, "to_y" : new_y, 
                                    "speed" : speed}
                self.query_points.append(point_tuple)
                if self.printing_timer is None:
                    self.printing_timer = GLib.idle_add(self.print_to_cursor)
    
    
    def in_home_position(self, data):
        if self.mode:
            z = abs(float(f"{data['gcode_move']['gcode_position'][2]:.2f}"))
            if z - abs(self.stepper_endstop["Z"]) <= 0.2: #z - abs(self.stepper_endstop["z"]) <= 0.2
                return True
        else:
            x = abs(float(f"{data['gcode_move']['gcode_position'][0]:.2f}")) #x - abs(self.stepper_endstop["x"]) <= 0.2
            y = abs(float(f"{data['gcode_move']['gcode_position'][1]:.2f}")) #y - abs(self.stepper_endstop["y"]) <= 0.2
            if (x - abs(self.stepper_endstop["X"]) <= 0.2) \
                and (y - abs(self.stepper_endstop["Y"]) <= 0.2):
                return True
        return False
    
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
        speed = None if self.ks_printer_cfg is None else self.ks_printer_cfg.getint(config_key, None)
        if speed is None:
            speed = self._config.get_config()['main'].getint(config_key, 20)
        speed = 60 * max(1, speed)
        #! Need For rework (uncorrectly work)
        flt_dist = float(dist)
        if flt_dist < 0:
            if self.min[axis] > self.last_coord[axis] + flt_dist:
                self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\n{KlippyGcodes.MOVE} {axis}{self.min[axis]} F{speed}")
            else:
               self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_RELATIVE}\n{KlippyGcodes.MOVE} {axis}{dist} F{speed}") 
        else:
            if self.max[axis] < self.last_coord[axis] + flt_dist:
                self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\n{KlippyGcodes.MOVE} {axis}{self.max[axis]} F{speed}")
            else:
               self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_RELATIVE}\n{KlippyGcodes.MOVE} {axis}{dist} F{speed}")  

        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")

    def last_mm_to_pixels(self, axis, dist):
        if axis == "X":
            cursor_position_w = ((self.last_coord["X"] + int(dist))*(self.area_w - self.cursor_button_width))/self.max["X"] + self.cursor_button_width/2
            cursor_position_h = self.area_h - (self.last_coord["Y"]*(self.area_h - self.cursor_button_height))/self.max["Y"] - self.cursor_button_height/2
            return cursor_position_w, cursor_position_h
        elif axis == "Y":
            cursor_position_w = (self.prev_coord["X"]*(self.area_w - self.cursor_button_width))/self.max["X"] + self.cursor_button_width/2
            cursor_position_h = self.area_h - ((self.last_coord["Y"] + int(dist))*(self.area_h - self.cursor_button_height))/self.max["Y"] - self.cursor_button_height/2
            return cursor_position_w, cursor_position_h
        elif axis == "Z":
            cursor_position_w = self.area_w/2
            cursor_position_h = ((self.last_coord["Z"] + int(dist))*(self.area_h - self.cursor_button_height))/self.max["Z"]
            return cursor_position_w, cursor_position_h

    def add_option(self, boxname, opt_array, opt_name, option):
        name = Gtk.Label()
        name.set_markup(f"<big><b>{option['name']}</b></big>")
        name.set_hexpand(True)
        name.set_vexpand(True)
        name.set_halign(Gtk.Align.START)
        name.set_valign(Gtk.Align.CENTER)
        name.set_line_wrap(True)
        name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        dev = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        dev.get_style_context().add_class("frame-item")
        dev.set_hexpand(True)
        dev.set_vexpand(False)
        dev.set_valign(Gtk.Align.CENTER)
        dev.add(name)

        if option['type'] == "binary":
            box = Gtk.Box()
            box.set_vexpand(False)
            switch = Gtk.Switch()
            switch.set_hexpand(False)
            switch.set_vexpand(False)
            switch.set_active(self._config.get_config().getboolean(option['section'], opt_name))
            switch.connect("notify::active", self.switch_config_option, option['section'], opt_name)
            switch.set_property("width-request", round(self._gtk.font_size * 7))
            switch.set_property("height-request", round(self._gtk.font_size * 3.5))
            box.add(switch)
            dev.add(box)
        elif option['type'] == "scale":
            dev.set_orientation(Gtk.Orientation.VERTICAL)
            scale = Gtk.Scale.new_with_range(orientation=Gtk.Orientation.HORIZONTAL,
                                             min=option['range'][0], max=option['range'][1], step=option['step'])
            scale.set_hexpand(True)
            scale.set_value(int(self._config.get_config().get(option['section'], opt_name, fallback=option['value'])))
            scale.set_digits(0)
            scale.connect("button-release-event", self.scale_moved, option['section'], opt_name)
            dev.add(scale)

        opt_array[opt_name] = {
            "name": option['name'],
            "row": dev
        }

        opts = sorted(list(opt_array), key=lambda x: opt_array[x]['name'])
        pos = opts.index(opt_name)

        self.labels[boxname].insert_row(pos)
        self.labels[boxname].attach(opt_array[opt_name]['row'], 0, pos, 1, 1)
        self.labels[boxname].show_all()

    def back(self):
        if len(self.menu) > 1:
            self.unload_menu()
            return True
        return False

    def home(self, widget):
        self.init = False
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME)

    def homexy(self, widget):
        self.init = False
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_XY)
    
    def homez(self, widget):
        self.init = False
        self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_Z)

    def z_tilt(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.Z_TILT)

    def quad_gantry_level(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.QUAD_GANTRY_LEVEL)