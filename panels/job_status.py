# -*- coding: utf-8 -*-
import logging
import os
import contextlib
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyGtk import find_widget
from math import pi, sqrt, trunc
from statistics import median
from time import time

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.grid = self._gtk.HomogeneousGrid()
        self.grid.set_row_homogeneous(False)
        self.pos_z = .0
        self.extrusion = 100
        self.speed_factor = 1.0
        self.speed = 100
        self.req_speed = 0
        self.f_layer_h = self.layer_h = 1
        self.oheight = .0
        self.current_extruder = None
        self.fila_section = pi * ((1.75 / 2) ** 2)
        self.filename_label = self.filename = self.prev_pos = self.prev_gpos = None
        self.can_close = False
        self.retries = 0
        self.flow_timeout = self.animation_timeout = None
        self.file_metadata = self.fans = {}
        self.state = "standby"
        self.timeleft_type = "auto"
        self.progress = self.zoffset = self.flowrate = self.vel = .0
        self.flowstore = []
        self.mm = _("mm")
        self.mms = _("mm/s")
        self.mms2 = _("mm/s²")
        self.mms3 = _("mm³/s")
        self.status_grid = self.move_grid = self.time_grid = self.extrusion_grid = None

        data = ['pos_x', 'pos_y', 'pos_z', 'time_left', 'duration', 'slicer_time', 'file_time',
                'filament_time', 'est_time', 'speed_factor', 'req_speed', 'max_accel', 'extrude_factor', 'zoffset',
                'zoffset', 'filament_used', 'filament_total', 'advance', 'layer', 'total_layers', 'height',
                'flowrate']

        for item in data:
            self.labels[item] = Gtk.Label("-")
            self.labels[item].set_vexpand(True)
            self.labels[item].set_hexpand(True)

        self.labels['left'] = Gtk.Label(_("Left:"))
        self.labels['elapsed'] = Gtk.Label(_("Elapsed:"))
        self.labels['total'] = Gtk.Label(_("Total:"))
        self.labels['slicer'] = Gtk.Label(_("Slicer:"))
        self.labels['file_tlbl'] = Gtk.Label(_("File:"))
        self.labels['fila_tlbl'] = Gtk.Label(_("Filament:"))
        self.labels['speed_lbl'] = Gtk.Label(_("Speed:"))
        self.labels['accel_lbl'] = Gtk.Label(_("Acceleration:"))
        self.labels['flow'] = Gtk.Label(_("Flow:"))
        self.labels['zoffset_lbl'] = Gtk.Label(_("Z offset:"))
        self.labels['fila_used_lbl'] = Gtk.Label(_("Filament used:"))
        self.labels['fila_total_lbl'] = Gtk.Label(_("Filament total:"))
        self.labels['pa_lbl'] = Gtk.Label(_("Pressure Advance:"))
        self.labels['flowrate_lbl'] = Gtk.Label(_("Flowrate:"))
        self.labels['height_lbl'] = Gtk.Label(_("Height:"))
        self.labels['layer_lbl'] = Gtk.Label(_("Layer:"))

        for fan in self._printer.get_fans():
            if fan == "fan":
                name = " "
            elif fan.startswith("fan_generic"):
                name = " ".join(fan.split(" ")[1:])[:1].upper() + ":"
                if name.startswith("_"):
                    continue
            else:
                continue
            self.fans[fan] = {
                "name": name,
                "speed": "-"
            }

        self.labels['file'] = Gtk.Label("Filename")
        self.labels['file'].get_style_context().add_class("printing-filename")
        self.labels['file'].set_hexpand(True)
        
        self.labels['filepath'] = Gtk.Label("Filepath")
        self.labels['file'].set_hexpand(True)
        self.labels['status'] = Gtk.Label("Status")
        self.labels['status'].get_style_context().add_class("printing-status")
        self.labels['lcdmessage'] = Gtk.Label("")
        self.labels['lcdmessage'].get_style_context().add_class("printing-status")

        for label in self.labels:
            self.labels[label].set_halign(Gtk.Align.START)
            self.labels[label].set_ellipsize(Pango.EllipsizeMode.END)

        fi_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fi_box.add(self.labels['file'])
        fi_box.add(self.labels['filepath'])
        fi_box.add(self.labels['status'])
        fi_box.add(self.labels['lcdmessage'])
        self.grid.attach(fi_box, 1, 0, 3, 1)

        self.labels['darea'] = Gtk.DrawingArea()
        self.labels['darea'].connect("draw", self.on_draw)

        box = Gtk.Box()
        box.set_halign(Gtk.Align.CENTER)
        self.labels['progress_text'] = Gtk.Label("0%")
        self.labels['progress_text'].get_style_context().add_class("printing-progress-text")
        box.add(self.labels['progress_text'])

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.add(self.labels['darea'])
        overlay.add_overlay(box)
        self.grid.attach(overlay, 0, 0, 1, 1)

        self.labels['thumbnail'] = self._gtk.Button("file")
        self.labels['thumbnail'].connect("clicked", self.show_fullscreen_thumbnail)
        self.labels['thumbnail'].set_hexpand(False)
        self.labels['info_grid'] = Gtk.Grid()
        self.labels['info_grid'].attach(self.labels['thumbnail'], 0, 0, 1, 1)
        self.current_extruder = self._printer.get_stat("toolhead", "extruder")
        if self.current_extruder:
            diameter = float(self._printer.get_config_section(self.current_extruder)['filament_diameter'])
            self.fila_section = pi * ((diameter / 2) ** 2)

        self.buttons = {}
        self.create_buttons()
        self.buttons['button_grid'] = self._gtk.HomogeneousGrid()
        self.buttons['button_grid'].set_vexpand(False)
        self.grid.attach(self.buttons['button_grid'], 0, 3, 4, 1)

        self.create_status_grid()
        self.create_extrusion_grid()
        self.create_time_grid()
        self.create_move_grid()
        self.grid.attach(self.labels['info_grid'], 0, 1, 4, 2)
        self.switch_info(info=self.status_grid)
        self.content.add(self.grid)

    def create_status_grid(self, widget=None):
        buttons = {
            'speed': self._gtk.Button("speed+", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
            'z': self._gtk.Button("home-z", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
            'extrusion': self._gtk.Button("extrude", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
            'fan': self._gtk.Button("fan", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
            'elapsed': self._gtk.Button("clock", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
            'left': self._gtk.Button("hourglass", "-", None, self.bts, Gtk.PositionType.LEFT, 1),
        }
        for button in buttons:
            buttons[button].set_halign(Gtk.Align.START)
        buttons['fan'].connect("clicked", self.menu_item_clicked, {"panel": "fan", "name": _("Fan")})
        self.buttons.update(buttons)

        self.buttons['extruder'] = {}
        for i, extruder in enumerate(self._printer.get_tools()):
            self.labels[extruder] = Gtk.Label(label="-")
            self.buttons['extruder'][extruder] = self._gtk.Button(f"extruder-{i}", "", None, self.bts,
                                                                  Gtk.PositionType.LEFT, 1)
            self.buttons['extruder'][extruder].set_label(self.labels[extruder].get_text())
            self.buttons['extruder'][extruder].connect("clicked", self.menu_item_clicked,
                                                       {"panel": "temperature", "name": _("Temperature"),
                                                        'extra': extruder})
            self.buttons['extruder'][extruder].set_halign(Gtk.Align.START)
            
        self.labels['temp_grid'] = Gtk.Grid()
        nlimit = 2 if self._screen.width <= 500 else 3
        n = 0
        if nlimit > 2 and len(self._printer.get_tools()) == 2:
            for extruder in self.buttons['extruder']:
                self.labels['temp_grid'].attach(self.buttons['extruder'][extruder], n, 0, 1, 1)
                n += 1
        else:
            self.current_extruder = self._printer.get_stat("toolhead", "extruder")
            if self.current_extruder:
                self.labels['temp_grid'].attach(self.buttons['extruder'][self.current_extruder], n, 0, 1, 1)
                n += 1
        self.buttons['heater'] = {}
        for dev in self._printer.get_heaters():
            if n >= nlimit:
                break
            if dev == "heater_bed":
                self.buttons['heater'][dev] = self._gtk.Button("bed", "", None, self.bts, Gtk.PositionType.LEFT, 1)
            else:
                self.buttons['heater'][dev] = self._gtk.Button("heater", "", None, self.bts, Gtk.PositionType.LEFT, 1)
            self.labels[dev] = Gtk.Label(label="-")

            self.buttons['heater'][dev].set_label(self.labels[dev].get_text())
            self.buttons['heater'][dev].connect("clicked", self.menu_item_clicked,
                                                {"panel": "temperature", "name": _("Temperature"), "extra": dev})
            self.buttons['heater'][dev].set_halign(Gtk.Align.START)
            self.labels['temp_grid'].attach(self.buttons['heater'][dev], n, 0, 1, 1)
            n += 1
        extra_item = not self._show_heater_power
        if self.ks_printer_cfg is not None:
            titlebar_items = self.ks_printer_cfg.get("titlebar_items", "")
            if titlebar_items is not None:
                titlebar_items = [str(i.strip()) for i in titlebar_items.split(',')]
                logging.info(f"Titlebar items: {titlebar_items}")
                for device in self._printer.get_temp_sensors():
                    name = " ".join(device.split(" ")[1:])
                    for item in titlebar_items:
                        if name == item:
                            if extra_item:
                                extra_item = False
                                nlimit += 1
                            if n >= nlimit:
                                break
                            self.buttons['heater'][device] = self._gtk.Button("heat-up", "", None, self.bts,
                                                                              Gtk.PositionType.LEFT, 1)
                            self.labels[device] = Gtk.Label(label="-")
                            self.buttons['heater'][device].set_label(self.labels[device].get_text())
                            self.buttons['heater'][device].connect("clicked", self.menu_item_clicked,
                                                                   {"panel": "temperature",
                                                                    "name": _("Temperature")})
                            self.buttons['heater'][device].set_halign(Gtk.Align.START)
                            self.labels['temp_grid'].attach(self.buttons['heater'][device], n, 0, 1, 1)
                            n += 1
                            break

        szfe = Gtk.Grid()
        szfe.set_column_homogeneous(True)
        szfe.attach(self.buttons['speed'], 0, 0, 3, 1)
        szfe.attach(self.buttons['z'], 2, 0, 2, 1)
        if self._printer.get_tools():
            szfe.attach(self.buttons['extrusion'], 0, 1, 3, 1)
        if self._printer.get_fans():
            szfe.attach(self.buttons['fan'], 2, 1, 2, 1)

        info = Gtk.Grid()
        info.set_row_homogeneous(True)
        info.get_style_context().add_class("printing-info")
        info.attach(self.labels['temp_grid'], 0, 0, 1, 1)
        info.attach(szfe, 0, 1, 1, 2)
        info.attach(self.buttons['elapsed'], 0, 3, 1, 1)
        info.attach(self.buttons['left'], 0, 4, 1, 1)
        self.status_grid = info

    def create_extrusion_grid(self, widget=None):
        goback = self._gtk.Button("back", None, "color1", self.bts, Gtk.PositionType.TOP, False)
        goback.connect("clicked", self.switch_info, self.status_grid)
        goback.set_hexpand(False)
        goback.get_style_context().add_class("printing-info")

        info = Gtk.Grid()
        info.set_hexpand(True)
        info.set_vexpand(True)
        info.set_halign(Gtk.Align.START)
        info.get_style_context().add_class("printing-info-secondary")
        info.attach(goback, 0, 0, 1, 6)
        info.attach(self.labels['flow'], 1, 0, 1, 1)
        info.attach(self.labels['extrude_factor'], 2, 0, 1, 1)
        info.attach(self.labels['flowrate_lbl'], 1, 1, 1, 1)
        info.attach(self.labels['flowrate'], 2, 1, 1, 1)
        info.attach(self.labels['pa_lbl'], 1, 2, 1, 1)
        info.attach(self.labels['advance'], 2, 2, 1, 1)
        info.attach(self.labels['fila_used_lbl'], 1, 3, 1, 1)
        info.attach(self.labels['filament_used'], 2, 3, 1, 1)
        info.attach(self.labels['fila_total_lbl'], 1, 4, 1, 1)
        info.attach(self.labels['filament_total'], 2, 4, 1, 1)
        self.extrusion_grid = info
        self.buttons['extrusion'].connect("clicked", self.switch_info, self.extrusion_grid)

    def create_move_grid(self, widget=None):
        goback = self._gtk.Button("back", None, "color2", self.bts, Gtk.PositionType.TOP, False)
        goback.connect("clicked", self.switch_info, self.status_grid)
        goback.set_hexpand(False)
        goback.get_style_context().add_class("printing-info")

        pos_box = Gtk.Box(spacing=5)
        pos_box.add(self.labels['pos_x'])
        pos_box.add(self.labels['pos_y'])
        pos_box.add(self.labels['pos_z'])

        info = Gtk.Grid()
        info.set_hexpand(True)
        info.set_vexpand(True)
        info.set_halign(Gtk.Align.START)
        info.get_style_context().add_class("printing-info-secondary")
        info.attach(goback, 0, 0, 1, 6)
        info.attach(self.labels['speed_lbl'], 1, 0, 1, 1)
        info.attach(self.labels['req_speed'], 2, 0, 1, 1)
        info.attach(self.labels['accel_lbl'], 1, 1, 1, 1)
        info.attach(self.labels['max_accel'], 2, 1, 1, 1)
        info.attach(pos_box, 1, 2, 2, 1)
        info.attach(self.labels['zoffset_lbl'], 1, 3, 1, 1)
        info.attach(self.labels['zoffset'], 2, 3, 1, 1)
        info.attach(self.labels['height_lbl'], 1, 4, 1, 1)
        info.attach(self.labels['height'], 2, 4, 1, 1)
        info.attach(self.labels['layer_lbl'], 1, 5, 1, 1)
        info.attach(self.labels['layer'], 2, 5, 1, 1)
        self.move_grid = info
        self.buttons['z'].connect("clicked", self.switch_info, self.move_grid)
        self.buttons['speed'].connect("clicked", self.switch_info, self.move_grid)

    def create_time_grid(self, widget=None):
        goback = self._gtk.Button("back", None, "color3", self.bts, Gtk.PositionType.TOP, False)
        goback.connect("clicked", self.switch_info, self.status_grid)
        goback.set_hexpand(False)

        info = Gtk.Grid()
        info.get_style_context().add_class("printing-info-secondary")
        info.attach(goback, 0, 0, 1, 6)
        info.attach(self.labels['elapsed'], 1, 0, 1, 1)
        info.attach(self.labels['duration'], 2, 0, 1, 1)
        info.attach(self.labels['left'], 1, 1, 1, 1)
        info.attach(self.labels['time_left'], 2, 1, 1, 1)
        info.attach(self.labels['total'], 1, 2, 1, 1)
        info.attach(self.labels['est_time'], 2, 2, 1, 1)
        info.attach(self.labels['slicer'], 1, 3, 1, 1)
        info.attach(self.labels['slicer_time'], 2, 3, 1, 1)
        info.attach(self.labels['file_tlbl'], 1, 4, 1, 1)
        info.attach(self.labels['file_time'], 2, 4, 1, 1)
        info.attach(self.labels['fila_tlbl'], 1, 5, 1, 1)
        info.attach(self.labels['filament_time'], 2, 5, 1, 1)
        self.time_grid = info
        self.buttons['elapsed'].connect("clicked", self.switch_info, self.time_grid)
        self.buttons['left'].connect("clicked", self.switch_info, self.time_grid)

    def switch_info(self, widget=None, info=None):
        if not info:
            logging.debug("No info to attach")
            return
        if self._screen.vertical_mode:
            self.labels['info_grid'].remove_row(1)
            self.labels['info_grid'].attach(info, 0, 1, 1, 1)
        else:
            self.labels['info_grid'].remove_column(1)
            self.labels['info_grid'].attach(info, 1, 0, 1, 1)
        self.labels['info_grid'].show_all()

    def on_draw(self, da, ctx):
        w = da.get_allocated_width()
        h = da.get_allocated_height()
        r = min(w, h) * .42

        ctx.set_source_rgb(0.13, 0.13, 0.13)
        ctx.set_line_width(self._gtk.font_size * .75)
        ctx.translate(w / 2, h / 2)
        ctx.arc(0, 0, r, 0, 2 * pi)
        ctx.stroke()
        ctx.set_source_rgb(0.718, 0.110, 0.110)
        ctx.arc(0, 0, r, 3 / 2 * pi, 3 / 2 * pi + (self.progress * 2 * pi))
        ctx.stroke()

    def activate(self):
        if self.flow_timeout is None:
            self.flow_timeout = GLib.timeout_add_seconds(2, self.update_flow)

    def deactivate(self):
        if self.flow_timeout is not None:
            GLib.source_remove(self.flow_timeout)
            self.flow_timeout = None

    def create_buttons(self):

        self.buttons = {
            'cancel': self._gtk.Button("stop", _("Cancel"), "color2"),
            'control': self._gtk.Button("settings", _("Settings"), "color3"),
            'fine_tune': self._gtk.Button("fine-tune", _("Fine Tuning"), "color4"),
            'menu': self._gtk.Button("complete", _("Main Menu"), "color4"),
            'pause': self._gtk.Button("pause", _("Pause"), "color1"),
            'restart': self._gtk.Button("refresh", _("Restart"), "color3"),
            'resume': self._gtk.Button("resume", _("Resume"), "color1"),
            'save_offset_endstop': self._gtk.Button("home-z", _("Save offset endstop"), "color2"),
        }
        self.buttons['cancel'].connect("clicked", self.cancel)
        self.buttons['control'].connect("clicked", self._screen._go_to_submenu, "")
        self.buttons['fine_tune'].connect("clicked", self.menu_item_clicked, {
            "panel": "fine_tune", "name": _("Fine Tuning")})
        self.buttons['menu'].connect("clicked", self.close_panel)
        self.buttons['pause'].connect("clicked", self.pause)
        self.buttons['restart'].connect("clicked", self.restart)
        self.buttons['resume'].connect("clicked", self.resume)
        self.buttons['save_offset_endstop'].connect("clicked", self.save_offset)

    def save_offset(self, widget):
        label = Gtk.Label()
        saved_z_offset = None
        msg = _("Apply %.3f offset to Endstop?") % (self.zoffset) 
        saved_z_offset = self._printer.get_stat("manual_probe", "z_position_endstop")
        if saved_z_offset:
            msg += "\n\n" + _("Saved offset: %.3f") % saved_z_offset
        label.set_label(msg)
        label.set_hexpand(True)
        label.set_halign(Gtk.Align.CENTER)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        grid = self._gtk.HomogeneousGrid()
        grid.attach(label, 0, 0, 1, 1)
        buttons = [
            {"name": _("Apply"), "response": Gtk.ResponseType.APPLY, "style": "color4"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "color2"}
        ]
        self._gtk.Dialog(buttons, grid, _("Save Z"), self.save_confirm)

    def save_confirm(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.APPLY:
            self._screen._ws.klippy.gcode_script("Z_OFFSET_APPLY_ENDSTOP")

    def restart(self, widget):
        if self.filename:
            self.disable_button("restart")
            self._screen._ws.klippy.print_start(self.filename, self.print_start_callback)
            logging.info(f"Starting print: {self.filename}")
            self.new_print()
        else:
            self.enable_button("restart")
            logging.info(f"Could not restart {self.filename}")

    def print_start_callback(self, result, method, params):
      self.enable_button("restart")
      
    def resume(self, widget):
        self.disable_button("resume")
        self._screen._ws.klippy.print_resume()
        self._screen.show_all()

    def pause(self, widget):
        self.disable_button("pause")
        self._screen._ws.klippy.print_pause()
        self._screen.show_all()

    def cancel(self, widget):
        buttons = [
            {"name": _("Cancel Print"), "response": Gtk.ResponseType.OK, "style": "color2"},
            {"name": _("Go Back"), "response": Gtk.ResponseType.CANCEL, "style": "color4"}
        ]
        if len(self._printer.get_stat("exclude_object", "objects")) > 1:
            buttons.insert(0, {"name": _("Exclude Object"), "response": Gtk.ResponseType.APPLY, "style": "color3"})
        label = Gtk.Label()
        label.set_markup(_("Are you sure you wish to cancel this print?"))
        label.set_hexpand(True)
        label.set_halign(Gtk.Align.CENTER)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        self._gtk.Dialog(buttons, label, _("Cancel"), self.cancel_confirm)

    def cancel_confirm(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.APPLY:
            self.menu_item_clicked(None, {"panel": "exclude", "name": _("Exclude Object")})
            return
        if response_id == Gtk.ResponseType.CANCEL:
            return
        logging.debug("Canceling print")
        self.set_state("cancelling")
        self._screen._ws.klippy.print_cancel()

    def close_panel(self, widget=None):
        if self.can_close:
            logging.debug("Closing job_status panel")
            self._screen.state_ready(wait=False)

    def enable_button(self, *args):
        for arg in args:
            self.buttons[arg].set_sensitive(True)

    def disable_button(self, *args):
        for arg in args:
            self.buttons[arg].set_sensitive(False)

    def new_print(self):
        self._screen.close_screensaver()
        if "virtual_sdcard" in self._printer.data:
            logging.info("reseting progress")
            self._printer.data["virtual_sdcard"]["progress"] = 0
        self.update_progress(0.0)
    
    def process_update(self, action, data):
        safety_printing_data = self._printer.get('safety_printing')
        if safety_printing_data:
          if safety_printing_data['safety_enabled']:
              if safety_printing_data['luft_overload']:
                  self.disable_button("resume")
              else:
                  self.enable_button("resume")
        if action == "notify_metadata_update" and data['filename'] == self.filename:
            if self.retries < 5:
              self.update_file_metadata()
        elif action != "notify_status_update":
            return
        for x in self._printer.get_temp_devices():
            if x in data:
                self.update_temp(
                    x,
                    self._printer.get_dev_stat(x, "temperature"),
                    self._printer.get_dev_stat(x, "target"),
                    self._printer.get_dev_stat(x, "power"),
                )
                if x in self.buttons['extruder']:
                    self.buttons['extruder'][x].set_label(self.labels[x].get_text())
                elif x in self.buttons['heater']:
                    self.buttons['heater'][x].set_label(self.labels[x].get_text())

        with contextlib.suppress(Exception):
          if data['filament_watcher']['show_message'] == True:
              self._screen.close_popup_message()
              self._screen.show_popup_message(_("Printing with PLA filament. Please, turn on camera fan or disable safety printing and open doors or hood"), 2, True, -1)
              #self._screen.set_can_close_message(False)
          else:
              #self._screen.set_can_close_message(True)
              self._screen.close_popup_message()

        if "display_status" in data and "message" in data["display_status"]:
            self.labels['lcdmessage'].set_label(
                f"{data['display_status']['message'] if data['display_status']['message'] is not None else ''}"
            )

        if 'toolhead' in data:
            if 'extruder' in data['toolhead'] and data['toolhead']['extruder'] != self.current_extruder:
                self.labels['temp_grid'].remove_column(0)
                self.labels['temp_grid'].insert_column(0)
                self.current_extruder = data["toolhead"]["extruder"]
                self.labels['temp_grid'].attach(self.buttons['extruder'][self.current_extruder], 0, 0, 1, 1)
                self._screen.show_all()
            if "max_accel" in data["toolhead"]:
                self.labels['max_accel'].set_label(f"{data['toolhead']['max_accel']:.0f} {self.mms2}")
        if 'extruder' in data and 'pressure_advance' in data['extruder']:
            self.labels['advance'].set_label(f"{data['extruder']['pressure_advance']:.2f}")

        if 'gcode_move' in data:
            if 'gcode_position' in data['gcode_move']:
                self.pos_z = round(float(data['gcode_move']['gcode_position'][2]), 2)
                self.buttons['z'].set_label(f"Z: {self.pos_z:6.2f}{f'/{self.oheight}' if self.oheight > 0 else ''}")
            if 'extrude_factor' in data['gcode_move']:
                self.extrusion = round(float(data['gcode_move']['extrude_factor']) * 100)
                self.labels['extrude_factor'].set_label(f"{self.extrusion:3}%")
            if 'speed_factor' in data['gcode_move']:
                self.speed = round(float(data['gcode_move']['speed_factor']) * 100)
                self.speed_factor = float(data['gcode_move']['speed_factor'])
                self.labels['speed_factor'].set_label(f"{self.speed:3}%")
            if 'speed' in data['gcode_move']:
                self.req_speed = round(float(data["gcode_move"]["speed"]) / 60 * self.speed_factor)
                self.labels['req_speed'].set_label(
                    f"{self.speed}% {self.vel:3.0f}/{self.req_speed:3.0f} "
                    f"{f'{self.mms}' if self.vel < 1000 and self.req_speed < 1000 and self._screen.width > 500 else ''}"
                )
                self.buttons['speed'].set_label(self.labels['req_speed'].get_label())
            if 'homing_origin' in data['gcode_move']:
                self.zoffset = float(data['gcode_move']['homing_origin'][2])
                self.labels['zoffset'].set_label(f"{self.zoffset:.3f} {self.mm}")
        if 'motion_report' in data:
            if 'live_position' in data['motion_report']:
                self.labels['pos_x'].set_label(f"X: {data['motion_report']['live_position'][0]:6.2f}")
                self.labels['pos_y'].set_label(f"Y: {data['motion_report']['live_position'][1]:6.2f}")
                self.labels['pos_z'].set_label(f"Z: {data['motion_report']['live_position'][2]:6.2f}")
                pos = data["motion_report"]["live_position"]
                now = time()
                if self.prev_pos is not None:
                    interval = (now - self.prev_pos[1])
                    # Calculate Flowrate
                    evelocity = (pos[3] - self.prev_pos[0][3]) / interval
                    self.flowstore.append(self.fila_section * evelocity)
                self.prev_pos = [pos, now]
            if 'live_velocity' in data['motion_report']:
                self.vel = float(data["motion_report"]["live_velocity"])
                self.labels['req_speed'].set_label(
                    f"{self.speed}% {self.vel:3.0f}/{self.req_speed:3.0f} "
                    f"{f'{self.mms}' if self.vel < 1000 and self.req_speed < 1000 and self._screen.width > 500 else ''}"
                )
                self.buttons['speed'].set_label(self.labels['req_speed'].get_label())
            if 'live_extruder_velocity' in data['motion_report']:
                self.flowstore.append(self.fila_section * float(data["motion_report"]["live_extruder_velocity"]))
        fan_label = ""
        for fan in self.fans:
            self.fans[fan]['speed'] = f"{self._printer.get_fan_speed(fan) * 100:3.0f}%"
            fan_label += f" {self.fans[fan]['name']}{self.fans[fan]['speed']}"
        if fan_label:
            self.buttons['fan'].set_label(fan_label[:12])

        if "print_stats" in data:
            if 'state' in data['print_stats']:
                self.set_state(
                    data["print_stats"]["state"],
                    msg=f'{data["print_stats"]["message"] if "message" in data["print_stats"] else ""}'
                )
            if 'filename' in data['print_stats']:
                self.update_filename(data['print_stats']["filename"])
            if 'filament_used' in data['print_stats']:
                self.labels['filament_used'].set_label(
                    f"{float(data['print_stats']['filament_used']) / 1000:.1f} m"
                )
            if 'info' in data["print_stats"]:
                if ('total_layer' in data['print_stats']['info']
                        and data["print_stats"]['info']['total_layer'] is not None):
                    self.labels['total_layers'].set_label(f"{data['print_stats']['info']['total_layer']}")
                if ('current_layer' in data['print_stats']['info']
                        and data['print_stats']['info']['current_layer'] is not None):
                    self.labels['layer'].set_label(
                        f"{data['print_stats']['info']['current_layer']} / "
                        f"{self.labels['total_layers'].get_text()}"
                    )
            elif "layer_height" in self.file_metadata and "object_height" in self.file_metadata:
                self.labels['layer'].set_label(
                    f"{1 + round((self.pos_z - self.f_layer_h) / self.layer_h)} / "
                    f"{self.labels['total_layers'].get_text()}"
                )
            if self.state in ["printing", "paused"]:
                self.update_time_left()

    def update_flow(self):
        if not self.flowstore:
            self.flowstore.append(0)
        self.flowrate = median(self.flowstore)
        self.flowstore = []
        self.labels['flowrate'].set_label(f"{self.flowrate:.1f} {self.mms3}")
        self.buttons['extrusion'].set_label(f"{self.extrusion:3}% {self.flowrate:5.1f} {self.mms3}")
        return True

    def update_time_left(self):
        total_duration = float(self._printer.get_stat('print_stats', 'total_duration'))
        print_duration = float(self._printer.get_stat('print_stats', 'print_duration'))
        fila_used = float(self._printer.get_stat('print_stats', 'filament_used'))
        if "gcode_start_byte" in self.file_metadata:
            progress = (max(self._printer.get_stat('virtual_sdcard', 'file_position') -
                        self.file_metadata['gcode_start_byte'], 0) / (self.file_metadata['gcode_end_byte'] -
                        self.file_metadata['gcode_start_byte']))
        else:
            progress = self._printer.get_stat('virtual_sdcard', 'progress')
        self.labels["duration"].set_label(self.format_time(total_duration))
        elapsed_label = f"{self.labels['elapsed'].get_text()}  {self.labels['duration'].get_text()}"
        self.buttons['elapsed'].set_label(elapsed_label)
        find_widget(self.buttons['elapsed'], Gtk.Label).set_ellipsize(Pango.EllipsizeMode.END)
        estimated = slicer_time = filament_time = file_time = 0
        timeleft_type = self._config.get_config()['main'].get('print_estimate_method', 'auto')

        if 'estimated_time' in self.file_metadata and self.file_metadata['estimated_time'] > 1:
            spdcomp = sqrt(self.speed_factor)
            slicer_time = ((self.file_metadata['estimated_time']) / spdcomp)
            self.labels["slicer_time"].set_label(self.format_time(slicer_time))
            if print_duration < 1:
                print_duration = slicer_time * progress
        elif print_duration < 1:  # No-extrusion
            print_duration = total_duration

        if 'filament_total' in self.file_metadata and self.file_metadata['filament_total'] >= fila_used > 0:
            filament_time = (print_duration / (fila_used / self.file_metadata['filament_total']))
            self.labels["filament_time"].set_label(self.format_time(filament_time))
        if progress > 0:
            file_time = (print_duration / progress)
            self.labels["file_time"].set_label(self.format_time(file_time))

        if timeleft_type == "file":
            estimated = file_time
        elif timeleft_type == "filament":
            estimated = filament_time
        elif timeleft_type == "slicer":
            estimated = slicer_time
        elif estimated < 1:  # Auto
            if print_duration < slicer_time > 1:
                if progress < 0.15:
                    # At the begining file and filament are innacurate
                    estimated = slicer_time
                elif filament_time > 1 and file_time > 1:
                    # Weighted arithmetic mean (Slicer is the most accurate)
                    estimated = (slicer_time * 3 + filament_time + file_time) / 5
                elif file_time > 1:
                    # Weighted arithmetic mean (Slicer is the most accurate)
                    estimated = (slicer_time * 2 + file_time) / 3
            elif print_duration < filament_time > 1 and file_time > 1:
                estimated = (filament_time + file_time) / 2
            elif file_time > 1:
                estimated = file_time
        if estimated > 1:
            progress = min(max(print_duration / estimated, 0), 1)
            self.labels["est_time"].set_label(self.format_time(estimated))
            self.labels["time_left"].set_label(self.format_eta(estimated, print_duration))
            remaining_label = f"{self.labels['left'].get_text()}  {self.labels['time_left'].get_text()}"
            self.buttons['left'].set_label(remaining_label)
            find_widget(self.buttons['left'], Gtk.Label).set_ellipsize(Pango.EllipsizeMode.END)
        self.update_progress(progress)

    def update_progress(self, progress: float):
        self.progress = progress
        self.labels['progress_text'].set_label(f"{trunc(progress * 100)}%")
        self.labels['darea'].queue_draw()

    def set_state(self, state, msg=""):
        if state == "printing":
            self.disable_button("resume")
            self.enable_button("pause")
            self.labels["status"].set_label(_("Printing"))
        elif state == "complete":
            self.retries = 0
            self.disable_button("resume", "pause")
            self.update_progress(1)
            self.labels["status"].set_label(_("Complete"))
            self.buttons['left'].set_label("-")
            self._add_timeout(self._config.get_main_config().getint("job_complete_timeout", 0))
        elif state == "error":
            self.retries = 0
            self.disable_button("resume", "pause")
            self._screen.show_popup_message(msg)
            self._add_timeout(self._config.get_main_config().getint("job_error_timeout", 0))
        elif state == "cancelling":
            self.retries = 0
            self.disable_button("resume", "pause")
            self.labels["status"].set_label(_("Cancelling"))
        elif state == "cancelled" or (state == "standby" and self.state == "cancelled"):
            self.retries = 0
            self.disable_button("resume", "pause")
            self.labels["status"].set_label(_("Cancelled"))
            self._add_timeout(self._config.get_main_config().getint("job_cancelled_timeout", 0))
        elif state == "paused":
            self.enable_button("resume")
            self.disable_button("pause")
            self.labels["status"].set_label(_("Paused"))
        elif state == "standby":
            self.retries = 0
            self.enable_button("resume")
            self.disable_button("pause")
            self.labels["status"].set_label(_("Standby"))
        if self.state != state:
            logging.debug(f"Changing job_status state from '{self.state}' to '{state}'")
            self.state = state
        self.show_buttons_for_state()
    
    def _add_timeout(self, timeout):
        self._screen.close_screensaver()
        if timeout != 0:
            GLib.timeout_add_seconds(timeout, self.close_panel)

    def show_buttons_for_state(self):
        self.buttons['button_grid'].remove_row(0)
        self.buttons['button_grid'].insert_row(0)
        if self.state == "printing":
            self.buttons['button_grid'].attach(self.buttons['pause'], 0, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['cancel'], 1, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['fine_tune'], 2, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['control'], 3, 0, 1, 1)
            self.can_close = False
        elif self.state == "paused":
            self.buttons['button_grid'].attach(self.buttons['resume'], 0, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['cancel'], 1, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['fine_tune'], 2, 0, 1, 1)
            self.buttons['button_grid'].attach(self.buttons['control'], 3, 0, 1, 1)
            self.can_close = False
        else:
            offset = self._printer.get_stat("gcode_move", "homing_origin")
            self.zoffset = float(offset[2]) if offset else 0
            if self.zoffset != 0:
                if "Z_OFFSET_APPLY_ENDSTOP" in self._printer.available_commands:
                    self.buttons['button_grid'].attach(self.buttons["save_offset_endstop"], 0, 0, 1, 1)
                else:
                    self.buttons['button_grid'].attach(Gtk.Label(""), 0, 0, 1, 1)
            else:
                self.buttons['button_grid'].attach(Gtk.Label(""), 0, 0, 1, 1)
                self.buttons['button_grid'].attach(Gtk.Label(""), 1, 0, 1, 1)

            if self.filename:
                self.buttons['button_grid'].attach(self.buttons['restart'], 2, 0, 1, 1)
                self.enable_button("restart")
            else:
                self.disable_button("restart")
            if self.state != "cancelling":
                self.buttons['button_grid'].attach(self.buttons['menu'], 3, 0, 1, 1)
                self.can_close = True
        self.content.show_all()

    def show_file_thumbnail(self):
        if self._screen.vertical_mode:
            width = self._screen.width * 0.9
            height = self._screen.height / 4
        else:
            width = self._screen.width * .25
            height = self._gtk.content_height * 0.47
        pixbuf = self.get_file_image(self.filename, width, height)
        logging.debug(self.filename)
        if pixbuf is None:
            logging.debug("no pixbuf")
            return
        image = find_widget(self.labels['thumbnail'], Gtk.Image)
        if image:
            image.set_from_pixbuf(pixbuf)

    def show_fullscreen_thumbnail(self, widget):
        buttons = [
            {"name": _("Close"), "response": Gtk.ResponseType.CANCEL, "style": "color4"}
        ]
        height = self._screen.height * .9 - self._gtk.font_size * 7.5
        pixbuf = self.get_file_image(self.filename, self._screen.width * .9, height)
        if pixbuf is None:
            return
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add(image)
        box.set_vexpand(True)
        self._gtk.Dialog(buttons, image, self.filename, self.close_fullscreen_thumbnail)
        return

    def close_fullscreen_thumbnail(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)

    def update_filename(self, filename):
        if not filename:
            return
        self.filename = filename
        self.labels["file"].set_label(self.filename.split('/').pop())
        self.labels["filepath"].set_label(os.path.splitext(self.filename)[0])
        self.filename_label = {
            "complete": self.labels['file'].get_label(),
            "current": self.labels['file'].get_label(),
            "position": 0,
            "limit": (self._screen.width * 37 / 480) // (self._gtk.font_size / 11),
            "length": len(self.labels['file'].get_label())
        }
        if self.animation_timeout is None and (self.filename_label['length'] - self.filename_label['limit']) > 0:
            self.animation_timeout = GLib.timeout_add_seconds(1, self.animate_label)
        if self.retries < 5:
          self.update_file_metadata()

    def animate_label(self):
        pos = self.filename_label['position']
        if pos > (self.filename_label['length'] - self.filename_label['limit']):
            self.filename_label['position'] = 0
            self.labels['filepath'].set_label(self.filename_label['complete'])
        else:
            self.labels['filepath'].set_label(self.filename_label['current'][pos:self.filename_label['length']])
            self.filename_label['position'] += 1
        return True

    def update_file_metadata(self):
        if self._files.file_metadata_exists(self.filename):
            self.file_metadata = self._files.get_file_info(self.filename)
            logging.info(f"Update Metadata. File: {self.filename} Size: {self.file_metadata['size']}")
            if "estimated_time" in self.file_metadata and self.timeleft_type == "slicer":
                self.labels["est_time"].set_label(self.format_time(self.file_metadata['estimated_time']))
            if "object_height" in self.file_metadata:
                self.oheight = float(self.file_metadata['object_height'])
                self.labels['height'].set_label(f"{self.oheight} {self.mm}")
                if "layer_height" in self.file_metadata:
                    self.layer_h = float(self.file_metadata['layer_height'])
                    if "first_layer_height" in self.file_metadata:
                        self.f_layer_h = float(self.file_metadata['first_layer_height'])
                    else:
                        self.f_layer_h = self.layer_h
                    self.labels['total_layers'].set_label(f"{((self.oheight - self.f_layer_h) / self.layer_h) + 1:.0f}")
            if "filament_total" in self.file_metadata:
                self.labels['filament_total'].set_label(f"{float(self.file_metadata['filament_total']) / 1000:.1f} m")
        else:
            logging.debug("Cannot find file metadata. Listening for updated metadata")
            self.retries += + 1
            self._files.request_metadata(self.filename)
        self.show_file_thumbnail()
