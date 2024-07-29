import logging
import contextlib
import profile
import re 
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.bedmap import BedMap
from ks_includes.widgets.typed_entry import TypedEntry

class Panel(ScreenPanel):
    default_re = re.compile('^profile_(?P<i>\d+)$')
    
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.overlayBoxWidth = self._gtk.content_width / 1.2
        self.show_create = False
        self.active_mesh = None
        self.scroll = None
        self.overlayBox = None
        self.new_default_profile_name = ""
        self.profiles = {}
        self.buttons = {
            'calib': self._gtk.Button("resume", " " + _("Calibrate"), "color3", self.bts, Gtk.PositionType.LEFT, 1),
            'show_profiles': self._gtk.Button(None, " " + _("Profile manager"), "color1", self.bts, Gtk.PositionType.LEFT, 1),
            'clear': self._gtk.Button("cancel", " " + _("Clear bed mesh"), "color2", self.bts, Gtk.PositionType.LEFT, 1),
            'save': self._gtk.Button("increase", _("Save profile"), "color3", self.bts, Gtk.PositionType.LEFT, 1)
        }

        self.buttons['save'].set_no_show_all(True)
        self.buttons['clear'].set_no_show_all(True)
        self.buttons['save'].set_vexpand(False)
        self.buttons['save'].set_halign(Gtk.Align.END)
        self.buttons['save'].connect("clicked", self.send_save_active_mesh)
        
        self.buttons['clear'].connect("clicked", self.send_clear_mesh)
        self.buttons['clear'].connect("size-allocate", self.on_allocate_clear_button)
        self.buttons['clear'].set_vexpand(False)
        self.buttons['clear'].set_halign(Gtk.Align.END)
        
        self.buttons['calib'].connect("clicked", self.show_create_profile_menu)
        self.buttons['calib'].set_hexpand(True)
        
        self.buttons['show_profiles'].connect("clicked", self.show_loaded_mesh)
        self.buttons['show_profiles'].set_hexpand(True)

        topbar = Gtk.Box(spacing=5, hexpand=True, vexpand=False)
        topbar.add(self.buttons['calib'])
        topbar.add(self.buttons['show_profiles'])
        
        # Create a grid for all profiles
        self.labels['profiles'] = Gtk.Grid(valign=Gtk.Align.CENTER)
        self.overlay = Gtk.Overlay()
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spacing = 10
        main_box.set_spacing(spacing)
        content_box = Gtk.Box()
        self.labels['map'] = BedMap(self._gtk.font_size, self.active_mesh)
        self.bedMapBox = Gtk.Box()
        self.bedMapBox.add(self.labels['map'])
        self.bedMapBox.set_vexpand(True)
        self.bedMapBox.set_valign(Gtk.Align.CENTER)
        self.bedMapBox.set_halign(Gtk.Align.CENTER)
        self.baseBedMapW, self.baseBedMapH = self._gtk.content_width / 1.3, self._gtk.content_height / 1.3 - (spacing * 3)
        content_box.add(self.bedMapBox)
        main_box.add(topbar)
        
        self.labels['active_profile_name'] = Gtk.Label()
        self.labels['active_profile_name'].set_use_markup(True)
        self.labels['active_profile_name'].set_halign(Gtk.Align.START)
        self.labels['active_profile_name'].set_ellipsize(True)
        
        label_box = Gtk.Box()
        label_box.pack_start(self.labels['active_profile_name'], True, True, 0)
        
        control_mesh_box = Gtk.Box()
        control_mesh_box.pack_start(self.buttons['save'], True, False, 0)
        control_mesh_box.pack_end(self.buttons['clear'], True, False, 0)
        
        main_box.add(label_box)
        main_box.add(control_mesh_box)
        main_box.add(content_box)
        self.overlay.add_overlay(main_box)
        self.labels['main_grid'] = self.overlay
        self.content.add(self.labels['main_grid'])

    def activate(self):
        self.load_meshes()
        with contextlib.suppress(KeyError):
            self.activate_mesh(self._printer.get_stat("bed_mesh", "profile_name"), self._printer.get_stat("bed_mesh", "unsaved_profiles"))
            

    
    def on_allocate_clear_button(self, widget=None, allocation=None, gdata=None):
        # Это очень смешно, но этот сраный сигнал показывает все виджеты, как минимум, находящиеся в родительском контейнере
        buttonHeight = allocation.height
        self.bedMapBox.set_size_request(self.baseBedMapW, self.baseBedMapH - buttonHeight)
        # self.labels['control_mesh_box'].set_size_request(self.baseBedMapW, buttonHeight)
        # w = self.labels['active_profile_name'].get_allocation().width
        # self.labels['active_profile_name'].set_size_request(w, buttonHeight)
        
    def activate_mesh(self, profile, unsaved_profiles):
        if profile == "":
            logging.info("Clearing active profile")
            if self.active_mesh and self.active_mesh in self.profiles:
                locale_name = self.active_mesh
                result = self.default_re.search(self.active_mesh)
                if result:
                    result = result.groupdict()
                    locale_name = _("profile_%d") % int(result['i'])
                self.profiles[self.active_mesh]["name"].set_markup("<b>%s</b>" % (locale_name))
                if "clear" in self.profiles[self.active_mesh]:
                    self.profiles[self.active_mesh]["button_grid"].remove_column(0)
                    del self.profiles[self.active_mesh]["clear"]
                if "load" not in self.profiles[self.active_mesh]:
                    self.profiles[self.active_mesh]["load"] = self._gtk.Button("complete", _("Load profile"), "color4", self.bts)
                    self.profiles[self.active_mesh]["load"].connect("clicked", self.send_load_mesh, self.active_mesh)
                    self.profiles[self.active_mesh]["button_grid"].insert_column(0)
                    self.profiles[self.active_mesh]["button_grid"].attach(self.profiles[self.active_mesh]["load"], 0, 0, 1, 1)   
                self.profiles[self.active_mesh]["button_grid"].show_all()
                self.active_mesh = None
            self.update_graph()
            self.labels['active_profile_name'].set_markup("<big><b>%s</b></big>" % (_("No mesh profile has been loaded")))
            self.buttons['clear'].hide()
            self.buttons['save'].hide()
            return
        
        if profile not in self.profiles:
            self.add_profile(profile, unsaved_profiles)
            if self.overlayBox and self.scroll:
                for child in self.scroll:
                    self.scroll.remove(child)
                self.scroll.add(self.labels['profiles'])
                
        locale_name = profile
        result = self.default_re.search(profile)
        if result:
            result = result.groupdict()
            locale_name = _("profile_%d") % int(result['i'])
            
        if self.active_mesh != profile:
            logging.info(f"Active {self.active_mesh} changing to {profile}")
            self.active_mesh = profile
            for pr in self.profiles:                    
                if self.active_mesh == pr:
                    self.profiles[pr]["name"].set_markup(_("<b>%s (%s)</b>" % (locale_name, _("active"))))
                    if "load" in self.profiles[pr]:
                        self.profiles[pr]["button_grid"].remove_column(0)
                        del self.profiles[pr]["load"]
                    if "clear" not in self.profiles[pr]:
                        self.profiles[pr]["clear"] = self._gtk.Button("cancel", _("Deactivate"), "color1", self.bts)
                        self.profiles[pr]["clear"].connect("clicked", self.send_clear_mesh)
                        self.profiles[pr]["button_grid"].insert_column(0)
                        self.profiles[pr]["button_grid"].attach(self.profiles[pr]["clear"], 0, 0, 1, 1)
                else:
                    if "clear" in self.profiles[pr]:
                        self.profiles[pr]["button_grid"].remove_column(0)
                        del self.profiles[pr]["clear"]
                    if "load" not in self.profiles[pr]:
                        self.profiles[pr]["name"].set_markup("<b>%s</b>" % (locale_name))
                        self.profiles[pr]["load"] = self._gtk.Button("complete", _("Load profile"), "color4", self.bts)
                        self.profiles[pr]["load"].connect("clicked", self.send_load_mesh, pr)
                        self.profiles[pr]["button_grid"].insert_column(0)
                        self.profiles[pr]["button_grid"].attach(self.profiles[pr]["load"], 0, 0, 1, 1)
                        
                                  
                if pr in unsaved_profiles:
                    logging.info("showing button save")
                    self.buttons['save'].show()
                    if "save" not in self.profiles[pr]:
                        self.profiles[pr]["save"] = self._gtk.Button("increase", _("Save profile"), "color3", self.bts)
                        self.profiles[pr]["save"].connect("clicked", self.send_save_mesh, profile)
                        self.profiles[pr]["button_grid"].insert_column(1)
                        self.profiles[pr]["button_grid"].attach(self.profiles[pr]["save"], 1, 0, 1, 1)
                else:
                    self.buttons['save'].hide()
                    if "save" in self.profiles[pr]:
                        self.profiles[pr]["button_grid"].remove_column(1)
                        del self.profiles[pr]["save"]
                        
                self.profiles[pr]["button_grid"].show_all()
                self.profiles[pr]["name"].show_all()
        self.update_graph(profile=profile)
        self.labels['active_profile_name'].set_markup(_("<big><b>%s: %s</b></big>") % (_("Active profile"), locale_name))
        self.buttons['clear'].show()
        if self.overlayBox and self.scroll:
                self.scroll.show_all()
        
    def retrieve_bm(self, profile):
        if profile is None:
            return None
        bm = self._printer.get_stat("bed_mesh")
        if bm is None:
            logging.info(f"Unable to load active mesh: {profile}")
            return None
        matrix = 'probed_matrix'
        return bm[matrix]

    def update_graph(self, widget=None, profile=None):
        self.labels['map'].update_bm(self.retrieve_bm(profile))
        self.labels['map'].queue_draw()
    
    def add_profile(self, profile: str, unsaved_profiles: list[str] = []):
        logging.debug(f"Adding Profile: {profile}")

        buttons = {} 
        if self.active_mesh != profile:
            buttons["load"] = self._gtk.Button("complete", _("Load profile"), "color4", self.bts)
            buttons["load"].connect("clicked", self.send_load_mesh, profile)
        else:
            buttons["clear"] = self._gtk.Button("cancel", _("Deactivate"), "color1", self.bts)
            buttons["clear"].connect("clicked", self.send_clear_mesh) 
        if profile in unsaved_profiles:
            buttons["save"] = self._gtk.Button("increase", _("Save profile"), "color3", self.bts)
            buttons["save"].connect("clicked", self.send_save_mesh, profile)
        buttons["delete"] = self._gtk.Button("cancel", _("Delete profile"), "color2", self.bts)
        buttons["delete"].connect("clicked", self.send_remove_mesh, profile)
        button_grid = Gtk.Grid(column_homogeneous=True)
        button_grid.set_size_request(self.overlayBoxWidth / 1.5, 1)
        button_grid.set_hexpand(True)
        button_grid.set_halign(Gtk.Align.END)
        #0 - load(None), 1 - save(delete), 2 - delete(None)
        for i, b in enumerate(buttons):
            button_grid.attach(buttons[b], i, 0, 1, 1)

        locale_name = profile
        result = self.default_re.search(profile)
        if result:
            result = result.groupdict()
            locale_name = _("profile_%d") % int(result['i'])
        name = Gtk.Label(locale_name)
        name.set_lines(2)
        name.set_justify(Gtk.Justification.LEFT)
        name.set_max_width_chars(20)
        name.set_use_markup(True)
        name.set_markup("<b>%s</b>" % (locale_name))
        name.set_line_wrap(True)
        name.set_line_wrap_mode(Pango.WrapMode.CHAR)
        name.set_ellipsize(True)
        name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        name.set_hexpand(True)
        name.set_halign(Gtk.Align.START)
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.get_style_context().add_class("frame-item")
        box.pack_start(name, True, True, 5)
        box.pack_end(button_grid, True, True, 5)
        self.profiles[profile] = {
            "name": name,
            "row": box,
            "button_grid": button_grid
        }
        
        for button_name in buttons:
            self.profiles[profile][button_name] = buttons[button_name]
                    
        pl = list(self.profiles)
        if "default" in pl:
            pl.remove('default')
        profiles = sorted(pl)
        pos = profiles.index(profile) + 1 if profile != "default" else 0

        self.labels['profiles'].insert_row(pos)
        self.labels['profiles'].attach(self.profiles[profile]['row'], 0, pos, 1, 1)
        
    def back(self):
        if self.show_create is True:
            self.remove_create()
            return True
        return False

    def load_meshes(self):
        bm_profiles = self._printer.get_stat("bed_mesh", "profiles")
        unsaved_profiles = self._printer.get_stat("bed_mesh", "unsaved_profiles")
        for prof in bm_profiles:
            if prof not in self.profiles:
                self.add_profile(prof, unsaved_profiles)
        for prof in self.profiles:
            if prof not in bm_profiles:
                self.remove_profile(prof)

    def saving_profile(self, unsaved_profiles):
        for pr in self.profiles:
          if pr not in unsaved_profiles:
              if self.active_mesh == pr:
                  self.buttons['save'].hide()
              if "save" in self.profiles[pr]:
                  self.profiles[pr]["button_grid"].remove_column(1)
                  del self.profiles[pr]["save"]
          locale_name = pr
          result = self.default_re.search(pr)
          if result:
              result = result.groupdict()
              locale_name = _("profile_%d") % int(result['i'])
          self.profiles[pr]["name"].set_markup("<b>%s</b>" % (locale_name))
          self.profiles[pr]["name"].show_all()
          self.profiles[pr]["button_grid"].show_all()
            
    def process_busy(self, busy):
        for button in self.buttons:
            if button != 'show_profiles':
                self.buttons[button].set_sensitive((not busy))
        self.labels['profiles'].set_sensitive((not busy))
                
    
    def process_update(self, action, data):
        if action == "notify_busy":
            self.process_busy(data)
            return
        if action == "notify_status_update":
            if 'bed_mesh' in data and 'profiles' in data['bed_mesh']:
                delete_profiles = [del_prof for del_prof in self.profiles if del_prof not in data['bed_mesh']['profiles']]
                add_profiles = [add_prof for add_prof in data['bed_mesh']['profiles'] if add_prof not in self.profiles]
                if len(delete_profiles) > 0:
                    for del_prof in delete_profiles:
                        self.remove_profile(del_prof)
                if len(add_profiles) > 0:
                    for add_prof in add_profiles:
                        self.add_profile(add_prof)
            with contextlib.suppress(KeyError):
                self.activate_mesh(data['bed_mesh']['profile_name'], self._printer.get_stat("bed_mesh", "unsaved_profiles"))
            if 'bed_mesh' in data and 'unsaved_profiles' in data['bed_mesh']:
                self.saving_profile(data['bed_mesh']['unsaved_profiles'])
                    

    def remove_create(self):
        if self.show_create is False:
            return

        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)

        self.show_create = False
        self.content.add(self.labels['main_grid'])
        self.content.show()

    def remove_profile(self, profile):
        if profile not in self.profiles:
            return
        pl = list(self.profiles)
        if "default" in pl:
            pl.remove('default')
        profiles = sorted(pl)
        pos = profiles.index(profile) + 1 if profile != "default" else 0
        self.labels['profiles'].remove_row(pos)
        del self.profiles[profile]
        if self.overlayBox and self.scroll:
            for child in self.scroll:
                self.scroll.remove(child)
            self.scroll.add(self.labels['profiles'])  
            self.scroll.show_all()
        if not self.profiles:
            self.active_mesh = None
            self.update_graph()

    def show_create_profile_menu(self, widget=None):
        for child in self.content.get_children():
            self.content.remove(child)
        

        scroll = self._screen.gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.new_profiles_grid = Gtk.Grid()
        new_profile_row = self.create_new_profile_row()
        self.new_profiles_grid.add(new_profile_row)
        plusButton = self._screen.gtk.Button("plus", None, "round_button")
        plusButton.connect("clicked", self.add_profile_row)
        plusButton.set_hexpand(True)
        plusButton.set_halign(Gtk.Align.CENTER)
        plusButton.set_vexpand(True)
        plusButton.set_valign(Gtk.Align.START)
        box.add(self.new_profiles_grid)
        box.add(plusButton)
        
        scroll.add(box)

        startCalibrateButton = self._gtk.Button(None, _("Start calibrate"), "color3", self.bts)
        startCalibrateButton.set_hexpand(True)
        startCalibrateButton.set_halign(Gtk.Align.END)
        startCalibrateButton.set_vexpand(True)
        startCalibrateButton.set_valign(Gtk.Align.END)
        startCalibrateButton.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        startCalibrateButton.connect("clicked", self.start_calibrate)

        box.add(startCalibrateButton)

        eventBox = Gtk.EventBox()
        eventBox.set_can_focus(True)
        eventBox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        eventBox.connect("button_release_event", self.click_to_eventbox)
        eventBox.add(scroll)

        

        self.content.add(eventBox)
        self.content.show_all()
        self.show_create = True
    
    def count_default_profiles(self):
        i = 0
        while ("profile_%d" % i) in self._printer.get_stat("bed_mesh", "profiles"):
            i = i + 1
        return i

    def add_profile_row(self, widget):
        new_row = self.create_new_profile_row()
        self.new_profiles_grid.attach(new_row, 0, len(self.new_profiles_grid), 1, 1)
        self.content.show_all()

    def delete_profile_row(self, widget, number):
        self.new_profiles_grid.remove_row(number)
        self.content.show_all()
    
    def count_new_default_profiles(self):
        new_profiles = []
        for row in self.new_profiles_grid:
            found_first_entry = False
            for box in row:
                if isinstance(box, Gtk.Box):
                    for child in box:
                        if isinstance(child, TypedEntry):
                            found_first_entry = True
                            new_profiles.append(child.get_placeholder_text())
                            break
                if found_first_entry:
                    break
        i = self.count_default_profiles()
        while (_("profile_%d") % i) in new_profiles:
            i = i + 1
        return i

    def get_new_profiles_grid_parameters_as_dict(self):
        new_profiles_dict = {}
        for i,row in enumerate(self.new_profiles_grid):
            new_profiles_dict[i] = {}
            for box in row:
                if isinstance(box, Gtk.Box):
                    for child in box:
                        if isinstance(child, TypedEntry):
                            if 'profile_name' not in new_profiles_dict[i]:
                              text = child.get_text()
                              if not text:
                                new_profiles_dict[i]['locale_name'] = child.get_placeholder_text()
                                new_profiles_dict[i]['profile_name'] = f"profile_{child.get_placeholder_text().partition('_')[2]}"
                              else:
                                new_profiles_dict[i]['profile_name'] = text
                            else:
                                new_profiles_dict[i]['preheat_temp'] = child.get_text()
                        if isinstance(child, Gtk.Box):
                            for ch in child:
                                if isinstance(ch, Gtk.Switch):
                                    if 'preheat' not in new_profiles_dict[i]:
                                        new_profiles_dict[i]['preheat'] = ch.get_active()
                        if isinstance(child, Gtk.Switch):
                            if 'save' not in new_profiles_dict[i]:
                              new_profiles_dict[i]['save'] = child.get_active()
        return new_profiles_dict       
            
    def create_new_profile_row(self):
        profile_label = Gtk.Label(label=_("Profile Name:"), hexpand=True, halign=Gtk.Align.START)
        profile_entry = TypedEntry("no_space")

        i = self.count_new_default_profiles()
        
        self.new_default_profile_name = f"profile_{i}"
        locale_name = _("profile_%d") % i
        profile_entry.set_placeholder_text(_(locale_name))
        profile_entry.set_text('')
        profile_entry.set_hexpand(True)
        profile_entry.set_vexpand(False)
        profile_entry.connect("focus-in-event", self.on_focus_in_event)
        profile_entry.connect("focus-out-event", self.on_focus_out_event)
        profile_entry.connect("button_release_event", self.click_to_entry)
        
        preheat_entry = TypedEntry("number", max=self._printer.get_config_section('heater_bed')['max_temp'])
        preheat_entry.connect("focus-in-event", self.on_focus_in_event)
        preheat_entry.connect("focus-out-event", self.on_focus_out_event)
        preheat_entry.connect("button_release_event", self.click_to_entry)
        preheat_entry.set_no_show_all(True)
        preheat_entry.hide()
        locale_preheat_placeholder = _("Set temperature")
        preheat_entry.set_placeholder_text(_(locale_preheat_placeholder))

        preheat_switch = Gtk.Switch()
        preheat_switch.connect("notify::active", self.on_switch_preheat, preheat_entry)

        preheat_switch_box = Gtk.Box()
        preheat_switch_box.add(Gtk.Label(label=_("Preheat")))
        preheat_switch_box.add(preheat_switch)

        preheat_box = Gtk.Box()
        preheat_box.pack_start(preheat_switch_box, True, True, 10)
        preheat_box.pack_end(preheat_entry, True, True, 10)
        

        minusButton = self._screen.gtk.Button("minus", None, "round_button")
        minusButton.connect("clicked", self.delete_profile_row, len(self.new_profiles_grid) - 1)

        save_box = Gtk.Box()
        save_box.add(Gtk.Label(label=_("Save after calibrate")))
        save_box.add(Gtk.Switch())

        profile_box = Gtk.Box()
        profile_box.add(profile_entry)
        profile_box.pack_end(minusButton, False, False, 5)

        main_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, 
                                                hexpand=True, 
                                                vexpand=True, 
                                                valign=Gtk.Align.CENTER, 
                                                spacing=5)
        main_row.pack_start(profile_label, True, True, 5)
        main_row.pack_start(profile_box, True, True, 5)
        main_row.add(preheat_box)
        main_row.add(save_box)
        return main_row

    def on_switch_preheat(self, switch, gdata, entry):
        entry.show() if switch.get_active() else entry.hide()
    
    def click_to_eventbox(self, eventBox, event):
        eventBox.grab_focus()
        
    def on_focus_out_event(self, entry, event):
        self._screen.remove_keyboard()

    def click_to_entry(self, entry, event):
        return True
        
    def on_focus_in_event(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self._screen.remove_keyboard)
        self._screen.keyboard.change_entry(entry=entry)
    
    def start_calibrate(self, widget=None):
        profiles_dict = self.get_new_profiles_grid_parameters_as_dict()
        logging.info(f"profiles dict {profiles_dict}")
        cmd = ""
        for profile_i in profiles_dict:
            cmd = cmd + f"BED_MESH_CALIBRATE PROFILE={profiles_dict[profile_i]['profile_name']} SAVE_PERMANENTLY={profiles_dict[profile_i]['save']}\n"
            if profiles_dict[profile_i]['preheat']:
                prh_t = profiles_dict[profile_i]['preheat_temp']
                if prh_t == '':
                    self._screen.show_popup_message(_("Not set temperature to profile %s") % profiles_dict[profile_i]['profile_name'])
                    return
                else:
                  cmd = cmd + f"M190 S{0 if prh_t == '' else prh_t}\n"
        cmd_array = cmd.split('\n')
        cmd_array.reverse()
        cmd = "\n".join(cmd_array)
        self._screen._ws.klippy.gcode_script(cmd)
        # logging.info(cmd)
        # name = self.labels['profile_name'].get_text()
        # if not name:
        #     name = self.new_default_profile_name
        # self.calibrate_mesh(None, name)
        # self.remove_create()

    # def calibrate_mesh(self, widget, profile):
    #     self._screen.show_popup_message(_("Calibrating"), level=1)
    #     self._screen._ws.klippy.gcode_script(f"BED_MESH_CALIBRATE PROFILE='{profile}'")

    def show_loaded_mesh(self, widget):
        self.overlayBox = Gtk.Box()
        close_profiles_button = self._gtk.Button("back_overlay", scale=self.bts, position=Gtk.PositionType.RIGHT)
        close_profiles_button.set_vexpand(False)
        close_profiles_button.set_hexpand(True)
        close_profiles_button.set_alignment(1., 0.)
        close_profiles_button.get_style_context().add_class("overlay_close_button")
        close_profiles_button.connect("clicked", self.close_loaded_mesh)
        self.overlayBox.pack_start(close_profiles_button, False, True, 0)
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.add(self.labels['profiles'])
        self.scroll.set_vexpand(False)
        self.scroll.set_hexpand(True)
        self.scroll.set_halign(Gtk.Align.FILL)
        self.scroll.set_min_content_width(self.overlayBoxWidth)
        self.scroll.get_style_context().add_class("scrolled_window_mesh_profiles")
        self.overlayBox.pack_start(self.scroll, True, True, 0)
        self.overlayBox.set_vexpand(False)
        self.overlayBox.set_hexpand(True)
        self.overlayBox.show_all()
        for child in self.overlay:
            child.set_opacity(0.2)
            child.set_sensitive(False)
        self.overlay.add_overlay(self.overlayBox)
        self.scroll.show_all()
    
    def close_loaded_mesh(self, widget=None):
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
    
    def send_clear_mesh(self, widget):
        self._screen._ws.klippy.gcode_script("BED_MESH_CLEAR")

    def has_cyrillic(text):
        return bool(re.search('[а-я]|[А-Я]', text))
    def send_load_mesh(self, widget, profile):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.bed_mesh_load(profile))

    def send_save_mesh(self, widget, profile):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.bed_mesh_save(profile))
    
    def send_save_active_mesh(self, widget):
        if not self.active_mesh:
          logging.info("Active mesh is none")
          return
        self._screen._ws.klippy.gcode_script(KlippyGcodes.bed_mesh_save(self.active_mesh))

    def send_remove_mesh(self, widget, profile):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.bed_mesh_remove(profile))