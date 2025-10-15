import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class DistGrid(Gtk.Grid):
    def __init__(self, screen, distances = ['.1', '.5', '1', '5', '10', '25', '50'], on_change_callback=None):
        super().__init__()
        if len(distances) < 2:
            logging.error("Len of distances list must be more than 2")
            distances = ['.1', '.5', '1', '5', '10', '25', '50']
        self.distance = distances[-2]
        self.distances = distances

        self.on_change_callback = on_change_callback

        self.dist_buttons = {}
        for j, i in enumerate(self.distances):
            self.dist_buttons[i] = screen.gtk.Button(label=i)
            self.dist_buttons[i].set_direction(Gtk.TextDirection.LTR)
            self.dist_buttons[i].connect("clicked", self.change_distance, i)
            ctx = self.dist_buttons[i].get_style_context()
            if (screen.lang_ltr and j == 0) or (not screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_top")
            elif (not screen.lang_ltr and j == 0) or (screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.distance:
                ctx.add_class("distbutton_active")
            self.attach(self.dist_buttons[i], j, 0, 1, 1)
    
    def get_distance(self):
        return self.distance

    def change_distance(self, widget, distance):
        self.dist_buttons[f"{self.distance}"].get_style_context().remove_class("distbutton_active")
        self.dist_buttons[f"{distance}"].get_style_context().add_class("distbutton_active")
        self.distance = distance
        if self.on_change_callback:
            self.on_change_callback(self.distance)