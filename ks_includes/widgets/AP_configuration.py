import gi
import logging
import subprocess
from ks_includes import access_point
import nmcli
import os
from ks_includes.widgets.typed_entry import TypedEntry
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class APConfiguration(Gtk.Box):
    def __init__(self, screen):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        nmcli.disable_use_sudo()
        self.ap_connection = None
        self._screen = screen
        self.is_external_set_access_point_activity = True
        self.is_access_point_active = None
        self.ap: access_point.AccessPoint = access_point.find_access_point(self._screen.base_panel.get_wifi_dev())
        if not self.ap:
            self.add(self.create_error_page())
            # TO DO Поменять на create_connection
            return     
        self.labels = {}
        
        self.labels['AP'] = {
            'autoconnect': Gtk.Switch(active=self.ap.is_autoconnect(), sensitive=False),
            'ssid' : TypedEntry(text=self.ap.get_ssid(), hexpand=True, sensitive=False),
            'psk' : TypedEntry(text=self.ap.get_psk(), hexpand=True, sensitive=False)
        }
        self.labels['AP']['ssid'].connect("button-press-event", self.on_change_entry)
        self.labels['AP']['psk'].connect("button-press-event", self.on_change_entry)
        self.connect_switch = Gtk.Switch(active=self.ap.is_active())
        self.connect_switch.connect("notify::active", self.switch_access_point)
        self.connect_switch.connect("button-press-event", self.on_click_switch)
        
        switchbox = Gtk.Box()
        switchbox.set_hexpand(True)
        switchbox.set_vexpand(False)
        switchbox.set_valign(Gtk.Align.CENTER)
        switchbox.pack_start(Gtk.Label(label=_("Access Point")), False, False, 0)
        switchbox.pack_end(self.connect_switch, False, False, 0)

        autobox = Gtk.Box()
        autobox.set_hexpand(True)
        autobox.set_vexpand(False)
        autobox.set_valign(Gtk.Align.CENTER)
        autobox.pack_start(Gtk.Label(label=_("Autoconnect")), False, False, 0)
        autobox.pack_end(self.labels['AP']['autoconnect'], False, False, 0)

        IP_address = TypedEntry()
        IP_address.set_text(self.ap.get_ip()) 
        IP_address.set_hexpand(True)
        IP_address.get_style_context().add_class("unused_entry")
        IP_address.set_sensitive(False)

        plugLeft = Gtk.Label()
        plugRight = Gtk.Label()
        plugLeft.set_size_request(self._screen.gtk.content_width/7, 1)
        plugRight.set_size_request(self._screen.gtk.content_width/7, 1)

        grid = Gtk.Grid()
        grid.attach(plugRight, 0, 0, 2, 3)
        grid.attach(Gtk.Label(label=_("IP-address")), 2, 1, 1, 1)
        grid.attach(IP_address, 3, 1, 8, 1)
        grid.attach(Gtk.Label(label=_("SSID")), 2, 2, 1, 1)
        grid.attach(self.labels['AP']['ssid'], 3, 2, 8, 1)
        grid.attach(Gtk.Label(label=_("Password")), 2, 3, 1, 1)
        grid.attach(self.labels['AP']['psk'], 3, 3, 8, 1)
        grid.attach(plugLeft, 12, 0, 3, 3)
        grid.set_row_spacing(5)
        grid.set_vexpand(True)
        grid.set_valign(Gtk.Align.CENTER)
        
        self.button = {'save_changes': self._screen.gtk.Button("complete", _("Save changes"), "color1"),
                       'change': self._screen.gtk.Button("complete", _("Change"), "color1"),
                       'disable': self._screen.gtk.Button("cancel", _("Cancel Change"), "color2")}
        for btn in self.button:
            self.button[btn].set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        self.button['save_changes'].connect('clicked', self.save_changes)
        self.button['change'].connect('clicked', self.change_fields)
        self.button['disable'].connect('clicked', self.disable_changes)
        self.button_box =  Gtk.Box(valign=Gtk.Align.END, halign=Gtk.Align.END)
        self.button_box.pack_start(self.button['change'], False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(switchbox, False, True, 5)
        box.pack_start(autobox, False, True, 5)
        box.pack_start(grid, True, True, 5)
        box.pack_end(self.button_box, True, True, 0)

        self.scroll = self._screen.gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.scroll.add(box)
        self.add(self.scroll)
    

    def create_error_page(self):
        err_scroll = self._screen.gtk.ScrolledWindow()
        err_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL) 
        err_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        title = Gtk.Label()
        title.set_markup(_("Access Point"))
        title.set_line_wrap(True)
        title.set_halign(Gtk.Align.CENTER)
        title.set_hexpand(True)
        
        message = Gtk.Label(_("Error on load access point.\nAccess point is not present"))
        message.set_line_wrap(True)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_valign(Gtk.Align.CENTER)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(message)
        
        grid = Gtk.Grid()
        grid.attach(title, 0, 0, 1, 1)
        grid.attach(Gtk.Separator(), 0, 1, 2, 1)
        grid.attach(scroll, 0, 2, 2, 1)
        
        err_box.pack_start(grid, True, True, 0)
        err_scroll.add(err_box)
        return err_scroll

    def switch_access_point(self, switch, gdata):
        if not self.is_external_set_access_point_activity:
          if switch.get_active():
            self.ap.up()
          else:
            self.ap.down()
    
    def change_fields(self, button):
        self.button_box.remove(self.button['change'])
        self.button_box.pack_start(self.button['disable'], False, False, 0) 
        self.button_box.pack_start(self.button['save_changes'], False, False, 0) 
        for property in self.labels['AP']:
               self.labels['AP'][property].set_sensitive(True)
        self.button_box.show_all()
    
    def disable_changes(self, button):
        self.labels['AP']['autoconnect'].set_active(self.ap.is_autoconnect())
        self.labels['AP']['ssid'].set_text(self.ap.get_ssid())
        self.labels['AP']['psk'].set_text(self.ap.get_psk())
        for prop in self.labels['AP']:
          self.labels['AP'][prop].set_sensitive(False)
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        self.button_box.show_all()

    def on_click_switch(self, switch, event):
        self.is_external_set_access_point_activity = False 
    
    def save_changes(self, widget):
        ssid = self.labels['AP']['ssid'].get_text()
        if not ssid:
            self._screen.show_popup_message(_("SSID cannot be null"))
            return
        psk = self.labels['AP']['psk'].get_text()
        if len(psk) < 8:
            self._screen.show_popup_message(_("Password must contains minimum 8 symbols"))
            return
        autoconnect = ['no', 'yes'][self.labels['AP']['autoconnect'].get_active()]
        try:
          self.ap.modify(ssid, psk, autoconnect)
        except Exception as e:
          logging.error(f"Error on save_changes")
          self._screen.show_popup_message(_("Access point error:\n%s") % e)
          return
        self._screen.remove_keyboard()
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        for property in self.labels['AP']:
                self.labels['AP'][property].set_sensitive(False)
        self.button_box.show_all()
    
    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self.on_accept_keyboard_dutton)
        self._screen.keyboard.change_entry(entry=entry)
    
    def get_access_point_activity(self, is_access_point_active):
        if self.is_access_point_active != is_access_point_active:
            self.is_external_set_access_point_activity = True
            self.is_access_point_active = is_access_point_active
            self.connect_switch.set_active(is_access_point_active)
          
    def on_accept_keyboard_dutton(self):
        self._screen.remove_keyboard()