import gi
from ks_includes.widgets.distgrid import DistGrid
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):    
    def __init__(self, screen, title):
        super().__init__(screen, title)

        self.distgrid = DistGrid(screen, ['.1', '.5', '1', '5', '10', '25', '50'])
        # self.distgrid.set_vexpand(False)
        self.buttons = {
            'y-': self._gtk.Button("arrow-left-up", None, "color1"),
            'x+': self._gtk.Button("arrow-right-up", None, "color1"),
            'x-': self._gtk.Button("arrow-left-down", None, "color1"),
            'y+': self._gtk.Button("arrow-right-down", None, "color1"),
            'z+': self._gtk.Button("z-farther", None, "color3"),
            'z-': self._gtk.Button("z-closer", None, "color3"),
            'motors_off': self._gtk.Button("motor-off", _("Off"), "color4"),
        }
        for btn in self.buttons:
           self.buttons[btn].set_vexpand(False)
           self.buttons[btn].set_hexpand(False)
        self.buttons['x+'].connect("clicked", self.force_move, "x", "+")
        self.buttons['x-'].connect("clicked", self.force_move, "x", "-")
        self.buttons['y+'].connect("clicked", self.force_move, "y", "+")
        self.buttons['y-'].connect("clicked", self.force_move, "y", "-")
        self.buttons['z+'].connect("clicked", self.force_move, "z", "-")
        self.buttons['z-'].connect("clicked", self.force_move, "z", "+")
        script = {"script": "M18"}
        self.buttons['motors_off'].connect("clicked", self._screen._confirm_send_action,
                                           _("Are you sure you wish to disable motors?"),
                                           "printer.gcode.script", script)
        self.button_grid = self.init_button_grid()
        self.button_grid.set_valign(Gtk.Align.CENTER)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.add(self.distgrid)
        description_button_box = Gtk.Box(vexpand=True, valign=Gtk.Align.CENTER)
        lbl = _("Использовать с осторожностью: движение не останавливается концевиками и может выходить за пределы рабочей зоны. Экструдер передвинуть к центру перед использованием")
        desc_lbl = Gtk.Label(label = lbl, wrap=True, halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        desc_lbl.get_style_context().add_class("label_chars")
        description_button_box.add(desc_lbl)
        description_button_box.add(self.button_grid)
        main_box.add(description_button_box)
        self.content.add(main_box)

    def force_move(self, widget, axis, direction):
      if self._config.get_config()['main'].getboolean(f"invert_{axis.lower()}", False):
          direction = "-" if direction == "+" else "+"
      stepper = f"stepper_{axis}"
      dist = float(f"{direction}{self.distgrid.get_distance()}")
      speed = 10 if axis == "z" else 130
      try:
          accel = self._printer.get_config_section(stepper)['max_z_accel']
      except:
         accel = 200
      self._screen._ws.klippy.gcode_script(f"FORCE_MOVE STEPPER={stepper} DISTANCE={dist} VELOCITY={speed} ACCEL={accel}") 

    def init_button_grid(self):
      grid = self._gtk.HomogeneousGrid() 

      grid.attach(self.buttons['y-'], 0, 0, 1, 1)
      grid.attach(self.buttons['x+'], 2, 0, 1, 1)
      grid.attach(self.buttons['z+'], 3, 0, 1, 1)

      grid.attach(self.buttons['motors_off'], 1, 1, 1, 1)

      grid.attach(self.buttons['x-'], 0, 2, 1, 1)
      grid.attach(self.buttons['y+'], 2, 2, 1, 1)
      grid.attach(self.buttons['z-'], 3, 2, 1, 1)
      return grid