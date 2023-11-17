import gi
import logging
import subprocess
import os
import nmcli
from ks_includes.widgets.keyboard import Keyboard
from ks_includes.widgets.typed_entry import TypedEntry
from datetime import datetime
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class APConfiguration(Gtk.Box):
    def __init__(self, screen):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        nmcli.disable_use_sudo()
        self.ap_connection = None
        self._screen = screen
        self.button = {}
        self.from_according = True
        self.wifi_mode = None
        for connection in nmcli.connection():
            if connection.conn_type == 'wifi':
                #logging.info(connection)
                connectionData = nmcli.connection.show(connection.name)
                if connectionData['802-11-wireless.mode'] == 'ap':
                    self.ap_connection = connectionData
                    data = subprocess.check_output("nmcli -f 802-11-wireless-security.psk  connection show -s %s | awk '{print $2}'" % (connection.name), universal_newlines=True, shell=True)
                    self.ap_connection['802-11-wireless-security.psk'] = data[:-1]
        self.labels = {}
        self.labels['AP'] = {
            'connection.autoconnect': Gtk.Switch(),
            '802-11-wireless.ssid' : TypedEntry(),
            '802-11-wireless-security.psk' : TypedEntry(),
            #'ipv4.addresses' : TypedEntry('interface'),
            #'netmask': TypedEntry('netmask'),
            # 'ipv4.gateway': Gtk.Entry(),
        }
        self.connect_switch = Gtk.Switch()
        self.connect_switch.connect("notify::active", self.change_wifi_mode)
        self.connect_switch.connect("button-press-event", self.on_click_switch)
        # addr_split = self.ap_connection['ipv4.addresses'].partition('/')
        # self.ap_connection.update({'ipv4.addresses' : addr_split[0]})
        # self.ap_connection['netmask'] = addr_split[1] + addr_split[2]
        autoconnect = self.ap_connection['connection.autoconnect']
        for property in self.labels['AP']:
            logging.info(property)
            if property == 'connection.autoconnect':
                self.labels['AP'][property].set_active((True if autoconnect == 'yes' else False))  
            else:
                self.labels['AP'][property].set_text(self.ap_connection[property])  
                self.labels['AP'][property].set_hexpand(True)
                self.labels['AP'][property].connect("button-press-event", self.on_change_entry)
            self.labels['AP'][property].set_sensitive(False)
                
                
        grid = Gtk.Grid()
        plugLeft = Gtk.Label()
        plugRight = Gtk.Label()
        plugLeft.set_size_request(self._screen.gtk.content_width/7, 1)
        plugRight.set_size_request(self._screen.gtk.content_width/7, 1)
        
        
        switchbox = Gtk.Box()
        switchbox.set_hexpand(True)
        switchbox.set_vexpand(False)
        switchbox.set_valign(Gtk.Align.CENTER)
        
        autobox = Gtk.Box()
        autobox.set_hexpand(True)
        autobox.set_vexpand(False)
        autobox.set_valign(Gtk.Align.CENTER)
        
        switchbox.pack_start(Gtk.Label(label=_("Access Point")), False, False, 5)
        switchbox.pack_end(self.connect_switch, False, False, 5)
        
        autobox.pack_start(Gtk.Label(label=_("Autoconnect")), False, False, 5)
        autobox.pack_end(self.labels['AP']['connection.autoconnect'], False, False, 5)
        
        self.scroll = self._screen.gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        grid.attach(plugRight, 0, 0, 2, 3)
        
        grid.attach(Gtk.Label(label=_("SSID")), 2, 1, 1, 1)
        grid.attach(self.labels['AP']['802-11-wireless.ssid'], 3, 1, 8, 1)
        
        grid.attach(Gtk.Label(label=_("Password")), 2, 2, 1, 1)
        grid.attach(self.labels['AP']['802-11-wireless-security.psk'], 3, 2, 8, 1)
        
        #grid.attach(Gtk.Label(label=_("Access Point Address")), 2, 3, 1, 1)
        #grid.attach(self.labels['AP']['ipv4.addresses'], 3, 3, 8, 1)
        
        grid.attach(plugLeft, 12, 0, 3, 3)
        grid.set_row_spacing(20)
        grid.set_vexpand(True)
        grid.set_valign(Gtk.Align.CENTER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(switchbox, False, True, 5)
        box.pack_start(autobox, False, True, 5)
        box.pack_start(grid, True, True, 5)
        self.button = {'save_changes': self._screen.gtk.Button("complete", _("Save changes"), "color1"),
                       'change': self._screen.gtk.Button("complete", _("Change"), "color1"),
                       'disable': self._screen.gtk.Button("cancel", _("Cancel Change"), "color2")}
        for btn in self.button:
            self.button[btn].set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
        #self.button['save_changes'].set_sensitive(False)
        self.button_box =  Gtk.Box()
        self.button_box =  Gtk.Box()
        self.button_box.pack_start(self.button['change'], False, False, 0)    
        self.button_box.set_valign(Gtk.Align.END)
        self.button_box.set_halign(Gtk.Align.END)
        self.button['save_changes'].connect('clicked', self.save_changes)
        self.button['change'].connect('clicked', self.change_fields)
        self.button['disable'].connect('clicked', self.disable_changes)
        box.pack_end(self.button_box, True, True, 0)
        self.scroll.add(box)
        self.add(self.scroll)
    

    def change_wifi_mode(self, switch, gdata):
        if not self.from_according:
            if switch.get_active():
                self._screen._ws.klippy.change_wifi_mode('AP')
            else:
                self._screen._ws.klippy.change_wifi_mode('Default')
    
    
    def change_fields(self, button):
        self.button_box.remove(self.button['change'])
        self.button_box.pack_start(self.button['disable'], False, False, 0) 
        self.button_box.pack_start(self.button['save_changes'], False, False, 0) 
        for property in self.labels['AP']:
               self.labels['AP'][property].set_sensitive(True)
        self.button_box.show_all()
    
    def disable_changes(self, button):
        for property in self.labels['AP']:
            if property == 'connection.autoconnect':
                self.labels['AP'][property].set_active((True if self.ap_connection['connection.autoconnect'] == 'yes' else False))  
            else:
                self.labels['AP'][property].set_text(self.ap_connection[property])
            self.labels['AP'][property].set_sensitive(False)
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        self.button_box.show_all()
    
    def on_click_switch(self, switch, event):
        self.from_according = False 
    
    def save_changes(self, widget):
        ssid = self.labels['AP']['802-11-wireless.ssid'].get_text()
        psk = self.labels['AP']['802-11-wireless-security.psk'].get_text()
        # addr = self.labels['AP']['ipv4.addresses'].get_text()
        # netmask = self.labels['AP']['netmask'].get_text()
        autoconnect = 'yes' if self.labels['AP']['connection.autoconnect'].get_active() else 'no'
        self._screen.remove_keyboard()
        os.system(f"nmcli connection modify {self.ap_connection['connection.id']} "
                  f"802-11-wireless.ssid {ssid} 802-11-wireless-security.psk {psk}"
                  f"connection.autoconnect {autoconnect}")
        
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        for property in self.labels['AP']:
                self.labels['AP'][property].set_sensitive(False)
        self.button_box.show_all()
    
    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self.on_accept_keyboard_dutton)
        self._screen.keyboard.change_entry(entry=entry)
    
    def show_according_wifi_mode(self, wifi_mode):
        if self.wifi_mode != wifi_mode:
            self.from_according = True
            self.wifi_mode = wifi_mode
            self.connect_switch.set_active((True if wifi_mode == 'AP' else False))
          
    def on_accept_keyboard_dutton(self):
        self._screen.remove_keyboard()