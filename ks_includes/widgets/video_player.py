import logging
import gi
import mpv
# import subprocess
# import json
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
class VideoPlayer(Gtk.EventBox):
    def __init__(self, screen, media_path):
        super().__init__(vexpand=True, valign=Gtk.Align.CENTER, hexpand=True)
        try:
          # dict_data = json.loads(subprocess.check_output("ffprobe -v error -select_streams v -show_entries stream=width,height -of json %s" % (media_path), universal_newlines=True, shell=True))
          # logging.info(dict_data)
          self.set_size_request(560, 380) #400 % 300
          # self.set_size_request(dict_data['streams'][0]['width'], dict_data['streams'][0]['height'])
        except Exception as e:
          logging.error(e)
          return
        self.media_path = media_path
        self.screen = screen
        self.canvas = Gtk.DrawingArea()
        self.canvas.connect('realize', self.on_canvas_realize)
        self.canvas.connect('draw', self.on_canvas_draw)
        self.canvas.connect('destroy', self.on_destroy)
        self.add(self.canvas)
        self.player = mpv.MPV(
                  config=True,
                  # scripts='modern.lua',
                  script_opts='osc-visibility=always, scalewindowed=2.0, scalefullscreen=2.0, osd-bar-h=25',
                  input_default_bindings=True,
                  keep_open = True,
                  idle = True,
                  force_window = True,
                  input_vo_keyboard=True,
                  osc=False,
                  log_handler=self.log)
        self.show_all()

    def on_destroy(self, *args):
      self.player.terminate()

    def on_canvas_realize(self, widget):
      self.player.wid = widget.get_property('window').get_xid()

    def on_canvas_draw(self, widget, cr):
      cr.set_source_rgb(0.0, 0.0, 0.0)
      cr.paint()
      self.player.play(self.media_path)
      self.player._set_property('pause', True)

    def log(self, loglevel, component, message: str):
      logging.info(f'[{loglevel}] {component}: {message}')