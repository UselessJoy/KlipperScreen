import gi
import logging
import nmcli
from ks_includes.widgets.typed_entry import TypedEntry, InterfaceRule, NetmaskRule
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

### os.system заменить на subprocess
class InterfaceConfiguration(Gtk.Box):
    def __init__(self, screen, int=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.realize = False
        self.nmcliData = {}
        self.connection_id = None
        self._screen = screen
        self.labels = {}
        self.in_dhcp_mode = None
        self.content = Gtk.Box()
        self.scroll = self._screen.gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        nmcli.disable_use_sudo()
        er = ""
        for connection in nmcli.connection():
          if connection.conn_type == 'ethernet':
            try:
              connectionData = nmcli.connection.show(connection.name)
              self.connection_id = connectionData['connection.id']
              logging.info(connectionData)
            except Exception as e:
              logging.info(f"Get connection error:\n{e}\n")
              er = e
        if not self.connection_id:
          self.scroll = self.create_error_page(er)
          self.scroll.show_all()
          return

        self.reinit_connectionData()
        
        self.labels['lan_static'] = {
            'ipv4.addresses' : TypedEntry(InterfaceRule),
            'netmask': TypedEntry(NetmaskRule),
            'ipv4.gateway': TypedEntry(InterfaceRule),
        }
        
        self.dhcp_entry = TypedEntry()
        self.dhcp_entry.get_style_context().add_class('unused_entry')
        self.dhcp_entry.set_sensitive(False) 
        for property in self.labels['lan_static']:
            self.labels['lan_static'][property].set_hexpand(True)
            self.labels['lan_static'][property].connect("button-press-event", self.on_change_entry)
            self.labels['lan_static'][property].set_sensitive(False)  
        
        self.reinit_entries()
        self.content = self.create_content()
        self.dhcp_switch = Gtk.Switch()
        self.dhcp_switch.set_active(self.in_dhcp_mode)  
        self.dhcp_switch.set_sensitive(False)
        self.dhcp_switch.connect("notify::active", self.switch_method)
        
        autobox = Gtk.Box()
        autobox.set_hexpand(True)
        autobox.set_vexpand(False)
        autobox.set_valign(Gtk.Align.CENTER)
        
        autobox.pack_start(Gtk.Label(label=_("DHCP")), False, False, 0)
        autobox.pack_end(self.dhcp_switch, False, False, 0)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(autobox, True, True, 5)
        box.pack_start(self.content, True, True, 5)
        
        self.button = {'save_changes': self._screen.gtk.Button("complete", _("Save changes"), "color1"),
                       'change': self._screen.gtk.Button("complete", _("Change"), "color1"),
                       'disable': self._screen.gtk.Button("cancel", _("Cancel Change"), "color2")}
        for btn in self.button:
            self.button[btn].set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
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
        self.realize = True
    
    def create_content(self):
        grid = Gtk.Grid()
        plugLeft = Gtk.Label()
        plugRight = Gtk.Label()
        plugLeft.set_size_request(self._screen.gtk.content_width/7, 1)
        plugRight.set_size_request(self._screen.gtk.content_width/7, 1)
        grid.attach(plugRight, 0, 0, 2, 4)
        
        grid.attach(Gtk.Label(label=_("DHCP-address")), 3, 0, 1, 1)
        grid.attach(self.dhcp_entry, 4, 0, 8, 1)
        
        grid.attach(Gtk.Label(label=_("IP-address")), 3, 1, 1, 1)
        grid.attach(self.labels['lan_static']['ipv4.addresses'], 4, 1, 8, 1)
        
        grid.attach(Gtk.Label(label=_("Netmask")), 3, 2, 1, 1)
        grid.attach(self.labels['lan_static']['netmask'], 4, 2, 8, 1)
        
        grid.attach(Gtk.Label(label=_("Gateway")), 3, 3, 1, 1)
        grid.attach(self.labels['lan_static']['ipv4.gateway'], 4, 3, 8, 1)
        
        grid.attach(plugLeft, 12, 0, 3, 4)
        
        grid.set_row_spacing(5)
        grid.set_vexpand(True)
        grid.set_valign(Gtk.Align.CENTER)
        
        return grid    
        
    def reinit_entries(self):
        for property in self.labels['lan_static']:
            if self.nmcliData[property] != None:
                self.labels['lan_static'][property].set_text(self.nmcliData[property])
            else:
                self.labels['lan_static'][property].set_text('')
        self.dhcp_entry.set_text(self.nmcliData['DHCP4.OPTION[5]'] if self.nmcliData['DHCP4.OPTION[5]'] != None else '')
        
    def reinit(self):
        if self.realize:
            self.reinit_connectionData()
            self.reinit_entries()  
        
    def reinit_connectionData(self):
        connectionData = None
        try:
            connectionData = nmcli.connection.show(self.connection_id)
            if 'ipv4.method' in connectionData:
                method = connectionData['ipv4.method']
                if method not in ['auto', 'manual']:
                    raise Exception(_("Cannot configure ipv4 addresses for connection.\n Reconfigure connection\n"))
            else:
                raise Exception(_("Cannot find method for connection\n"))
        except Exception as e:
            logging.error(e)
            for child in self.scroll.get_children():
                self.scroll.remove(child)
            self.scroll = self.create_error_page(e)
            self.scroll.show_all()
            return
        self.nmcliData = connectionData
        self.in_dhcp_mode = True if method == 'auto' else False
        self.nmcliData['netmask'] = None
        if 'DHCP4.OPTION[5]' not in self.nmcliData:
            self.nmcliData['DHCP4.OPTION[5]'] = None
        if 'ipv4.addresses' in self.nmcliData and self.nmcliData['ipv4.addresses'] != None:
            try:
              addr_split = self.nmcliData['ipv4.addresses'].partition('/')
            except:
              addr_split = ["", "", ""]
            self.nmcliData.update({'ipv4.addresses' : addr_split[0]})
            self.nmcliData['netmask'] = addr_split[2]
        if 'DHCP4.OPTION[5]' in self.nmcliData and self.nmcliData['DHCP4.OPTION[5]'] != None:
            try:
              addr_split = self.nmcliData['DHCP4.OPTION[5]'].partition('=')
            except:
              addr_split = ["", "", ""]
            self.nmcliData.update({'DHCP4.OPTION[5]' : addr_split[2].lstrip()})
     
    def create_error_page(self, error):
        err_scroll = self._screen.gtk.ScrolledWindow()
        err_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL) 
        err_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        title = Gtk.Label()
        title.set_markup(_("Error on load LAN interface"))
        title.set_line_wrap(True)
        title.set_halign(Gtk.Align.CENTER)
        title.set_hexpand(True)
        
        message = Gtk.Label(label=str(error))
        message.set_line_wrap(True)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_valign(Gtk.Align.END)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(message)
        
        grid = Gtk.Grid()
        grid.attach(title, 0, 0, 1, 1)
        grid.attach(Gtk.Separator(), 0, 1, 2, 1)
        grid.attach(scroll, 0, 2, 2, 1)
        
        err_box.pack_start(grid, True, True, 0)
        err_scroll.add(err_box)
        return err_scroll
      
    def change_fields(self, button):
        self.button_box.remove(self.button['change'])
        self.button_box.pack_start(self.button['disable'], False, False, 0) 
        self.button_box.pack_start(self.button['save_changes'], False, False, 0) 
        for property in self.labels['lan_static']:
            self.labels['lan_static'][property].set_sensitive(True)
        self.dhcp_switch.set_sensitive(True)
        self.button_box.show_all()
    
    def disable_changes(self, button):
        for property in self.labels['lan_static']:
            if self.nmcliData[property] != None:
                self.labels['lan_static'][property].set_text(self.nmcliData[property])
            else:
                self.labels['lan_static'][property].set_text('')
            self.labels['lan_static'][property].set_sensitive(False)
        self.dhcp_entry.set_text(self.nmcliData['DHCP4.OPTION[5]'] if self.nmcliData['DHCP4.OPTION[5]'] != None else '')
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        self.button_box.show_all()
        self._screen.remove_numpad()

    def on_change_entry(self, entry, event):
        self._screen.show_numpad(entry=entry, accept_function=self.on_accept_numpad_button)
        self._screen.numpad.change_entry(entry=entry)

    def switch_method(self, switch, gparam):
        self.in_dhcp_mode = switch.get_active()
        if self.in_dhcp_mode:
            self._screen.show_popup_message(_("DHCP selected. Set parameters will be deleted after saving"), level=2, just_popup = True)
        for property in self.labels['lan_static']:
                self.labels['lan_static'][property].set_sensitive((not switch.get_active()))

    #Реализовать
    def validate(self):
        return True
    
    def save_changes(self, widget):
        if not self.validate():
            self._screen.show_popup_message(_("Data is not valid"))
        if self.dhcp_switch.get_active():
            for property in self.labels['lan_static']:
                self.labels['lan_static'][property].set_text('')     
            nmcli.connection.down(self.connection_id)
            nmcli.connection.modify(self.connection_id, {
                'ipv4.method': 'auto',
                'connection.autoconnect': 'yes',
                'ipv4.addresses': '',
                'ipv4.gateway': ''
            })
            nmcli.connection.up(self.connection_id)
        else:
            addr = self.labels['lan_static']['ipv4.addresses'].get_text()
            netmask = self.labels['lan_static']['netmask'].get_text()
            gateway = self.labels['lan_static']['ipv4.gateway'].get_text()

            nmcli.connection.down(self.connection_id)
            nmcli.connection.modify(self.connection_id, {
                'ipv4.method': 'manual',
                'connection.autoconnect': 'yes',
                'ipv4.addresses': f"{addr}/{netmask}",
                'ipv4.gateway': gateway
            })
            nmcli.connection.up(self.connection_id)
        self._screen.remove_numpad()
        for child in self.button_box:
            self.button_box.remove(child)
        self.button_box.pack_start(self.button['change'], False, False, 0) 
        for property in self.labels['lan_static']:
                self.labels['lan_static'][property].set_sensitive(False)
        self.dhcp_switch.set_sensitive(False)
        self.button_box.show_all()
        
    def on_accept_numpad_button(self):
        self._screen.remove_numpad()