# -*- coding: utf-8 -*-
import contextlib
import logging
import os
import pathlib
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, Gtk, Pango

def find_widget(widget, wanted_type):
    # Returns a widget of wanted_type or None
    if isinstance(widget, wanted_type):
        return widget
    if isinstance(widget, (Gtk.Container, Gtk.Bin, Gtk.Button, Gtk.Alignment, Gtk.Box)):
        for _ in widget.get_children():
            result = find_widget(_, wanted_type)
            if result is not None:
                return result

def format_label(widget, lines=2, is_ellipsize=True):
    if isinstance(widget, Gtk.Label):
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_justify(Gtk.Justification.CENTER)
        if is_ellipsize:
            widget.set_ellipsize(True)
            widget.set_ellipsize(Pango.EllipsizeMode.END)
            widget.set_lines(lines)
        return widget, lines, is_ellipsize
    elif isinstance(widget, (Gtk.Container, Gtk.Bin, Gtk.Button, Gtk.Alignment, Gtk.Box)):
        for _ in widget.get_children():
            format_label(_, lines, is_ellipsize)


class KlippyGtk:
    labels = {}

    def __init__(self, screen):
        self.screen = screen
        self.themedir = os.path.join(pathlib.Path(__file__).parent.resolve().parent, "styles", screen.theme, "images")
        self.cursor = screen.show_cursor
        self.font_size_type = screen._config.get_main_config().get("font_size", "medium")
        self.width = screen.width
        self.height = screen.height
        self.font_ratio = [33, 49] if self.screen.vertical_mode else [43, 29]
        self.font_size = min(self.width / self.font_ratio[0], self.height / self.font_ratio[1])
        self.img_scale = self.font_size * 2
        self.button_image_scale = 1.38
        self.bsidescale = .65  # Buttons with image at the side
        self.dialog_buttons_height = round(self.height / 5)

        if self.font_size_type == "max":
            self.font_size = self.font_size * 1.2
            self.bsidescale = .7
        elif self.font_size_type == "extralarge":
            self.font_size = self.font_size * 1.14
            self.img_scale = self.img_scale * 0.7
            self.bsidescale = 1
        elif self.font_size_type == "large":
            self.font_size = self.font_size * 1.09
            self.img_scale = self.img_scale * 0.9
            self.bsidescale = .8
        elif self.font_size_type == "small":
            self.font_size = self.font_size * 0.91
            self.bsidescale = .55
        self.img_width = self.font_size * 3
        self.img_height = self.font_size * 3
        self.titlebar_height = self.font_size * 2
        logging.info(f"Font size: {self.font_size:.1f} ({self.font_size_type})")

        if self.screen.vertical_mode:
            self.action_bar_width = int(self.width)
            self.action_bar_height = int(self.height * .1)
            self.content_width = self.width
            self.content_height = self.height - self.titlebar_height - self.action_bar_height
        else:
            self.action_bar_width = int(self.width * .1)
            self.action_bar_height = int(self.height)
            self.content_width = self.width - self.action_bar_width
            self.content_height = self.height - self.titlebar_height

        self.keyboard_height = self.content_height * 0.5
        if (self.height / self.width) >= 3:  # Ultra-tall
            self.keyboard_height = self.keyboard_height * 0.5

        self.color_list = {}  # This is set by screen.py init_style()
        for key in self.color_list:
            if "base" in self.color_list[key]:
                rgb = [int(self.color_list[key]['base'][i:i + 2], 16) for i in range(0, 6, 2)]
                self.color_list[key]['rgb'] = rgb

    def get_temp_color(self, device):
        # logging.debug("Color list %s" % self.color_list)
        if device not in self.color_list:
            return False, False

        if 'base' in self.color_list[device]:
            rgb = self.color_list[device]['rgb'].copy()
            if self.color_list[device]['state'] > 0:
                rgb[1] = rgb[1] + self.color_list[device]['hsplit'] * self.color_list[device]['state']
            self.color_list[device]['state'] += 1
            rgb = [x / 255 for x in rgb]
            # logging.debug(f"Assigning color: {device} {rgb}")
        else:
            colors = self.color_list[device]['colors']
            if self.color_list[device]['state'] >= len(colors):
                self.color_list[device]['state'] = 0
            color = colors[self.color_list[device]['state'] % len(colors)]
            rgb = [int(color[i:i + 2], 16) / 255 for i in range(0, 6, 2)]
            self.color_list[device]['state'] += 1
            # logging.debug(f"Assigning color: {device} {rgb} {color}")
        return rgb

    def reset_temp_color(self):
        for key in self.color_list:
            self.color_list[key]['state'] = 0

    def Image(self, image_name=None, width=None, height=None):
        if image_name is None:
            return Gtk.Image()
        pixbuf = self.PixbufFromIcon(image_name, width, height)
        return Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf is not None else Gtk.Image()
    
    def PixbufFromIcon(self, filename, width=None, height=None):
        width = width if width is not None else self.img_width
        height = height if height is not None else self.img_height
        filename = os.path.join(self.themedir, filename)
        for ext in ["svg", "png"]:
            pixbuf = self.PixbufFromFile(f"{filename}.{ext}", int(width), int(height))
            if pixbuf is not None:
                return pixbuf
        return None

    def update_image(self, image_object, image_name, width=None, height=None):
        filename = os.path.join(self.themedir, image_name)
        width = width if width is not None else self.img_width
        height = height if height is not None else self.img_height
        for ext in ["svg", "png"]:
            with contextlib.suppress(Exception):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(f"{filename}.{ext}", int(width), int(height))
                if pixbuf is not None:
                    image_object.set_from_pixbuf(pixbuf)
                else:
                    logging.warning(f"Unable to find image {filename}.{ext}")

    @staticmethod
    def PixbufFromFile(filename, width=-1, height=-1):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(filename, int(width), int(height))
        except Exception as e:
            logging.exception(e)
            logging.error(f"Unable to find image {filename}")
            return None

    def PixbufFromHttp(self, resource, width=-1, height=-1):
        response = self.screen.apiclient.get_thumbnail_stream(resource)
        if response is False:
            return None
        stream = Gio.MemoryInputStream.new_from_data(response, None)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, int(width), int(height), True)
        except Exception as e:
            logging.exception(e)
            return None
        stream.close_async(2)
        return pixbuf

    def Button(self, image_name=None, label=None, style=None, scale=None, position=Gtk.PositionType.TOP, lines=2, is_ellipsize=True,
               hexpand=True, vexpand=True):
        if self.font_size_type == "max" and label is not None and scale is None:
            image_name = None
        b = Gtk.Button(hexpand=hexpand, vexpand=vexpand, can_focus=False, image_position=position, always_show_image=True)
        if label is not None:
            b.set_label(label)
        if image_name is not None:
            if scale is None:
                scale = self.button_image_scale
            if label is None:
                scale = scale * 1.5
            width = height = self.img_scale * scale
            b.set_image(self.Image(image_name, width, height))
            spinner = Gtk.Spinner(width_request=width, height_request=height, no_show_all=True)
            spinner.hide()
            box = find_widget(b, Gtk.Box)
            if box:
                box.add(spinner)

        if label is not None:
            format_label(b, lines, is_ellipsize)
        if style is not None:
            b.get_style_context().add_class(style)
        b.connect("clicked", self.screen.reset_screensaver_timeout)
        return b
    
    @staticmethod
    def Button_busy(widget, busy):
        spinner = find_widget(widget, Gtk.Spinner)
        image = find_widget(widget, Gtk.Image)
        if busy:
            widget.set_sensitive(False)
            if image:
                widget.set_always_show_image(False)
                image.hide()
            if spinner:
                spinner.show()
                spinner.start()
        else:
            if image:
                widget.set_always_show_image(True)
                image.show()
            if spinner:
                spinner.hide()
                spinner.stop()
            widget.set_sensitive(True)

    def Dialog(self, buttons, content, title=None, callback=None, *args, width=None, height=None, style=None, resizable=False):
        dialog = Gtk.Dialog(modal=True, transient_for=self.screen)
        if title:
            dialog.set_title(title)
        if not width:
            if not height:
                dialog.set_size_request(self.screen.width, self.screen.height)
            else:
                dialog.set_size_request(self.screen.width, height)
        else:
            if height:
                dialog.set_size_request(width, height)
            else:
                dialog.set_size_request(width, self.screen.height)
        dialog.set_resizable(resizable)
        
        if buttons:
          for button in buttons:
              dialog.add_button(button['name'], button['response'])
              b = dialog.get_widget_for_response(button['response'])
              if "image_name" in button:
                  w = h = self.img_scale * self.button_image_scale
                  b.set_image(self.Image(button['image_name'], w, h))
                  b.set_image_position(Gtk.PositionType.TOP)
                  b.set_always_show_image(True)
              if "style" in button:
                  b.get_style_context().add_class(button['style'])
              if width and height:
                  if "width" and "height" in button:
                      b.set_size_request(button['width'], button['height'])
              else:
                  if len(buttons) > 2:
                      dialog.get_action_area().set_layout(Gtk.ButtonBoxStyle.EXPAND)
                      button_hsize = -1
                  else:
                      button_hsize = int((self.width / 3))
                  b.set_size_request(button_hsize - 30, round(self.height / 5))
              format_label(button, 3)
        else:
          if callback:
            dialog.connect("button-release-event", callback, *args)
        dialog.connect("response", self.screen.reset_screensaver_timeout)
        if callback:
          dialog.connect("response", callback, *args)
        if style is not None:
            for cl in style:   
                dialog.get_style_context().add_class(cl)

        content_area = dialog.get_content_area()
        content_area.set_margin_start(15)
        content_area.set_margin_end(15)
        content_area.set_margin_top(15)
        content_area.set_margin_bottom(15)        
        content.set_valign(Gtk.Align.CENTER)
        content_area.add(content)
        self.screen.base_panel.main_grid.set_opacity(0.2)
        self.screen.base_panel.main_grid.set_sensitive(False)
        dialog.show_all()
        # Change cursor to blank
        if self.cursor:
            dialog.get_window().set_cursor(
                Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.ARROW))
        else:
            dialog.get_window().set_cursor(
                Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))
        self.screen.dialogs.append(dialog)
        logging.info(f"Showing dialog {dialog}")
        return dialog

    def remove_dialog(self, dialog, *args):
        dialog.destroy()
        self.screen.base_panel.main_grid.set_opacity(1)
        self.screen.base_panel.main_grid.set_sensitive(True)
        if dialog in self.screen.dialogs:
            logging.info("Removing Dialog")
            self.screen.dialogs.remove(dialog)
            return
        logging.debug(f"Cannot remove dialog {dialog}")

    @staticmethod
    def HomogeneousGrid(width=None, height=None):
        g = Gtk.Grid()
        g.set_row_homogeneous(True)
        g.set_column_homogeneous(True)
        if width is not None and height is not None:
            g.set_size_request(width, height)
        return g

    def ScrolledWindow(self, steppers=True):
        scroll = Gtk.ScrolledWindow(vexpand=True, overlay_scrolling=False)
        scroll.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                          Gdk.EventMask.TOUCH_MASK |
                          Gdk.EventMask.BUTTON_RELEASE_MASK)
        scroll.set_kinetic_scrolling(True)
        if self.screen._config.get_main_config().getboolean("show_scroll_steppers", fallback=False) and steppers:
            scroll.get_vscrollbar().get_style_context().add_class("with-steppers")
        return scroll

    @staticmethod
    def VerticalNotebook(pages):
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.LEFT)
        notebook.set_show_border(True)
        for page in pages:
            page['content'].set_border_width(10)
            notebook.append_page(page['content'], Gtk.Label(label=page['label']))
        return notebook
    
            
        