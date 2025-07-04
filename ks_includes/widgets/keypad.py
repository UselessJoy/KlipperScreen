import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class Keypad(Gtk.Box):
    def __init__(self, screen, change_temp, pid_calibrate, close_function):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.labels = {}
        self.change_temp = change_temp
        self.pid_calibrate = pid_calibrate
        self.screen = screen
        self._gtk = screen.gtk

        numpad = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        numpad.set_direction(Gtk.TextDirection.LTR)
        numpad.get_style_context().add_class('numpad')

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
          ['✔', 'numpad_bleft'],
          ['0', 'numpad_bottom'],
          ['⌫', 'numpad_bright']
        ]
        for i in range(len(keys)):
            k_id = f'button_{str(keys[i][0])}'
            if keys[i][0] == "⌫":
                self.labels[k_id] = self._gtk.Button("backspace", scale=1)
            elif keys[i][0] == "✔":
                self.labels[k_id] = self._gtk.Button("complete", scale=1)
            else:
                self.labels[k_id] = Gtk.Button(label=keys[i][0])
                self.labels[k_id].get_style_context().add_class("numpad_chars")
            self.labels[k_id].connect('clicked', self.update_entry, keys[i][0])
            self.labels[k_id].set_can_focus(False)
            self.labels[k_id].get_style_context().add_class(keys[i][1])
            # self.labels[k_id].get_style_context().add_class("numpad_key")
            numpad.attach(self.labels[k_id], i % 3, i / 3, 1, 1)

        self.labels["keypad"] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.labels['entry'] = Gtk.Entry()
        self.labels['entry'].props.xalign = 0.5
        self.labels['entry'].connect("activate", self.update_entry, "✔")

        self.pid = self._gtk.Button('heat-up', _('Calibrate') + ' PID', None, .66, Gtk.PositionType.LEFT, 1)
        self.pid.connect("clicked", self.update_entry, "PID")
        self.pid.set_sensitive(True)
        # self.pid.set_sensitive(False)
        self.pid.set_no_show_all(True)
        b = self._gtk.Button('cancel', _('Close'), None, .66, Gtk.PositionType.LEFT, 1)
        b.connect("clicked", close_function)

        self.add(self.labels['entry'])
        self.add(numpad)
        self.bottom = Gtk.Box()
        self.bottom.add(self.pid)
        self.bottom.add(b)
        self.add(self.bottom)

        self.labels["keypad"] = numpad
        
    def show_pid(self, can_pid):
        self.pid.set_visible(can_pid)

    def clear(self):
        self.labels['entry'].set_text("")

    def set_active(self, active):
        if active:
            self.pid.get_style_context().add_class("button_active")
        else:
            self.pid.get_style_context().remove_class("button_active")
            
    
    def update_entry(self, widget, digit):
        text = self.labels['entry'].get_text()
        temp = self.validate_temp(text)
        if digit == '⌫':
            if len(text) < 1:
                return
            self.labels['entry'].set_text(text[:-1])
        elif digit == '✔':
            self.change_temp(temp)
            self.labels['entry'].set_text("")
        elif digit == 'PID':
            if self.pid.get_style_context().has_class("button_active"):
                self.set_active(False)
                self.pid_calibrate(temp, False)
            else:
                self.set_active(True)
                self.pid_calibrate(temp, True)
            self.labels['entry'].set_text("")
        elif len(text + digit) > 3:
            return
        else:
            self.labels['entry'].set_text(text + digit)
        self.pid.set_sensitive(True)
        
    @staticmethod
    def validate_temp(temp):
        try:
            return int(temp)
        except ValueError:
            return 0
