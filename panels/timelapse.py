import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.video_player import VideoPlayer, Stream
from PIL import Image

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.cur_timelapse_frames = []
        self.video = []
        self.settings = {}
        self.path = "/tmp"
        self.init = False
        self.flip_x = False
        self.flip_y = False
        self.rotation = 0
        self.video_player = None
        self.video_dialog = None
        self.frame_box = None
        self.frame_box_state = ''
        self.video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.cur_timelapse_image = Gtk.Image()
        self.adj = Gtk.Adjustment(0, 1, 0, 1, 5, 0)
        self.grid = Gtk.Grid(column_homogeneous=True)
        self.content.add(self.grid)
        self.video_player_initialized = False
        self.stream_video_player = None
        self.frame_buttons = {
            'delete_frames': self._gtk.Button("delete", _("Delete frames"), "color3", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'saveframes': self._gtk.Button(None, _("Save frames"), "color1", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'render': self._gtk.Button(None, _("Render"), "color4", self.bts, Gtk.PositionType.LEFT, 1, vexpand=False),
            'settings': self._gtk.Button("settings", _("Render settings"), "color2", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False)
        }

    def activate(self):
        self._screen._ws.klippy.get_dir_info(self.load_timelapse, 'timelapse')
        # Удаляем старые элементы перед добавлением новых
        for child in self.grid.get_children():
            self.grid.remove(child)
            
        self.grid.attach(self.VideoScroll(), 0, 0, 1, 3)
        # Пересоздаем кнопки при каждой активации
        self.grid.attach(self.FrameButtonsGrid(), 1, 1, 2, 1)
        self.grid.show_all()

    def deactivate(self):
        self.init = False
        self.destroy_video_player()
        self.destroy_stream_video_player()
        self.close_video_dialog()
        # Удаляем все дочерние элементы grid
        for child in self.grid.get_children():
            self.grid.remove(child)
        self.frame_box_state = ''
        self.cur_timelapse_image = Gtk.Image()
        # Очищаем словарь кнопок при деактивации
        self.frame_buttons = {}

    def destroy_video_player(self):
        """Безопасное уничтожение основного видеоплеера"""
        if self.video_player:
            try:
                self.video_player.on_destroy()
            except Exception as e:
                logging.error(f"Error destroying video player: {e}")
            finally:
                self.video_player = None
                self.video_player_initialized = False

    def destroy_stream_video_player(self):
        """Безопасное уничтожение видеоплеера потока"""
        if self.stream_video_player:
            try:
                self.stream_video_player.on_destroy()
            except Exception as e:
                logging.error(f"Error destroying stream video player: {e}")
            finally:
                self.stream_video_player = None

    def close_video_dialog(self, *args):
        """Безопасное закрытие видео диалога"""
        if self.video_player:
            try:
                self.video_player.on_destroy()
            except Exception as e:
                logging.error(f"Error destroying video player in dialog: {e}")
            self.video_player = None
        if self.video_dialog:
            self._gtk.remove_dialog(self.video_dialog)
            self.video_dialog = None

    def load_timelapse(self, result, method, params):
        for child in self.video_box.get_children():
            self.video_box.remove(child)
        self.video_box.add(Gtk.Label(_("Render list:")))
        if not result.get("result") or not isinstance(result["result"], dict):
            logging.info(result)
            self.video_box.show_all()
            return
        self.path = result["result"]["core_path"]
        for video in result["result"]["files"]:
            if video['filename'].endswith('.mp4'):
                self.video.append(video['filename'])
                videoLabel = self._gtk.Button(label=video['filename'], style="hide_button", hexpand=False, vexpand=False)
                videoLabel.get_style_context().add_class("frame-item")
                videoLabel.connect("clicked", self.open_video_dialog)
                self.video_box.add(videoLabel)
        self.video_box.show_all()
        if not self.init:
            self._screen._ws.klippy.run_timelapse_method("get_settings")
            self._screen._ws.klippy.get_old_frames(self.on_old_frames)

    def on_old_frames(self, *args):
        self.init = True

    def VideoScroll(self):
        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.video_box)
        return scroll

    def open_video_dialog(self, widget):
        # Закрываем предыдущий диалог если есть
        self.close_video_dialog()
        box_video = Gtk.Box(hexpand=True, halign=Gtk.Align.CENTER)
        try:
            self.video_player = VideoPlayer(self._screen, f"{self.path}/{widget.get_label()}")
            box_video.add(self.video_player)
            self.video_player_initialized = True
        except Exception as e:
            logging.error(f"Failed to create video player: {e}")
            self.video_player = None
            self.video_player_initialized = False
            error_label = Gtk.Label(label=_("Failed to initialize video player"))
            box_video.add(error_label)
        button_box = Gtk.Box(hexpand=True, halign=Gtk.Align.END)
        button_box.set_margin_top(5)
        btn_delete = self._gtk.Button(None, _("Delete"), "color1", hexpand=False)
        btn_delete.set_size_request(self._screen.width / 3 - 30, round(self._screen.height / 5))
        btn_cancel = self._gtk.Button(None, _("Close"), "color2", hexpand=False)
        btn_cancel.set_size_request(self._screen.width / 3 - 30, round(self._screen.height / 5))
        button_box.add(btn_delete)
        button_box.add(btn_cancel)
        dialog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog_box.add(box_video)
        dialog_box.add(button_box)
        self.video_dialog = self._gtk.Dialog([], dialog_box, _("Video"), self.close_video_dialog)
        btn_cancel.connect("clicked", self.close_video_dialog)
        btn_delete.connect("clicked", self.confirm_delete_video, f"timelapse/{widget.get_label()}")

    def confirm_delete_video(self, widget, videopath):
        params = {"path": f"{videopath}"}
        self._screen._confirm_send_action(
            None,
            _("Delete File?") + "\n\n" + videopath,
            "server.files.delete_file",
            params,
            self.on_confirm
        )

    def on_confirm(self, result, method, params):
        self.close_video_dialog()
        self._screen._ws.klippy.get_dir_info(self.load_timelapse, 'timelapse')

    def update_frame_box(self, newframe_data):
        if newframe_data['status'] == 'success':
            if self.frame_box_state == 'stream' or self.frame_box_state == '':
                if self.frame_box is not None and self.frame_box in self.grid:
                    self.grid.remove(self.frame_box)
                    self.destroy_stream_video_player()  # Уничтожаем старый видеоплеер потока
                self.frame_box = self.FrameBox()
                self.grid.attach(self.frame_box, 1, 0, 2, 1)
                self.frame_box_state = 'frames'
            if (newframe_data['framefile'] not in self.cur_timelapse_frames and 
                (newframe_data['framefile'].endswith('.jpg') or newframe_data['framefile'].endswith('.png'))):
                if not len(self.cur_timelapse_frames):
                    self.set_sensitive_frame_buttons(True)
                self.cur_timelapse_frames.append(newframe_data['framefile'])
                self.adj.set_upper(len(self.cur_timelapse_frames))
                if len(self.cur_timelapse_frames) > 0:
                    self.adj.set_value(len(self.cur_timelapse_frames))
                    self.set_timelapse_image(value=len(self.cur_timelapse_frames) - 1)
        else:
            if self.frame_box_state == 'frames' or self.frame_box_state == '':
                if self.frame_box is not None and self.frame_box in self.grid:
                    self.grid.remove(self.frame_box)
                self.frame_box = self.StreamBox()
                self.grid.attach(self.frame_box, 1, 0, 2, 1)
                self.frame_box_state = 'stream'
        self.grid.show_all()

    def StreamBox(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        cameras = self._screen.apiclient.send_request("server/webcams/list")
        if cameras is not False:
            self._printer.configure_cameras(cameras['result']['webcams'])
        if len(self._printer.cameras) == 1:
            cam = next(iter(self._printer.cameras))
            if cam['enabled']:
                url = cam['stream_url']
                if url.startswith('/'):
                    logging.info("camera URL is relative")
                    endpoint = self._screen.apiclient.endpoint.split(':')
                    url = f"{endpoint[0]}:{endpoint[1]}{url}"
                if '/webrtc' in url:
                    self._screen.show_popup_message(_('WebRTC is not supported by the backend trying Stream'))
                    url = url.replace('/webrtc', '/stream')
                try:
                    # Создаем видеоплеер с меньшим размером для предпросмотра
                    self.stream_video_player = VideoPlayer(self._screen, url, Stream(cam), (120, self._screen.height * 0.6))
                    box.add(self.stream_video_player)
                except Exception as e:
                    logging.error(f"Failed to create stream video player: {e}")
                    self.stream_video_player = None
                    error_label = Gtk.Label(label=_("Stream not available"))
                    box.add(error_label)
        return box

    def FrameBox(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        box.add(self.cur_timelapse_image)
        upper = max(len(self.cur_timelapse_frames), 1)
        self.adj = Gtk.Adjustment(
            min(upper, 1),
            1,
            upper,
            1,
            5,
            0
        )
        scale = Gtk.Scale(adjustment=self.adj, digits=0, hexpand=True, 
                        has_origin=True, vexpand=True, valign=Gtk.Align.END)
        scale.set_digits(0)
        scale.set_hexpand(True)
        scale.set_has_origin(True)
        scale.get_style_context().add_class("option_slider")
        scale.connect("button-release-event", self.set_timelapse_image)
        scale.connect("value-changed", self.on_scale_value_changed)
        box.add(scale)
        return box

    def on_scale_value_changed(self, scale):
        if self.frame_box_state == 'frames' and len(self.cur_timelapse_frames) > 0:
            value = int(scale.get_value()) - 1
            if 0 <= value < len(self.cur_timelapse_frames):
                self.set_timelapse_image(value=value)

    def set_timelapse_image(self, widget=None, event=None, value=None):
        if value is None:
            if widget:
                value = int(self.adj.get_value()) - 1
            else:
                return
        if (len(self.cur_timelapse_frames) > 0 and 
            0 <= value < len(self.cur_timelapse_frames)):
            try:
                pixbuf = self.make_buffer_with_flip(value)
                self.cur_timelapse_image.set_from_pixbuf(pixbuf)
            except Exception as e:
                logging.error(f"Error loading frame image: {e}")
                self.cur_timelapse_image.clear()
        else:
            self.cur_timelapse_image.clear()

    def set_cur_timelapse_image_as_last(self):
        if len(self.cur_timelapse_frames) > 0:
            self.cur_timelapse_image.set_from_pixbuf(self.make_buffer_with_flip(-1))

    def make_buffer_with_flip(self, frame_num=-1):
        try:
            pil_img = Image.open(f"{self.path}_tmp/{self.cur_timelapse_frames[frame_num]}")
            if self.flip_x:
                pil_img = pil_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if self.flip_y:
                pil_img = pil_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            pil_img = pil_img.rotate(self.rotation)
            pil_img = pil_img.resize((227, 171))
            glibbytes = GLib.Bytes.new(pil_img.tobytes())
            return GdkPixbuf.Pixbuf.new_from_data(
                glibbytes.get_data(), 
                GdkPixbuf.Colorspace.RGB, 
                False, 
                8, 
                pil_img.width, 
                pil_img.height, 
                len(pil_img.getbands())*pil_img.width, 
                None, 
                None
            )
        except Exception as e:
            logging.error(f"Error creating pixbuf: {e}")
            return None

    def set_setting(self, setting, value):
        self._screen._ws.klippy.timelapse_set_settings({setting: value})

    def open_render_settings_dialog(self, widget):
        self._screen._ws.klippy.run_timelapse_method("get_settings", self.on_get_settings)

    def on_get_settings(self, result, method, params):
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
        box = Gtk.Box(hexpand=True, vexpand=False, valign=Gtk.Align.CENTER)
        switch = Gtk.Switch(active=self.settings[setting])
        switch.connect("notify::active", self.timelapse_switch, setting)
        box.pack_start(Gtk.Label(label=name), False, False, 0)
        box.pack_end(switch, False, False, 0)
        return box

    def ScaleGrid(self, setting, name):
        if f"{setting}_min" not in self.settings:
            self.settings[f"{setting}_min"] = 1
        if f"{setting}_max" not in self.settings:
            self.settings[f"{setting}_max"] = 1
        adj = Gtk.Adjustment(self.settings[setting], self.settings[f"{setting}_min"], self.settings[f"{setting}_max"], 1)
        scale = Gtk.Scale(adjustment=adj, digits=0, hexpand=True, has_origin=True)
        scale.set_digits(0)
        scale.set_hexpand(True)
        scale.set_has_origin(True)
        scale.get_style_context().add_class("option_slider")
        scale.connect("button-release-event", self.timelapse_scale, setting)
        grid = Gtk.Grid()
        grid.attach(Gtk.Label(label=name), 0, 0, 1, 1)
        grid.attach(scale, 0, 1, 1, 1)
        return grid

    def RenderSettingsBox(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
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

    def FrameButtonsGrid(self):
        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        # Пересоздаем кнопки каждый раз при вызове этого метода
        frame_buttons = {
            'delete_frames': self._gtk.Button("delete", _("Delete frames"), "color3", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'saveframes': self._gtk.Button(None, _("Save frames"), "color1", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False),
            'render': self._gtk.Button(None, _("Render"), "color4", self.bts, Gtk.PositionType.LEFT, 1, vexpand=False),
            'settings': self._gtk.Button("settings", _("Render settings"), "color2", self.bts, Gtk.PositionType.LEFT, 2, vexpand=False)
        }
        for i, btn_name in enumerate(frame_buttons):
            if btn_name != 'settings':
                frame_buttons[btn_name].set_sensitive(bool(len(self.cur_timelapse_frames)))
            frame_buttons[btn_name].set_size_request(1, self._screen.height * 0.15)
            if btn_name != 'settings':
                frame_buttons[btn_name].connect("clicked", self.run_method, btn_name)
            else:
                frame_buttons[btn_name].connect("clicked", self.open_render_settings_dialog)
            grid.attach(frame_buttons[btn_name], i % 2, i // 2, 1, 1)
        # Обновляем словарь кнопок
        self.frame_buttons = frame_buttons
        return grid

    def run_method(self, widget, method):
        self._screen.gtk.Button_busy(widget, True)
        self._screen._ws.klippy.run_timelapse_method(method, self.on_method, widget)

    def on_method(self, result, method:str, params, widget):
        self._screen.gtk.Button_busy(widget, False)
        if 'result' in result:
          if 'status' in result['result']:
            if method.split('.')[-1] == 'saveframes':
              if result['result']['status'] == 'finished':
                self._screen.show_popup_message(_("Frames saved. Viewing is available via the web interface"), level=1)
              else:
                self._screen.show_popup_message(_("Saving frames failed"))
            elif method.split('.')[-1] == 'render':
              if result['result']['status'] == 'success':
                self._screen.show_popup_message(_("Rendering Video successful: %s") % result['result']['filename'], level=1)
              else:
                self._screen.show_popup_message(_("Render failed"))

    def set_stream_box(self):
        if self.frame_box_state == 'frames' or self.frame_box_state == '':
            if self.frame_box and self.frame_box in self.grid:
                self.grid.remove(self.frame_box)
                self.destroy_stream_video_player()  # Уничтожаем видеоплеер потока
            self.frame_box = self.StreamBox()
            self.grid.attach(self.frame_box, 1, 0, 2, 1)
            self.frame_box_state = 'stream'
            self.grid.show_all()

    def process_update(self, action, data):
        if action != "notify_timelapse_event":
            return
        if data['action'] == 'settings':
            self.flip_x = data['flip_x']
            self.flip_y = data['flip_y']
            self.rotation = data['rotation']
            if len(self.cur_timelapse_frames) > 0:
                self.set_timelapse_image(value=int(self.adj.get_value()) - 1)
        elif data['action'] == 'newframe':
            self.update_frame_box(data)
        elif data['action'] == 'render':
            if 'filename' in data:
                if data['filename'] not in self.video and data['filename'].endswith('.mp4'):
                    videoLabel = self._gtk.Button(label=data['filename'], style="hide_button", hexpand=False, vexpand=False)
                    videoLabel.get_style_context().add_class("frame-item")
                    videoLabel.connect("clicked", self.open_video_dialog)
                    self.video_box.add(videoLabel)
                    self.video_box.show_all()
        elif data['action'] == 'delete':
            self.cur_timelapse_frames = []
            self.set_sensitive_frame_buttons(False)
            self.cur_timelapse_image.clear()
            self.adj.set_value(0)
            self.adj.set_upper(0)
            self.set_stream_box()

    def set_sensitive_frame_buttons(self, sensitive):
        for btn in self.frame_buttons:
          if btn != 'settings':
            self.frame_buttons[btn].set_sensitive(sensitive)