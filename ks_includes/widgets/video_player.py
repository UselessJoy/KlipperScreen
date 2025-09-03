from contextlib import suppress
import logging
import mpv
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
# player = mpv.MPV(
#                   config=True,
#                   # scripts='modern.lua',
#                   script_opts='osc-visibility=always, scalewindowed=2.0, scalefullscreen=2.0, osd-bar-h=25',
#                   input_default_bindings=True,
#                   keep_open = True,
#                   idle = True,
#                   force_window = True,
#                   input_vo_keyboard=True,
#                   osc=False)
                  # log_handler=self.log)
class Logger():
   def log(self, loglevel, component, message: str):
      logging.info(f'[{loglevel}] {component}: {message}')

class Video(mpv.MPV, Logger):
   def __init__(self):
      mpv.MPV.__init__(
          self,
          config=True,
          script_opts='osc-visibility=always, scalewindowed=2.0, scalefullscreen=2.0, osd-bar-h=25',
          input_default_bindings=True,
          keep_open = True,
          idle = True,
          force_window = True,
          input_vo_keyboard=True,
          osc=False,
          log_handler=self.log
      )
      self._set_property('pause', True)

class Stream(mpv.MPV, Logger):
   def __init__(self, camera_settings):
      mpv.MPV.__init__(self, log_handler=self.log, vo='gpu,wlshm,xv,x11')
      vf_list = []
      if camera_settings["flip_horizontal"]:
          vf_list.append("hflip")
      if camera_settings["flip_vertical"]:
          vf_list.append("vflip")
      if camera_settings["rotation"] != 0:
          vf_list.append(f"rotate:{camera_settings['rotation'] * 3.14159 / 180}")
      self.vf = ','.join(vf_list)
      with suppress(Exception):
          self.profile = 'sw-fast'
      # LOW LATENCY PLAYBACK
      with suppress(Exception):
          self.profile = 'low-latency'
      self.untimed = True
      self.audio = 'no'

class VideoPlayer(Gtk.EventBox):
    def __init__(self, screen, media_path, player = None, size = (560, 380)):#, set_setting = True, pause_on_draw = True):
        super().__init__(vexpand=True, valign=Gtk.Align.CENTER, hexpand=True)
        try:
          # dict_data = json.loads(subprocess.check_output("ffprobe -v error -select_streams v -show_entries stream=width,height -of json %s" % (media_path), universal_newlines=True, shell=True))
          # logging.info(dict_data)
          self.set_size_request(size[0], size[1]) #400 % 300
          # self.set_size_request(dict_data['streams'][0]['width'], dict_data['streams'][0]['height'])
        except Exception as e:
          logging.error(e)
          return
        self.media_path = media_path
        self.screen = screen
        self.canvas = Gtk.DrawingArea()
        self.canvas.connect('realize', self.on_canvas_realize)
        self.canvas.connect('draw', self.on_canvas_draw)#, pause_on_draw)
        self.canvas.connect('destroy', self.on_destroy)
        self.add(self.canvas)
        if not player:
          player = Video()
        self.player = player
        self.show_all()

    def on_destroy(self, *args):
        self.player.terminate()

    # Ошибка в этом
    def on_canvas_realize(self, widget):
      try:
        self.player.wid = widget.get_property('window').get_xid()
      except:
         self.player.terminate()

    def on_canvas_draw(self, widget, cr):#, pause_on_draw):
      cr.set_source_rgb(0.0, 0.0, 0.0)
      cr.paint()
      self.player.play(self.media_path)
      # if pause_on_draw:
      #   self.player._set_property('pause', True)
    
    def play(self, media_path):
       self.media_path = media_path
       self.player.play(self.media_path)