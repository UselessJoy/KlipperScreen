import gi
gi.require_version("Gtk", "3.0")
gi.require_version('Vte', '2.91')
from gi.repository import Vte, Gdk
from gi.repository import GLib
import os
class Terminal(Vte.Terminal):
    def __init__(self):
        super(Vte.Terminal, self).__init__()
        self.spawn_async(Vte.PtyFlags.DEFAULT, 
            os.path.expanduser("~"),
            ["/bin/bash"],
            None,
            GLib.SpawnFlags.DO_NOT_REAP_CHILD,
            None,
            None,
            -1,
            None,
            None
            )
        self.set_font_scale(0.9)
        self.set_scroll_on_output(True)
        self.set_scroll_on_keystroke(True)
        palette = [Gdk.RGBA(0.4, 0.8, 1.0, 1.0)] * 16
        self.set_colors(Gdk.RGBA(1.0, 1.0, 1.0, 1.0), Gdk.RGBA(0.2, 0.2, 0.2, 1.0), palette)
        self.set_color_highlight(Gdk.RGBA(0.3, 0.3, 0.9, 1.0))
        self.set_color_highlight_foreground(Gdk.RGBA(0.8, 0.8, 0.8, 1.0))
        self.connect("key_press_event", self.copy_or_paste)
        self.set_scrollback_lines(-1)
        self.set_audible_bell(0)

    def update_entry(self, key):
      if key != "⌫":
        self.feed_child(key.encode())

    def copy_or_paste(self, widget, event):
        control_key = Gdk.ModifierType.CONTROL_MASK
        shift_key = Gdk.ModifierType.SHIFT_MASK
        if event.type == Gdk.EventType.KEY_PRESS:
            if event.state == shift_key | control_key:
                if event.keyval == 67:
                    self.copy_clipboard_format(1)
                elif event.keyval == 86:
                    self.paste_clipboard()
                return True