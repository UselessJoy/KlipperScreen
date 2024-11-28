import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GObject


class Numpad(Gtk.Box):
    def __init__(self, screen, accept_cb=None, entry=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.labels = {}
        self.screen = screen
        self._gtk = screen.gtk
        self.accept_cb = accept_cb
        self.entry = entry
        numpad = self._gtk.HomogeneousGrid()
        numpad.set_direction(Gtk.TextDirection.LTR)
        self.timeout = self.clear_timeout = None
        keys = [
          ['1', 'numpad_tleft'],
          ['2', 'numpad_top'],
          ['3', 'numpad_tright'],
          ['4', 'numpad_left'],
          ['5', 'numpad_button'],
          ['6', 'numpad_right'],
          ['7', 'numpad_left'],
          ['8', 'numpad_button'],
          ['9', 'numpad_right'],
          ['.', 'numpad_left'],
          ['0', 'numpad_button'],
          ['⌫', 'numpad_right'],
          ['✔', 'numpad_bottom']
        ]
        
        for i in range(len(keys)):
            k_id = f'button_{str(keys[i][0])}'
            if keys[i][0] == "⌫":
                self.labels[k_id] = self._gtk.Button("backspace", scale=.6)
            elif keys[i][0] == "✔":
                self.labels[k_id] = self._gtk.Button("complete", scale=.6)
            elif keys[i][0] == "✕":
                self.labels[k_id] = screen.gtk.Button("cancel", scale=.6)
                
            else:
                self.labels[k_id] = Gtk.Button(label=keys[i][0])
            self.labels[k_id].connect('clicked', self.update_entry, keys[i][0])
            self.labels[k_id].set_can_focus(False)
            self.labels[k_id].get_style_context().add_class(keys[i][1])
            if keys[i][0] == "✔":
                numpad.attach(self.labels[k_id], 1, 4, 1, 1)
            else:
                numpad.attach(self.labels[k_id], i % 3, i / 3, 1, 1)

        self.labels["keypad"] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.add(numpad)
        numpad.set_margin_start(5)
        numpad.set_margin_end(32)
        numpad.set_margin_bottom(5)
        self.labels["keypad"] = numpad
    
    def repeat(self, widget, event, key):
        # Button-press
        self.update_entry(widget, key)
        if self.timeout is None and key == "⌫":
            # Hold for repeat, hold longer to clear the field
            #self.clear_timeout = GLib.timeout_add_seconds(3, self.clear, widget)
            # This can be used to repeat all the keys,
            # but I don't find it useful on the console
            self.timeout = GLib.timeout_add(500, self.repeat, widget, None, key)
        return True

    def release(self, widget, event):
        # Button-release
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        if self.clear_timeout is not None:
            GLib.source_remove(self.clear_timeout)
            self.clear_timeout = None
    
    def change_entry(self, entry, event=None):
        self.entry = entry
               
    def update_entry(self, widget, key):
        if key == "✔":
          if self.accept_cb:
            self.accept_cb()
          else:
            self.get_parent().remove(self)
        else:
            self.entry.update_entry(key)
