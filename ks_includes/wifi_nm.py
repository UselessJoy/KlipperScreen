# Network in KlipperScreen is a connection in NetworkManager
# Interface in KlipperScreen is a device in NetworkManager

import contextlib
import logging
import traceback
import uuid
import os
from ks_includes import NetworkManager
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import gi
from subprocess import Popen
from threading import Thread

gi.require_version('Gdk', '3.0')
from gi.repository import GLib

from ks_includes.wifi import WifiChannels

NM_STATE = {
    NetworkManager.NM_DEVICE_STATE_UNKNOWN : {
            'msg': "State is unknown",
            'callback': "disconnected"
        },
    NetworkManager.NM_DEVICE_STATE_REASON_UNKNOWN : {
            'msg': "State is unknown",
            'callback': "disconnected"
        },
    NetworkManager.NM_DEVICE_STATE_UNMANAGED : {
            'msg': "Error: Not managed by NetworkManager",
            'callback': "disconnected"
        },
    NetworkManager.NM_DEVICE_STATE_UNAVAILABLE : {
            'msg': "Error: Not available for use:\nReasons may include the wireless switched off, missing firmware, etc.",
            'callback': "disconnected"
        },
    NetworkManager.NM_DEVICE_STATE_DISCONNECTED : {
            'msg': "Currently disconnected",
            'callback': "disconnected"
        },
    NetworkManager.NM_DEVICE_STATE_PREPARE : {
            'msg': "Preparing the connection to the network",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_CONFIG : {
            'msg': "Connecting to the requested network...",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_NEED_AUTH : {
            'msg': "Authorizing",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_IP_CONFIG : {
            'msg': "Requesting IP addresses and routing information",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_IP_CHECK : {
            'msg': "Checking whether further action is required for the requested network connection",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_SECONDARIES : {
            'msg': "Waiting for a secondary connection (like a VPN)",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_ACTIVATED : {
            'msg': "Connected",
            'callback': "connecting_status"
        },
    NetworkManager.NM_DEVICE_STATE_DEACTIVATING : {
            'msg': "A disconnection from the current network connection was requested",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_FAILED : {
            'msg': _("Failed to connect to the requested network"),
            'callback': "popup"
        },
    NetworkManager.NM_DEVICE_STATE_REASON_DEPENDENCY_FAILED : {
            'msg': "A dependency of the connection failed",
            'callback': "connecting"
        },
    NetworkManager.NM_DEVICE_STATE_REASON_CARRIER : {
            'msg': "",
            'callback': ""
        }
    
}

class WifiManager:
    networks_in_supplicant = []

    def __init__(self, wireless_interface, *args, **kwargs):
        super().__init__(*args, **kwargs)
        DBusGMainLoop(set_as_default=True)
        self._callbacks = {
            "connected": [],
            "connecting_status": [],
            "scan_results": [],
            "popup": [],
            "disconnected": [],
            "connecting": [],
            "rescan_finish": []
            #"properties_changed": []
        }
        self.connected = False
        self.connected_ssid = None
        self.known_networks = {}  # List of known connections
        self.visible_networks = {}  # List of visible access points
        self.ssid_by_path = {}
        self.path_by_ssid = {}
        self.hidden_ssid_index = 0
        try:
            self.last_connected_ssid = self.get_connected_ssid()
        except:
            self.last_connected_ssid = None
        # NetworkManager.NetworkManager.OnPropertiesChanged(self.nm_prop_changed)
        self.wireless_device = NetworkManager.NetworkManager.GetDeviceByIpIface(wireless_interface)
        self.wireless_device.OnAccessPointAdded(self._ap_added)
        self.wireless_device.OnAccessPointRemoved(self._ap_removed)
        self.wireless_device.OnStateChanged(self._ap_state_changed)
        # Коллбэк на очередное состояние NetworkManager
        #self.wireless_device.OnPropertiesChanged(self.nm_prop_changed)

        for ap in self.wireless_device.GetAccessPoints():
            self._add_ap(ap)
        self._update_known_connections()
        self.initialized = True
        
        self.rescan_thread = None
        self.rescan_thread = self.thread_rescan_popen_callback(self._on_rescan)
        self.rescan_timer = GLib.timeout_add_seconds(30, self.rescan)

    # NetworkingConnectivity bug (show 4(limited) but nmcli show 5(full)) "Full"singal from both interfaces  
    # Обработка коллбэка на очередное состояние NetworkManager
    # def nm_prop_changed(self, ap, interface, signal, properties):
    #     logging.info(f"Callback nm_prop_changed:")
    #     logging.info( NetworkManager.NetworkManager.CheckConnectivity())
    #     logging.info(properties)
        
    def _update_known_connections(self):
        self.known_networks = {}
        for con in NetworkManager.Settings.ListConnections():
            settings = con.GetSettings()
            if "802-11-wireless" in settings:
                ssid = settings["802-11-wireless"]['ssid']
                self.known_networks[ssid] = con
                
    def _ap_added(self, nm, interface, signal, access_point):
        try:
            # Привязка коллбэка на изменение поля для очередного соединения 
            #access_point.OnPropertiesChanged(self._ap_prop_changed)
            ssid = self._add_ap(access_point)
            for cb in self._callbacks['scan_results']:
                args = (cb, [ssid], [])
                GLib.idle_add(*args)
        except Exception as e:
            logging.error("Error in _ap_added")
            logging.exception(f"{e}\n\n{traceback.format_exc()}")

    def _ap_removed(self, dev, interface, signal, access_point):
        try:
            path = access_point.object_path
            if path in self.ssid_by_path:
                ssid = self.ssid_by_path[path]
                self._remove_ap(path)
                for cb in self._callbacks['scan_results']:
                    args = (cb, [ssid], [])
                    GLib.idle_add(*args)
        except Exception as e:
            logging.error("Error in _ap_removed")
            logging.exception(f"{e}\n\n{traceback.format_exc()}")

    def _ap_state_changed(self, nm, interface, signal, old_state, new_state, reason):
        if new_state in NM_STATE:
            self.callback(NM_STATE[new_state]['callback'], NM_STATE[new_state]['msg'])
            #logging.info(f"State {NM_STATE[new_state]['callback']} msg {NM_STATE[new_state]['msg']}")

        if new_state == NetworkManager.NM_DEVICE_STATE_ACTIVATED:
            self.connected = True
            self.last_connected_ssid = self.get_connected_ssid
            for cb in self._callbacks['connected']:
                args = (cb, self.get_connected_ssid(), None)
                GLib.idle_add(*args)
        else:
            self.connected = False
            
    # Обработка коллбэка на изменение поля для очередного соединения        
    # Пропсы очень плохо регистрируются (на активном соеднении вообще не регистрируются) 
    # def _ap_prop_changed(self, ap, interface, signal, properties):
    #     logging.info(f"Callback _ap_prop_changed:")
    #     logging.info(ap.Ssid)
    #     logging.info(ap.Strength)
        #logging.info(properties)
        # ap_status = {'ssid': ap.Ssid}
        # ap_status['properties'] = properties
        # self.callback("properties_changed", ap_status)

    def _add_ap(self, ap):
        ssid = ap.Ssid
        if ssid == "":
            ssid = _("Hidden") + f" {self.hidden_ssid_index}"
            self.hidden_ssid_index += 1
        self.ssid_by_path[ap.object_path] = ssid
        self.path_by_ssid[ssid] = ap.object_path
        self.visible_networks[ap.object_path] = ap
        return ssid

    def _remove_ap(self, path):
        self.ssid_by_path.pop(path, None)
        self.visible_networks.pop(path, None)

    def add_callback(self, name, callback):
        if name in self._callbacks and callback not in self._callbacks[name]:
            self._callbacks[name].append(callback)

    def callback(self, cb_type, msg):
        if cb_type in self._callbacks:
            for cb in self._callbacks[cb_type]:
                GLib.idle_add(cb, msg)

    def add_network(self, ssid, psk):
        aps = self._visible_networks_by_ssid()
        if ssid in aps:
            ap = aps[ssid]
        new_connection = {
            '802-11-wireless': {
                'mode': 'infrastructure',
                'security': '802-11-wireless-security',
                'ssid': ssid
            },
            '802-11-wireless-security': {
                'auth-alg': 'open',
                'key-mgmt': 'wpa-psk',
                'psk': psk
            },
            'connection': {
                'id': ssid,
                'type': '802-11-wireless',
                'uuid': str(uuid.uuid4())
            },
            'ipv4': {
                'method': 'auto'
            },
            'ipv6': {
                'method': 'auto'
            }
        }
        try:
            NetworkManager.Settings.AddConnection(new_connection)
        except dbus.exceptions.DBusException as e:
            msg = _("Invalid password") if "802-11-wireless-security.psk" in e else f"{e}"
            self.callback("popup", msg)
            logging.info(f"Error adding network {e}")
            return False
        self._update_known_connections()
        return True

    def connect(self, ssid):
        if ssid in self.known_networks:
            conn = self.known_networks[ssid]
            with contextlib.suppress(NetworkManager.ObjectVanished):
                msg = f"Connecting to: {ssid}"
                logging.info(msg)
                self.callback("connecting_status", msg)
                NetworkManager.NetworkManager.ActivateConnection(conn, self.wireless_device, "/")

    def disconnect_network(self, ssid):
        self.last_connected_ssid = ssid
        self.wireless_device.SpecificDevice().Disconnect()
        
    def delete_network(self, ssid):
        con = self.known_networks[ssid]
        con.Delete()
        self._update_known_connections()

    def get_connected_ssid(self):
        if self.wireless_device.SpecificDevice().ActiveAccessPoint:
            return self.wireless_device.SpecificDevice().ActiveAccessPoint.Ssid
        return None

    def _get_connected_ap(self):
        return self.wireless_device.SpecificDevice().ActiveAccessPoint

    def _visible_networks_by_ssid(self):
        aps = self.wireless_device.GetAccessPoints()
        ret = {}
        for ap in aps:
            with contextlib.suppress(NetworkManager.ObjectVanished):
                ret[ap.Ssid] = ap
        return ret

    def get_network_info(self, ssid):
        netinfo = {}
        if ssid in self.visible_networks:
            con = self.visible_networks[ssid]
            with contextlib.suppress(NetworkManager.ObjectVanished):
                settings = con.GetSettings()
                if settings and '802-11-wireless' in settings:
                    netinfo.update({
                        "ssid": settings['802-11-wireless']['ssid'],
                        "connected": self.get_connected_ssid() == ssid
                    })
        path = self.path_by_ssid[ssid]
        aps = self.visible_networks
        if path in aps:
            ap = aps[path]
            with contextlib.suppress(NetworkManager.ObjectVanished):
                netinfo.update({
                    "mac": ap.HwAddress,
                    "channel": WifiChannels.lookup(str(ap.Frequency))[1],
                    "configured": ssid in self.visible_networks,
                    "frequency": str(ap.Frequency),
                    "flags": ap.Flags,
                    "ssid": ssid,
                    "is_hotspot": ap.Mode == NetworkManager.NM_802_11_MODE_AP,
                    "connected": self._get_connected_ap() == ap,
                    "encryption": self._get_encryption(ap.RsnFlags),
                    "signal_level_dBm": int(ap.Strength),
                })
        return netinfo

    @staticmethod
    def _get_encryption(flags):
        encryption = ""
        if (flags & NetworkManager.NM_802_11_AP_SEC_PAIR_WEP40 or
                flags & NetworkManager.NM_802_11_AP_SEC_PAIR_WEP104 or
                flags & NetworkManager.NM_802_11_AP_SEC_GROUP_WEP40 or
                flags & NetworkManager.NM_802_11_AP_SEC_GROUP_WEP104):
            encryption += "WEP "
        if (flags & NetworkManager.NM_802_11_AP_SEC_PAIR_TKIP or
                flags & NetworkManager.NM_802_11_AP_SEC_GROUP_TKIP):
            encryption += "TKIP "
        if (flags & NetworkManager.NM_802_11_AP_SEC_PAIR_CCMP or
                flags & NetworkManager.NM_802_11_AP_SEC_GROUP_CCMP):
            encryption += "AES "
        if flags & NetworkManager.NM_802_11_AP_SEC_KEY_MGMT_PSK:
            encryption += "WPA-PSK "
        if flags & NetworkManager.NM_802_11_AP_SEC_KEY_MGMT_802_1X:
            encryption += "802.1x "
        return encryption.strip()

    def get_networks(self):
        return list(set(list(self.known_networks.keys()) + list(self.ssid_by_path.values())))

    def get_supplicant_networks(self):
        return {ssid: {"ssid": ssid} for ssid in self.known_networks.keys()}

    def rescan(self):
        if not self.rescan_thread.is_alive():
            self.rescan_thread = self.thread_rescan_popen_callback(self._on_rescan)
        return True
    
    def _on_rescan(self):
        self.callback("rescan_finish", "")
        
    def thread_rescan_popen_callback(self, callback) -> Thread:
        def run_in_thread(callback):
            proc = Popen(["nmcli","device", "wifi", "list", "--rescan", "yes"])
            proc.wait()
            callback()
            return
        thread = Thread(target=run_in_thread, args=(callback,))
        thread.start()
        return thread

