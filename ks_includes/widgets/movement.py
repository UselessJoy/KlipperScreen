import gi
import logging
import time
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.widgets import movement_area
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

def get_pixel_mm_ratio(full_height, button_height, max_mm, min_mm):
    return (full_height - button_height)/(max_mm - min_mm)

class CoordinateController:
    def __init__(self):
        self.min = {"X": None, "Y": None, "Z": None}
        self.max = {"X": None, "Y": None, "Z": None}
        self.axes = ["X", "Y", "Z"]

    def _validate_axis(self, axis):
        if axis.upper() not in self.axes:
            logging.error(f"Axis must be one of {self.axes}")
            return False
        return True

    def _validate_value(self, value):
        if not isinstance(value, (float, int)):
            logging.error("Value must be float or int")
            return False
        return True

    def set_min(self, axis, value):
        if not self._validate_axis(axis) or not self._validate_value(value):
            return
        self.min[axis.upper()] = value

    def get_min(self, axis):
        if self._validate_axis(axis):
            return self.min[axis.upper()]
    
    def set_max(self, axis, value):
        if not self._validate_axis(axis) or not self._validate_value(value):
            return
        self.max[axis.upper()] = value

    def get_max(self, axis):
        if self._validate_axis(axis):
            return self.max[axis.upper()]
    
    def get_limits(self, axis):
        if self._validate_axis(axis):
          return (self.get_min(axis), self.get_max(axis))

class XYBorderController():
    def __init__(self, movement_area):
        self.movement_area = movement_area
        self.border_status = "inside"
    
    def borders(self, cursor_x, cursor_y, button_width, button_height):
        borders = [
                    cursor_x + button_width/2 < self.movement_area.area_w, #right
                    cursor_x - button_width/2 > 0, #left
                    cursor_y + button_height/2 < self.movement_area.area_h, #bottom
                    cursor_y - button_height/2 > 0, #top
                   ]
        return borders

    def recount(self, correct_x, correct_y, button_width, button_height):
        borders = self.borders(correct_x, correct_y, button_width, button_height)
        if not False in borders:
            return correct_x, correct_y
        elif borders.count(False) > 1:
            self.border_status = "corner"
            return self.corner_overflow(borders, button_width, button_height)
        if not borders[3]:
            self.border_status = "border_top"
            return correct_x, button_height/2
        if not borders[2]:
            self.border_status = "border_bottom"
            return correct_x, self.movement_area.area_h - button_height/2
        if not borders[1]:
            self.border_status = "border_left"
            return button_width/2, correct_y
        if not borders[0]:
            self.border_status = "border_right"
            return self.movement_area.area_w - button_width/2, correct_y
    
    def corner_overflow(self, borders, button_width, button_height):
        if not borders[1] and not borders[3]:
            return button_width/2, button_height/2
        if not borders[0] and not borders[3]:
            return self.movement_area.area_w - button_width/2, button_height/2
        if not borders[1] and not borders[2]:
            return button_width/2, self.movement_area.area_h - button_height/2
        if not borders[0] and not borders[2]:
            return self.movement_area.area_w - button_width/2, self.movement_area.area_h - button_height/2
        
class ZBorderController():
    def __init__(self, movement_area):
        self.movement_area = movement_area
        self.border_status = "inside"
    
    def borders(self, cursor_y, button_height):
        borders = [
                    cursor_y + button_height/2 < self.movement_area.area_h, #bottom
                    cursor_y - button_height/2 > 0, #top
                   ]
        return borders

    def recount(self, correct_y, button_height):
        borders = self.borders(correct_y, button_height)
        if not False in borders:
            return correct_y
        if not borders[1]:
            self.border_status = "border_top"
            return button_height/2
        if not borders[0]:
            self.border_status = "border_bottom"
            return self.movement_area.area_h - button_height/2

class BaseStrategy:
    def __init__(self, movement_area):
        self.movement_area = movement_area
        self.coordinates = CoordinateController()

class ZStrategy(BaseStrategy):
    def __init__(self, movement_area):
        super().__init__(movement_area)
        self.border_controller = ZBorderController(movement_area)
        self.image = self.movement_area.screen.gtk.Image("heater_bed_lines", self.movement_area.screen.width/4, self.movement_area.screen.height*2)
        self.buffer_image = self.movement_area.screen.gtk.Image("heater_bed_outlines", self.movement_area.screen.width/4, self.movement_area.screen.height*2)
        self.label = Gtk.Label(label=_("Must home Z"))
        self.label.set_lines(2)
        self.label.set_justify(Gtk.Justification.CENTER)

        self.cursor_button_width   = 0
        self.cursor_button_height  = 0
        self.pixel_mm_ratio        = 0
        self.mm_pixel_ratio        = 0
        self.zero_pixel_z          = 0
        self.image_width           = 0
        self.image_height          = 0
        self.buffer_image_height   = 0
        
        max_z = float(self.movement_area.printer.get_config_section("stepper_z")['position_max'])
        min_z = 0
        self.coordinates.set_min("Z", min_z)
        self.coordinates.set_max("Z", max_z)

    def init_sizes(self):
        self.image_width = self.image.get_allocation().width
        self.image_height = self.image.get_allocation().height
        self.buffer_image_height = self.buffer_image.get_allocation().height
        self.cursor_button_width = self.image_width
        self.cursor_button_height = int(self.image_height*0.064)
        
        min_z, max_z = self.coordinates.get_limits("Z")
        self.pixel_mm_ratio = get_pixel_mm_ratio(self.movement_area.area_h, self.cursor_button_height, max_z, min_z)
        self.mm_pixel_ratio = 1 / self.pixel_mm_ratio
        self.zero_pixel_z = abs(min_z * self.pixel_mm_ratio)

    def image_to_cursor(self, gcode_position: list[float]):
        cursor_h = self.convert_mm_to_pixel(gcode_position[2])
        return self.movement_area.area_w/2 - self.cursor_button_width/2, cursor_h - self.image_height/2 + self.cursor_button_height/2 + self.zero_pixel_z

    def buffer_image_to_cursor(self, gcode_position: list[float]):
        cursor_h = self.convert_mm_to_pixel(gcode_position[2])
        return self.movement_area.area_w/2 - self.cursor_button_width/2, cursor_h + self.zero_pixel_z

    def convert_mm_to_pixel(self, mm):
        return mm * self.pixel_mm_ratio

    def recount_coordinates(self, x, y):
        correct_x = self.movement_area.area_w/2 - self.image_width/2
        return correct_x, self.border_controller.recount(y, self.cursor_button_height)

    def center_coordinates(self, x, y):
        return x, y - self.image_height/2
  
    def center_buffer(self, x, y):
        return x, y - self.buffer_image_height/2

    def make_move_gcode(self, x, y):
        speed = self.movement_area.screen._config.get_config()['main'].getint("move_speed_z", 20)
        speed = 60 * max(1, speed)
        cmd = self.move_from_layout(x, y, speed)
        self.movement_area.main_gcode.append(cmd)
  
    def move_from_layout(self, pixel_x, pixel_y, speed):
        z_coord = (pixel_y - self.cursor_button_height/2 - self.zero_pixel_z) * self.mm_pixel_ratio
        return f"{KlippyGcodes.MOVE} Z{z_coord:.2f} F{speed}"

    def is_homed_required_axes(self):
        return "z" in self.movement_area.printer.get_stat("toolhead", "homed_axes")

    def mm_speed_to_pixel_speed(self, speed_x, speed_y):
        min_z, max_z = float(self.movement_area.printer.get_config_section("stepper_z")['position_min']), float(self.movement_area.printer.get_config_section("stepper_z")['position_max'])#self.coordinates.get_limits("Z")
        speed_pixel_y = ((speed_y) * (self.movement_area.area_h - self.cursor_button_height)) / (max_z - min_z)
        return 0, speed_pixel_y

    def new_point(self, old_gcode_position, new_gcode_position):
        cathet_z = new_gcode_position[2] - old_gcode_position[2]
        speed = self.movement_area.printer.data['gcode_move']['speed'] / 60
        to_x, to_y = self.buffer_image_to_cursor(new_gcode_position)
        move = {
            "to_x": to_x,
            "to_y": to_y,
            "speed": self.convert_mm_to_pixel(speed),
            'Gy': cathet_z,
            'Gx': 0
        }
        return move

class XYStrategy(BaseStrategy):
    def __init__(self, movement_area):
        super().__init__(movement_area)
        self.border_controller = XYBorderController(movement_area)
        self.image = self.movement_area.screen.gtk.Image("big_extruder", self.movement_area.screen.width*2, self.movement_area.screen.height*2)
        self.buffer_image = self.movement_area.screen.gtk.Image("big_extruder_opacity", self.movement_area.screen.width*2, self.movement_area.screen.height*2)
        self.label = Gtk.Label(label=_("Must home XY"))
        self.label.set_lines(2)
        self.label.set_justify(Gtk.Justification.CENTER)

        self.cursor_button_width = 0
        self.cursor_button_height = 0
        self.pixel_mm_ratio_x = 0
        self.pixel_mm_ratio_y = 0
        self.mm_pixel_ratio_x = 0
        self.mm_pixel_ratio_y = 0
        self.zero_pixel_x = 0
        self.zero_pixel_y = 0
        self.image_width = 0
        self.image_height = 0
        self.buffer_image_width = 0
        self.buffer_image_height = 0
        
        # Инициализируем координаты через CoordinateController
        max_x = float(self.movement_area.printer.get_config_section("stepper_x")['position_max'])
        min_x = float(self.movement_area.printer.get_config_section("stepper_x")['position_min'])
        max_y = float(self.movement_area.printer.get_config_section("stepper_y")['position_max'])
        min_y = float(self.movement_area.printer.get_config_section("stepper_y")['position_min'])
        
        self.coordinates.set_min("X", min_x)
        self.coordinates.set_max("X", max_x)
        self.coordinates.set_min("Y", min_y)
        self.coordinates.set_max("Y", max_y)

    def init_sizes(self):
        self.image_width = self.image.get_allocation().width
        self.image_height = self.image.get_allocation().height
        self.buffer_image_width = self.buffer_image.get_allocation().width
        self.buffer_image_height = self.buffer_image.get_allocation().height
        
        self.cursor_button_width = int(self.image_width*0.032)
        self.cursor_button_height = self.image_height

        min_x, max_x = self.coordinates.get_limits("X")
        min_y, max_y = self.coordinates.get_limits("Y")
        
        self.pixel_mm_ratio_x = get_pixel_mm_ratio(self.movement_area.area_w, self.cursor_button_width, max_x, min_x)
        self.pixel_mm_ratio_y = get_pixel_mm_ratio(self.movement_area.area_h, self.cursor_button_height, max_y, min_y)

        self.mm_pixel_ratio_x = 1 / self.pixel_mm_ratio_x
        self.mm_pixel_ratio_y = 1 / self.pixel_mm_ratio_y
        
        self.zero_pixel_x = abs(min_x * self.pixel_mm_ratio_x)
        self.zero_pixel_y = abs(min_y * self.pixel_mm_ratio_y)

    def image_to_cursor(self, gcode_position: list[float]):
        cursor_w = self.convert_mm_to_pixel_x(gcode_position[0])
        cursor_h = self.convert_mm_to_pixel_y(gcode_position[1])
        return cursor_w - self.image_width/2 + self.cursor_button_width/2 + self.zero_pixel_x, self.movement_area.area_h - (cursor_h + self.cursor_button_height + self.zero_pixel_y)

    def buffer_image_to_cursor(self, gcode_position: list[float]):
        return self.image_to_cursor(gcode_position)

    def convert_mm_to_pixel_x(self, mm):
        return mm * self.pixel_mm_ratio_x

    def convert_mm_to_pixel_y(self, mm):
        return mm * self.pixel_mm_ratio_y

    def recount_coordinates(self, x, y):
        return self.border_controller.recount(x, y, self.cursor_button_width, self.cursor_button_height)

    def center_coordinates(self, x, y):
        return x - self.image_width/2, y - self.cursor_button_height/2
  
    def center_buffer(self, x, y): 
        return x, y - self.cursor_button_height

    def make_move_gcode(self, x, y):
        speed = self.movement_area.screen._config.get_config()['main'].getint("move_speed_xy", 20)
        speed = 60 * max(1, speed)
        cmd = self.move_from_layout(x, y, speed)
        self.movement_area.main_gcode.append(cmd)
  
    def move_from_layout(self, pixel_x, pixel_y, speed):
        x_coord = (pixel_x - self.cursor_button_width/2 - self.zero_pixel_x) * self.mm_pixel_ratio_x
        y_coord = (self.movement_area.area_h - pixel_y - self.cursor_button_height/2 - self.zero_pixel_y) * self.mm_pixel_ratio_y
        
        return f"{KlippyGcodes.MOVE} X{x_coord:.2f} Y{y_coord:.2f} F{speed}"

    def is_homed_required_axes(self):
        logging.info(f"get toolhead homed_axes data: {self.movement_area.printer.get_stat('toolhead', 'homed_axes')}")
        return "x" in self.movement_area.printer.get_stat("toolhead", "homed_axes") and "y" in self.movement_area.printer.get_stat("toolhead", "homed_axes")

    def mm_speed_to_pixel_speed(self, speed_x, speed_y):
        min_x, max_x = float(self.movement_area.printer.get_config_section("stepper_x")['position_min']), float(self.movement_area.printer.get_config_section("stepper_x")['position_max'])#self.coordinates.get_limits("X")
        min_y, max_y = float(self.movement_area.printer.get_config_section("stepper_y")['position_min']), float(self.movement_area.printer.get_config_section("stepper_y")['position_max'])#self.coordinates.get_limits("Y")
        speed_pixel_x = ((speed_x) * (self.movement_area.area_w - self.cursor_button_width)) / (max_x - min_x)
        speed_pixel_y = ((speed_y) * (self.movement_area.area_h - self.cursor_button_height)) / (max_y - min_y)
        return speed_pixel_x, speed_pixel_y

    def new_point(self, old_gcode_position, new_gcode_position):
        cathet_x = new_gcode_position[0] - old_gcode_position[0]
        cathet_y = new_gcode_position[1] - old_gcode_position[1]
        speed = self.movement_area.printer.data['gcode_move']['speed'] * self.movement_area.printer.data['gcode_move']['speed_factor'] / 60
        
        to_x, to_y = self.buffer_image_to_cursor(new_gcode_position)
        move = {
            "to_x": to_x,
            "to_y": to_y,
            "speed": speed,
            'Gx': cathet_x,
            'Gy': -cathet_y
        }
        return move

class MovementArea(Gtk.EventBox):
    def __init__(self, screen, printer, Strategy=XYStrategy, x_size=None, y_size=None):
        super().__init__(resize_mode=False, vexpand=True, hexpand=True)
        self.screen = screen
        self.printer = printer
        self.initialized = False
        self.activated = False
        self.strategy = Strategy(self)
        self.move_controller = MoveController(self)
        self.movement_area = Gtk.Layout()
        self.movement_area.set_resize_mode(False)
        self.main_gcode = []
        self.put_widgets()

        # Параметры поля
        self.area_w = 0
        self.area_h = 0

        self.add(self.movement_area)
        if not x_size:
            x_size = int(self.screen.width/3.5)
        if not y_size:
            y_size = int(self.screen.height/1.5)
        self.set_size_request(x_size, y_size)
        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(.5,.5,.5,.5))
        self.connect("motion-notify-event", self.move_to_cursor)
        self.connect('button-release-event', self.start_move)
        self.connect('button-press-event', self.wait_move)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        GLib.timeout_add(1300, self.init_sizes)

    def ready_to_activate(self):
        return self.strategy.is_homed_required_axes() and not self.activated

    def change_strategy(self, NewStrategy):
        self.activated = False
        self.movement_area.remove(self.strategy.image)
        self.movement_area.remove(self.strategy.buffer_image)
        self.movement_area.remove(self.strategy.label)
        self.strategy = NewStrategy(self)
        self.put_widgets()
        GLib.timeout_add(1300, self.init_sizes)

    def put_widgets(self):
        for child in self.movement_area.get_children():
            self.movement_area.remove(child)
        self.movement_area.put(self.strategy.image, 0, 0)
        self.movement_area.put(self.strategy.buffer_image, 0, 0)
        self.movement_area.put(self.strategy.label, 0, 0)
        self.movement_area.set_opacity(0)
        self.movement_area.show_all()

    def init_sizes(self):
        self.area_w = self.get_allocation().width
        self.area_h = self.get_allocation().height
        self.strategy.init_sizes()
        if self.strategy.is_homed_required_axes():
            self.activate_movement_area()
        else:
            self.deactivate_movement_area()
        self.movement_area.set_opacity(1)
        self.movement_area.show_all()
        return False

    def activate_movement_area(self):
        self.strategy.label.set_opacity(0)
        self.move_controller.init_position(self.printer.data['gcode_move']['gcode_position'])
        image_w, image_h = self.strategy.image_to_cursor(self.printer.data['gcode_move']['gcode_position'])
        self.movement_area.move(self.strategy.image, image_w, image_h)
        buffer_image_w, buffer_image_h = self.strategy.buffer_image_to_cursor(self.printer.data['gcode_move']['gcode_position'])
        self.movement_area.move(self.strategy.buffer_image, buffer_image_w, buffer_image_h)
        self.set_sensitive(True)
        self.activated = True

    def deactivate_movement_area(self):
        self.activated = False
        field_center = self.area_w/2 - self.strategy.image_width/2, self.area_h/2 - self.strategy.image_height/2
        logging.info(f"center coord {field_center} img width {self.strategy.image_width} img height {self.strategy.image_height}")
        self.movement_area.move(self.strategy.image, field_center[0], field_center[1])
        self.movement_area.move(self.strategy.buffer_image, field_center[0], field_center[1])
        label_width = self.strategy.label.get_allocation().width
        start_pixel_for_center = (self.area_w - label_width) if self.area_w > label_width else 0
        start_pixel_for_center = start_pixel_for_center / 2 if start_pixel_for_center > 0 else start_pixel_for_center
        self.strategy.label.set_opacity(1)
        self.movement_area.move(self.strategy.label, start_pixel_for_center, self.area_h/5)
        self.set_sensitive(False)

    def wait_move(self, widget, args):
        self.clicked = True
        self.move_to_cursor(widget, args)

    def move_to_cursor(self, widget, args):
        try:
            recount_width, recount_height = self.strategy.recount_coordinates(args.x, args.y)
            center_width, center_height = self.strategy.center_coordinates(recount_width, recount_height)
            self.movement_area.move(self.strategy.image, center_width, center_height)
        except Exception as e:
            logging.error(f"Error in load coordinates:\n{e}")

    def start_move(self, widget, args):
        self.clicked = False
        recount_width, recount_height = self.strategy.recount_coordinates(args.x, args.y)
        
        self.strategy.make_move_gcode(recount_width, recount_height)
        gcode = '\n'.join(str(cmd) for cmd in self.main_gcode)
        self.screen._ws.klippy.gcode_script(gcode)
        self.main_gcode = []

    def on_external_move(self, new_position):
        logging.info("adding point")
        self.move_controller.add_point(new_position)

    def move(self, image, x, y):
        self.movement_area.move(image, x, y)

class MoveController():
    def __init__(self, movement_area: MovementArea):
        self.movement_area = movement_area
        self.current_point = None
        self.current_gcode_position = None
        self.wait_points = []
        self.is_moving = False
        self.start_time = 0
        self.hypot      = 0
        self.speed_x    = 0
        self.speed_y    = 0
        self.position_x = 0
        self.position_y = 0
        self.timeout_id = None  # ID таймера для управления

    def get_axis_gcode_position(self, axis:str):
        if len(axis) > 1:
            return None
        i = "xyz".find(axis.lower())
        if i == -1:
            return None
        return self.current_gcode_position[i]

    def init_position(self, gcode_position):
        logging.info("init mover position")
        self.current_gcode_position = gcode_position[:]
        self.position_x, self.position_y = self.movement_area.strategy.buffer_image_to_cursor(self.current_gcode_position)

    def add_point(self, new_gcode_position):
        logging.info(f"cur_gcode_pos: {self.current_gcode_position}, new_gcode_pos: {new_gcode_position}")
        point = self.movement_area.strategy.new_point(self.current_gcode_position, new_gcode_position)
        self.current_gcode_position = new_gcode_position[:]
        logging.info(f"created point: {point}")
        if not abs(point['Gx']) + abs(point['Gy']) == 0:
            logging.info("point added")
            self.wait_points.append(point)
            self._start_mover()

    def _start_mover(self):
        if self.timeout_id is None:
            self.timeout_id = GLib.timeout_add(16, self.mover)

    def _stop_mover(self):
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def new_move(self, new_point):
        logging.info("adding move")
        hypot = ((self.position_x - new_point["to_x"])**2 + (self.position_y - new_point["to_y"])**2)**0.5
        ghypot = (new_point["Gx"]**2 + new_point["Gy"]**2)**0.5
        sin_Gx = new_point["Gx"]/ghypot
        sin_Gy = new_point["Gy"]/ghypot
        speed_x = new_point['speed'] * sin_Gx
        speed_y = new_point['speed'] * sin_Gy
        speed_pixel_x, speed_pixel_y = self.movement_area.strategy.mm_speed_to_pixel_speed(speed_x, speed_y)
        return hypot, speed_pixel_x, speed_pixel_y

    def mover(self):
        self.timeout_id = None
        
        if not self.is_moving:
            if len(self.wait_points) == 0:
                return False
            
            self.current_point = self.wait_points.pop(0)
            self.hypot, self.speed_x, self.speed_y = self.new_move(self.current_point)
            self.start_time = time.monotonic()
            self.is_moving = True
        
        time_now = time.monotonic() - self.start_time
        now_x = self.position_x + time_now * self.speed_x
        now_y = self.position_y + time_now * self.speed_y
        gone_distance = ((self.position_x - now_x)**2 + (self.position_y - now_y)**2)**0.5
        
        if self.hypot <= gone_distance:
            self.position_x, self.position_y = now_x, now_y
            self.is_moving = False
            if self.current_point:
                self.movement_area.move(self.movement_area.strategy.buffer_image, self.current_point["to_x"], self.current_point["to_y"])
                self.current_point = None
        else:
            self.movement_area.move(self.movement_area.strategy.buffer_image, now_x, now_y)

        if self.is_moving or len(self.wait_points) > 0:
            self.timeout_id = GLib.timeout_add(16, self.mover)
            return False
        else:
            return False

class ZCalibrateStrategy(BaseStrategy):
    def __init__(self, movement_area):
        super().__init__(movement_area)
        self.border_controller = ZBorderController(movement_area)
        self.image = self.movement_area.screen.gtk.Image("heater_bed_outlines", 300, 300)
        self.buffer_image = self.movement_area.screen.gtk.Image("heater_bed_outlines", 300, 300)
        self.label = Gtk.Label(label=_("Must home Z"))
        self.label.set_lines(2)
        self.label.set_justify(Gtk.Justification.CENTER)

        self.cursor_button_width   = 0
        self.cursor_button_height  = 0
        self.pixel_mm_ratio        = 0
        self.mm_pixel_ratio        = 0
        self.zero_pixel_z          = 0
        self.image_width           = 0
        self.image_height          = 0
        self.buffer_image_height   = 0

        max_z = float(20)
        min_z = float(self.movement_area.printer.get_config_section("stepper_z")['position_endstop']) - 5
        
        self.coordinates.set_min("Z", min_z)
        self.coordinates.set_max("Z", max_z)

    def init_sizes(self):
        self.image_width = self.image.get_allocation().width
        self.image_height = self.image.get_allocation().height
        self.buffer_image_height = self.buffer_image.get_allocation().height
        self.cursor_button_width = self.image_width
        self.cursor_button_height = int(self.image_height)#int(self.image_height*0.064)
        
        min_z, max_z = self.coordinates.get_limits("Z")
        self.pixel_mm_ratio = get_pixel_mm_ratio(self.movement_area.area_h, self.cursor_button_height, max_z, min_z)
        self.mm_pixel_ratio = 1 / self.pixel_mm_ratio
        self.zero_pixel_z = abs(min_z * self.pixel_mm_ratio)

    def image_to_cursor(self, gcode_position: list[float]):
        cursor_h = self.convert_mm_to_pixel(gcode_position[2])
        return self.movement_area.area_w/2 - self.cursor_button_width/2, cursor_h - self.image_height/2 + self.cursor_button_height/2 + self.zero_pixel_z

    def buffer_image_to_cursor(self, gcode_position: list[float]):
        cursor_h = self.convert_mm_to_pixel(gcode_position[2])
        return self.movement_area.area_w/2 - self.cursor_button_width/2, cursor_h + self.zero_pixel_z

    def convert_mm_to_pixel(self, mm):
        return mm * self.pixel_mm_ratio

    def recount_coordinates(self, x, y):
        correct_x = self.movement_area.area_w/2 - self.image_width/2
        return correct_x, self.border_controller.recount(y, self.cursor_button_height)

    def center_coordinates(self, x, y):
        return x, y - self.image_height/2
    
    def center_buffer(self, x, y):
        return x, y - self.buffer_image_height/2

    def make_move_gcode(self, x, y):
        speed = self.movement_area.screen._config.get_config()['main'].getint("move_speed_z", 20)
        speed = 60 * max(1, speed)
        cmd = self.move_from_layout(x, y, speed)
        self.movement_area.main_gcode.append(cmd)
    
    def move_from_layout(self, pixel_x, pixel_y, speed):
        z_coord = (pixel_y - self.cursor_button_height/2 - self.zero_pixel_z) * self.mm_pixel_ratio
        return f"{KlippyGcodes.MOVE} Z{z_coord:.2f} F{speed}"

    def is_homed_required_axes(self):
        return "z" in self.movement_area.printer.get_stat("toolhead", "homed_axes")

    def mm_speed_to_pixel_speed(self, speed_x, speed_y):
        min_z, max_z = float(self.movement_area.printer.get_config_section("stepper_z")['position_min']), float(self.movement_area.printer.get_config_section("stepper_z")['position_max'])#self.coordinates.get_limits("Z")
        speed_pixel_y = ((speed_y) * (self.movement_area.area_h - self.cursor_button_height)) / (max_z - min_z)
        return 0, speed_pixel_y

    def new_point(self, old_gcode_position, new_gcode_position):
        cathet_z = new_gcode_position[2] - old_gcode_position[2]
        speed = self.movement_area.printer.data['gcode_move']['speed'] / 60
        to_x, to_y = self.image_to_cursor(new_gcode_position)
        move = {
            "to_x": to_x,
            "to_y": to_y,
            "speed": self.convert_mm_to_pixel(speed),
            'Gy': cathet_z,
            'Gx': 0
        }
        return move