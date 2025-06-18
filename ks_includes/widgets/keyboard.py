import logging
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

PALLETE_KEYWORDS = ["⇮", "⇧", "!#1", "ABC", "ru", "RU" , "1/2", "2/2", "en" , "EN"]

class Keyboard(Gtk.Box):
    langs = ["de", "en", "fr", "es"]
    def __init__(self, screen, reject_cb = None, accept_cb = None, entry = None, backspace_cb = None, rej_cb_destroy = True, acc_cb_destroy = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class("keyboard")
        self.reject_cb = reject_cb
        self.accept_cb = accept_cb
        # Флаги устанавливают, подразумевается ли удаление клавы в коллбэках или нет
        # Необходимо, чтобы при закрытии освобождался ресурс таймера и можно было повторно открыть клавиатуру
        self.rej_cb_destroy = rej_cb_destroy
        self.acc_cb_destroy = acc_cb_destroy
        self.backspace_cb = backspace_cb
        self.pressing = False
        self.keyboard = screen.gtk.HomogeneousGrid()
        self.keyboard.set_direction(Gtk.TextDirection.LTR)
        self.timeout = self.clear_timeout = None
        self.entry = entry
        self.lang = 'en'
        self.isLowerCase = True
        # language = self.detect_language(screen._config.get_main_config().get("language", None))
        # logging.info(f"Keyboard {language}")
        self.keys = [
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
            ["⇮", "a", "s", "d", "f", "g", "h", "j", "k", "l"],
            ["!#1", "ru", "z", "x", "c", "v", "b", "n", "m", "⌫"],
          ],
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["⇧","A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["!#1", "RU", "Z", "X", "C", "V", "B", "N", "M", "⌫"],
          ],
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["+", "-", "*", "/", "=", "_", "{", "}", "[", "]"],
            ["1/2", "!", "@", "#", "$", "%", "^", "&", "(", ")"],
            ["ABC", "'", "\"", ":", ";", ".", ",", "?", "⌫"],
          ],
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["`", "~", "\\", "|", "<", ">", "€", "£", "¥", "฿"],
            ["2/2", "÷", "×", "○", "●", "□", "■", "—", "≈", "√"],
            ["ABC", "≤", "≥", "≪", "≫", "Ⅰ", "Ⅴ", "Ⅹ", "⌫"],
          ],
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["й", "ц", "у", "к", "е", "н", "г", "ш", "щ", "з", "х", "ъ"],
            ["⇮", "ф", "ы", "в", "а", "п", "р", "о", "л", "д", "ж", "э"],
            ["!#1", "en", "я", "ч", "с", "м", "и", "т", "ь", "б", "ю", "⌫"],
          ],
          [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["Й", "Ц", "У", "К", "Е", "Н", "Г", "Ш", "Щ", "З", "Х", "Ъ"],
            ["⇧", "Ф", "Ы", "В", "А", "П", "Р", "О", "Л", "Д", "Ж", "Э"],
            ["!#1", "EN", "Я", "Ч", "С", "М", "И", "Т", "Ь", "Б", "Ю", "⌫"],
          ]
        ]

        for pallet in self.keys:
            pallet.append(["✕", ".", " ", "/", "✔"])

        self.buttons = self.keys.copy()
        for p, pallet in enumerate(self.keys):
            for r, row in enumerate(pallet):
                for k, key in enumerate(row):
                    if key == "⌫":
                        self.buttons[p][r][k] = screen.gtk.Button("backspace", scale=.6)
                    elif key == "✕":
                        self.buttons[p][r][k] = screen.gtk.Button("cancel", scale=.6)
                    elif key == "✔":
                         self.buttons[p][r][k] = screen.gtk.Button("complete", scale=.6)
                    else:
                        self.buttons[p][r][k] = screen.gtk.Button(label=key, lines=1)
                    self.buttons[p][r][k].set_hexpand(True)
                    self.buttons[p][r][k].set_vexpand(True)
                    self.buttons[p][r][k].set_can_focus(False)
                    if key in PALLETE_KEYWORDS and key != "⌫":
                      self.buttons[p][r][k].connect('clicked', self.change_pallete, key)
                    else:
                      self.buttons[p][r][k].connect('button-press-event', self.press, key)
                      self.buttons[p][r][k].connect('button-release-event', self.release)
                    self.buttons[p][r][k].get_style_context().add_class("keyboard_pad")

        self.pallet_nr = 0
        self.set_pallet(self.pallet_nr)
        self.add(self.keyboard)
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, *args):
      if self.timeout:
        GLib.source_remove(self.timeout)

    def detect_language(self, language):
        if language is None or language == "system_lang":
            for language in self.langs:
                if os.getenv('LANG').lower().startswith(language):
                    return language
        for _ in self.langs:
            if language.startswith(_):
                return _
        return "en"

    def set_pallet(self, p):
        for _ in range(len(self.keys[self.pallet_nr]) + 1):
            self.keyboard.remove_row(0)
        self.pallet_nr = p
        for r, row in enumerate(self.keys[p][:-1]):
            for k, key in enumerate(row):
                if p == 4 or p == 5:
                    x = k * 6 if r == 0 else k * 5
                    if r == 0:
                        self.keyboard.attach(self.buttons[p][r][k], x, r, 6, 1)
                    else:
                        self.keyboard.attach(self.buttons[p][r][k], x, r, 5, 1)
                elif p == 2 or p == 3:
                    x = k * 2 + 1 if r == 3 else k * 2
                    self.keyboard.attach(self.buttons[p][r][k], x, r, 2, 1)
                else:
                    x = k * 2
                    self.keyboard.attach(self.buttons[p][r][k], x, r, 2, 1)
        if p == 4 or p == 5:
            self.keyboard.attach(self.buttons[p][4][0], 0, 4, 10, 1)  # ✕
            self.keyboard.attach(self.buttons[p][4][1], 10, 4, 5, 1)  # .
            self.keyboard.attach(self.buttons[p][4][2], 15, 4, 30, 1)  # Space
            self.keyboard.attach(self.buttons[p][4][3], 45, 4, 5, 1)  # /
            self.keyboard.attach(self.buttons[p][4][4], 50, 4, 10, 1)  # ✔
        else:
            self.keyboard.attach(self.buttons[p][4][0], 0, 4, 4, 1)  # ✕
            self.keyboard.attach(self.buttons[p][4][1], 4, 4, 2, 1)  # .
            self.keyboard.attach(self.buttons[p][4][2], 6, 4, 8, 1)  # Space
            self.keyboard.attach(self.buttons[p][4][3], 14, 4, 2, 1)  # /
            self.keyboard.attach(self.buttons[p][4][4], 16, 4, 4, 1)  # ✔
        self.show_all()

    def press(self, widget, event, key):
      if self.timeout:
        GLib.source_remove(self.timeout)
        self.timeout = None
      if self.pressing:
        return
      self.pressing = True
      widget.get_style_context().add_class("active")
      if key == "⌫"and self.backspace_cb:
          self.backspace_cb()
          if not self.timeout:
            self.timeout = GLib.timeout_add(300, self.on_wait, widget, key)
      self.update_entry(widget, key)
      if not self.timeout:
        self.timeout = GLib.timeout_add(300, self.on_wait, widget, key)

    def on_wait(self, widget, key):
      if self.pressing:
        if self.timeout:
          GLib.source_remove(self.timeout)
        self.timeout = GLib.timeout_add(40, self.repeat, widget, key)

    def repeat(self, widget, key):
      if not self.pressing:
        if self.timeout:
          GLib.source_remove(self.timeout)
          self.timeout = None
        return False
      if key == "⌫" and self.backspace_cb:
        self.backspace_cb()
        return True
      return self.update_entry(widget, key)

    def release(self, widget, event):
        # Button-release
        self.pressing = False
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        if self.clear_timeout is not None:
            GLib.source_remove(self.clear_timeout)
            self.clear_timeout = None
        widget.get_style_context().remove_class("active")

    def clear(self, widget=None):
        self.entry.set_text("")
        if self.clear_timeout is not None:
            GLib.source_remove(self.clear_timeout)
            self.clear_timeout = None

    def change_entry(self, entry, event=None):
        self.entry = entry

    def change_pallete(self, widget, key):
      if key == "⇧":
            self.isLowerCase = True
            if self.lang == 'en':
                self.set_pallet(0)
            else:
                self.set_pallet(4)
      elif key == "ABC":
          if self.lang == 'en':
              if self.isLowerCase:
                  self.set_pallet(0)
              else:
                  self.set_pallet(1)
          else:
              if self.isLowerCase:
                  self.set_pallet(4)
              else:
                  self.set_pallet(5)
      elif key == "⇮":
          self.isLowerCase = False
          if self.lang == 'en':
              self.set_pallet(1)
          else:
              self.set_pallet(5)
      elif key == "!#1" or key == "2/2":
          self.set_pallet(2)
      elif key == "1/2":
          self.set_pallet(3)
      elif key == 'ru':
          self.lang = 'ru'
          self.set_pallet(4)
      elif key == 'RU':
          self.lang = 'ru'
          self.set_pallet(5)
      elif key == 'en':
          self.lang = 'en'
          self.set_pallet(0)
      elif key == 'EN':
          self.lang = 'en'
          self.set_pallet(1)
               
    def update_entry(self, widget, key):
        if not self.pressing:
          return False
        if key == "✔":
            if self.accept_cb:
              self.accept_cb()
            else:
              self.get_parent().remove(self)
            return not self.acc_cb_destroy
        elif key == "✕":
            if self.reject_cb:
              self.reject_cb()
            else:
              self.get_parent().remove(self)
            return not self.rej_cb_destroy
          

        else:
            self.entry.update_entry(key)
            return True