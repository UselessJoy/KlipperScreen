import logging
import gi
import mpv
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.video_player import VideoPlayer
from ks_includes.widgets.typed_entry import TypedEntry

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.cur_timelapse_frames = self.video = []
        self.settings = {}
        self.video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.last_timelapse_image = Gtk.Image()
        self.adj = Gtk.Adjustment(0, 1, 0, 1, 5, 0)
        self._screen._ws.klippy.get_old_frames()
        self._screen._ws.klippy.get_dir_info(self.load_timelapse, 'timelapse')
        grid = Gtk.Grid(column_homogeneous=True)
        box = Gtk.Box(hexpand=True)
        self.render_settings_button = self._gtk.Button("settings", _("Render settings"), "color2", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False)
        self.render_settings_button.set_size_request((self._screen.width - 30) / 4, self._screen.height / 5)
        self.render_settings_button.connect("clicked", self.open_render_settings_dialog)
        self.render_settings_button.set_halign(Gtk.Align.CENTER)
        box.add(self.render_settings_button)
        grid.attach(self.VideoScroll(), 0, 0, 1, 2)
        grid.attach(self.TimelapseImgBox(), 1, 0, 2, 1)
        grid.attach(self.CurrentRenderButtonGrid(), 1, 1, 2, 1)
        grid.attach(box, 1, 2, 2, 1)
        self.content.add(grid)

    def load_timelapse(self, result, method, params):
      if not result.get("result") or not isinstance(result["result"], dict):
          logging.info(result)
          return
      for video in result["result"]["files"]:
        if video['filename'].endswith('.mp4'):
          self.video.append(video['filename'])
          videoLabel = self._gtk.Button(label = video['filename'], style="hide_button", hexpand=False, vexpand=False)
          videoLabel.get_style_context().add_class("frame-item")
          videoLabel.connect("clicked", self.open_video_dialog)
          self.video_box.add(videoLabel)
          self.video_box.show_all()
    
    def VideoScroll(self):
      scroll = self._gtk.ScrolledWindow()
      scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
      scroll.add(self.video_box)
      return scroll

    def open_video_dialog(self, widget):
      buttons = [
        {"name": _("Close"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
      ]
      box_content = Gtk.Box(hexpand=True, halign=Gtk.Align.CENTER)
      box_content.add(VideoPlayer(self._screen, "/home/orangepi/printer_data/mmcblk0p1/timelapse/"+widget.get_label()))
      self._gtk.Dialog(buttons, box_content, _("Video"), self.close_video_dialog)
        
    def close_video_dialog(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
    
    def TimelapseImgBox(self):
      box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
      box.add(self.last_timelapse_image)
      scale = Gtk.Scale(adjustment=self.adj, digits=0, hexpand=True, has_origin=True, vexpand=True, valign=Gtk.Align.END)
      scale.set_digits(0)
      scale.set_hexpand(True)
      scale.set_has_origin(True)
      scale.get_style_context().add_class("option_slider")
      scale.connect("button-release-event", self.set_timelapse_image_from_scale)
      box.add(scale)
      return box

    def set_timelapse_image_from_scale(self, widget=None, event=None):
      adj_val: float = self.adj.get_value()
      if len(self.cur_timelapse_frames):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/home/orangepi/printer_data/mmcblk0p1/timelapse_tmp/"+self.cur_timelapse_frames[int(adj_val) - 1], int(200), int(200))
        self.last_timelapse_image.set_from_pixbuf(pixbuf)
    
    def set_last_timelapse_image(self):
      pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/home/orangepi/printer_data/mmcblk0p1/timelapse_tmp/"+self.cur_timelapse_frames[-1], int(200), int(200))
      self.last_timelapse_image.set_from_pixbuf(pixbuf)
    
    
    def set_setting(self, setting, value):
      self._screen._ws.klippy.timelapse_set_settings({setting: value})

    def open_render_settings_dialog(self, widget):
      self._screen._ws.klippy.run_timelapse_method("get_settings", self.on_get_settings)
      
    def on_get_settings(self, result, method, params):
      logging.info("getting info")
      logging.info(result)
      self.settings = result['result']
      buttons = [
        {"name": _("Close"), "response": Gtk.ResponseType.CANCEL, "style": "color2"},
        {"name": _("Save"), "response": Gtk.ResponseType.OK, "style": "color1"}
      ]
      scroll = self._gtk.ScrolledWindow()
      scroll.set_min_content_width(self._gtk.content_width * 0.75)
      scroll.set_min_content_height(self._gtk.content_height * 0.75)
      scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
      scroll.add(self.RenderSettingsBox())
      box = Gtk.Box()
      box.add(scroll)
      self._gtk.Dialog(buttons, box, _("Render settings"), self.close_render_settings_dialog)

    def SwitchBox(self, setting, name):
      box = Gtk.Box(hexpand = True, vexpand = False, valign = Gtk.Align.CENTER)
      switch = Gtk.Switch(active=self.settings[setting])
      switch.connect("notify::active", self.timelapse_switch, setting)
      box.pack_start(Gtk.Label(label=name), False, False, 0)
      box.pack_end(switch, False, False, 0)
      return box

    def ScaleGrid(self, setting, name):
      if not f"{setting}_min" in self.settings:
        self.settings[f"{setting}_min"] = 1
      if not f"{setting}_max" in self.settings:
        self.settings[f"{setting}_max"] = 1
      adj = Gtk.Adjustment(self.settings[setting], self.settings[f"{setting}_min"], self.settings[f"{setting}_max"], 1)
      scale = Gtk.Scale(adjustment=adj, digits=0, hexpand=True, has_origin=True)
      scale.set_digits(0)#get data
      scale.set_hexpand(True)
      scale.set_has_origin(True)
      scale.get_style_context().add_class("option_slider")
      scale.connect("button-release-event", self.timelapse_scale, setting)
      grid = Gtk.Grid()
      grid.attach(Gtk.Label(label=name), 0, 0, 1, 1)
      grid.attach(scale, 0, 1, 1, 1)
      return grid

    def RenderSettingsBox(self):
      box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, spacing = 5)
      box.add(self.SwitchBox("enabled", _("Turn on")))
      box.add(self.SwitchBox("autorender", _("Autorender")))
      box.add(self.SwitchBox("variable_fps", _("Variable FPS")))
      box.add(self.SwitchBox("saveframes", _("Save frames")))
      box.add(self.SwitchBox("previewimage", _("Preview image")))
      box.add(self.ScaleGrid("output_framerate", _("Output framerate")))
      box.add(self.ScaleGrid("duplicatelastframe", _("Duplicate last frame")))
      box.add(self.ScaleGrid("constant_rate_factor", _("Constant Rate Factor")))
      return box

    def timelapse_scale(self, widget, event, setting):
      self.settings[setting] = widget.get_value()

    def timelapse_switch(self, switch, gdata, setting):
      self.settings[setting] = switch.get_active()

    def close_render_settings_dialog(self, dialog, response_id):
      if response_id == Gtk.ResponseType.OK:
        self._screen._ws.klippy.timelapse_set_settings(self.settings)
        self.settings = {}
      self._gtk.remove_dialog(dialog)

    def CurrentRenderButtonGrid(self):
      current_buttons = {
            'delete_frames': self._gtk.Button("delete", _("Delete frames"), "color3", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'saveframes': self._gtk.Button(None, _("Save frames"), "color1", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'render': self._gtk.Button("settings", _("Render"), "color2", self.bts, Gtk.PositionType.LEFT, 1, vexpand=False),
        }
      for btn_name in current_buttons:
        current_buttons[btn_name].set_size_request(1, self._screen.height / 5)
        current_buttons[btn_name].connect("clicked", self.run_method, btn_name)
      return self.ButtonGrid(current_buttons)

    def run_method(self, widget, method):
      self._screen._ws.klippy.run_timelapse_method(method)
      

    def ButtonGrid(self, buttons):
      grid = Gtk.Grid(row_homogeneous = True, column_homogeneous = True)
      for i, btn in enumerate(buttons):
        grid.attach(buttons[btn], i, 0, 1, 1)
      return grid

    def process_update(self, action, data):
        if action != "notify_timelapse_event":
            return
        logging.info(f"from timelapse event data: {data}")

        if data['action'] == 'newframe':
          if data['framefile'] not in self.cur_timelapse_frames:
            self.cur_timelapse_frames.append(data['framefile'])
            self.set_last_timelapse_image()
            self.adj.set_upper(len(self.cur_timelapse_frames))
        elif data['action'] == 'render':
          if 'filename' in data:
            if data['filename'] not in self.video and data['filename'].endswith('.mp4'):
              self.video
              self.video_box.add(Gtk.Label(label = data['filename']))
              self.video_box.show_all()