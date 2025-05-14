import contextlib
import logging
import gi
from ks_includes.KlippyGcodes import KlippyGcodes
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Diagnostic")
        super().__init__(screen, title)

        self.state_content = {
          'begin': self.BeginContent,
          'choise': self.ChoiseContent,
          'extruder_fan': self.ExtruderFanContent,
          'model_fan': self.ModelFanContent,
          'camera_fan': self.CameraFanContent,
          'back_fan': self.BackFanContent,
          'doors_endstop': self.DoorsEndstopContent,
          'hood_endstop': self.HoodEndstopContent,
          'z_motor': self.ZMotorContent,
          'xy_motors': self.XYMotorsContent,
          'extruder_motor': self.ExtruderMotorContent,
          'neopixel': self.NeopixelContent,
          'self_diagnostic': self.SelfDiagnosticContent,
          'results': self.ResultContent
        }
        self.sd_box = None
        self.d_button_grid = None
        self.state_button_box = None
        self.axes_center = {'X': 150, 'Y': 150}
        self.sd_functions = [
          {
            'name': _("Test magnet probe"),
            'ws_function': self._screen._ws.klippy.test_magnet_probe,
          },
          {
            'name': _("Heating extruder"),
            'ws_params': 'extruder',
            'ws_function': self._screen._ws.klippy.test_heating,
            'function_after': self._screen._ws.klippy.turn_off_all_heaters,
            # 'after_params': ['extruder', 0]
          },
          {
            'name': _("Heating heater bed"),
            'ws_params': 'heater_bed',
            'ws_function': self._screen._ws.klippy.test_heating,
            'function_after': self._screen._ws.klippy.turn_off_all_heaters,
            # 'after_params': ['heater_bed', 0]
          },
        ]
        
        self.states = DoublyLinkedList()
        self.states.append('begin')
        self.states.append('choise')
        
        self.content.add(self.state_content[self.states.current.data]())
        
    def VerticalBox(self):
      return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    def state_box(self, content, next_button_label=_("Next"), next_button_cb = None, next_button_args=[]):
      box = self.VerticalBox()

      next_button = self._gtk.Button(None, next_button_label, style="color4")
      next_button.set_valign(Gtk.Align.END)
      next_button.set_halign(Gtk.Align.END)
      next_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
      if next_button_cb:
        next_button.connect("clicked", next_button_cb, next_button_args)
      else:
        if not self.states.current.next:
          next_button.set_label(_("End diagnosis"))
          next_button.connect("clicked", self.end_diagnosis)
        else:
          next_button.connect("clicked", self.next_state)

      button_box = Gtk.Box()
      if self.states.current.prev:
        back_button = self._gtk.Button(None, _("Back"), style="color2")
        back_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        back_button.set_valign(Gtk.Align.END)
        back_button.set_halign(Gtk.Align.START)
        back_button.connect("clicked", self.back_state)
        button_box.add(back_button)
      button_box.add(next_button)

      box.add(content)
      box.add(button_box)
      return box

    def end_diagnosis(self, widget):
      self.states.go_to('choise')
      self.__update_content(self.states.current.data)

    def back_state(self, widget):
      self.__update_content(self.states.back())

    def next_state(self, widget=None):
      if not self.states.current.next:
        if self.states.current.data == 'choise':
          self._screen.show_popup_message(_("Nothing selected"), just_popup=True)
      self.__update_content(self.states.next())

    def __update_content(self, state):
      for child in self.content:
        self.content.remove(child)
      self.content.add(self.state_content[state]())
      self.content.show_all()

    def BeginContent(self):      
      text = _("1. Please, install the glass on the table if it is missing.\n\n"
               "2. When checking the extruder motor, the filament must be removed\n\n"
               "3. Аll diagnosis will take a few minutes.")
      tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Pango.WrapMode.WORD_CHAR, 
                        pixels_inside_wrap=5, vexpand=True, valign=Gtk.Align.END, margin_left=10)
      tv.get_style_context().add_class("label_chars")
      tv.set_buffer(Gtk.TextBuffer(text=text))
      return self.state_box(tv, _("Continue"))

    def ChoiseContent(self):
      radio_button_group = Gtk.Grid(row_spacing=5, column_spacing=5)#self.VerticalBox()
      # radio_button_group.set_spacing(5)
      filter_d_content = {}
      # Вот сюда добавить __append_fans, а контентом добавить общую функцию fan_confirm_scroll (там будет box скорее всего)
      i = 0
      for k, v in self.state_content.items():
        if k not in ('begin', 'choise', 'results'):
            filter_d_content[k] = v
      for i, state in enumerate(filter_d_content):
        r_button = Gtk.CheckButton(label = _(state))
        r_button.get_style_context().add_class("label_chars")
        if self.states.find(state):
          r_button.set_active(True)
        radio_button_group.attach(r_button, i % 2, i / 2, 1, 1)
        # radio_button_group.add(r_button)
      action_all_box = self.VerticalBox()
      action_all_box.set_hexpand(True)
      action_all_box.set_halign(Gtk.Align.END)
      action_all_box.set_spacing(20)
      select_all_button = self._gtk.Button(None, _("Select all"), style="color3", vexpand=False, hexpand=False)
      select_all_button.set_size_request((self._screen.width - 30) * 0.3, self._screen.height * 0.2)
      select_all_button.connect("clicked", self.action_all, True, radio_button_group)
      disable_all_button = self._gtk.Button(None, _("Disable all"), style="color1", vexpand=False, hexpand=False)
      disable_all_button.set_size_request((self._screen.width - 30) * 0.3, self._screen.height * 0.2)
      disable_all_button.connect("clicked", self.action_all, False, radio_button_group)
      action_all_box.add(select_all_button)
      action_all_box.add(disable_all_button)
      
      choise_box = Gtk.Box(spacing=20, vexpand=True, valign=Gtk.Align.END)
      choise_box.add(radio_button_group)
      choise_box.add(action_all_box)
      return self.state_box(choise_box, _("Start diagnosis"), self.on_next_button_clicked, radio_button_group)
    
    def on_next_button_clicked(self, widget, r_group):
      list_states = list(self.state_content)[2:len(self.state_content)-1]
      list_states.reverse()
      for d_state in list_states:
        self.states.remove(d_state)
      rev_list = []
      for i, ch in enumerate(r_group):
        if ch.get_active():
          rev_list.append(list_states[i])
      for item in reversed(rev_list):
        self.states.append(item)
      self.next_state()

    def action_all(self, widget, active, r_group):
      for child in r_group:
          child.set_active(active)

    def fan_confirm_scroll(self, fan_type):
      fans_scroll = self._screen.gtk.ScrolledWindow()
      fans_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)

      fans_main_grid = self._gtk.HomogeneousGrid()
      fans_main_grid.set_row_spacing(10)
      fans_main_grid.set_column_spacing(10)
      if fan_type == 'fan':
        fans = self._printer.get_fans([], True)
      else:
        fans = self._printer.get_fans([fan_type], False)
      # Здесь fan имеент полное имя [fan_type fan]
      for fan in fans:
        config_fan = self._printer.get_config_section(fan)
        cur_lang = self._config.get_main_config().get("language", 'en')
        fan_name = fan
        if f"locale_{cur_lang}" in config_fan and config_fan[f"locale_{cur_lang}"]:
          fan_name = config_fan[f"locale_{cur_lang}"]
        elif fan.split()[0] == 'fan_back':
          fan_name = _("Elecronic fan")
        title_label = Gtk.Label(_(self.states.current.data), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER)
        title_label.get_style_context().add_class("label_chars")
        cur_fan_grid = Gtk.Grid(column_spacing=5, row_spacing=15, valign=Gtk.Align.CENTER)
        cur_fan_grid.attach(title_label, 0, 0, 2, 1)
        confirm_box = Gtk.Box(spacing = 5, hexpand=True, halign=Gtk.Align.CENTER)
        turn_on_button = self._gtk.Button(None, _("Turn on"), "color3", vexpand=False, hexpand=False)
        turn_on_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        turn_off_button = self._gtk.Button(None, _("Turn off"), "color1", vexpand=False, hexpand=False)
        turn_off_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        confirm_box.add(turn_on_button)
        confirm_box.add(turn_off_button)
        cur_fan_grid.attach(confirm_box, 0, 1, 2, 1)
        fan_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min=0, max=100, step=1)
        # fan_scale.get_style_context().add_class("media")
        fan_scale.set_digits(0)
        fan_scale.set_hexpand(True)
        fan_scale.set_has_origin(True)
        fan_scale.connect("button-release-event", self.set_fan_speed, fan.split()[-1])
        turn_on_button.connect("clicked", self.turn_on, fan.split()[-1], fan_scale)
        turn_off_button.connect("clicked", self.turn_off, fan.split()[-1], fan_scale)
        cur_fan_grid.attach(fan_scale, 0, 2, 2, 1)
        grid_len = len(fans_main_grid.get_children())
        fans_main_grid.attach(cur_fan_grid, grid_len % 3, grid_len / 3, 1, 1)
      fans_scroll.add(fans_main_grid)
      fans_scroll.set_min_content_height(self._gtk.content_height * 0.7)
      fans_scroll.set_min_content_width(self._gtk.content_width * 0.9)
      fans_scroll.connect("realize", self.on_realized, fan.split()[-1])
      fans_scroll.connect("destroy", self.on_destroy, fan.split()[-1])
      return fans_scroll

    def on_realized(self, widget, fan_name):
      self._screen._ws.klippy.gcode_script(f"DEBUG_SET_MANUAL FAN={fan_name} MANUAL=True")
      self._screen._ws.klippy.gcode_script(f"SET_FAN_SPEED fan={fan_name} speed=0")

    def on_destroy(self, widget, fan_name):
      self._screen._ws.klippy.gcode_script(f"SET_FAN_SPEED fan={fan_name} speed=0")
      self._screen._ws.klippy.gcode_script(f"DEBUG_SET_MANUAL FAN={fan_name} MANUAL=False")

    def set_fan_speed(self, widget, event, fan_name):
      value = widget.get_value()
      if fan_name == "fan":
          self._screen._ws.klippy.gcode_script(KlippyGcodes.set_fan_speed(value))
      else:
          self._screen._ws.klippy.gcode_script(f"SET_FAN_SPEED FAN={fan_name} SPEED={float(value) / 100}")

    def turn_on(self, widget, fan_name, fan_scale):
      fan_scale.set_value(100)
      self._screen._ws.klippy.gcode_script(f"SET_FAN_SPEED fan={fan_name} speed=1")
      return

    def turn_off(self, widget, fan_name, fan_scale):
      fan_scale.set_value(0)
      self._screen._ws.klippy.gcode_script(f"SET_FAN_SPEED fan={fan_name} speed=0")
      return

    def ExtruderFanContent(self):
      scroll = self.fan_confirm_scroll('heater_fan')
      return self.state_box(scroll)

    def ModelFanContent(self):
      scroll = self.fan_confirm_scroll('fan')
      return self.state_box(scroll)

    def CameraFanContent(self):
      scroll = self.fan_confirm_scroll('fan_generic')
      return self.state_box(scroll)

    def BackFanContent(self):
      scroll = self.fan_confirm_scroll('fan_back')
      return self.state_box(scroll)

    def endstop_box(self, endstop):
      box = self.VerticalBox()
      box.set_vexpand(True)
      box.set_spacing(20)
      box.set_valign(Gtk.Align.END)
      locale_endstop = _(endstop)
      locale_close = ngettext("closed", "closed", 1 if endstop == 'Hood' else 2)
      locale_open = ngettext("opened", "opened", 1 if endstop == 'Hood' else 2)
      title_label = Gtk.Label(locale_endstop, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER)
      title_label.get_style_context().add_class("label_chars")
      description_label = Gtk.Label(_("Check that endstop state is changing correctly"), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER) # Проверьте, что состояние концевика %s меняется правильно
      description_label.get_style_context().add_class("label_chars")
      box.add(title_label)
      box.add(description_label)
      
      closed_button = self._gtk.Button(None, locale_endstop + " " + locale_close, style="d_button", vexpand=False)
      closed_button.set_halign(Gtk.Align.CENTER)
      closed_button.set_sensitive(False)
      closed_button.set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
      opened_button = self._gtk.Button(None, locale_endstop + " " + locale_open, style="d_button", vexpand=False)
      opened_button.set_halign(Gtk.Align.CENTER)
      opened_button.set_sensitive(False)
      self.state_button_box = Gtk.Box(hexpand=True)
      opened_button.set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
      self.state_button_box.add(closed_button)
      self.state_button_box.add(opened_button)
      box.add(self.state_button_box)
      box.connect("realize", self.on_endstop_box_realized, endstop)
      return box
    
    def on_endstop_box_realized(self, widget, endstop: str):
      is_open = True
      try:
        is_open = self._screen.apiclient.send_request("printer/objects/query?safety_printing")['result']['status']['safety_printing'][f"is_{endstop.lower()}_open"]
      except Exception as e:
        self._screen.show_popup_message(_("Request error: %s") % "printer/objects/query?safety_printing", just_popup=True)
        logging.info(f"Request error: {e}")
      self.update_endstop_buttons(is_open)

    def update_endstop_buttons(self, is_open):
      childs = self.state_button_box.get_children()
      # 0 - closed_button, 1 - opened_button
      # если open => True, то зеленый первый => add class to 1
      # если не open => False, то зеленый нулевой => add class to 0
      self.remove_class(childs[int(not is_open)], "endstop_cur_state")
      self.add_class(childs[int(is_open)], "endstop_cur_state")

    def DoorsEndstopContent(self):
      return self.state_box(self.endstop_box('Doors'))

    def HoodEndstopContent(self):
      return self.state_box(self.endstop_box('Hood'))

    def process_update(self, action, data):
      if action != "notify_status_update" or 'safety_printing' not in data:
        return
      if self.states.current.data in ['doors_endstop', 'hood_endstop']:
        key = self.states.current.data.split('_')[0]
        logging.info(key)
        # Сохранить первые стейты и по реалайзу делать первые стили
        with contextlib.suppress(KeyError):
          # 0 - closed button 1 - opened button
          is_open = data['safety_printing'][f"is_{key}_open"]
          self.update_endstop_buttons(is_open)

    def remove_class(self, widget, style):
      widget.get_style_context().remove_class(style)  
    def add_class(self, widget, style):
      widget.get_style_context().add_class(style) 
 
    def ZMotorContent(self):
      box = Gtk.Box(vexpand=True, hexpand=True, valign=Gtk.Align.END)
      title = Gtk.Label(_("Z motor"))
      title.get_style_context().add_class("label_chars")
      home_button = self._gtk.Button("home", "Z", "color4", hexpand=False, vexpand=False)
      home_button.set_size_request((self._screen.width - 30) * 0.3, self._screen.height * 0.2)
      home_button.set_valign(Gtk.Align.CENTER)

      z_scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, min=0, max=float(self._printer.get_config_section("stepper_z")['position_max']), step=1)
      z_scale.set_sensitive(False)
      home_button.connect("clicked", self.home_z, z_scale)
      z_scale.connect("button-release-event", self.z_move)
      z_scale.set_size_request(0, self._gtk.content_height * 0.5)
      z_scale.get_style_context().add_class("media")
      z_scale.set_digits(0)
      z_scale.set_has_origin(True)
      label = Gtk.Label(_("Before checking the movement,\nmake sure that there are no\nforeign objects under the table"))
      label.get_style_context().add_class("label_chars")
      box.add(home_button)
      box.add(z_scale)
      box.add(label)
      
      main_box = self.VerticalBox()
      main_box.set_spacing(15)
      main_box.add(title)
      main_box.add(box)

      return self.state_box(main_box)

    def home_z(self, widget, scale):
      self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME_Z)
      scale.set_sensitive(True)
    def z_move(self, widget, event):
      self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\n{KlippyGcodes.MOVE} Z{widget.get_value()} F3000")

    def XYMotorsContent(self):
      content_box = self.VerticalBox()
      title = Gtk.Label(label= _("XY motors"))
      title.get_style_context().add_class("label_chars")
      content_box.add(title)
      
      #Тоже что-то типа очереди сделать надо
      dict_boxes = [
        {'lbl': Gtk.Label(_("Bed down")), 
         'btn': self._gtk.Button("home", _("Z 5"), "color2", hexpand=False, vexpand=False),
         'callback': self.bed_down,
         'sensitive': True
        },
        {'lbl': Gtk.Label(_("Turn off motors")), 
         'btn': self._gtk.Button("home", _("Off"), "color3", hexpand=False, vexpand=False),
         'callback': self.disable_motors,
         'sensitive': False
        },
        {'lbl': Gtk.Label(_("Manually move the extruder to the middle of the work area to avoid damaging the printer during the inspection"), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR),# max_width_chars=40),
         'btn': self._gtk.Button("home", _("Complete"), "color4", hexpand=False, vexpand=False),
         'sensitive': False
        }
      ]
      for i, db in enumerate(dict_boxes):
        start_end_box = Gtk.Box()
        start_end_box.set_hexpand(True)
        start_end_box.set_vexpand(False)
        start_end_box.set_valign(Gtk.Align.CENTER)
        db['lbl'].get_style_context().add_class('label_chars')
        db['btn'].set_size_request((self._gtk.content_width) * 0.2, self._gtk.content_height * 0.2)
        if 'callback' in db:
          # Тоже очень плохо
          db['btn'].connect("clicked", db['callback'], dict_boxes[i + 1]['btn'])
        db['btn'].set_sensitive(db['sensitive'])
        start_end_box.pack_start(db['lbl'], False, False, 0)
        start_end_box.pack_end(db['btn'], False, False, 0)
        content_box.add(start_end_box)

      main_box = self.VerticalBox()

      pass_button = self._gtk.Button(None, _("Pass diagnostic"), style="color3", vexpand=False, hexpand=False)
      pass_button.set_size_request((self._gtk.content_width - 30) * 0.33, self._gtk.content_height * 0.2)
      pass_button.connect("clicked", self.next_state)
      next_button = self._gtk.Button(None, _("Next"), style="color4", vexpand=False, hexpand=False)
      next_button.connect("clicked", self.to_xy_motors_check)
      next_button.set_sensitive(False)
      dict_boxes[-1]['btn'].connect("clicked", self.ready, next_button)
      
      back_button = self._gtk.Button(None, _("Back"), style="color2", vexpand=False, hexpand=False)
      back_button.connect("clicked", self.back_state)

      button_grid = Gtk.Grid(column_homogeneous=True, vexpand=True, valign=Gtk.Align.END)
      button_grid.attach(back_button, 0, 0, 1, 1)
      button_grid.attach(pass_button, 1, 0, 1, 1)
      button_grid.attach(next_button, 2, 0, 1, 1)

      main_box.add(content_box)
      main_box.add(button_grid)
      
      try:
        z_pos = self._printer.get_stat("toolhead", "position")[2]
        if z_pos >= 5:
          self.bed_down(None, dict_boxes[1]['btn'], False)
          homed_axes = self._printer.get_stat("toolhead", "homed_axes")
          if 'x' not in homed_axes and 'y' not in homed_axes:
            self.disable_motors(None, dict_boxes[2]['btn'])
      except:
        pass
      return main_box

    def bed_down(self, widget=None, next_button = None, run_gcode=True):
      if next_button:
        next_button.set_sensitive(True)
      if run_gcode:
        self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.HOME_Z}\nG0 Z5")

    def disable_motors(self, widget=None, next_button = None):
      if next_button:
        next_button.set_sensitive(True)
      self._screen._ws.klippy.gcode_script(KlippyGcodes.DISABLE_MOTORS)

    def ready(self, widget, next_button):
      next_button.set_sensitive(True)

    def to_xy_motors_check(self, widget):
      title = Gtk.Label(label= _("XY motors"))
      title.get_style_context().add_class("label_chars")
      
      x_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min=-50, max=50, step=1)
      x_scale.connect("button-release-event", self.xy_move, "X")
      x_scale.set_vexpand(True)
      x_scale.set_valign(Gtk.Align.CENTER)
      x_scale.set_size_request(self._gtk.content_width * 0.5, 0)
      x_scale.get_style_context().add_class("media")
      x_scale.set_digits(0)
      values = [-50, 0, 50]
      for val in values:
        x_scale.add_mark(val, Gtk.PositionType.BOTTOM, "X" if not val else str(val))
      x_scale.set_value(0)
      y_scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, min=-50, max=50, step=1)
      y_scale.set_inverted(True)
      y_scale.connect("button-release-event", self.xy_move, "Y")
      y_scale.set_size_request(0, self._gtk.content_height * 0.6)
      y_scale.get_style_context().add_class("media")
      y_scale.set_digits(0)
      y_scale.set_hexpand(True)
      y_scale.set_halign(Gtk.Align.END)
      values = [-50, 0, 50]
      for val in values:
        y_scale.add_mark(val, Gtk.PositionType.LEFT, "Y" if not val else str(val))
      y_scale.set_value(0)
      info_button = self._gtk.Button("info", style="round_button")#, scale=0.7)
      info_button.set_halign(Gtk.Align.END)
      info_button.set_valign(Gtk.Align.START)
      info_popover = Gtk.Popover.new(info_button)
      info_popover.set_position(Gtk.PositionType.BOTTOM)
      info_popover.set_halign(Gtk.Align.CENTER)
      msg = Gtk.Button(label=_("If the movement is in the opposite direction:\n"
                                "1. Check the engine cables.\n"
                                "2. Check the engine settings in the printer configuration file.\n\n"
                                "If the movement is diagonal:\n"
                                "1. One of the engines is not working. Check the motors, cables and their connection.\n"
                                "2. The pulley is not fixed on the motor shaft. Check the tightening of the pulley locking screws."))
      msg.set_hexpand(True)
      msg.set_vexpand(True)
      msg.get_child().set_max_width_chars(40)
      msg.get_child().set_line_wrap(True)
      msg.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
      info_popover.add(msg)
      msg.connect("clicked", self.popup_popdown, info_popover)
      info_button.connect("clicked", self.show_info_popover, info_popover)
      c_box = Gtk.Box()
      c_box.add(x_scale)
      c_box.add(y_scale)
      c_box.add(info_button)
      
      main_box = self.VerticalBox()
      main_box.set_vexpand(True)
      main_box.add(title)
      main_box.add(c_box)
      main_box.connect("realize", self.on_xy_box_realized)
      main_box.connect("destroy", self.on_xy_destroy)
      for child in self.content:
        self.content.remove(child)
      self.content.add(self.state_box(main_box))
      self.content.show_all()

    def on_xy_box_realized(self, *args):
      self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_ABSOLUTE}\nSET_KINEMATIC_POSITION X=150 Y=150")

    def on_xy_destroy(self, *args):
      self.disable_motors()

    def xy_move(self, widget, event, axis):
      new_val = widget.get_value()
      # if axis == 'Y':
      #   new_val *= -1
      self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE} {axis}{self.axes_center[axis] + new_val} F3000")

    def popup_popdown(self, widget, popup):
      popup.popdown()
    
    def show_info_popover(self, widget, popup):
      popup.popup()
      popup.show_all()
      
    def ExtruderMotorContent(self):
      title = Gtk.Label(label= _("extruder_motor"), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER)
      title.get_style_context().add_class("label_chars")
      
      box = Gtk.Box(vexpand=True, valign=Gtk.Align.END, hexpand=True, halign=Gtk.Align.CENTER, spacing=15)
      
      extrusion_button = self._gtk.Button(None, _("Extrusion"), style="color3")
      extrusion_button.connect("clicked", self.load_unload)
      extrusion_button.set_valign(Gtk.Align.CENTER)
      extrusion_button.set_halign(Gtk.Align.START)
      extrusion_button.set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
      
      retract_button = self._gtk.Button(None, _("Retract"), style="color1")
      retract_button.connect("clicked", self.load_unload, "-")
      retract_button.set_valign(Gtk.Align.CENTER)
      retract_button.set_halign(Gtk.Align.START)
      retract_button.set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
      
      state_button_box = self.VerticalBox()
      state_button_box.set_spacing(20)
      state_button_box.add(extrusion_button)
      state_button_box.add(retract_button)
      
      comment_label = Gtk.Label(_("Remove the plastic from the extruder before checking"), max_width_chars=20, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER)
      comment_label.get_style_context().add_class("label_chars")
      box.add(state_button_box)
      box.add(comment_label)
      main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 10)
      main_box.add(title)
      main_box.add(box)
      return self.state_box(main_box)
    
    def load_unload(self, widget, direction = ""):
      self._screen._ws.klippy.gcode_script(f"G91\nG92 E0\nG1 E{direction}40 F300")
                
    def NeopixelContent(self):
      box = Gtk.Box()
      title = Gtk.Label(label = _(self.states.current.data), vexpand = True, valign = Gtk.Align.END)
      title.get_style_context().add_class("label_chars")
      colorWheel = Gtk.HSV(vexpand=True, hexpand=True, valign = Gtk.Align.END)
      cw_size = self._gtk.content_width * 0.4
      colorWheel.set_metrics(cw_size, cw_size * 0.1)
      colors = [
          float(self._printer.config['neopixel my_neopixel']['initial_red']),
          float(self._printer.config['neopixel my_neopixel']['initial_green']),
          float(self._printer.config['neopixel my_neopixel']['initial_blue'])
      ]
      hsv = Gtk.rgb_to_hsv(colors[0], colors[1], colors[2])
      colorWheel.set_color(hsv[0], hsv[1], hsv[2])
      enabled = False
      try:
        enabled = self._screen.apiclient.send_request("printer/objects/query?led_control")['result']['status']['led_control']['enabled']
      except Exception as e:
        self._screen.show_popup_message(_("Request error: %s") % "printer/objects/query?led_control", just_popup=True)
        logging.info(f"Request error: {e}")
      colorWheel.set_sensitive(enabled)
      led_button = self._gtk.Button("shutdown", _("Turn off"), "color3")
      led_button.set_valign(Gtk.Align.CENTER)
      led_button.set_halign(Gtk.Align.END)
      led_button.set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
      led_button.set_label(_("Turn off neopixel") if enabled else _("Turn on neopixel"))
      led_button.connect("clicked", self.turn_led, colorWheel)
      colorWheel.connect("changed", self.color_changed)
      
      main_box = self.VerticalBox()
      main_box.add(title)
      box.add(colorWheel)
      box.add(led_button)
      main_box.add(box)
      return self.state_box(main_box)

    def turn_led(self, btn, cw):
      if not cw.get_sensitive():
        self._screen._ws.klippy.turn_on_led()
        cw.set_sensitive(True)
        btn.set_label(_("Turn off neopixel"))
        return
      self._screen._ws.klippy.turn_off_led()
      cw.set_sensitive(False)
      btn.set_label(_("Turn on neopixel"))

    def color_changed(self, cw):
      colors = cw.get_color()
      colors = cw.to_rgb(colors[0], colors[1], colors[2])
      if not cw.is_adjusting():
        self._screen._ws.klippy.set_neopixel_color(self._printer.get_neopixels()[0][9:], colors[0], colors[1], colors[2])
    
    # Потребует переделки
    def SelfDiagnosticContent(self):
      box = self.VerticalBox()
      box.set_vexpand(True)
      title = Gtk.Label(label= _("Self diagnosis"), vexpand=True, valign=Gtk.Align.END)
      title.get_style_context().add_class("label_chars")
      self.sd_box = self.VerticalBox()
      self.sd_box.set_vexpand(True)
      self.sd_box.set_spacing(5)

      for sdf in self.sd_functions:
        btn = self._gtk.Button(None, sdf['name'], style="hide_button")
        btn.get_style_context().add_class("label_chars")
        r_button = Gtk.CheckButton(hexpand=True, halign=Gtk.Align.CENTER)
        btn.connect("clicked", self.set_active_r_button, r_button)
        r_button_grid = self._gtk.HomogeneousGrid()
        r_button_grid.attach(btn, 0, 0, 6, 1)
        r_button_grid.attach(r_button, 7, 0, 3, 1)
        self.sd_box.add(r_button_grid)

      action_all_box = self.VerticalBox()
      action_all_box.set_hexpand(True)
      action_all_box.set_halign(Gtk.Align.END)
      action_all_box.set_spacing(20)
      select_all_button = self._gtk.Button(None, _("Select all"), style="color3", vexpand=False, hexpand=False)
      select_all_button.set_size_request((self._screen.width - 30) * 0.3, self._screen.height * 0.2)
      select_all_button.connect("clicked", self.self_diagnosis_action_all, True)
      disable_all_button = self._gtk.Button(None, _("Disable all"), style="color1", vexpand=False, hexpand=False)
      disable_all_button.set_size_request((self._screen.width - 30) * 0.3, self._screen.height * 0.2)
      disable_all_button.connect("clicked", self.self_diagnosis_action_all, False)
      action_all_box.add(select_all_button)
      action_all_box.add(disable_all_button)

      c_box = Gtk.Box(vexpand=True, valign=Gtk.Align.END)
      c_box.pack_start(self.sd_box, True, True, 5)
      c_box.pack_end(action_all_box, True, False, 5)
      box.add(title)
      box.add(c_box)
    
      main_box = self.VerticalBox()
      
      back_button = self._gtk.Button(None, _("Back"), style="color2", vexpand=False, hexpand=False)
      back_button.set_size_request((self._gtk.content_width - 30) * 0.33, self._gtk.content_height * 0.2)
      back_button.connect("clicked", self.back_state)
      repeat_button = self._gtk.Button(None, _("Repeat"), style="color3", vexpand=False, hexpand=False)
      repeat_button.set_sensitive(False)
      repeat_button.connect("clicked", self.repeat_state, select_all_button, disable_all_button)
      next_button = self._gtk.Button(None, _("Start diagnosis"), style="color4", vexpand=False, hexpand=False)
      next_button.connect("clicked", self.to_self_diagnosis, select_all_button, disable_all_button)

      self.d_button_grid = Gtk.Grid(column_homogeneous=True, vexpand=True, valign=Gtk.Align.END)
      self.d_button_grid.attach(back_button, 0, 0, 1, 1)
      self.d_button_grid.attach(repeat_button, 1, 0, 1, 1)
      self.d_button_grid.attach(next_button, 2, 0, 1, 1)
      
      self.d_button_grid.add(back_button)
      self.d_button_grid.add(next_button)

      main_box.add(box)
      main_box.add(self.d_button_grid)
      return main_box

    def set_active_r_button(self, widget, rb):
      rb.set_active(not rb.get_active())

    def repeat_state(self, widget, *args):
      widget.set_sensitive(False)
      for arg in args:
        arg.set_sensitive(True)
      for i, grid in enumerate(self.sd_box):
        btn = self._gtk.Button(None, self.sd_functions[i]['name'], style="hide_button")
        btn.get_style_context().add_class("label_chars")
        r_button = Gtk.CheckButton(hexpand=True, halign=Gtk.Align.CENTER)
        btn.connect("clicked", self.set_active_r_button, r_button)
        grid.remove(grid.get_child_at(1, 0))
        grid.remove(grid.get_child_at(7, 0))
        grid.attach(btn, 0, 0, 6, 1)
        grid.attach(r_button, 7, 0, 3, 1)
      self.sd_box.show_all()

      self.d_button_grid.remove(self.d_button_grid.get_child_at(2, 0))
      next_button = self._gtk.Button(None, _("Start diagnosis"), style="color4", vexpand=False, hexpand=False)
      next_button.connect("clicked", self.to_self_diagnosis, *args)
      self.d_button_grid.attach(next_button, 2, 0, 1, 1)
      self.d_button_grid.show_all()
      
      
    def self_diagnosis_action_all(self, widget, active):
      for box in self.sd_box:
        box.get_child_at(7, 0).set_active(active)

    # Потребует переделки
    def to_self_diagnosis(self, widget, *args):
      self.available_functions = []
      for i, grid in enumerate(self.sd_box):
        rb = grid.get_child_at(7, 0)
        if rb.get_active():
          self.available_functions.append(self.sd_functions[i])
          self.available_functions[-1]['grid'] = grid
          rb.set_sensitive(False)
      if not len(self.available_functions):
        self._screen.show_popup_message(_("Nothing selected"), just_popup=True)
        return
      for arg in args:
        arg.set_sensitive(False)
      for grid in self.sd_box:
        rb = grid.get_child_at(7, 0)
        if not rb.get_active():
          grid.remove(rb)
          grid.attach(Gtk.Label(label=_("Passed")), 7, 0, 3, 1)
      self.change_next_button(widget)
      self.busy_state()
      self.run_func()
      self.sd_box.show_all()

    def change_next_button(self, widget):
      self.d_button_grid.remove(widget)
      next_button = self._gtk.Button(None, _("Next"), style="color4", vexpand=False, hexpand=False)
      if not self.states.current.next:
        next_button.set_label(_("End diagnosis"))
        next_button.connect("clicked", self.end_diagnosis)
      else:
        next_button.connect("clicked", self.next_state)
      self.d_button_grid.attach(next_button, 2, 0, 1, 1)
      self.d_button_grid.set_sensitive(False)
      self.d_button_grid.show_all()

    def busy_state(self):
      rb = self.available_functions[0]['grid'].get_child_at(7, 0)
      self.available_functions[0]['grid'].remove(rb)
      spinner = Gtk.Spinner(hexpand=True, halign=Gtk.Align.CENTER)
      self.available_functions[0]['grid'].attach(spinner, 7, 0, 3, 1)
      spinner.start()
    
    def run_func(self):
      if 'ws_params' in self.available_functions[0]:
        self.available_functions[0]['ws_function'](self.available_functions[0]['ws_params'], callback=self.callback)
      else:
        self.available_functions[0]['ws_function'](callback=self.callback)

    def callback(self, result, method, params):
      grid = self.available_functions[0]['grid']
      rb = grid.get_child_at(7, 0)
      grid.remove(rb)
      logging.info(f"result for {method}: {result}\n")
      img = self._gtk.Image("cancel")
      if 'result' in result:
        if 'test_result' in result['result'] and result['result']['test_result']:
          img = self._gtk.Image("complete")
          if 'function_after' in self.available_functions[0]:
            # Как-то по-другому сделать
            # h, t = self.available_functions[0]['after_params'][0], self.available_functions[0]['after_params'][1]
            self.available_functions[0]['function_after']()#h, t
      grid.attach(img, 7, 0, 3, 1)
      self.available_functions.pop(0)
      if len(self.available_functions):
        self.busy_state()
        self.run_func()
      else:
        for ch in self.d_button_grid:
          ch.set_sensitive(True)
        self.d_button_grid.set_sensitive(True)
      self.sd_box.show_all()

    def ResultContent(self):
      box = self.VerticalBox()
      lbl = Gtk.Label(label= "ResultContent")
      box.add(lbl)
      return self.state_box(box)

class Node:
    def __init__(self, data):
        self.data = data
        self.prev = None  # Ссылка на предыдущий элемент
        self.next = None  # Ссылка на следующий элемент

class DoublyLinkedList:
  def __init__(self):
      self.current: Node = None
      self.head = None  # Начальный (первый) узел
      self.tail = None  # Конечный (последний) узел
  
  def append(self, data):
    new_node = Node(data)
    if self.head is None:  # Если список пуст
        self.head = self.tail = self.current = new_node  # Первый элемент — и голова, и хвост
    else:
        self.tail.next = new_node  # Связываем текущий хвост с новым узлом
        new_node.prev = self.tail  # Связываем новый узел с текущим хвостом
        self.tail = new_node  # Обновляем хвост

  def prepend(self, data):
    new_node = Node(data)
    if self.head is None:
      self.head = self.tail = self.current = new_node
    else:
      self.head.prev = new_node
      new_node.next = self.head
      self.head = new_node

  def find(self, data):
    current = self.head
    while current:
      if current.data == data:
        return current
      current = current.next
    return None

  def go_to(self, data):
    node = self.find(data)
    if node:
      self.current = node

  # Тут бы и self.current проверять. Но поскольку у нас нет ситации, когда пользователь может удалить меню,
  # находясь в одном из меню диагностики так, чтобы выпасть в None - это излишне. Только если обобщать на
  # возможность использования в других местах приложения
  def remove(self, data):
    if self.head is None:
        return  # Список пуст
    current = self.head
    while current:
        if current.data == data:
            # Если удаляемый элемент - это голова
            if current == self.head:
                self.head = current.next
                if self.head:
                    self.head.prev = None  # Обнуляем указатель на предыдущий узел у новой головы
            # Если удаляемый элемент - это хвост
            elif current == self.tail:
                self.tail = current.prev
                if self.tail:
                    self.tail.next = None  # Обнуляем указатель на следующий узел у нового хвоста
            # Если удаляемый элемент находится в середине
            else:
                current.prev.next = current.next
                current.next.prev = current.prev
            return
        current = current.next

  def next(self):
    if self.current.next:
      self.current = self.current.next
    return self.current.data
    
  def back(self):
    if self.current.prev:
      self.current = self.current.prev
    return self.current.data
