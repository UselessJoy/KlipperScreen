import logging
import contextlib
import profile
import re 
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.bedmap import BedMap
from ks_includes.widgets.typed_entry import TypedEntry
#from transliterate import translit

def create_panel(*args):
    return BedMeshPanel(*args)


class BedMeshPanel(ScreenPanel):

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.show_create = False
        self.active_mesh = None
        self.profiles = {}
        self.buttons = {
            'calib': self._gtk.Button("resume", " " + _("Calibrate"), "color3", self.bts, Gtk.PositionType.LEFT, 1),
            'show_profiles': self._gtk.Button(None, " " + _("Profile manager"), "color1", self.bts, Gtk.PositionType.LEFT, 1),
            'clear': self._gtk.Button("cancel", " " + _("Clear"), "color2", self.bts, Gtk.PositionType.LEFT, 1),
        }
            
        self.buttons['clear'].connect("clicked", self.send_clear_mesh)
        self.buttons['clear'].connect("size-allocate", self.on_allocate_clear_button)
        self.buttons['clear'].set_vexpand(False)
        self.buttons['clear'].set_halign(Gtk.Align.END)
        self.buttons['calib'].connect("clicked", self.show_create_profile)
        self.buttons['calib'].set_hexpand(True)
        self.buttons['show_profiles'].connect("clicked", self.show_loaded_mesh)
        self.buttons['show_profiles'].set_hexpand(True)
        self.scroll = None
        self.overlayBox = None
        topbar = Gtk.Box(spacing=5)
        topbar.set_hexpand(True)
        topbar.set_vexpand(False)
        topbar.add(self.buttons['calib'])
        topbar.add(self.buttons['show_profiles'])
        
        # Create a grid for all profiles
        self.labels['profiles'] = Gtk.Grid()
        self.labels['profiles'].set_valign(Gtk.Align.START)
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
        
        self.labels['label_box'] = Gtk.Box()
        self.labels['active_profile_name'] = Gtk.Label()
        self.labels['active_profile_name'].set_use_markup(True)
        
        self.labels['active_profile_name'].set_halign(Gtk.Align.START)
        self.labels['active_profile_name'].set_ellipsize(True)
        self.labels['label_box'].pack_start(self.labels['active_profile_name'], True, True, 0)
        self.labels['label_box'].pack_end(self.buttons['clear'], True, True, 0)
        main_box.add(self.labels['label_box'])
        main_box.add(content_box)
        self.overlay.add_overlay(main_box)
        self.labels['main_grid'] = self.overlay
        self.content.add(self.labels['main_grid'])

    def activate(self):
        self.load_meshes()
        with contextlib.suppress(KeyError):
            self.activate_mesh(self._printer.get_stat("bed_mesh", "profile_name"), self._printer.get_stat("bed_mesh", "unsaved_profiles"))

    
    def on_allocate_clear_button(self, widget=None, allocation=None, gdata=None):
        buttonHeight = allocation.height
        self.bedMapBox.set_size_request(self.baseBedMapW, self.baseBedMapH - buttonHeight)
        w = self.labels['active_profile_name'].get_allocation().width
        self.labels['active_profile_name'].set_size_request(w, buttonHeight)
        
    def activate_mesh(self, profile, unsaved_profiles):
        logging.info(f"olololo, thats profile {profile} and our bm name {self.active_mesh}")
        logging.info(f"unsaved profiles is {unsaved_profiles}")
        if profile == "":
            logging.info("Clearing active profile")
            if self.active_mesh and self.active_mesh in self.profiles and "load" not in self.profiles[self.active_mesh]:
                self.profiles[self.active_mesh]["name"].set_markup("<b>%s</b>" % (self.active_mesh))
                self.profiles[self.active_mesh]["load"] = self._gtk.Button("complete", _("Загрузить профиль"), "color4", self.bts)
                self.profiles[self.active_mesh]["load"].connect("clicked", self.send_load_mesh, self.active_mesh)
                self.profiles[self.active_mesh]["button_grid"].insert_column(0)
                self.profiles[self.active_mesh]["button_grid"].attach(self.profiles[self.active_mesh]["load"], 0, 0, 1, 1)   
                self.profiles[self.active_mesh]["button_grid"].show_all()
                self.active_mesh = None
            self.update_graph()
            self.labels['active_profile_name'].set_markup(_("<big><b>No mesh profile has been loaded</b></big>"))
            self.buttons['clear'].hide()
            return
        
        if profile not in self.profiles:
            self.add_profile(profile, unsaved_profiles)
            if self.overlayBox and self.scroll:
                for child in self.scroll:
                    self.scroll.remove(child)
                self.scroll.add(self.labels['profiles'])
        if self.active_mesh != profile:
            logging.info(f"Active {self.active_mesh} changing to {profile}")
            self.active_mesh = profile
            for pr in self.profiles:
                if self.active_mesh == pr:
                    self.profiles[pr]["name"].set_markup(_("<b>%s (active)</b>" % (pr)))
                    if "load" in self.profiles[pr]:
                        self.profiles[pr]["button_grid"].remove_column(0)
                        del self.profiles[pr]["load"]
                else:
                    if "load" not in self.profiles[pr]:
                        self.profiles[pr]["name"].set_markup("<b>%s</b>" % (pr))
                        self.profiles[pr]["load"] = self._gtk.Button("complete", _("Загрузить профиль"), "color4", self.bts)
                        self.profiles[pr]["load"].connect("clicked", self.send_load_mesh, pr)
                        self.profiles[pr]["button_grid"].insert_column(0)
                        self.profiles[pr]["button_grid"].attach(self.profiles[pr]["load"], 0, 0, 1, 1)
                        
                                  
                if pr in unsaved_profiles:
                    if "save" not in self.profiles[pr]:
                        self.profiles[pr]["save"] = self._gtk.Button("increase", _("Сохранить профиль"), "color3", self.bts)
                        self.profiles[pr]["save"].connect("clicked", self.send_save_mesh, profile)
                        self.profiles[pr]["button_grid"].insert_column(1)
                        self.profiles[pr]["button_grid"].attach(self.profiles[pr]["save"], 1, 0, 1, 1)
                else:
                    if "save" in self.profiles[pr]:
                        self.profiles[pr]["button_grid"].remove_column(1)
                        del self.profiles[pr]["save"]
                        
                self.profiles[pr]["button_grid"].show_all()
                self.profiles[pr]["name"].show_all()
        self.update_graph(profile=profile)
        self.labels['active_profile_name'].set_markup(_("<big><b>Active profile: %s</b></big>" % (profile)))
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
            buttons["load"] = self._gtk.Button("complete", _("Загрузить профиль"), "color4", self.bts)
            buttons["load"].connect("clicked", self.send_load_mesh, profile)
                
        if profile in unsaved_profiles:
            buttons["save"] = self._gtk.Button("increase", _("Сохранить профиль"), "color3", self.bts)
            buttons["save"].connect("clicked", self.send_save_mesh, profile)
        buttons["delete"] = self._gtk.Button("cancel", _("Удалить профиль"), "color2", self.bts)
        buttons["delete"].connect("clicked", self.send_remove_mesh, profile)
        button_grid = Gtk.Grid()
        button_grid.set_hexpand(True)
        button_grid.set_halign(Gtk.Align.END)
        #0 - load(None), 1 - save(delete), 2 - delete(None)
        for i, b in enumerate(buttons):
            button_grid.attach(buttons[b], i, 0, 1, 1)
            
            
        # for label in self.button_labels:
            # self.button_labels[label].set_justify(Gtk.Justification.CENTER)
            # self.button_labels[label].set_width_chars(10)
        
        name = Gtk.Label(label = profile)
        # name.set_size_request(self._gtk.content_width / 10, 1)
        name.set_lines(2)
        name.set_justify(Gtk.Justification.LEFT)
        name.set_max_width_chars(20)
        name.set_use_markup(True)
        name.set_markup("<b>%s</b>" % (profile))
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
        if len(unsaved_profiles) == 0:
            return
        for pr in self.profiles:        
            if pr not in unsaved_profiles:
                if "save" in self.profiles[pr]:
                    self.profiles[pr]["button_grid"].remove_column(1)
                    del self.profiles[pr]["save"]
        self.profiles[pr]["name"].set_markup("<b>%s</b>" % (pr))
        self.profiles[pr]["name"].show_all()
        self.profiles[pr]["button_grid"].show_all()
            
    def process_busy(self, busy):
        for button in self.buttons:
            if button != 'show_profiles':
                self.buttons[button].set_sensitive((not busy))
        self.labels['profiles'].set_sensitive((not busy))
        if self.show_create is True:
            for child in self.labels['create_profile']:
                if type(child) is Gtk.Button:
                    child.set_sensitive((not busy))
                
    
    def process_update(self, action, data):
        if action == "notify_busy":
            self.process_busy(data)
            return
        if action == "notify_status_update":
            if 'bed_mesh' in data and 'profiles' in data['bed_mesh']:
                delete_profile = [del_prof for del_prof in self.profiles if del_prof not in data['bed_mesh']['profiles']]
                if delete_profile:
                    self.remove_profile(delete_profile[0])
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

    def show_create_profile(self, widget=None):

        for child in self.content.get_children():
            self.content.remove(child)

        if "create_profile" not in self.labels:
            pl = self._gtk.Label(_("Profile Name:"))
            pl.set_hexpand(True)
            self.labels['profile_name'] = TypedEntry()
            reserved = []
            name = None
            for prof in self.profiles:
                if prof.startswith("profile_"):
                    reserved.append[prof]
            i = len(reserved)
            while name == None:
                name = f"profile_{i}" if f"profile_{i}" not in reserved else None
                logging.info(name)
                i = i+1
            self.labels['profile_name'].set_placeholder_text(name)
            self.labels['profile_name'].set_text('')
            self.labels['profile_name'].set_hexpand(True)
            self.labels['profile_name'].set_vexpand(False)
            #self.labels['profile_name'].connect("activate", self.create_profile)
            self.labels['profile_name'].connect("focus-in-event", self.on_change_entry)

            save = self._gtk.Button(None, _("Начать калибровку"), "color3", self.bts)
            save.set_hexpand(False)
            save.connect("clicked", self.create_profile)

            box = Gtk.Box()
            box.pack_start(self.labels['profile_name'], True, True, 5)
            box.pack_start(save, False, False, 5)

            self.labels['create_profile'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            self.labels['create_profile'].set_valign(Gtk.Align.CENTER)
            self.labels['create_profile'].set_hexpand(True)
            self.labels['create_profile'].set_vexpand(True)
            self.labels['create_profile'].pack_start(pl, True, True, 5)
            self.labels['create_profile'].pack_start(box, True, True, 5)

        self.content.add(self.labels['create_profile'])
        self.content.show_all()
        #self.labels['profile_name'].grab_focus_without_selecting()
        self.show_create = True
    
    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry)
        self._screen.keyboard.change_entry(entry=entry)
    
    def create_profile(self, widget=None):
        name = self.labels['profile_name'].get_text()
        if not name:
            name = self.labels['profile_name'].get_placeholder_text()
        self.calibrate_mesh(None, name)
        self.remove_create()

    def calibrate_mesh(self, widget, profile):
        self._screen.show_popup_message(_("Calibrating"), level=1)
        if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
            self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME)
        self._screen._ws.klippy.gcode_script(f"BED_MESH_CALIBRATE PROFILE='{profile}'")

    def show_loaded_mesh(self, widget):
        #self.load_meshes()
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
        self.scroll.set_min_content_width(self._gtk.content_width / 1.2)
        self.scroll.get_style_context().add_class("scrolled_window_mesh_profiles")
        #self.scroll.show_all()
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

    def send_remove_mesh(self, widget, profile):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.bed_mesh_remove(profile))