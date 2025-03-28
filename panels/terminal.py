import gi
from ks_includes.widgets.keyboard import Keyboard
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from pynput.keyboard import Key, Controller
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.vte_terminal import Terminal

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.dnd_list = [Gtk.TargetEntry.new("text/uri-list", 0, 80), Gtk.TargetEntry.new("text/plain", 0, 4294967293)]
        self.dnd_text = Gtk.TargetEntry.new("text/plain", 0, 4294967293)
        self.controller = Controller()
        self.terminal = Terminal()
        self.terminal.drag_dest_set(Gtk.DestDefaults.ALL, self.dnd_list, Gdk.DragAction.COPY)
        self.terminal.drag_dest_set_target_list(self.dnd_list)
        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True, spacing=10)
        terminal_scroll = Gtk.ScrolledWindow()
        terminal_scroll.set_min_content_height(screen.gtk.content_height * 0.5)
        terminal_scroll.add(self.terminal)
        t_box.add(terminal_scroll)
        self.keyboard = Keyboard(screen, self.pass_function, self.virtual_enter, self.terminal, self.virtual_backspace, False, False)
        self.keyboard.get_style_context().remove_class("keyboard")
        self.keyboard.set_hexpand(True)
        t_box.add(self.keyboard)
        self.overlayBox = None
        self.terminal.grab_focus()
        self.overlay = Gtk.Overlay()
        self.overlay.add_overlay(t_box)
        self.overlay.add_overlay(self.InfoButton())
        self.content.add(self.overlay)

    def pass_function(self):
      return

    def InfoButton(self):
      info_button = self._gtk.Button("info", style="round_button", scale=0.7)
      info_button.connect("clicked", self.show_loaded_mesh)
      info_button.set_halign(Gtk.Align.END)
      info_button.set_valign(Gtk.Align.START)
      info_button.set_vexpand(False)
      return info_button

    def show_loaded_mesh(self, widget):
        self.overlayBox = Gtk.Box()
        close_profiles_button = self._gtk.Button("back_overlay", scale=self.bts, position=Gtk.PositionType.RIGHT)
        close_profiles_button.set_vexpand(False)
        close_profiles_button.set_hexpand(True)
        close_profiles_button.set_alignment(1., 0.)
        close_profiles_button.get_style_context().add_class("overlay_close_button")
        close_profiles_button.connect("clicked", self.close_loaded_mesh)
        self.overlayBox.pack_start(close_profiles_button, False, True, 0)
        self.scroll = self._gtk.ScrolledWindow()
        command_buttons = []
        for lbl in ["sudo systemctl restart [service]", "./kiauh/kiauh.sh", "journalctl -eu [service]"]:
          b = self._gtk.Button(None, "", scale=self.bts, position=Gtk.PositionType.RIGHT, vexpand=False, hexpand=False, style="shadow")
          b.set_valign(Gtk.Align.START)
          for child in b:
            if isinstance(child, Gtk.Label):
              child.set_markup(f"<i>{lbl}</i>")
              child.set_ellipsize(False)
              break
          b.connect("clicked", self.command_clicked, lbl)
          command_buttons.append(b)

        helper_box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        header_label = Gtk.Label()
        header_label.set_markup("<big><b>Внимание! Меню консоли рассчитано на пользователей, владеющими навыками работы с командной строкой</b></big>.\n\n"
                         "Пароль для использования команд sudo - <big><b>orangepi</b></big>.\n\n")
        header_label.set_line_wrap(True)
        header_label.set_valign(Gtk.Align.START)
        helper_box.add(header_label)

        commands_label = Gtk.Label("Список полезных команд:\n\n")
        commands_label.set_line_wrap(True)
        commands_label.set_valign(Gtk.Align.START)
        helper_box.add(commands_label)

        com_lbl = [
          " - команда перезагрузки сервиса. Может быть полезна, если "
          "сервис по какой-либо причине не перезагружается стандартным методом. Список используемых сервисов "
          "для работы принтера: moonraker, KlipperScreen, klipper, crowsnest.\n\n",
          " - скрипт для установки/удаления сервисов принтера. Необходим, если по какой-либо причине "
          "необходимо переустановить определенный сервис. Также можно установить иные сервисы, однако мы не гарантируем "
          "их полную работоспособность.\n\n",
          " - команда просмотра логов сервиса. Некоторые ошибки могут не записаться в исходный "
          "файл лога, поэтому данная команда может дать дополнительную информацию об ошибке.\n\n",
        ]
        command_grid = Gtk.Grid(row_homogeneous = True)
        for i, b in enumerate(command_buttons):
          command_grid.attach(b, 0, i, 1, 1)
          l = Gtk.Label(com_lbl[i])
          l.set_line_wrap(True)
          l.set_valign(Gtk.Align.START)
          command_grid.attach(l, 1, i, 1, 1)

        helper_box.add(command_grid)

        self.scroll.add(helper_box)
        self.scroll.set_vexpand(False)
        self.scroll.set_hexpand(True)
        self.scroll.set_halign(Gtk.Align.FILL)
        self.scroll.set_min_content_width(self._gtk.content_width / 1.2)
        self.scroll.get_style_context().add_class("overlay_background")
        self.overlayBox.pack_start(self.scroll, True, True, 0)
        self.overlayBox.set_vexpand(False)
        self.overlayBox.set_hexpand(True)
        self.overlayBox.show_all()
        for child in self.overlay:
            child.set_opacity(0.2)
            child.set_sensitive(False)
        self.overlay.add_overlay(self.overlayBox)
        self.scroll.show_all()

    def close_loaded_mesh(self, widget=None):
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

    def command_clicked(self, widget, msg):
      self.close_loaded_mesh()
      self.terminal.grab_focus()
      self.terminal.feed_child(msg.encode())

    def activate(self):
      self.terminal.grab_focus()

    def virtual_enter(self):
      self.terminal.grab_focus()
      self.controller.press(Key.enter)
      self.controller.release(Key.enter)

    def virtual_backspace(self):
      self.terminal.grab_focus()
      self.controller.press(Key.backspace)
      self.controller.release(Key.backspace)