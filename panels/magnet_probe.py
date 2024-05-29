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
        self.probe_options = {}
        self.dist_buttons = {}
        self.max =  {    
                        "X": float(self._printer.get_config_section("stepper_x")['position_max']),
                        "Y": float(self._printer.get_config_section("stepper_y")['position_max'])
        }
        self.min =  {    
                        "X": float(self._printer.get_config_section("stepper_x")['position_min']),
                        "Y": float(self._printer.get_config_section("stepper_y")['position_min'])
        }
        self.last_coord = {
                            "X": 0,
                            "Y": 0,
        }
        self.confirm_grid = self._gtk.HomogeneousGrid()
        self.action_buttons = {
          'start_adjustment': self._gtk.Button("magnetOff", _("Start adjustment"), "color1", self.bts),
          'accept': self._gtk.Button("complete", _("Complete"), "color1", self.bts),
          'reject': self._gtk.Button("cancel", _("Cancel"), "color1", self.bts),
        }
        funcs = {
          'start_adjustment': self.start_adjustment,
          'accept': self.accept,
          'reject': self.reject
        }
        for button in self.action_buttons:
          self.action_buttons[button].connect("clicked", funcs[button])
          
        # Флаги состояния
        self.is_homing = False
        self.busy = False
        self.is_adjusting = self._printer.get_stat('probe', 'is_adjusting')
        
        self.main_grid = self._gtk.HomogeneousGrid()
        self.info_grid = Gtk.Grid()
        self.info_grid.add(self.create_info_box())
        self.action_grid = Gtk.Grid()
        self.action_grid.add(self.create_action_grid())

        self.main_grid.attach(self.info_grid, 0, 0, 1, 1)
        self.main_grid.attach(self.action_grid, 1, 0, 1, 1)
        self.content.add(self.main_grid)
        
        
    def create_info_box(self):
      probe_config_data = self._printer.get_config_section('probe')
      info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, vexpand = True, valign = Gtk.Align.CENTER, hexpand = True, halign = Gtk.Align.CENTER)
      for field in ['magnet_x', 'magnet_y']:
        self.probe_options[field] = {
          'old': 
            {
              'name': Gtk.Label(label = _(field.lower())), 
              'value': Gtk.Label(label = probe_config_data[field])
            }, 
          'new': 
            {
              'name': Gtk.Label(label = f"{_('New coord')} {_(field.lower())}"), 
              'value': Gtk.Label(probe_config_data[field])
            }, 
          }
        
        label_boxes = {}
        for label_type in self.probe_options[field]:
          label_boxes[label_type] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
          for label in self.probe_options[field][label_type]:
            self.probe_options[field][label_type][label].get_style_context().add_class("label_chars")
            label_boxes[label_type].add(self.probe_options[field][label_type][label])

        field_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        for box_type in label_boxes:
          field_box.add(label_boxes[box_type])
        info_box.add(field_box)  
      return info_box
        
    def create_action_grid(self):
      distgrid = Gtk.Grid()
      for j, i in enumerate(self.distances):
          self.dist_buttons[i] = self._gtk.Button(label=i)
          self.dist_buttons[i].set_direction(Gtk.TextDirection.LTR)
          self.dist_buttons[i].connect("clicked", self.change_distance, i)
          ctx = self.dist_buttons[i].get_style_context()
          if (self._screen.lang_ltr and j == 0) or (not self._screen.lang_ltr and j == len(self.distances) - 1):
              ctx.add_class("distbutton_top")
          elif (not self._screen.lang_ltr and j == 0) or (self._screen.lang_ltr and j == len(self.distances) - 1):
              ctx.add_class("distbutton_bottom")
          else:
              ctx.add_class("distbutton")
          if i == self.distance:
              ctx.add_class("distbutton_active")
          distgrid.attach(self.dist_buttons[i], j, 0, 1, 1)
      
      
      self.keypad_buttons = {
          'x+': self._gtk.Button("arrow-right", None, "color1"),
          'x-': self._gtk.Button("arrow-left", None, "color1"),
          'y+': self._gtk.Button("arrow-up", None, "color1"),
          'y-': self._gtk.Button("arrow-down", None, "color1"),
      }
      self.keypad_buttons['x+'].connect("clicked", self.move, "X", "+")
      self.keypad_buttons['x-'].connect("clicked", self.move, "X", "-")
      self.keypad_buttons['y+'].connect("clicked", self.move, "Y", "+")
      self.keypad_buttons['y-'].connect("clicked", self.move, "Y", "-")
      
      keypad_grid = self._gtk.HomogeneousGrid()
      keypad_grid.set_row_spacing(15)
      keypad_grid.attach(self.keypad_buttons['x+'], 2, 1, 1, 1)
      keypad_grid.attach(self.keypad_buttons['x-'], 0, 1, 1, 1)
      keypad_grid.attach(self.keypad_buttons['y+'], 1, 0, 1, 1)
      keypad_grid.attach(self.keypad_buttons['y-'], 1, 1, 1, 1)
      
      if self.is_adjusting:
        self.confirm_grid.add(self.action_buttons['accept'])
        self.confirm_grid.add(self.action_buttons['reject'])
      else:
        self.confirm_grid.add(self.action_buttons['start_adjustment'])
        
      actions = Gtk.Grid()
      actions.attach(distgrid, 0 ,0, 1, 1)
      actions.attach(keypad_grid, 0, 1, 1, 1)
      actions.attach(self.confirm_grid,0, 2, 1, 1)
      
      return actions
        
        
    def start_adjustment(self, widget):
      self._screen._ws.klippy.gcode_script("START_ADJUSTMENT")
      return

    def accept(self, widget):
      self._screen._ws.klippy.gcode_script(f"ACCEPT_ADJUSTMENT X={self.probe_options['magnet_x']['new']['value'].get_text()} Y={self.probe_options['magnet_y']['new']['value'].get_text()}")
      return

    def reject(self, widget):
      self._screen._ws.klippy.gcode_script("END_ADJUSTMENT")
      return

    def process_update(self, action, data):
        if action == "notify_busy":
            # self.process_busy(data)
            return
        if action != "notify_status_update":
            return
        if "probe" in data:
            if "is_adjusting" in data["probe"]:
                self.is_adjusting = data['probe']['is_adjusting']
                if self.is_adjusting:
                  for child in self.confirm_grid:
                    self.confirm_grid.remove(child)
                  self.confirm_grid.add(self.action_buttons['accept'])
                  self.confirm_grid.add(self.action_buttons['reject'])
                else:
                  for child in self.confirm_grid:
                      self.confirm_grid.remove(child)
                  self.confirm_grid.add(self.action_buttons['start_adjustment'])
                  for axis in 'xy':
                    self.keypad_buttons[f'{axis}+'].set_sensitive(False)
                    self.keypad_buttons[f'{axis}-'].set_sensitive(False)
                    self.probe_options[f"magnet_{axis}"]['new']['value'].set_text(f"?")
                self.confirm_grid.show_all()
              
        if "gcode_move" in data and "gcode_position" in data["gcode_move"]:
            homed_axes = self._printer.get_stat("toolhead", "homed_axes")
            AXIS = {'X': 0, 'Y': 1, 'Z': 2}
            for axis in 'xy':
              axis_up = axis.upper()
              if axis in homed_axes and self.is_adjusting:
                self.last_coord[axis_up] = data['gcode_move']['gcode_position'][AXIS[axis_up]]
                self.keypad_buttons[f'{axis}+'].set_sensitive(True)
                self.keypad_buttons[f'{axis}-'].set_sensitive(True)
                self.probe_options[f"magnet_{axis}"]['new']['value'].set_text(f"{data['gcode_move']['gcode_position'][AXIS[axis_up]]:.2f}")
    
    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.dist_buttons[f"{self.distance}"].get_style_context().remove_class("distbutton_active")
        self.dist_buttons[f"{distance}"].get_style_context().add_class("distbutton_active")
        self.distance = distance
        
    def move(self, widget, axis, direction):
      if self._config.get_config()['main'].getboolean(f"invert_{axis.lower()}", False):
          direction = "-" if direction == "+" else "+"

      dist = f"{direction}{self.distance}"
      speed = self._config.get_config()['main'].getint("move_speed_xy", 20)
      speed = 60 * max(1, speed)
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