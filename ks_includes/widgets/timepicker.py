import gi
import logging
import subprocess
from datetime import datetime
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Timepicker(Gtk.Box):
    def __init__(self, screen, change_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._screen = screen
        self.change_cb = change_cb
        now = datetime.now()
        hours = int(f'{now:%H}')
        minutes = int(f'{now:%M}')
        adjustmentH = Gtk.Adjustment(upper=23, step_increment=1, page_increment=1)
        adjustmentM = Gtk.Adjustment(upper=59, step_increment=1, page_increment=1)
        self.spin_hours = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_hours.connect("value-changed", self.change_value, 'hours')
        self.spin_hours.set_size_request(screen.width / 5, screen.height / 4)
        self.spin_hours.set_adjustment(adjustmentH)
        self.spin_hours.set_numeric(True)
        self.spin_hours.set_value(hours)
        self.spin_minutes = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        self.spin_minutes.connect("value-changed", self.change_value, 'minutes')
        self.spin_minutes.set_size_request(screen.width / 5, screen.height / 4)
        self.spin_minutes.set_adjustment(adjustmentM)
        self.spin_minutes.set_numeric(True)
        self.spin_minutes.set_value(minutes)
        
        
        switchbox = Gtk.Box()
        switchbox.set_hexpand(True)
        switchbox.set_vexpand(True)
        switchbox.set_valign(Gtk.Align.END)
        switchbox.set_halign(Gtk.Align.START)
        self.switch_button_ntp = Gtk.Switch()

    
        switchbox.pack_start(Gtk.Label(label=_("Synchronize time")), False, False, 5)
        switchbox.pack_end(self.switch_button_ntp, False, False, 5)
        
        #box.pack_start(switchbox, False, True, 5)
        grid = Gtk.Grid()
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "ntp.service"])
        self.switch_button_ntp.set_active(True if stat == 0 else False)
        label = {
            'title': Gtk.Label(label=_("Set new time")),
            'separator': Gtk.Label(label=":")}
        grid.attach(label['title'], 0, 0, 3, 1)
        grid.attach(self.spin_hours, 0, 1, 1, 1)
        grid.attach(label['separator'], 1, 1, 1, 1)
        grid.attach(self.spin_minutes, 2, 1, 1, 1)
        
        self.pack_start(grid, True, True, 15)
        self.pack_end(switchbox, True, True, 15)
        
        
        
    def change_value(self, spinbutton, name):
        logging.info(f'name is {name} value is {spinbutton.get_value()}')
        value = int(spinbutton.get_value())
        self.change_cb(name, value)
        
        
    
    
    
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        # self.listbox = Gtk.ListBox()
        # self.adjust = Gtk.Adjustment()
        # self.adjust.connect("changed", self.changed)
        # # # # listbox.get_style_context().add_class('listbox')
        # self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        # self.listbox.connect("row-selected", self.row_selected)
        # # self.connect("changed", self.changed)
        # self.labels = []
        # for i in range(35):
        #     self.labels.append(Gtk.Label(label=f"{i}"))
        #     self.listbox.insert(self.labels[i], -1)
        #     logging.info(f"added label {i}")
        #     # if(i == 0):
        #     #     grid.attach(self.labels[i], 0,0,1,1)
        #     # else:
        # #     #     grid.attach_next_to(self.labels[i], self.labels[i-1], Gtk.PositionType.BOTTOM, 1, 1)
        # self.selected_index = 0
        # try:
        #     self.selected_index = self.listbox.get_selected_row().get_index()
        # except:
        #     self.selected_index = 4
            
        # self.add(self.listbox)
        # grid = Gtk.Grid()
        # grid.attach(Gtk.Label(label="hello from time modal"), 0,0,3,1)
        # grid.attach(self.spin_hours, 0, 1, 1, 1)
        # grid.attach(Gtk.Label(label=" : "), 1, 1, 1, 1)
        # grid.attach(self.spin_minutes, 2, 1, 1, 1)
        
        
    # def row_selected(self, listbox, listboxrow):
    #     self.selected_index = listboxrow.get_index()
        
    #     for row in self.listbox:
    #         if row.get_index() - self.selected_index not in [0, 1]:
    #             logging.info(row.get_index())
    #     # self.listbox.insert(Gtk.Label(label="Hellloo"), -1)
    #     # self.show_all()
    #     # logging.info(listboxrow.get_index())

    
    # def changed(self, widget, args):
    #     logging.info("shanhed on scroll")