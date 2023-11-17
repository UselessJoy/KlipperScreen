import gi
import logging
import subprocess
import os
from ks_includes.widgets.typed_entry import TypedEntry
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class InterfaceConfiguration(Gtk.Box):
    def __init__(self, screen, interface):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.interface = interface
        self._screen = screen
        self.labels = {}
        
        
        self.labels['lan_static'] = {
            'method': Gtk.Switch(),
            'addresses' : TypedEntry("interface"),
            'netmask': TypedEntry("netmask"),
            'gateway': TypedEntry("interface"),
        }
        
        data = subprocess.check_output(f"nmcli -f ipv4.method,ipv4.addresses,ipv4.gateway connection show {self.interface}", universal_newlines=True, shell=True)
        data = data.split()
        self.nmcliData = {}
        for i in range(0, len(data), 2):
            self.nmcliData[data[i].partition('ipv4.')[2].split(':')[0]] = data[i+1]
        addr_split = self.nmcliData['addresses'].partition('/')
        self.method = self.nmcliData['method']
        self.nmcliData.update({'addresses' : addr_split[0]})
        self.nmcliData['netmask'] = addr_split[1] + addr_split[2]
        
        
        label = self._screen.gtk.Label(_("IP configuration"))
        label.set_hexpand(False)
        for property in self.labels['lan_static']:
            if property == 'method':
                self.labels['lan_static'][property].set_active((True if self.method == 'auto' else False))  
                self.labels['lan_static'][property].connect("notify::active", self.switch_method)
            else:
                self.labels['lan_static'][property].set_text(self.nmcliData[property])  
                self.labels['lan_static'][property].set_hexpand(True)
                self.labels['lan_static'][property].connect("button-press-event", self.on_change_entry)
            self.labels['lan_static'][property].set_sensitive(False)
        grid = Gtk.Grid()
        plugLeft = Gtk.Label()
        plugRight = Gtk.Label()
        plugLeft.set_size_request(self._screen.gtk.content_width/7, 1)
        plugRight.set_size_request(self._screen.gtk.content_width/7, 1)
        autobox = Gtk.Box()
        autobox.set_hexpand(True)
        autobox.set_vexpand(False)
        autobox.set_valign(Gtk.Align.CENTER)
        autobox.pack_start(Gtk.Label(label="DHCP"), False, False, 5)
        autobox.pack_end(self.labels['lan_static']['method'], False, False, 5)
        grid.attach(plugRight, 0, 0, 2, 3)
        
        grid.attach(Gtk.Label(label=_("IP-address")), 3, 1, 1, 1)
        grid.attach(self.labels['lan_static']['addresses'], 4, 1, 8, 1)
        
        grid.attach(Gtk.Label(label=_("Netmask")), 3, 2, 1, 1)
        grid.attach(self.labels['lan_static']['netmask'], 4, 2, 8, 1)
        
        grid.attach(Gtk.Label(label=_("Gateway")), 3, 3, 1, 1)
        grid.attach(self.labels['lan_static']['gateway'], 4, 3, 8, 1)
        
        grid.attach(plugLeft, 12, 0, 3, 3)
        
        self.scroll = self._screen.gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        
        grid.set_row_spacing(20)
        grid.set_vexpand(True)
        grid.set_valign(Gtk.Align.CENTER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(autobox, True, True, 5)
        box.pack_start(grid, True, True, 5)
        
        self.button = {'save_changes': self._screen.gtk.Button("complete", _("Save changes"), "color1"),
                       'change': self._screen.gtk.Button("complete", _("Change"), "color1"),
                       'disable': self._screen.gtk.Button("cancel", _("Cancel Change"), "color2")}
        for btn in self.button:
            self.button[btn].set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
        #self.button['save_changes'].set_sensitive(False)
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
    
    
    
    def change_fields(self, button):
        self.button_box.remove(self.button['change'])
        self.button_box.pack_start(self.button['disable'], False, False, 0) 
        self.button_box.pack_start(self.button['save_changes'], False, False, 0) 
        for property in self.labels['lan_static']:
            if self.method == 'manual':
                self.labels['lan_static'][property].set_sensitive(True)
            if property == 'method':
               self.labels['lan_static']['method'].set_sensitive(True)
        self.button_box.show_all()
    
    def disable_changes(self, button):
        for property in self.labels['lan_static']:
            if property == 'method':
                self.labels['lan_static'][property].set_active((True if self.nmcliData['method'] == 'auto' else False))  
            else:
                self.labels['lan_static'][property].set_text(self.nmcliData[property])
            self.labels['lan_static'][property].set_sensitive(False)
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        self.button_box.show_all()
        
    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self.on_accept_keyboard_button)
        self._screen.keyboard.change_entry(entry=entry)
    

    def switch_method(self, switch, gparam):
        self.method = 'auto' if switch.get_active() else 'manual'
        for property in self.labels['lan_static']:
            if property != 'method':
                self.labels['lan_static'][property].set_sensitive((not switch.get_active()))
    
    def save_changes(self, widget):
        addr = self.labels['lan_static']['addresses'].get_text()
        netmask = self.labels['lan_static']['netmask'].get_text()
        gateway = self.labels['lan_static']['gateway'].get_text()
        self._screen.remove_keyboard()
        os.system(f"nmcli connection down {self.interface}")
        os.system(f"nmcli connection modify {self.interface} ipv4.addresses {addr}{netmask} ipv4.gateway {gateway} ipv4.method {self.method} connection.autoconnect yes")
        os.system(f"nmcli connection up {self.interface}")
        
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        for property in self.labels['lan_static']:
                self.labels['lan_static'][property].set_sensitive(False)
        self.button_box.show_all()
    
    def on_accept_keyboard_button(self):
        self._screen.remove_keyboard()
