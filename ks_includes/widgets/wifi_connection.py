import logging
import os

import gi
import netifaces
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango
from ks_includes.wifi_nm import WifiManager
from ks_includes.widgets.typed_entry import TypedEntry
### Сделать: 
### - панель ошибки при отсутствии беспроводных интерфейсов
### - список подключений для нескольких сетевых интерфейсов
### - (необязательно) возможность создания нового сетевого интерфейса
### - os.system заменить на subprocess
class WiFiConnection(Gtk.Box):
    def __init__(self, screen):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.show_add = False
        self._screen = screen
        self.is_access_point_active = None
        self.networks = {}
        self.prev_network = None
        self.update_timeout = None
        self.network_interfaces = netifaces.interfaces()
        self.wireless_interfaces = [iface for iface in self.network_interfaces if iface.startswith('w')]
        self.timer_points = None
        self.counter = 1
        self.connecting = False
        self.wifi: WifiManager = self._screen.base_panel.get_wifi_dev()
        self.connecting_ssid = None
    
        self.labels = {}
        self.labels['interface'] = Gtk.Label()
        self.labels['interface'].set_text(self.wireless_interfaces[0])
        self.labels['interface'].set_hexpand(True)
        self.labels['ip'] = Gtk.Label()
        self.labels['ip'].set_hexpand(True)
        
        self.labels['networks'] = {}
        if netifaces.AF_INET in netifaces.ifaddresses('wlan0') and len(netifaces.ifaddresses('wlan0')[netifaces.AF_INET]) > 0:
            ip = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        else:
            ip = None

        self.rescan_button = self._screen.gtk.Button("refresh", None, "color1", .66)
        self.rescan_button.connect("clicked", self.reload_networks)
        self.rescan_button.set_hexpand(False)
        sbox = Gtk.Box()
        sbox.set_hexpand(True)
        sbox.set_vexpand(False)
        sbox.add(Gtk.Label(label=_("Interface: ")))
        sbox.add(self.labels['interface'])
        if ip is not None:
            self.labels['ip'].set_text(f"IP: {ip}  ") 
        sbox.add(self.labels['ip'])
        sbox.add(self.rescan_button)

        scroll = self._screen.gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_vexpand(True)
        self.labels['networklist'] = Gtk.Grid()

        if self.wifi is not None and self.wifi.initialized:
            box.pack_start(sbox, False, False, 5)
            box.pack_start(scroll, True, True, 0)
            GLib.idle_add(self.load_networks)
            scroll.add(self.labels['networklist'])

            self.wifi.add_callback("connected", self.connected_callback)
            self.wifi.add_callback("scan_results", self.scan_callback)
            self.wifi.add_callback("popup", self.popup_callback)
            self.wifi.add_callback("disconnected", self.disconnected_callback)
            self.wifi.add_callback("connecting", self.connecting_callback)
            self.wifi.add_callback("rescan_finish", self.rescan_finish_callback)
            if self.update_timeout is None:
                self.update_timeout = GLib.timeout_add_seconds(5, self.update_all_networks)
        else:
            self.labels['networkinfo'] = Gtk.Label("")
            self.labels['networkinfo'].get_style_context().add_class('temperature_entry')
            box.pack_start(self.labels['networkinfo'], False, False, 0)
            self.update_single_network_info()
            if self.update_timeout is None:
                self.update_timeout = GLib.timeout_add_seconds(5, self.update_single_network_info)
        self.add(box)
        self.labels['main_box'] = box

        ap_scroll = self._screen.gtk.ScrolledWindow()
        ap_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL) 
        ap_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label()
        title.set_markup(_("<b>Disable the access point?</b>\n"))
        title.set_line_wrap(True)
        title.set_halign(Gtk.Align.CENTER)
        title.set_hexpand(True)
        message = Gtk.Label(label=_("After turning on the access point, Wi-Fi is turned off.\n To turn on Wi-Fi, turn off the access point"))
        message.set_line_wrap(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_valign(Gtk.Align.END)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        scroll.add(message)
        grid = Gtk.Grid()
        grid.attach(title, 0, 0, 1, 1)
        grid.attach(Gtk.Separator(), 0, 1, 2, 1)
        grid.attach(scroll, 0, 2, 2, 1)
        button = {
            'resume': self._screen.gtk.Button("complete", _("Resume"), "color1"),
        }
        button['resume'].set_size_request((self._screen.width - 30) / 3, self._screen.height / 5)
        button_box =  Gtk.Box()
        button_box.pack_start(button['resume'], True, False, 0)    
        button_box.set_valign(Gtk.Align.END)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_vexpand(True)
        button_box.set_hexpand(True)
        button['resume'].connect('clicked', self.resume)
        ap_box.pack_start(grid, True, True, 0)
        ap_box.pack_end(button_box, True, True, 0)
        ap_scroll.add(ap_box)
        self.labels['AP_box'] = ap_scroll

    def print_network_mode(self, is_access_point_active):
        if self.is_access_point_active != is_access_point_active:
            self.is_access_point_active = is_access_point_active
            if self.is_access_point_active:
                self.in_AP_mode()
            else:
                self.in_DEF_mode()

    def in_AP_mode(self):
        for child in self.get_children():
                self.remove(child)
        self.add(self.labels['AP_box'])
        self.show_all()

    def in_DEF_mode(self):
        for child in self.get_children():
                self.remove(child)
        self.add(self.labels['main_box'])
        self.show_all()

    def resume(self, widget):
        self.disconnect_network(None, self.wifi.get_connected_ssid())
        
    def load_networks(self):
        networks = self.wifi.get_networks()  
        if not networks:
            return 
        for net in networks:
            self.add_network(net, False)
        self.update_all_networks()
        self.show_all()

    def add_network(self, ssid, show=True):
        try:
            netinfo = self.wifi.get_network_info(ssid)
        except:
            return
        if ssid is None:
            return
        ssid = ssid.strip()
        if ssid in list(self.networks):
            return

        configured_networks = self.wifi.get_supplicant_networks()
        network_id = -1
        for net in list(configured_networks):
            if configured_networks[net]['ssid'] == ssid:
                network_id = net

        display_name = _("Hidden") if ssid.startswith("\x00") else f"{ssid}"
        connected_ssid = self.wifi.get_connected_ssid()
        if connected_ssid == ssid:
            netinfo = {'connected': True}
        else:
            netinfo = {'connected': False}

        if connected_ssid == ssid:
            display_name += " (" + _("Connected") + ")"

        name = Gtk.Label("")
        name.set_markup(f"<big><b>{display_name}</b></big>")
        name.set_hexpand(True)
        name.set_halign(Gtk.Align.START)
        name.set_line_wrap(True)
        name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        info = Gtk.Label()
        info.set_halign(Gtk.Align.START)
        info.set_line_wrap(True)
        info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        labels.add(name)
        labels.add(info)
        labels.set_vexpand(True)
        labels.set_valign(Gtk.Align.CENTER)
        labels.set_halign(Gtk.Align.START)

        connect = self._screen.gtk.Button("load", None, "color3", .66)
        connect.connect("clicked", self.connect_network, ssid)
        connect.set_hexpand(False)
        connect.set_halign(Gtk.Align.END)
        
        disconnect = self._screen.gtk.Button("signout", None, "color2", .66)
        disconnect.connect("clicked", self.disconnect_network, ssid)
        disconnect.set_hexpand(False)
        disconnect.set_halign(Gtk.Align.END)

        delete = self._screen.gtk.Button("delete", None, "color3", .66)
        delete.connect("clicked", self.remove_wifi_network, ssid)
        delete.set_hexpand(False)
        delete.set_halign(Gtk.Align.END)

        network = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        network.get_style_context().add_class("frame-item")
        network.set_hexpand(True)
        network.set_vexpand(False)

        network.add(labels)
        
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        if self.connecting:
            disconnect.set_sensitive(False)
            delete.set_sensitive(False)
            connect.set_sensitive(False)
        if netinfo['connected']:
            buttons.pack_end(disconnect, False, False, 0)
            buttons.pack_end(delete, False, False, 0)
        elif network_id != -1:
            buttons.pack_end(connect, False, False, 0)
            buttons.pack_end(delete, False, False, 0)
        else:
            buttons.pack_end(connect, False, False, 0)
        network.add(buttons)
        self.networks[ssid] = network

        nets = sorted(list(self.networks), reverse=False)
        if connected_ssid in nets:
            nets.remove(connected_ssid)
            nets.insert(0, connected_ssid)
        if nets.index(ssid) is not None:
            pos = nets.index(ssid)
        else:
            logging.info("Error: SSID not in nets")
            return

        self.labels['networks'][ssid] = {
            "connect": connect,
            "delete": delete,
            "disconnect": disconnect,
            "info": info,
            "name": name,
            "row": network
        }

        self.labels['networklist'].insert_row(pos)
        self.labels['networklist'].attach(self.networks[ssid], 0, pos, 1, 1)
        if show:
            logging.info("Show network " + ssid)
            self.labels['networklist'].show()

    def add_new_network(self, widget, ssid, connect=False):
        psk = self.labels['network_psk'].get_text()
        if len(psk) < 8:
            self._screen.show_popup_message(_("Password must contains over 8 symbols"), 3, True)
            return
        result = self.wifi.add_network(ssid, psk)
        self._screen.remove_keyboard()
        self.close_add_network()
        if connect:
            if result:
                self.connect_network(widget, ssid, False)
            else:
                self._screen.show_popup_message(_(f"Error adding network {ssid}"))
            return

    def check_missing_networks(self):
        networks = self.wifi.get_networks()
        for net in list(self.networks):
            if net in networks:
                networks.remove(net)

        for net in networks:
            self.add_network(net, False)
        self.labels['networklist'].show_all()

    def close_add_network(self):
        if not self.show_add:
            return

        for child in self.get_children():
            self.remove(child)
        self.add(self.labels['main_box'])
        self.show()
        for i in ['add_network', 'network_psk']:
            if i in self.labels:
                del self.labels[i]
        self.show_add = False

    def popup_callback(self, msg):
        self.connecting = False
        if self.timer_points:
            GLib.source_remove(self.timer_points)
            self.timer_points = None
        if self.connecting_ssid:
            self.remove_network(self.connecting_ssid)
            self.connecting_ssid = None
        self._screen.show_popup_message(msg)
    
    def disconnected_callback(self, msg):
        self.connecting = False
        if self.timer_points:
            GLib.source_remove(self.timer_points)
            self.timer_points = None
        self.check_missing_networks()
    
    def connecting_callback(self, msg):
        self.connecting = True
    
    def rescan_finish_callback(self, msg):
        self._screen.gtk.Button_busy(self.rescan_button, False)
        GLib.idle_add(self.load_networks)
                                    
    def connected_callback(self, ssid, prev_ssid):
        logging.info("Now connected to a new network")
        self.connecting = False
        self.connecting_ssid = None
        if self.timer_points:
                GLib.source_remove(self.timer_points)
                self.timer_points = None
        if ssid is not None:
            self.remove_network(ssid)
        if prev_ssid != ssid:
            self.remove_network(prev_ssid)
        self.check_missing_networks()
        self.add_network(ssid)
        self.update_all_networks()

    def disconnect_network(self, widget, ssid):
        self.remove_network(ssid)
        self.wifi.disconnect_network(ssid)
        
    def connect_network(self, widget, ssid, showadd=True):
        self.connecting_ssid = ssid
        snets = self.wifi.get_supplicant_networks()
        isdef = False
        for netid, net in snets.items():
            if net['ssid'] == ssid:
                isdef = True
                break

        if not isdef:
            if showadd:
                self.show_add_network(widget, ssid)
            return
        self.prev_network = self.wifi.get_connected_ssid()
        if self.prev_network in list(self.networks):
            self.remove_network(self.prev_network)
        self.wifi.connect(ssid)
        GLib.idle_add(self.load_networks)
        self.update_all_networks()
        if self.timer_points:
            GLib.source_remove(self.timer_points)
            self.timer_points = None
        self.timer_points = GLib.timeout_add(500, self.update_connecting_status, ssid)

    def update_connecting_status(self, ssid):
        points = "." * int(self.counter%4)
        conn = _("Connecting")
        self.labels['networks'][ssid]['name'].set_markup(f"<big><b>{ssid} ({conn}{points})</b></big>")
        self.counter +=1
        return True
    
    def connecting_status_callback(self, msg):
        self.labels['connecting_info'].set_text(f"{self.labels['connecting_info'].get_text()}\n{msg}")
        self.labels['connecting_info'].show_all()

    def remove_network(self, ssid, show=True):
        if ssid not in list(self.networks):
            return
        for i in range(len(self.labels['networklist'])):
            if self.networks[ssid] == self.labels['networklist'].get_child_at(0, i):
                self.labels['networklist'].remove_row(i)
                self.labels['networklist'].show()
                del self.networks[ssid]
                del self.labels['networks'][ssid]
                return

    def remove_wifi_network(self, widget, ssid):
        self.wifi.delete_network(ssid)
        self.remove_network(ssid)
        self.check_missing_networks()

    def scan_callback(self, new_networks, old_networks):
        for net in old_networks:
            self.remove_network(net, False)
        for net in new_networks:
            self.add_network(net, False)
        self.show_all()

    def back(self):
        if self.show_add:
            self.close_add_network()
            return True
        return False
    
    def show_add_network(self, widget, ssid):
        self.ssid = ssid
        if self.show_add:
            return

        for child in self.get_children():
            self.remove(child)

        if "add_network" in self.labels:
            del self.labels['add_network']
        label = Gtk.Label(label=_("PSK for") + f' {ssid}', hexpand=False)
        self.labels['network_psk'] = TypedEntry()
        self.labels['network_psk'].set_text('')
        self.labels['network_psk'].set_hexpand(True)
        self.labels['network_psk'].connect("activate", self.add_new_network, ssid, True)
        self.labels['network_psk'].connect("focus-in-event", self.on_change_entry)
        
        save = self._screen.gtk.Button("complete", _("Connect"), "color3")
        save.set_hexpand(False)
        save.connect("clicked", self.add_new_network, ssid, True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.labels['network_psk'], True, True, 5)
        save.get_style_context().add_class("keyboard_pad")
        self.labels['add_network'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.labels['add_network'].set_valign(Gtk.Align.CENTER)
        self.labels['add_network'].set_hexpand(True)
        self.labels['add_network'].set_vexpand(True)
        self.labels['add_network'].pack_start(label, True, True, 5)
        self.labels['add_network'].pack_start(box, True, True, 5)

        self.add(self.labels['add_network'])
        self.labels['network_psk'].grab_focus_without_selecting()
        self.show_all()
        self.show_add = True
    
    def on_change_entry(self, entry, event):
        self._screen.show_keyboard(entry=entry, accept_function=self.on_accept_keyboard_dutton)
        self._screen.keyboard.change_entry(entry=entry)

    def on_accept_keyboard_dutton(self):
        self.add_new_network(self.labels['network_psk'], self.ssid, True)
                   
    def update_all_networks(self):
        for network in list(self.networks):
            self.update_network_info(network)
        return True

    def update_network_info(self, ssid):
        info = freq = encr = chan = lvl = ipv4 = ipv6 = ""
        if ssid not in list(self.networks) or ssid not in self.labels['networks']:
            logging.info(f"Unknown SSID {ssid}")
            return
        try:
            netinfo = self.wifi.get_network_info(ssid)
            if netinfo == {}:
                self.remove_network(ssid)
                return
        except:
                self.remove_network(ssid)
                return
        if "connected" in netinfo:
            connected = netinfo['connected']
        else:
            connected = False

        if connected or self.wifi.get_connected_ssid() == ssid:
            stream = os.popen('hostname -f')
            hostname = stream.read().strip()
            ifadd = netifaces.ifaddresses('wlan0')
            if netifaces.AF_INET in ifadd and len(ifadd[netifaces.AF_INET]) > 0:
                ipv4 = f"<b>IPv4:</b> {ifadd[netifaces.AF_INET][0]['addr']} "
                self.labels['ip'].set_text(f"IP: {ifadd[netifaces.AF_INET][0]['addr']}  ")
            if netifaces.AF_INET6 in ifadd and len(ifadd[netifaces.AF_INET6]) > 0:
                ipv6 = f"<b>IPv6:</b> {ifadd[netifaces.AF_INET6][0]['addr'].split('%')[0]} "
            info = '<b>' + _("Hostname") + f':</b> {hostname}\n{ipv4}\n{ipv6}\n'
        elif "psk" in netinfo:
            info = _("Password saved")
        if "encryption" in netinfo:
            if netinfo['encryption'] != "off":
                encr = netinfo['encryption'].upper()
        if "frequency" in netinfo:
            freq = "2.4 GHz" if netinfo['frequency'][0:1] == "2" else "5 Ghz"
        if "channel" in netinfo:
            chan = _("Channel") + f' {netinfo["channel"]}'
        if "signal_level_dBm" in netinfo:
            lvl = f"{netinfo['signal_level_dBm']}%"
            icon_name = self._screen.base_panel.signal_strength(int(netinfo["signal_level_dBm"]))
            if 'icon' not in self.labels['networks'][ssid]:
                icon = self._screen.gtk.Image(icon_name)
                self.labels['networks'][ssid]['icon'] = icon
                self.labels['networks'][ssid]['row'].add(icon)
                self.labels['networks'][ssid]['row'].reorder_child(icon, 0)
            else:
                self._screen.gtk.update_image(self.labels['networks'][ssid]['icon'], icon_name)
        else:
            if not self.timer_points:
                self.labels['networks'][ssid]['name'].set_markup(f"<big><b>{ssid}</b></big>")
        self.labels['networks'][ssid]['info'].set_markup(f"{info} <small>{encr}  {freq}  {chan}  {lvl}</small>")
        buttons = ("connect", "disconnect", "delete")
        for button in buttons:
            if button in self.labels['networks'][ssid]:
                self.labels['networks'][ssid][button].set_sensitive(not self.connecting)
        self.labels['networks'][ssid]['info'].show_all()
        self.labels['networks'][ssid]['row'].show_all()
    
    def update_single_network_info(self):
        stream = os.popen('hostname -f')
        hostname = stream.read().strip()
        ifadd = netifaces.ifaddresses(self.wireless_interfaces[0])
        ipv4 = ""
        ipv6 = ""
        if netifaces.AF_INET in ifadd and len(ifadd[netifaces.AF_INET]) > 0:
            ipv4 = f"<b>IPv4:</b> {ifadd[netifaces.AF_INET][0]['addr']} "
            self.labels['ip'].set_text(f"Статический IP для проводного подключения")
        if netifaces.AF_INET6 in ifadd and len(ifadd[netifaces.AF_INET6]) > 0:
            ipv6 = f"<b>IPv6:</b> {ifadd[netifaces.AF_INET6][0]['addr'].split('%')[0]} "
        connected = (
            f'<b>{self.wireless_interfaces[0]}</b>\n\n'
            f'<small><b>' + _("Connected") + f'</b></small>\n'
            + '<b>' + _("Hostname") + f':</b> {hostname}\n'
            f'{ipv4}\n'
            f'{ipv6}\n'
        )
        self.labels['networkinfo'].set_markup(connected)
        self.labels['networkinfo'].show_all()
        return True

    def reload_networks(self, widget=None):
        self.networks = {}
        self.labels['networklist'].remove_column(0)
        if self.wifi is not None and self.wifi.initialized:
            self._screen.gtk.Button_busy(self.rescan_button, True)
            self.wifi.rescan()

    def activate(self):
        if self.initialized:
            self.reload_networks()
            if self.update_timeout is None:
                if self.wifi is not None and self.wifi.initialized:
                    self.update_timeout = GLib.timeout_add_seconds(5, self.update_all_networks)
                else:
                    self.update_timeout = GLib.timeout_add_seconds(5, self.update_single_network_info)

    def deactivate(self):
        if self.update_timeout is not None:
            GLib.source_remove(self.update_timeout)
            self.update_timeout = None
            