import contextlib
import logging
import re
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, Pango
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyGtk import format_label

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.screw_dict = {}
        self.screws = []
        self.y_cnt = 0
        self.x_cnt = 0
        self.x_offset = 0
        self.y_offset = 0
        self.buttons = {}
        self.popover = {}
        self.is_using_magnet = False
        self.screws_adjust_data = {}
        self.probe_coord = []
        self.overlay = Gtk.Overlay()
        self.overlayBox = None
        self.scroll_clicked = False
        self.is_calibrating = False
        self.pressed = False
        try:
            self.is_using_magnet = self._screen.apiclient.send_request("printer/objects/query?probe")['result']['status']['probe']['is_using_magnet_probe']
        except Exception as e:
            raise f"Can't get probe info from moonraker: {e}"

        self.buttons[True] = self._gtk.Button("magnetOff",_("Return Magnet Probe"), "color1", self.bts)#, hexpand=False, vexpand=False)
        self.buttons[False] = self._gtk.Button("magnetOn", _("Get Magnet Probe"), "color3", self.bts)#, hexpand=False, vexpand=False)
        self.buttons[True].connect("clicked", self.return_magnet)
        self.buttons[False].connect("clicked", self.get_magnet)
        
        self.buttonGrid = Gtk.Grid()
        self.buttonGrid.attach(self.buttons[self.is_using_magnet], 0, 0, 1, 1)

        if "screws_tilt_adjust" in self._printer.get_config_section_list():
            try:
                self.screws_adjust_data = self._screen.apiclient.send_request("printer/objects/query?screws_tilt_adjust")['result']['status']['screws_tilt_adjust']
            except Exception as e:
                raise f"Can't get screws_tilt_adjust info from moonraker: {e}"
            self.buttons['screws_tilt_calibrate'] = self.CalibrateButton()
            self.buttons['stop_screws_tilt_calibrate'] = self._gtk.Button("cancel", _("Stop calibrating"), "color2", self.bts)#, hexpand=False, vexpand=False)
            self.buttons['stop_screws_tilt_calibrate'].connect("clicked", self.stop_screws_tilt_calibrate)
            self.buttons['stop_screws_tilt_calibrate'].connect("realize", self.on_realize)
            self.buttons['stop_screw_calibrate'] = self._gtk.Button("refresh", _("Next screw"), "color3", self.bts)#, hexpand=False, vexpand=False)
            self.buttons['stop_screw_calibrate'].connect("clicked", self.stop_screw_calibrate)
            self.buttonGrid.attach(self.buttons['screws_tilt_calibrate'], 0, 2, 1, 1)
            self.screws = self._get_screws("screws_tilt_adjust")
            logging.info(f"screws_tilt_adjust: {self.screws}")
            probe = self._printer.get_probe()
            if probe:
                if "x_offset" in probe:
                    self.x_offset = round(float(probe['x_offset']), 1)
                if "y_offset" in probe:
                    self.y_offset = round(float(probe['y_offset']), 1)
                logging.debug(f"offset X: {self.x_offset} Y: {self.y_offset}")
            # bed_screws uses NOZZLE positions
            # screws_tilt_adjust uses PROBE positions and to be offseted for the buttons to work equal to bed_screws
            new_screws = [
                [round(screw[0] + self.x_offset, 1), round(screw[1] + self.y_offset, 1), screw[2]]
                for screw in self.screws
            ]
            self.screws = new_screws
            logging.info(f"screws with offset: {self.screws}")
        elif "bed_screws" in self._printer.get_config_section_list():
            self.screws = self._get_screws("bed_screws")
            logging.info(f"bed_screws: {self.screws}")

        # get dimensions
        x_positions = {x[0] for x in self.screws}
        y_positions = {y[1] for y in self.screws}
        logging.info(f"X: {x_positions} Y: {y_positions}")
        self.x_cnt = len(x_positions)
        self.y_cnt = len(y_positions)

        min_x = min(x_positions)
        max_x = max(x_positions)
        min_y = min(y_positions)
        max_y = max(y_positions)

        fl_xy = [i for i in self.screws if min_x == i[0] and min_y == i[1]][0]
        bl_xy = [i for i in self.screws if min_x == i[0] and max_y == i[1]][0]
        br_xy = [i for i in self.screws if max_x == i[0] and max_y == i[1]][0]
        fr_xy = [i for i in self.screws if max_x == i[0] and min_y == i[1]][0]

        fl = [min_x, min_y, _("Front left screw"), fl_xy[2]]
        bl = [min_x, max_y, _("Back left screw"), bl_xy[2]]
        br = [max_x, max_y, _("Back right screw"), br_xy[2]]
        fr = [max_x, min_y, _("Front right screw"), fr_xy[2]]

        if self.x_cnt == 3:
            mid_x = [x for x in list(zip(*self.screws))[0] if x not in (min_x, max_x)][0]
            fm_xy = [i for i in self.screws if mid_x == i[0] and min_y == i[1]][0]
            bm_xy = [i for i in self.screws if mid_x == i[0] and max_y == i[1]][0]
            fm = [mid_x, min_y, _("Front middle screw"), fm_xy[2]]
            bm = [mid_x, max_y, _("Back middle screw"), bm_xy[2]]
        else:
            fm = bm = None
        if self.y_cnt == 3:
            mid_y = [y for y in list(zip(*self.screws))[1] if y not in (min_y, max_y)][0]
            lm_xy = [i for i in self.screws if min_x == i[0] and mid_y == i[1]][0]
            rm_xy = [i for i in self.screws if max_x == i[0] and mid_y == i[1]][0]
            lm = [min_x, mid_y, _("Left middle screw"), lm_xy[2]]
            rm = [max_x, mid_y, _("Right middle screw"), rm_xy[2]]
        else:
            lm = rm = None

        logging.debug(f"Using {len(self.screws)}-screw locations [x,y] [{self.x_cnt}x{self.y_cnt}]")

        self.buttons['border_bl'] = self._gtk.Button("bed-level-t-l", scale=2.5)
        self.buttons['border_br'] = self._gtk.Button("bed-level-t-r", scale=2.5)
        self.buttons['border_fl'] = self._gtk.Button("bed-level-b-l", scale=2.5)
        self.buttons['border_fr'] = self._gtk.Button("bed-level-b-r", scale=2.5)
        self.buttons['border_lm'] = self._gtk.Button("bed-level-l-m", scale=2.5)
        self.buttons['border_rm'] = self._gtk.Button("bed-level-r-m", scale=2.5)
        self.buttons['border_fm'] = self._gtk.Button("bed-level-b-m", scale=2.5)
        self.buttons['border_bm'] = self._gtk.Button("bed-level-t-m", scale=2.5)
        try:
          rotation = self.ks_printer_cfg.getint("screw_rotation", 0)
        except:
          rotation = 0

        self.bedgrid = Gtk.Grid(column_homogeneous=True)
        self.bedbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=10)
        nscrews = len(self.screws)

        if nscrews in {4, 6, 8}:
            self.calibration_button_manager = self._gtk.Button("screws_adjust", _("Calibration Manager"), "color5") 
            self.calibration_button_manager.connect("clicked", self.show_calibration_overlay)
            self.bedgrid.attach(self.calibration_button_manager, 1, 1, 1, 4)
            self.bedgrid.attach(self.buttons['border_bl'], 0, 0, 1, 2)
            self.bedgrid.attach(self.buttons['border_fl'], 0, 4, 1, 2)
            self.bedgrid.attach(self.buttons['border_br'], 2, 0, 1, 2)
            self.bedgrid.attach(self.buttons['border_fr'], 2, 4, 1, 2)
            if self.x_cnt == 3:
                self.bedgrid.attach(self.buttons['border_bm'], 1, 0, 1, 1)
                self.bedgrid.attach(self.buttons['border_fm'], 1, 5, 1, 1)
            if self.y_cnt == 3:
                self.bedgrid.attach(self.buttons['border_lm'], 0, 1, 1, 1)
                self.bedgrid.attach(self.buttons['border_rm'], 2, 1, 1, 1)
        else:
            label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
            label.set_text(
                _("Bed screw configuration:") + f" {nscrews}\n\n"
                + _("Not supported for auto-detection, it needs to be configured in klipperscreen.conf")
            )
            self.bedgrid.attach(label, 1, 0, 3, 2)
            self.content.add(self.bedgrid)
            return
        self.overlay.add(self.bedgrid)
        if rotation == 90:
            # fl lm bl
            # fm    bm
            # fr rm br
            self.screw_dict = {
                'border_bl': fl,
                'border_br': bl,
                'border_fr': br,
                'border_fl': fr,
            }
            if fm:
                self.screw_dict['border_lm'] = fm
            if bm:
                self.screw_dict['border_rm'] = bm
            if lm:
                self.screw_dict['border_bm'] = lm
            if rm:
                self.screw_dict['border_fm'] = rm
        elif rotation == 180:
            # fr fm fl
            # rm    lm
            # br bm bl
            self.screw_dict = {
                'border_br': fl,
                'border_fr': bl,
                'border_fl': br,
                'border_bl': fr,
            }
            if fm:
                self.screw_dict['border_bm'] = fm
            if bm:
                self.screw_dict['border_fm'] = bm
            if lm:
                self.screw_dict['border_rm'] = lm
            if rm:
                self.screw_dict['border_lm'] = rm   
        elif rotation == 270:
            # br rm fr
            # bm    fm
            # bl lm fl
            self.screw_dict = {
                'border_fr': fl,
                'border_fl': bl,
                'border_bl': br,
                'border_br': fr,
            }
            if fm:
                self.screw_dict['border_rm'] = fm
            if bm:
                self.screw_dict['border_lm'] = bm
            if lm:
                self.screw_dict['border_fm'] = lm
            if rm:
                self.screw_dict['border_bm'] = rm  
        else:
            # bl bm br
            # lm    rm
            # fl fm fr
            self.screw_dict = {
                'border_fl': fl,
                'border_bl': bl,
                'border_br': br,
                'border_fr': fr,
            }
            if fm:
                self.screw_dict['border_fm'] = fm
            if bm:
                self.screw_dict['border_bm'] = bm
            if lm:
                self.screw_dict['border_lm'] = lm
            if rm:
                self.screw_dict['border_rm'] = rm

        for screw in self.screw_dict:
            self.buttons[screw].connect("clicked", self.open_popover, screw)
            self.popover[screw] = {}
            self.popover[screw]['popover'] = Gtk.Popover()
            pobox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.popover[screw]['go_to_position'] = self._gtk.Button(label=_("Go to position")) 
            self.popover[screw]['go_to_position'].connect("clicked", self.go_to_position, screw)
            pobox.pack_start(self.popover[screw]['go_to_position'], True, True, 5)

            self.popover[screw]['set_as_base'] = self._gtk.Button(label=_("Set as base screw")) 
            self.popover[screw]['set_as_base'].connect("clicked", self.set_base_screw, screw)
            pobox.pack_start(self.popover[screw]['set_as_base'], True, True, 5)

            self.popover[screw]['next_screw_calibrate'] = self._gtk.Button(label=_("Go to calibrate")) 
            self.popover[screw]['next_screw_calibrate'].connect("clicked", self.set_next_calibrating_screw, screw)
            pobox.pack_start(self.popover[screw]['next_screw_calibrate'] , True, True, 5)

            self.popover[screw]['popover'].set_relative_to(self.buttons[screw])
            self.popover[screw]['popover'].add(pobox)
            if screw in ['border_fl', 'border_lm', 'border_bl']:
                self.popover[screw]['popover'].set_position(Gtk.PositionType.RIGHT)
            elif screw in ['border_fr', 'border_rm', 'border_br']:
                self.popover[screw]['popover'].set_position(Gtk.PositionType.LEFT)
            elif screw == 'border_fm':
                self.popover[screw]['popover'].set_position(Gtk.PositionType.BOTTOM)
            elif screw == 'border_bm':
                self.popover[screw]['popover'].set_position(Gtk.PositionType.TOP)
        self.content.add(self.overlay)

    def on_realize(self, widget):
      if self.pressed:
        return
      self._gtk.Button_busy(widget, False)

    def on_info_button_clicked(self, widget, event, popover):
      popover.show_all()
      return Gdk.EVENT_STOP

    def InfoButton(self):
      label = Gtk.Label(label=_("Before adjusting, it is recommended to tighten all the screws until they stop"))
      format_label(label, lines=2, is_ellipsize=True)
      info_popover = Gtk.Popover()
      info_popover.get_style_context().add_class("message_popup")
      info_popover.set_halign(Gtk.Align.CENTER)
      info_popover.set_position(Gtk.PositionType.BOTTOM)
      info_popover.add(label)
      info_button = self._gtk.Button("info", style="round_button", scale=0.7)
      info_button.set_halign(Gtk.Align.END)
      info_button.set_valign(Gtk.Align.START)
      info_button.set_vexpand(False)
      info_button.connect("button-release-event", self.on_info_button_clicked, info_popover)
      info_popover.set_relative_to(info_button)
      return info_button

    def CalibrateLabel(self):
      calibrate_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
      img_size = self._gtk.img_scale * self.bts
      img = self._gtk.Image("screws_adjust", img_size, img_size)
      img.set_valign(Gtk.Align.END)
      label = Gtk.Label(label=_("Screws Adjust"), vexpand=True, valign=Gtk.Align.START)
      format_label(label, lines=2, is_ellipsize=True)
      calibrate_box.add(img)
      calibrate_box.add(label)
      return calibrate_box

    def CalibrateButton(self):
      calibrate_box = Gtk.EventBox()
      calibrate_box.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK)
      calibrate_box.connect("button-release-event", self.screws_tilt_calibrate)
      content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
      content_box.get_style_context().add_class("color4")
      content_box.add(self.InfoButton())
      content_box.set_center_widget(self.CalibrateLabel())
      calibrate_box.add(content_box)
      return calibrate_box

    def show_calibration_overlay(self, widget):
        self.overlayBox = Gtk.EventBox()
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        self.scroll.add(self.buttonGrid)
        self.scroll.set_vexpand(False)
        self.scroll.set_halign(Gtk.Align.CENTER)
        self.scroll.set_valign(Gtk.Align.CENTER)
        self.scroll.set_min_content_width(self._gtk.content_width * 0.4)
        self.scroll.set_min_content_height(self._gtk.content_height * 0.6)
        self.scroll.get_style_context().add_class("scrolled_window_bed_level")
        self.overlayBox.add(self.scroll)
        self.overlayBox.set_vexpand(True)
        self.overlayBox.set_hexpand(True)
        self.scroll.connect("button-release-event", self.clicked_in_scroll)
        self.overlayBox.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.overlayBox.connect("button-release-event", self.close_calibration_manager)
        self.overlayBox.show_all()
        # for child in self.overlay:
        #     child.set_opacity(0.8)
        #     child.set_sensitive(False)
        self.overlay.add_overlay(self.overlayBox)

    def clicked_in_scroll(self, *args):
        self.scroll_clicked = True

    def close_calibration_manager(self, *args):
        if self.scroll_clicked:
            self.scroll_clicked = False
            return
        if self.overlayBox:
            self.overlay.remove(self.overlayBox)
            for child in self.overlayBox:
                self.overlayBox.remove(child)
            self.overlayBox = None
            for child in self.scroll:
                self.scroll.remove(child)
            self.scroll = None
            for child in self.overlay:
                child.set_opacity(1)
                child.set_sensitive(True)
            self.overlayBox = None

    def open_popover(self, widget, screw):
        self.popover[screw]['popover'].show_all()

    def activate(self):
        for key, value in self.screw_dict.items():
            if value:
                self.buttons[key].set_label(f"{value[2]}")
                self.buttons[key].get_style_context().remove_class("bed-level-chars")

    def go_to_position(self, widget, position):
        if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
            self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME)
        logging.debug(f"Going to position: {position}")
        script = [
            f"{KlippyGcodes.MOVE_ABSOLUTE}",
            "G1 Z7 F800\n",
            f"G1 X{position[0]} Y{position[1]} F3600\n",
            "G1 Z.1 F300\n"
        ]
        self._screen._ws.klippy.gcode_script(
            "\n".join(script)
        )

    def process_busy(self, busy):
        for button in ['screws_tilt_calculate', 'screws_tilt_calibrate', True, False]:
            self.buttons[button].set_sensitive((not busy))

    def process_update(self, action, data):
        if action == "notify_status_update":
            if 'probe' in data:
                if 'is_using_magnet_probe' in data['probe']:
                    self.is_using_magnet = data['probe']['is_using_magnet_probe']
                    if self.buttons[not self.is_using_magnet] in self.buttonGrid:
                        self.buttonGrid.remove(self.buttons[not self.is_using_magnet])
                    self.buttonGrid.attach(self.buttons[self.is_using_magnet], 0, 0, 1, 1)
                    self.buttonGrid.show_all()
            if 'screws_tilt_adjust' in data:
                if 'results' in data['screws_tilt_adjust']: 
                    if len(data['screws_tilt_adjust']['results']) != 0:
                        for screw in data['screws_tilt_adjust']['results']:
                            screw_res = data['screws_tilt_adjust']['results'][screw]
                            for key, value in self.screw_dict.items():
                                if value[3] == screw:
                                    if screw_res['is_base']:
                                        self.buttons[key].set_label(_("Reference"))
                                    elif screw_res['adjust'] == "00:00":
                                        self.buttons[key].get_style_context().add_class("bed-level-chars")
                                        self.buttons[key].set_label(f"✔ {screw_res['adjust']}")
                                        continue
                                    else:
                                        self.buttons[key].set_label(f"↶ {screw_res['adjust']}") if screw_res['sign'] == "CCW" else self.buttons[key].set_label(f"↷ {screw_res['adjust']}")
                                        self.buttons[key].get_style_context().add_class("bed-level-chars")
                    else:
                        self.activate()
                if 'base_screw' in data['screws_tilt_adjust']:
                    self.screws_adjust_data['base_screw'] = data['screws_tilt_adjust']['base_screw']
                    if self.screws_adjust_data['base_screw']:
                        for key, value in self.screw_dict.items():
                            if value[3] == self.screws_adjust_data['base_screw']:
                                self.popover[key]['set_as_base'].set_sensitive(False)
                                self.popover[key]['next_screw_calibrate'].set_sensitive(False)
                            elif not self.screws_adjust_data['is_calibrating']:
                                self.popover[key]['set_as_base'].set_sensitive(True)

                if 'calibrating_screw' in data['screws_tilt_adjust']:
                    self.screws_adjust_data['calibrating_screw'] = data['screws_tilt_adjust']['calibrating_screw']
                    if self.screws_adjust_data['calibrating_screw']:
                        for key, value in self.screw_dict.items():
                            if value[3] == self.screws_adjust_data['calibrating_screw']['prefix']:
                                self.popover[key]['next_screw_calibrate'].set_sensitive(False)
                            elif value[3] != self.screws_adjust_data['base_screw']:
                                self.popover[key]['next_screw_calibrate'].set_sensitive(True)
                with contextlib.suppress(Exception):
                  if 'is_calibrating' in data['screws_tilt_adjust']:
                      self.screws_adjust_data['is_calibrating'] = data['screws_tilt_adjust']['is_calibrating']
                      if self.screws_adjust_data['is_calibrating']:
                          if self.buttons['screws_tilt_calibrate'] in self.buttonGrid:
                              self.buttonGrid.remove(self.buttons['screws_tilt_calibrate'])
                          # for btn in ['screws_tilt_calculate', 'screws_tilt_calibrate']:
                          #     if self.buttons[btn] in self.buttonGrid:
                          #         self.buttonGrid.remove(self.buttons[btn])
                          for btn in ['stop_screws_tilt_calibrate', 'stop_screw_calibrate']:
                              if self.buttons[btn] not in self.buttonGrid:
                                  self.buttonGrid.attach(self.buttons[btn], 0, len(self.buttonGrid.get_children()), 1, 1)
                          self.buttonGrid.show_all()
                          for key, value in self.screw_dict.items():
                              self.popover[key]['set_as_base'].set_sensitive(False)
                              self.popover[key]['go_to_position'].set_sensitive(False)
                              if value[3] not in [self.screws_adjust_data['base_screw'], self.screws_adjust_data['calibrating_screw']['prefix']]:
                                  self.popover[key]['next_screw_calibrate'].set_sensitive(True)
                              else:
                                  self.popover[key]['next_screw_calibrate'].set_sensitive(False)
                      else:
                          for btn in ['stop_screws_tilt_calibrate', 'stop_screw_calibrate']:
                              self._gtk.Button_busy(self.buttons[btn], False)
                              self.pressed = False
                              if self.buttons[btn] in self.buttonGrid:
                                  self.buttonGrid.remove(self.buttons[btn])
                          if self.buttons['screws_tilt_calibrate'] not in self.buttonGrid:
                              self.buttonGrid.attach(self.buttons['screws_tilt_calibrate'], 0, len(self.buttonGrid.get_children()), 1, 1)
                          # for btn in ['screws_tilt_calculate', 'screws_tilt_calibrate']:
                          #     if self.buttons[btn] not in self.buttonGrid:
                          #         self.buttonGrid.attach(self.buttons[btn], 0, len(self.buttonGrid.get_children()), 1, 1)
                          for key, value in self.screw_dict.items():
                              self.popover[key]['go_to_position'].set_sensitive(True)
                              if self.screws_adjust_data['base_screw'] != value[3]:
                                  self.popover[key]['set_as_base'].set_sensitive(True)
                              self.popover[key]['next_screw_calibrate'].set_sensitive(False)

    def _get_screws(self, config_section_name):
        screws = []
        config_section = self._printer.get_config_section(config_section_name)
        logging.debug(config_section_name)
        for item in config_section:
            logging.debug(f"{item}: {config_section[item]}")
            result = re.match(r"([\-0-9\.]+)\s*,\s*([\-0-9\.]+)", config_section[item])
            if result:
                screws.append([
                    round(float(result[1]), 1),
                    round(float(result[2]), 1),
                    item
                ])
        return sorted(screws, key=lambda s: (float(s[1]), float(s[0])))

    def screws_tilt_calculate(self, widget):
        if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
            self._screen._ws.klippy.gcode_script(KlippyGcodes.HOME)
        self._screen._ws.klippy.gcode_script("SCREWS_TILT_CALCULATE")

    def return_magnet(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.return_magnet_probe())

    def get_magnet(self, widget):
        self._screen._ws.klippy.gcode_script(KlippyGcodes.get_magnet_probe())

    def screws_tilt_calibrate(self, *args):
        self._screen._ws.klippy.gcode_script("SCREWS_TILT_CALIBRATE")

    def set_base_screw(self, widget, screw):
        self._screen._ws.klippy.gcode_script(f"SET_BASE_SCREW SCREW={self.screw_dict[screw][3]}")

    def stop_screws_tilt_calibrate(self, widget):
        self._gtk.Button_busy(widget, True)
        self.pressed = True
        self._screen._ws.klippy.run_async_command("ASYNC_STOP_SCREWS_TILT_CALIBRATE")

    def stop_screw_calibrate(self, widget):
        self._screen._ws.klippy.run_async_command("ASYNC_STOP_SCREW_CALIBRATE")

    def set_next_calibrating_screw(self, widget, screw):
        self._screen._ws.klippy.run_async_command(f"ASYNC_SET_CALIBRATING_SCREW SCREW={self.screw_dict[screw][3]}")
