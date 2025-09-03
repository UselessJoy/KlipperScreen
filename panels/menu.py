import logging
import gi
import json
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from jinja2 import Template
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.autogrid import AutoGrid

class Panel(ScreenPanel):
    def __init__(self, screen, title, items=None):
        super().__init__(screen, title)
        self.items = items
        self.j2_data = self._printer.get_printer_status_data()
        self.create_menu_items()
        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.autogrid = AutoGrid()

    def activate(self):
        self.j2_data = self._printer.get_printer_status_data()
        self.add_content()
    
    def add_content(self):
        for child in self.scroll.get_children():
            self.scroll.remove(child)
        self.scroll.add(self.arrangeMenuItems(self.items))
        if not self.content.get_children():
            self.content.add(self.scroll)

    def arrangeMenuItems(self, items, columns=None, expand_last=False):
        self.autogrid.clear()
        enabled = []
        for item in items:
            key = list(item)[0]
            if not self.evaluate_enable(item[key]['enable']):
                logging.debug(f"Not enabled > {key}")
                continue
            if not self.evaluate_sensitive(item[key]['sensitive']):
                logging.debug(f"Not sensitive > {key}")
                self.labels[key].set_sensitive(False)
            else:
                self.labels[key].set_sensitive(True)
            enabled.append(self.labels[key])
        self.autogrid.__init__(enabled, columns, expand_last, self._screen.vertical_mode)
        return self.autogrid

    def create_menu_items(self):
        enable_items = [item for item in self.items] #if bool(self.evaluate_enable(item[next(iter(item))]['enable']))]
        count = len(enable_items)
        divider = 3 if count <= 8 else 4
        scale = 1.1 if 12 < count <= 16 else None  # hack to fit a 4th row
        for i in range(len(enable_items)):
            key = list(enable_items[i])[0]
            item = enable_items[i][key]
            name = self._screen.env.from_string(item['name']).render(self.j2_data)
            icon = self._screen.env.from_string(item['icon']).render(self.j2_data) if item['icon'] else None
            style = self._screen.env.from_string(item['style']).render(self.j2_data) if item['style'] else None

            b = self._gtk.Button(icon, name, style or f"color{i % divider + 1}", scale=scale)
            logging.info(name + " " + f"color{i % divider + 1}")

            if item['panel']:
                b.connect("clicked", self.menu_item_clicked, item)
            elif item['method']:
                params = {}

                if item['params'] is not False:
                    try:
                        p = self._screen.env.from_string(item['params']).render(self.j2_data)
                        params = json.loads(p)
                    except Exception as e:
                        logging.exception(f"Unable to parse parameters for [{name}]:\n{e}")
                        params = {}

                if item['confirm']:
                    b.connect("clicked", self._screen._confirm_send_action, item['confirm'], item['method'], params)
                else:
                    b.connect("clicked", self._screen._send_action, item['method'], params)
            else:
                b.connect("clicked", self._screen._go_to_submenu, key)
            self.labels[key] = b
    
    def evaluate_sensitive(self, sensitive):
        if sensitive == "{{ has_homing_origin }}":
            try:
              has_homing_origin = self._screen.apiclient.send_request("printer/objects/query?gcode_move")['result']['status']['gcode_move']['homing_origin'][2] != .0
              logging.info(f"has_homing_origin: {has_homing_origin}")
              return has_homing_origin
            except Exception as e:
                logging.debug(f"Error evaluating sensitive statement: {sensitive}\n{e}")
                return False
        try:
            j2_temp = Template(sensitive, autoescape=True)
            return j2_temp.render(self.j2_data) == 'True'
        except Exception as e:
            logging.debug(f"Error evaluating sensitive statement: {sensitive}\n{e}")
            return False

    def evaluate_enable(self, enable):
        if enable == "{{ moonraker_connected }}":
            logging.info(f"moonraker connected {self._screen._ws.connected}")
            return self._screen._ws.connected
        elif enable == "{{ has_homing_origin }}":
            try:
                has_homing_origin = self._screen.apiclient.send_request("printer/objects/query?gcode_move")['result']['status']['gcode_move']['homing_origin'][2] != .0
                logging.info(f"has_homing_origin: {has_homing_origin}")
                return has_homing_origin
            except Exception as e:
                logging.debug(f"Error evaluating enable statement: {enable}\n{e}")
                return False
        try:
            j2_temp = Template(enable, autoescape=True)
            return j2_temp.render(self.j2_data) == 'True'
        except Exception as e:
            logging.debug(f"Error evaluating enable statement: {enable}\n{e}")
            return False
