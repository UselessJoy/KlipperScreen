import logging
from ks_includes.widgets.keyboard import Keyboard
from ks_includes.widgets.settings.combo_box_setting import ComboBoxSetting

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.video_player import VideoPlayer, Stream
from ks_includes.widgets.combo_box import KSComboBox
from ks_includes.widgets.settings.switch_setting import SwitchSetting
from ks_includes.widgets.settings.entry_setting import EntrySetting


class Panel(ScreenPanel):
    streams = {
      _("mjpegstreamer-adaptive"): "mjpegstreamer-adaptive",
      _("mjpegstreamer"): "mjpegstreamer",
      _("hlsstream"): "hlsstream",
      _("webrtc-camerastreamer"): "webrtc-camerastreamer",
      _("ipstream"): "ipstream",
      _("iframe"): "iframe",
      _("webrtc-go2rtc"): "webrtc-go2rtc"
    }
    
    def __init__(self, screen, title):
        title = title or _("Camera")
        super().__init__(screen, title)
        self.scroll = None
        self.keyboard = None
        self.camera_box = None
        self.camera_dialog = None
        self.main_box = None
        self.show_settings = False
        self.camera_settings = {}
        self.video_player = None
        self.active_camera = None
        self.cameras_combo_box = None
        self.was_child_scrolled = False

    def deactivate(self):
        if self.video_player:
            try:
                self.video_player.on_destroy()
            except Exception as e:
                logging.error(f"Error destroying video player: {e}")
            self.video_player = None
        
        for child in self.content.get_children():
            self.content.remove(child)
        
        self.scroll = None
        self.keyboard = None
        self.camera_box = None
        self.camera_dialog = None
        self.main_box = None
        self.camera_settings = {}

    def activate(self):
        self.init_cameras()
        if not self._printer.cameras:
            self._screen.show_popup_message(_("No cameras configured"))
            return
            
        self.active_camera = next(iter(self._printer.cameras))
        url = self.configure_url()
        
        if url:
            try:
                self.video_player = VideoPlayer(self._screen, url, Stream(self.active_camera), 
                                              (self._screen.width * 0.65, self._screen.height * 0.65))
            except Exception as e:
                logging.error(f"Failed to create video player: {e}")
                self.video_player = None
                self._screen.show_popup_message(_("Failed to initialize video player"))
        else:
            self.video_player = None
            
        self.cameras_combo_box = KSComboBox(self._screen, self.active_camera['name'])
        self.cameras_combo_box.set_size_request(1, self._screen.height * 0.2)
        self.cameras_combo_box.button.set_vexpand(False)
        self.cameras_combo_box.button.set_size_request(1,1)
        self.cameras_combo_box.button.get_style_context().add_class('color1')
        
        for cam in self._printer.cameras:
            self.cameras_combo_box.append(cam['name'])
        self.cameras_combo_box.connect("selected", self.on_camera_change)
        
        settings_button = self._gtk.Button("settings", _("Settings"), "color3")
        settings_button.set_vexpand(False)
        settings_button.set_size_request(1, 1)
        settings_button.connect("clicked", self.show_camera_settings)
        
        bottom_bar = Gtk.Box(spacing=5, hexpand=True, vexpand=False)
        bottom_bar.add(self.cameras_combo_box)
        bottom_bar.add(settings_button)
        
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        if self.video_player:
            self.main_box.add(self.video_player)
        else:
            error_label = Gtk.Label(label=_("Camera not available"))
            self.main_box.add(error_label)
        self.main_box.add(bottom_bar)
        
        self.content.add(self.main_box)
        self.content.show_all()

    def reinit_video_player(self):
        if self.video_player:
            try:
                self.main_box.remove(self.video_player)
                self.video_player.on_destroy()
            except Exception as e:
                logging.error(f"Error removing old video player: {e}")
        
        url = self.configure_url()
        if url:
            try:
                self.video_player = VideoPlayer(self._screen, url, Stream(self.active_camera), 
                                              (self._screen.width * 0.65, self._screen.height * 0.65))
                self.main_box.add(self.video_player)
                self.main_box.show_all()
            except Exception as e:
                logging.error(f"Failed to reinitialize video player: {e}")
                self.video_player = None
                self._screen.show_popup_message(_("Failed to reinitialize video"))

    def init_cameras(self):
        cameras = self._screen.apiclient.send_request("server/webcams/list")
        if cameras is not False:
            self._printer.configure_cameras(cameras['result']['webcams'])
    
    def configure_url(self):
        url = ""
        if self.active_camera and self.active_camera['enabled']:
            url = self.active_camera['stream_url']
            if url.startswith('/'):
                logging.info("camera URL is relative")
                endpoint = self._screen.apiclient.endpoint.split(':')
                url = f"{endpoint[0]}:{endpoint[1]}{url}"
            if '/webrtc' in url:
                self._screen.show_popup_message(_('WebRTC is not supported by the backend trying Stream'))
                url = url.replace('/webrtc', '/stream')
        return url

    def show_camera_settings(self, widget=None):
        if self.video_player:
            try:
                self.video_player.on_destroy()
                self.video_player = None
            except Exception as e:
                logging.error(f"Error destroying video player for settings: {e}")
        
        for child in self.content.get_children():
            self.content.remove(child)
        
        self.camera_settings = self.active_camera.copy()

        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        settings_box.add(SwitchSetting(_("Turn on"), self.camera_settings['enabled'], self.on_setting, "enabled"))
        settings_box.add(EntrySetting(_("Name"), self.camera_settings['name'], update_callback=self.on_setting, setting="name", screen=self._screen))
        settings_box.add(SwitchSetting(_("Flip horizontally"), self.camera_settings['flip_horizontal'], self.on_setting, "flip_horizontal"))
        settings_box.add(SwitchSetting(_("Flip vertically"), self.camera_settings['flip_vertical'], self.on_setting, "flip_vertical"))
        settings_box.add(ComboBoxSetting(_("Rotate by"), self._screen, ["0", "90", "180", "270"], str(self.camera_settings['rotation']), self.on_setting, "rotation"))
        
        locale_keys = [_(key) for key in self.streams.keys()]
        settings_box.add(ComboBoxSetting(_("Stream type"), self._screen, locale_keys, _(str(self.camera_settings['service'])), self.on_setting, "service"))
        settings_box.add(EntrySetting(_("Stream URL"), self.camera_settings['stream_url'], update_callback=self.on_setting, setting="stream_url", screen=self._screen))
        settings_box.add(EntrySetting(_("Snapshot URL"), self.camera_settings['snapshot_url'], update_callback=self.on_setting, setting="snapshot_url", screen=self._screen))

        for child in settings_box:
            if isinstance(child, EntrySetting):
                child.entry.connect("focus-in-event", self.on_focus_in_entry)
                child.entry.connect("focus-out-event", self.on_focus_out_entry)
                child.entry.connect("button_release_event", self.click_to_entry)

        self.scroll = self._gtk.ScrolledWindow()
        adj = Gtk.Adjustment()
        adj.connect("value-changed", self.on_scrolling)
        self.scroll.set_vadjustment(adj)
        self.scroll.set_vexpand(True)
        self.scroll.set_hexpand(True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        scrolled_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrolled_box.add(settings_box)

        apply_button = self._gtk.Button(None, _("Apply"), "color3", self.bts)
        apply_button.connect("button_release_event", self.apply)
        apply_button.set_vexpand(True)
        apply_button.set_valign(Gtk.Align.END)
        apply_button.set_hexpand(True)
        apply_button.set_halign(Gtk.Align.END)
        apply_button.set_can_focus(False)
        apply_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        scrolled_box.add(apply_button)

        viewport = Gtk.Viewport()
        viewport.add(scrolled_box)
        self.scroll.add(viewport)

        eventBox = Gtk.EventBox()
        eventBox.set_can_focus(True)
        eventBox.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        eventBox.connect("button_release_event", self.click_to_eventbox)
        eventBox.add(self.scroll)

        self.content.add(eventBox)
        self.content.show_all()
        self.show_settings = True

    def back(self):
        if self.show_settings:
            self.show_settings = False
            self.deactivate()
            self.activate()
            return True
        return False
    
    def on_focus_out_entry(self, *args):
        if self.keyboard:
            self.content.remove(self.keyboard)
        self.keyboard = None

    def on_focus_in_entry(self, entry, event):
        self.keyboard = Keyboard(self._screen, entry=entry, accept_cb=self.on_accept_keyboard_dutton)
        self.keyboard.change_entry(entry=entry)
        self.keyboard.set_vexpand(False)
        self.keyboard.set_hexpand(True)
        self.keyboard.set_size_with_resolution(self._screen.width, self._screen.height)      
        self.content.add(self.keyboard)
        self.content.show_all()

    def click_to_entry(self, *args):
        return True

    def on_accept_keyboard_dutton(self):
        self._screen.set_focus(None)

    def click_to_eventbox(self, eventBox, event):
        if not self.was_child_scrolled:
            eventBox.grab_focus()
        else:
            self.was_child_scrolled = False

    def on_scrolling(self, *args):
        self.was_child_scrolled = True

    def on_setting(self, widget, value, setting):
        if setting == "service":
            value = self.streams[value]
        self.camera_settings[setting] = value

    def apply(self, widget, event):
        self._screen._ws.klippy.update_webcam(self.camera_settings, self.on_update_webcam)

    def on_update_webcam(self, result, method, params):
        self.back()

    def on_camera_change(self, combo_box, camera):
        for cam in self._printer.cameras:
            if cam['name'] == camera:
                self.active_camera = cam
                break
        self.reinit_video_player()