import gi
from ks_includes.widgets.keyboard import Keyboard
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.typed_entry import TypedEntry, NumberRule, SpaceRule

RESOLUTION_K = {(800, 480): 0.43}

class Panel(ScreenPanel):
  def __init__(self, screen, title):
    super().__init__(screen, title)
    scroll = self._screen.gtk.ScrolledWindow()
    self.was_child_scrolled = False
    adj = Gtk.Adjustment()
    adj.connect("value-changed", self.on_scrolling)
    scroll.set_vadjustment(adj)
    scroll.set_vexpand(True)
    scroll.set_hexpand(True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    self.preheat_grid = Gtk.Grid(row_spacing=20)
    # plusButton = self._screen.gtk.Button("plus", None, "round_button", scale=1)
    # plusButton.connect("clicked", self.add_preheat_row)
    # plusButton.set_hexpand(True)
    # plusButton.set_halign(Gtk.Align.CENTER)
    # plusButton.set_vexpand(True)
    # plusButton.set_valign(Gtk.Align.START)
    box.add(self.preheat_grid)
    # box.add(plusButton)
    scroll.add(box)
    change_temperature_button = self._gtk.Button(None, _("Save changes"), "color3", self.bts)
    change_temperature_button.set_can_focus(False)
    change_temperature_button.set_hexpand(True)
    change_temperature_button.set_halign(Gtk.Align.END)
    change_temperature_button.set_vexpand(True)
    change_temperature_button.set_valign(Gtk.Align.END)
    change_temperature_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
    change_temperature_button.connect("button_release_event", self.change_preheats)
    box.add(change_temperature_button)
    eventBox = Gtk.EventBox()
    eventBox.set_can_focus(True)
    eventBox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    eventBox.connect("button_release_event", self.click_to_eventbox)
    eventBox.add(scroll)
    self.content.add(eventBox)

  def activate(self):
    for child in self.preheat_grid:
      self.preheat_grid.remove(child)
    preheats = self._screen._config.get_default_preheats()
    for i, name in enumerate(preheats):
      self.preheat_grid.attach(self.create_preheat_row(preheats[name], name), 0, i, 1, 1)
  
  def on_scrolling(self, *args):
    self.was_child_scrolled = True

  def create_preheat_row(self, preheat = None, name=None):
    preheat_name_label = Gtk.Label(label=_("Preheat"), hexpand=True, halign=Gtk.Align.START)
    preheat_name_entry = TypedEntry(SpaceRule)
    preheat_name_entry.set_sensitive(False)
    preheat_name_entry.get_style_context().add_class('unused_entry')
    preheat_name_entry.set_hexpand(True)
    preheat_name_entry.set_vexpand(False)
    preheat_name_entry.connect("focus-in-event", self.on_focus_in_event)
    preheat_name_entry.connect("focus-out-event", self.on_focus_out_event)
    preheat_name_entry.connect("button_release_event", self.click_to_entry)
    if name:
      preheat_name_entry.set_text(name)
    
    # minusButton = self._screen.gtk.Button("minus", None, "round_button")
    name_box = Gtk.Box()
    name_box.add(preheat_name_label)
    name_box.add(preheat_name_entry)
    # name_box.pack_end(minusButton, False, False, 5)
    
    preheat_bed_label = Gtk.Label(label=_("Temp bed:"), hexpand=True, halign=Gtk.Align.CENTER)
    preheat_bed_entry = TypedEntry(NumberRule, max=self._printer.get_config_section('heater_bed')['max_temp'])
    preheat_bed_entry.connect("focus-in-event", self.on_focus_in_event)
    preheat_bed_entry.connect("focus-out-event", self.on_focus_out_event)
    preheat_bed_entry.connect("button_release_event", self.click_to_entry)
    
    preheat_extruder_label = Gtk.Label(label=_("Temp extruder:"), hexpand=True, halign=Gtk.Align.CENTER)
    preheat_extruder_entry = TypedEntry(NumberRule, max=self._printer.get_config_section('extruder')['max_temp'])
    preheat_extruder_entry.connect("focus-in-event", self.on_focus_in_event)
    preheat_extruder_entry.connect("focus-out-event", self.on_focus_out_event)
    preheat_extruder_entry.connect("button_release_event", self.click_to_entry)
    
    if preheat:
      preheat_bed_entry.set_text(str(preheat['bed']))
      preheat_extruder_entry.set_text(str(preheat['extruder']))
    
    preheat_temperatures_grid = Gtk.Grid(column_homogeneous=True)
    
    preheat_bed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_right=10)
    preheat_bed_box.add(preheat_bed_label)
    preheat_bed_box.add(preheat_bed_entry)
    preheat_temperatures_grid.attach(preheat_bed_box, 0, 0, 1, 1)  
    
    preheat_extruder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_right=10)
    preheat_extruder_box.add(preheat_extruder_label)
    preheat_extruder_box.add(preheat_extruder_entry)
    preheat_temperatures_grid.attach(preheat_extruder_box, 1, 0, 1, 1)  
    main_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, 
                                            hexpand=True, 
                                            vexpand=True, 
                                            valign=Gtk.Align.CENTER, 
                                            spacing=5)
    main_row.add(name_box)
    main_row.add(preheat_temperatures_grid)
    # minusButton.connect("clicked", self.delete_profile_row, main_row)
    return main_row
  
  
  # def delete_profile_row(self, widget, row):
  #   self.preheat_grid.remove(row)
  #   self.content.show_all()

  # def add_preheat_row(self, widget):
  #   new_row = self.create_preheat_row()
  #   self.preheat_grid.attach(new_row, 0, len(self.preheat_grid), 1, 1)
  #   self.content.show_all()
  

  # def delete_profile_row(self, widget, row):
  #   self.preheat_grid.remove(row)
  #   self.content.show_all()

  # def add_preheat_row(self, widget):
  #   new_row = self.create_preheat_row()
  #   self.preheat_grid.attach(new_row, 0, len(self.preheat_grid), 1, 1)
  #   self.content.show_all()
  
  def ErrorPopup(self, widget, msg):
    popup = Gtk.Popover.new(widget)
    popup.get_style_context().add_class("message_popup_error")
    popup.set_position(Gtk.PositionType.BOTTOM)
    popup.set_halign(Gtk.Align.CENTER)
    msg = Gtk.Button(label=msg)
    msg.set_hexpand(True)
    msg.set_vexpand(True)
    msg.get_child().set_line_wrap(True)
    msg.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    popup.add(msg)
    msg.connect("clicked", self.popup_popdown, popup)
    return popup
    
    
                

                
  def change_preheats(self, widget=None, event=None):
    preheat_dict = self.get_preheat_grid_as_dict()
    error_popups = []
    config_preheat = {}
    for preheat_i in preheat_dict:
      if not preheat_dict[preheat_i]['name']:
        error_popups.append(self.ErrorPopup(preheat_dict[preheat_i]['widget_name'], _("Name not specified")))
      if not preheat_dict[preheat_i]['bed']:
        error_popups.append(self.ErrorPopup(preheat_dict[preheat_i]['widget_bed'], _("Bed temp not specified")))        
      if not preheat_dict[preheat_i]['extruder']:
        error_popups.append(self.ErrorPopup(preheat_dict[preheat_i]['widget_extruder'], _("Extruder temp not specified")))   
      config_preheat[preheat_dict[preheat_i]['name']] = { 'bed': preheat_dict[preheat_i]['bed'], 'extruder': preheat_dict[preheat_i]['extruder'] }
    if len(error_popups):
        for popup in error_popups:
          popup.popup()
          popup.show_all()
        GLib.timeout_add_seconds(5, self.close_preheat_popups, error_popups)
        return Gdk.EVENT_STOP
    for name in config_preheat:
      for key in ['bed', 'extruder']:
        self._config.set("main", f"{name}_{key}", config_preheat[name][key])
    self._config.save_user_config_options()

  def close_preheat_popups(self, popups: list):
      for child in popups:
          child.popdown()   
      popups.clear()

  def get_preheat_grid_as_dict(self):
    preheats = {}
    for i,row in enumerate(self.preheat_grid):
      preheats[i] = {}
      for box in row:
        if isinstance(box, Gtk.Box):
          for name_box_child in box:
            if isinstance(name_box_child, TypedEntry):
              preheats[i]['name'] = name_box_child.get_text()
              preheats[i]['widget_name'] = name_box_child
        elif isinstance(box, Gtk.Grid):
          is_first_entry = True
          for grid_box in box:
            if isinstance(grid_box, Gtk.Box):
              for grid_box_child in grid_box:
                if isinstance(grid_box_child, TypedEntry):
                  if is_first_entry:
                    is_first_entry = False
                    key = 'extruder'
                  else:
                    key = 'bed'
                  preheats[i][f"widget_{key}"] = grid_box_child
                  preheats[i][key] = grid_box_child.get_text()
    return preheats

  def on_focus_in_event(self, entry, event):
    self.keyboard = Keyboard(self._screen, entry=entry)
    self.keyboard.change_entry(entry=entry)
    self.keyboard.set_vexpand(False)
    self.keyboard.set_hexpand(True)
    if (self._screen.width, self._screen.height) in RESOLUTION_K:
      self.keyboard.set_size_request(1, self._screen.height * RESOLUTION_K[(self._screen.width, self._screen.height)])
    self.content.add(self.keyboard)
    self.content.show_all()

  def on_focus_out_event(self, entry, event):
    if self.keyboard:
      self.content.remove(self.keyboard)
    self.keyboard = None

  def popup_popdown(self, widget, popup):
    popup.popdown()

  def click_to_entry(self, entry, event):
    return True

  def click_to_eventbox(self, eventBox, event):
    if not self.was_child_scrolled:
      eventBox.grab_focus()
    else:
        self.was_child_scrolled = False

        