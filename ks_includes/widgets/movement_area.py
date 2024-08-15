import gi
import logging
import time
from ks_includes.KlippyGcodes import KlippyGcodes
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

# Надо создать общий класс MovementArea и создать наследуемые от него классы XY и Z

class MovementArea(Gtk.EventBox):
    def __init__(self, screen, printer):
        super().__init__(resize_mode=False, vexpand=True, hexpand=True)
        
        self.screen = screen
        self.printer = printer
        # Флаги состояния
        self.init = False
        self.verified = False
        self.is_z_axes = False
        self.clicked = False
        self.move_to_coordinate = False
        # Заполнение поля передвижения
        self.image = self.screen.gtk.Image("big_extruder", self.screen.width*2, self.screen.height*2)
        self.buffer_image = self.screen.gtk.Image("big_extruder_opacity", self.screen.width*2, self.screen.height*2)
        self.label_XY = Gtk.Label(label=_("Must home XY"))
        self.label_Z = Gtk.Label(label=_("Must home Z"))
        self.label_Z.set_lines(2)
        self.label_Z.set_justify(Gtk.Justification.CENTER)
        self.label_XY.set_lines(2)
        self.label_XY.set_justify(Gtk.Justification.CENTER)
        self.movement_area = Gtk.Layout()
        self.movement_area.put(self.image, 0,0)
        self.movement_area.put(self.buffer_image, 0,0)
        self.movement_area.put(self.label_XY, 0,0)
        self.movement_area.put(self.label_Z, 0,0)
        self.movement_area.set_opacity(0)
        self.movement_area.set_resize_mode(False)
        self.border_corner = "inside"
        
        # Графические параметры
        self.area_w = 0
        self.area_h = 0
        self.image_width = 0
        self.image_height = 0
        self.cursor_button_width = 0
        self.cursor_button_height = 0
        self.buffer_image_height = 0
        self.zero_pixel_z = 0
        self.zero_pixel_x = 0
        self.zero_pixel_y = 0
        
        # Параметры для расчета
        self.GCODE = {
            'X': 0,
            'Y': 0,
            'Z': 0
            
        }
        self.prev_coord = {
                        "X": 0,
                        "Y": 0,
                        "Z": 0
        }
        self.last_coord = {
                            "X": 0,
                            "Y": 0,
                            "Z": 0
        }
        self.max =  {    
                        "X": float(self.printer.get_config_section("stepper_x")['position_max']),
                        "Y": float(self.printer.get_config_section("stepper_y")['position_max']),
                        "Z": float(self.printer.get_config_section("stepper_z")['position_max'])
        }
        self.min =  {    
                        "X": float(self.printer.get_config_section("stepper_x")['position_min']),
                        "Y": float(self.printer.get_config_section("stepper_y")['position_min']),
                        "Z": float(self.printer.get_config_section("stepper_z")['position_min'])
        }
        self.stepper_endstop = {
                                    "X" : float(self.printer.get_config_section("stepper_x")['position_endstop']), 
                                    "Y" : float(self.printer.get_config_section("stepper_y")['position_endstop']), 
                                    "Z" : float(self.printer.get_config_section("stepper_z")['position_endstop']),
        }
        self.old_x, self.old_y = 0,0
        self.speed_x, self.speed_y = 0,0
        self.hypot = 0
        
        # Очередь команд
        self.query_points = []
        self.point_parameters = []
        self.main_gcode = []
        
        # Таймеры
        self.moving_timer = None
        self.printing_timer = None
        self.corrective_time = 0
        
        self.add(self.movement_area)
        self.set_size_request(int(self.screen.width/3.5),int(self.screen.height/1.5))
        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(.5,.5,.5,.5))
        self.connect("motion-notify-event", self.move_to_cursor)
        self.connect('button-release-event', self.stop_moving)
        self.connect('button-press-event', self.area_clicked)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        # Сигнал "size-allocate" срабатывает при каждом движении по полю
        #self.movement_area.connect("size-allocate", self.init_sizes)
        GLib.timeout_add(200, self.init_sizes)
        
    def init_sizes(self, *args):
        self.init = False
        self.verified = False
        self.area_w = self.get_allocation().width
        self.area_h = self.get_allocation().height
        self.image_width = self.image.get_allocation().width
        self.image_height = self.image.get_allocation().height
        if self.is_z_axes:
            self.cursor_button_width = self.image_width
            self.cursor_button_height = int(self.image_height*0.064)
            self.buffer_image_height = self.cursor_button_height
            self.zero_pixel_z = abs(((self.min["Z"])*(self.area_h - self.cursor_button_height))/(self.max["Z"] - self.min["Z"]))
        else:
            self.cursor_button_width = int(self.image_width*0.032)
            self.cursor_button_height = self.image_height
            self.zero_pixel_x = abs(((self.min["X"])*(self.area_w - self.cursor_button_width))/(self.max["X"] - self.min["X"]))
            self.zero_pixel_y = abs(((self.min["Y"])*(self.area_h - self.cursor_button_height))/(self.max["Y"] - self.min["Y"]))
        if self.verify_movement_area():
            self.activate_movement_area()
        else:
            self.deactivate_movement_area()
        self.movement_area.set_opacity(1)
        self.init = True
        return False
      
    def verify_movement_area(self):
        if not self.is_z_axes:
            required_axes = "xy"
        else:
            required_axes = "z"
        homed_axes = self.printer.get_stat("toolhead", "homed_axes")    
        if required_axes in homed_axes:
            return True
        return False
    
    def activate_movement_area(self):
        if self.is_z_axes:
            if "gcode_move" in self.printer.data and "gcode_position" in self.printer.data["gcode_move"]:
                self.old_x, self.old_y, image_to_pixel_w, image_to_pixel_h = self.mm_coordinates_to_pixel_coordinates(0,0, self.printer.data['gcode_move']['gcode_position'][2])
            else:
                self.deactivate_movement_area()
                return
        else:
            if "gcode_move" in self.printer.data and "gcode_position" in self.printer.data["gcode_move"]:
                self.old_x, self.old_y, image_to_pixel_w, image_to_pixel_h = self.mm_coordinates_to_pixel_coordinates(self.printer.data['gcode_move']['gcode_position'][0], self.printer.data['gcode_move']['gcode_position'][1], 0)
            else:
                self.deactivate_movement_area()
                return
        self.label_XY.set_opacity(0)
        self.label_Z.set_opacity(0)
        self.movement_area.move(self.image, image_to_pixel_w, image_to_pixel_h)
        if not self.is_z_axes:
            self.movement_area.move(self.buffer_image, image_to_pixel_w, image_to_pixel_h)
        else:
            buffer_h = self.mm_coordinates_to_pixel_coordinates_buffer(self.printer.data['gcode_move']['gcode_position'][2])
            self.movement_area.move(self.buffer_image, image_to_pixel_w, buffer_h)
        self.set_sensitive(True)
        self.verified = True
        return
    
    def deactivate_movement_area(self):
        if self.move_to_coordinate:
            self.remove_moving_timer()
            self.query_points.clear()
            self.point_parameters.clear()
            self.move_to_coordinate = False
        self.verified = False
        field_center = self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2
        self.movement_area.move(self.image, field_center[0], field_center[1])
        if self.is_z_axes:
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
        self.set_sensitive(False)
        return
      
    def mm_coordinates_to_pixel_coordinates_buffer(self, z):
        
        cursor_position_h = ((z)*(self.area_h - self.buffer_image_height))/(self.max["Z"] - self.min["Z"])
        
        return cursor_position_h + self.zero_pixel_z

    def mm_coordinates_to_pixel_coordinates(self, x, y, z):
        if self.is_z_axes:
            
            cursor_position_w = self.area_w/2
            
            cursor_position_h = ((z)*(self.area_h - self.cursor_button_height))/(self.max["Z"] - self.min["Z"])
            
            image_to_cursor_w = cursor_position_w - self.image_width/2
            image_to_cursor_h = cursor_position_h - self.image_height/2 + self.cursor_button_height/2 + self.zero_pixel_z
            
            return cursor_position_w, cursor_position_h + self.cursor_button_height/2 + self.zero_pixel_z, image_to_cursor_w, image_to_cursor_h
            
        else:
            
            cursor_position_w = ((x)*(self.area_w - self.cursor_button_width))/(self.max["X"] - self.min["X"])
            cursor_position_h = ((y)*(self.area_h - self.cursor_button_height))/(self.max["Y"] - self.min["Y"])
            
            image_to_cursor_w = -self.image_width/2 + cursor_position_w + self.zero_pixel_x + self.cursor_button_width/2
            image_to_cursor_h = self.area_h - self.zero_pixel_y - cursor_position_h - self.cursor_button_height
            
            corrective_cursor_position_w = cursor_position_w + self.zero_pixel_x + self.cursor_button_width/2
            corrective_cursor_position_h = self.area_h - self.zero_pixel_y - self.cursor_button_height/2 - cursor_position_h
            
            return corrective_cursor_position_w, corrective_cursor_position_h, image_to_cursor_w, image_to_cursor_h
           
    def stop_moving(self, widget, args):
        self.clicked = False
        correct_x, correct_y = self.correcting_coordinates(args.x, args.y)
        self.start_moving(correct_x, correct_y)
        gcode = '\n'.join(str(g_command) for g_command in self.main_gcode)
        self.screen._ws.klippy.gcode_script(gcode)
        self.main_gcode = []
        
    def area_clicked(self, widget, args):
        self.clicked = True
        self.move_to_cursor(widget, args)
        
    def move_to_cursor(self, widget, args):
      try:
          correct_x, correct_y = self.correcting_coordinates(args.x, args.y)
          #logging.info("from move " + str(args.x) + " " + str(args.y))
          if self.is_z_axes:
              center_width = correct_x
              center_height = correct_y - self.image_height/2
          else:
              center_width = correct_x - self.image_width/2 
              center_height = correct_y - self.image_height/2
          self.movement_area.move(self.image, center_width, center_height)
          # if self.clicked:
          #     self.start_moving(correct_x, correct_y)
      except Exception as e:
          logging.error(f"Error in load coordinates:\n{e}")
    
    def correcting_coordinates(self, current_x, current_y):
        if self.is_z_axes:
            correct_x = self.area_w/2 - self.cursor_button_width/2
            correct_y = current_y
            borders = self.in_borders(correct_x, correct_y)
            if not False in borders:
                self.border_corner = "inside"
            else:
                correct_x, correct_y = self.border_overflow(borders, correct_x, correct_y)
        else:
            correct_x = current_x
            correct_y = current_y
            borders = self.in_borders(current_x, current_y)
            if not False in borders:
                self.border_corner = "inside"
            # Если в borders всего одного переполнение (в массиве находится только одно значение False) - достигнутна одна из граней поля
            # В противном случае - достигнут угол
            elif borders.count(False) == 1:
                correct_x, correct_y = self.border_overflow(borders, correct_x, correct_y)
            else:
                self.border_corner = "corner"
                correct_x, correct_y = self.corner_overflow(borders)
        del borders
        return correct_x, correct_y
      
    def in_borders(self, cursor_x, cursor_y):
        borders = [
                    cursor_x + self.cursor_button_width/2 < self.area_w, #right
                    cursor_x - self.cursor_button_width/2 > 0, #left
                    cursor_y + self.cursor_button_height/2 < self.area_h, #bottom
                    cursor_y - self.cursor_button_height/2 > 0, #top
                   ]
        #logging.info(str(borders))
        return borders

    def border_overflow(self, borders, correct_x, correct_y):
        if self.is_z_axes:
            if not borders[3]:
                self.border_corner = "border_top"
                self.GCODE['Z'] = self.min["Z"]
                return correct_x, self.cursor_button_height/2
            if not borders[2]:
                self.border_corner = "border_bottom"
                self.GCODE['Z'] = self.max["Z"]
                return correct_x, self.area_h - self.cursor_button_height/2
        else:
            if not borders[3]:
                self.border_corner = "border_top"
                self.GCODE['Y'] = self.max["Y"]
                return correct_x, self.cursor_button_height/2
            if not borders[2]:
                self.border_corner = "border_bottom"
                self.GCODE['Y'] = self.min["Y"]
                return correct_x, self.area_h - self.cursor_button_height/2
            if not borders[1]:
                self.border_corner = "border_left"
                self.GCODE['X'] = self.min["X"]
                return self.cursor_button_width/2, correct_y
            if not borders[0]:
                self.border_corner = "border_right"
                self.GCODE['X'] = self.max["X"]
                return self.area_w - self.cursor_button_width/2, correct_y
        return correct_x, correct_y
    
    def corner_overflow(self, borders):
        if not borders[1] and not borders[3]:
            self.GCODE['X'] = self.min["X"]
            self.GCODE['Y'] = self.max["Y"]
            return  self.cursor_button_width/2, self.cursor_button_height/2
        if not borders[0] and not borders[3]:
            self.GCODE['X'] = self.max["X"]
            self.GCODE['Y'] = self.max["Y"]
            return self.area_w - self.cursor_button_width/2, self.cursor_button_height/2
        if not borders[1] and not borders[2]:
            self.GCODE['X'] = self.min["X"]
            self.GCODE['Y'] = self.min["Y"]
            return + self.cursor_button_width/2, self.area_h - self.cursor_button_height/2
        if not borders[0] and not borders[2]:
            self.GCODE['X'] = self.max["X"]
            self.GCODE['Y'] = self.min["Y"]
            return self.area_w - self.cursor_button_width/2, self.area_h - self.cursor_button_height/2
    
    def start_moving(self, correct_x, correct_y):
        config_key = "move_speed_z" if self.is_z_axes else "move_speed_xy"
        speed = self.screen._config.get_config()['main'].getint(config_key, 20)
        speed = 60 * max(1, speed)
        self.move_from_layout(correct_x, correct_y, speed)
        
    def move_from_layout(self, pixel_x, pixel_y, speed):
        #logging.info("corrective from layout " + str(pixel_x) + " " + str(pixel_y))
        self.cursor_coordinates_to_printer_cordinates(pixel_x, pixel_y)
        if self.is_z_axes:
            #logging.info(str(self.GCODE['Z']))
            self.main_gcode.append(f"{KlippyGcodes.MOVE} Z{self.GCODE['Z']:.2f} F{speed}")
        else:
            self.main_gcode.append(f"{KlippyGcodes.MOVE} X{self.GCODE['X']:.2f} Y{self.GCODE['Y']:.2f} F{speed}")
    
    def cursor_coordinates_to_printer_cordinates(self, pixel_x, pixel_y):
        #logging.info("to printer coordinate " + str(pixel_x) + " " +str(pixel_y))
        if self.is_z_axes:
            self.calculate_z_pixels_to_z_mm(pixel_y)
        else:
            if self.border_corner == "corner":
                return
            self.calculate_xy_pixels_to_xy_mm(pixel_x, pixel_y)
    
    def calculate_z_pixels_to_z_mm(self, pixel_y):
        #logging.info("calculate " +str(pixel_y))
        self.GCODE['Z'] = ((pixel_y - self.cursor_button_height/2 - self.zero_pixel_z)*(self.max["Z"] - self.min["Z"]))/(self.area_h - self.cursor_button_height)
        #logging.info("calculated Gcode" +str(self.GCODE['Z']))
        
    def calculate_xy_pixels_to_xy_mm(self, pixel_x, pixel_y):
        if self.border_corner.startswith("border"):
            if self.border_corner.endswith("left") or self.border_corner.endswith("right"):
                self.GCODE['Y'] = ((self.area_h - pixel_y - self.cursor_button_height/2 - self.zero_pixel_y)*(self.max["Y"] - self.min["Y"]))/(self.area_h - self.cursor_button_height)
            elif self.border_corner.endswith("top") or self.border_corner.endswith("bottom"):
                self.GCODE['X'] = ((pixel_x - self.cursor_button_width/2 - self.zero_pixel_x)*(self.max["X"] - self.min["X"]))/(self.area_w - self.cursor_button_width)
        else:
           self.GCODE['X'] = ((pixel_x - self.cursor_button_width/2 - self.zero_pixel_x)*(self.max["X"] - self.min["X"]))/(self.area_w - self.cursor_button_width)
           self.GCODE['Y'] = ((self.area_h - pixel_y - self.cursor_button_height/2 - self.zero_pixel_y)*(self.max["Y"] - self.min["Y"]))/(self.area_h - self.cursor_button_height)
    
    def change_axis(self, widget):
        self.movement_area.remove(self.image)
        self.movement_area.remove(self.buffer_image)
        if self.move_to_coordinate:
            self.remove_moving_timer()
            self.query_points.clear()
            self.point_parameters.clear()
            self.move_to_coordinate = False
        if self.is_z_axes:
            self.is_z_axes = False
            widget.set_image(self.screen.gtk.Image("Z-axis"))
            self.image = self.screen.gtk.Image("big_extruder", self.screen.width*2, self.screen.height*2)
            self.buffer_image = self.screen.gtk.Image("big_extruder_opacity", self.screen.width*2, self.screen.height*2)
        else:
            self.is_z_axes = True
            widget.set_image(self.screen.gtk.Image("XY-axis"))
            self.image = self.screen.gtk.Image("heater_bed_lines", self.screen.width/4, self.screen.height*2)
            self.buffer_image = self.screen.gtk.Image("heater_bed_outlines", self.screen.width/4, self.screen.height*2)
        self.movement_area.put(self.image, self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2)
        self.movement_area.put(self.buffer_image,self.area_w/2 - self.image_width/2, self.area_h/2 - self.image_height/2)
        self.movement_area.show_all()
        GLib.timeout_add(100, self.init_sizes)  
        
    def print_to_cursor(self, finish_cb):
        self.move_to_coordinate = True
        if len(self.point_parameters) == 0:
            try:
                self.point_parameters = self.query_points.pop(0)
                self.hypot = ((self.old_x - self.point_parameters["to_x"])**2 + (self.old_y - self.point_parameters["to_y"])**2)**0.5
                if not self.is_z_axes:
                    Ghypot = ((self.point_parameters["Gx"])**2 + (self.point_parameters["Gy"]**2))**0.5
                    sin_Gx = (self.point_parameters["Gx"])/(Ghypot)
                    sin_Gy = -1*(self.point_parameters["Gy"])/(Ghypot)
                    self.speed_x, self.speed_y = self.speed_mm_to_speed_pixel(self.point_parameters["speed"], sin_Gx, sin_Gy)
                else:
                    self.speed_x, self.speed_y = self.speed_mm_to_speed_pixel(self.point_parameters["speed"])
            except:
                self.move_to_coordinate = False
                self.remove_moving_timer()
                return
            self.corrective_time = time.time()
        time_now = time.time() - self.corrective_time
        now_x = self.old_x + time_now * self.speed_x
        now_y = self.old_y + time_now * self.speed_y
        dist_now = ((self.old_x - now_x)**2 + (self.old_y - now_y)**2)**0.5
        if self.hypot - dist_now <= 0:
            self.old_x, self.old_y = self.point_parameters["to_x"], self.point_parameters["to_y"]
            self.move_to_coordinate = False
            if self.is_z_axes:
                self.movement_area.move(self.buffer_image, self.point_parameters["to_x"] - self.cursor_button_width/2, self.point_parameters["to_y"] - self.cursor_button_height/2)
            else:
                self.movement_area.move(self.buffer_image, self.point_parameters["to_x"] - self.image_width/2, self.point_parameters["to_y"] - self.cursor_button_height/2)
            self.point_parameters = []
            self.corrective_time = time.time()
        if self.move_to_coordinate:
            if self.is_z_axes:
                center_width = now_x - self.cursor_button_width/2
                center_height = now_y - self.buffer_image_height/2
            else:
                center_width = now_x - self.image_width/2
                center_height = now_y - self.cursor_button_height/2
            self.movement_area.move(self.buffer_image, center_width, center_height)
        elif len(self.query_points) == 0:
            self.remove_moving_timer()
            finish_cb()
        return True
      
    def remove_moving_timer(self):
        if self.printing_timer is not None:
            self.corrective_time = 0
            GLib.source_remove(self.printing_timer)
            self.printing_timer = None
    
    
    def speed_mm_to_speed_pixel(self, speed, sin_x=0, sin_y=0, x=False, y=False):
        mm_speed = ((speed)/60)
        mm_speed_x = mm_speed * sin_x
        mm_speed_y = mm_speed * sin_y
        
        if self.is_z_axes:
            speed_pixel_x = 0
            speed_pixel_y = ((mm_speed)*(self.area_h - self.cursor_button_height))/(self.max["Z"] - self.min["Z"])
        else:
            speed_pixel_x = ((mm_speed_x)*(self.area_w - self.cursor_button_width))/(self.max["X"] - self.min["X"])
            speed_pixel_y = ((mm_speed_y)*(self.area_h - self.cursor_button_height))/(self.max["Y"] - self.min["Y"])
        return speed_pixel_x, speed_pixel_y
            
    def onExternalMove(self, new_position, finish_cb):
        new_x, new_y, new_position_w, new_position_h = self.mm_coordinates_to_pixel_coordinates(
            new_position[0], 
            new_position[1],
            new_position[2]
        )
        point_tuple = None
        if not self.is_z_axes and self.prev_coord['X'] and self.prev_coord['Y']:
            cathet_x = new_position[0] - self.prev_coord["X"]
            cathet_y = new_position[1] - self.prev_coord["Y"]
            point_tuple = {"to_x" : new_x, "to_y" : new_y, 
                            "speed" : self.printer.data['gcode_move']['speed'], "Gy": cathet_y, "Gx": cathet_x}      
        elif self.is_z_axes and self.prev_coord['Z']:
            speed = self.printer.data['gcode_move']['speed']
            cathet_z = new_position[2] - self.prev_coord["Z"]
            if cathet_z < 0:
                speed = speed * -1
            point_tuple = {"to_x" : new_x, "to_y" : new_y, 
                            "speed" : speed, 'Gy': cathet_z, 'Gx': 0}
        if point_tuple:
            # Проверка на то, существует ли вообще какое-либо движение
            if not abs(point_tuple['Gx']) + abs(point_tuple['Gy']) == 0:
                self.query_points.append(point_tuple)
                if self.printing_timer is None:
                    self.printing_timer = GLib.idle_add(self.print_to_cursor, finish_cb)    