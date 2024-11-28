import contextlib
import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.objectmap import ObjectMap

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self._screen = screen
        self.object_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self.boxes = {}
        self.current_object = self._gtk.Button("extrude", "", position=Gtk.PositionType.LEFT, lines=1, style="color3") # scale=self.bts,
        self.current_object.connect("clicked", self.exclude_current)
        self.current_object.set_vexpand(False)
        # self.current_object.set_hexpand(False)
        self.current_object.set_halign(Gtk.Align.CENTER)
        self.excluded_objects = self._printer.get_stat("exclude_object", "excluded_objects")
        logging.info(f'Excluded: {self.excluded_objects}')
        self.objects = self._printer.get_stat("exclude_object", "objects")
        self.labels['map'] = None
        for obj in self.objects:
            logging.info(f"Adding {obj['name']}")
            self.add_object(obj["name"])

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.object_list)

        box = Gtk.Box()
        box.add(self.current_object)
        grid = Gtk.Grid(column_homogeneous=True)
        grid.attach(box, 0, 0, 1, 1)
        grid.attach(Gtk.Separator(), 0, 1, 1, 1)

        if self.objects and "polygon" in self.objects[0]:
            self.labels['map'] = ObjectMap(self._screen, self._printer, self._gtk.font_size)
            if self._screen.vertical_mode:
                grid.attach(self.labels['map'], 0, 2, 2, 1)
                grid.attach(scroll, 0, 3, 2, 1)
            else:
                grid.attach(self.labels['map'], 0, 2, 1, 1)
                grid.attach(scroll, 1, 1, 1, 3)
        else:
            grid.attach(scroll, 0, 2, 2, 1)

        self.content.add(grid)
        self.content.show_all()

    def add_object(self, name):
        if name not in self.boxes and name not in self.excluded_objects:
            label = Gtk.Label(label = name.replace('_', ' '))
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_line_wrap(True)
            btn_show = self._gtk.Button(label=_("Mark"), style="color1")
            btn_show.connect("clicked", self.mark_object, name)
            btn_delete = self._gtk.Button(label=_("Delete"), style="color2")
            btn_delete.connect("clicked", self.exclude_object, name)
            button_grid = self._gtk.HomogeneousGrid()
            button_grid.attach(btn_show, 0, 0, 1, 1)
            button_grid.attach(btn_delete, 1, 0, 1, 1)
            self.boxes[name] = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
            self.boxes[name].add(label)
            self.boxes[name].add(button_grid)
            self.object_list.add(self.boxes[name])

    def mark_object(self, widget, name):
      self.labels['map'].mark_obj(name)
      if self.labels['map']:
            self.labels['map'].queue_draw()

    def exclude_object(self, widget, name):
        if len(self.excluded_objects) == len(self.objects) - 1:
            # Do not exclude the last object, this is a workaround for a bug of klipper that starts
            # to move the toolhead really fast skipping gcode until the file ends
            # Remove this if they fix it.
            self._screen._confirm_send_action(
                widget,
                _("Are you sure you wish to cancel this print?"),
                "printer.print.cancel",
            )
            return
        script = {"script": f"EXCLUDE_OBJECT NAME={name}"}
        self._screen._confirm_send_action(
            widget,
            _("Are you sure do you want to exclude the object?") + f"\n\n{name}",
            "printer.gcode.script",
            script
        )

    def exclude_current(self, widget):
        self.exclude_object(widget, f"{self.current_object.get_label().strip().replace(' ', '_')}")

    def process_update(self, action, data):
        if action == "notify_status_update":
            with contextlib.suppress(KeyError):
                # Update objects
                self.objects = data["exclude_object"]["objects"]
                logging.info(f'Objects: {data["exclude_object"]["objects"]}')
                for obj in self.boxes:
                    self.object_list.remove(self.boxes[obj])
                self.boxes = {}
                for obj in self.objects:
                    logging.info(f"Adding {obj['name']}")
                    self.add_object(obj["name"])
                self.content.show_all()
            with contextlib.suppress(KeyError):
                # Update current objects
                if data["exclude_object"]["current_object"]:
                    self.current_object.set_label(f'{data["exclude_object"]["current_object"].replace("_", " ")}')
                self.update_graph()
            with contextlib.suppress(KeyError):
                # Update excluded objects
                logging.info(f'Excluded objects: {data["exclude_object"]["excluded_objects"]}')
                self.excluded_objects = data["exclude_object"]["excluded_objects"]
                for name in self.excluded_objects:
                    if name in self.boxes:
                        self.object_list.remove(self.boxes[name])
                self.update_graph()
                if len(self.excluded_objects) == len(self.objects):
                    self._screen._menu_go_back()
        elif action == "notify_gcode_response" and "Excluding object" in data:
            self._screen.show_popup_message(data, level=1)
            self.update_graph()

    def activate(self):
        self.update_graph()

    def update_graph(self):
        if self.labels['map']:
            self.labels['map'].queue_draw()
