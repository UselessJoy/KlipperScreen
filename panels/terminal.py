import gi
# from ks_includes.widgets.keyboard import Keyboard
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from pynput.keyboard import Key, Controller
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.vte_terminal import Terminal
COLORS = {
    "command": "#bad8ff",
    "error": "#ff6975",
    "response": "#b8b8b8",
    "time": "grey",
    "warning": "#c9c9c9"
}

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.dnd_list = [Gtk.TargetEntry.new("text/uri-list", 0, 80), Gtk.TargetEntry.new("text/plain", 0, 4294967293)]
        self.dnd_text = Gtk.TargetEntry.new("text/plain", 0, 4294967293)
        self.controller = Controller()
        self.terminal = Terminal()
        self.terminal.drag_dest_set(Gtk.DestDefaults.ALL, self.dnd_list, Gdk.DragAction.COPY)
        self.terminal.drag_dest_set_target_list(self.dnd_list)
        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        t_box.add(self.terminal)
        self.scrolled_win = Gtk.ScrolledWindow()
        self.scrolled_win.add(t_box)
        self.scrolled_win.set_min_content_height(screen.gtk.content_height * 0.6)
        self.terminal.grab_focus()
        self.content.add(self.scrolled_win)

    def activate(self):
      self.terminal.grab_focus()
      self.show_kb()

    def show_kb(self):
      self._screen.show_keyboard(entry=self.terminal, reject_function=self.pass_function, accept_function=self.virtual_enter, backspace_function=self.virtual_backspace)

    def pass_function(self):
      return

    def virtual_enter(self):
      self.terminal.grab_focus()
      self.controller.press(Key.enter)
    
    def virtual_backspace(self):
      self.terminal.grab_focus()
      self.controller.press(Key.backspace)