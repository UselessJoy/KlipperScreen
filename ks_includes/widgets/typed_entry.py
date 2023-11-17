import logging
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GObject



class BaseRule:
    @staticmethod
    def is_valid(entry, key):
        return True
    

class InterfaceRule(BaseRule):
    @staticmethod
    def is_valid(entry, key):
        text = entry.get_text()
        position = entry.get_position()
        left_point_index = -1
        right_point_index = -1
        try: 
            left_point_index = text.rindex('.', 0, position)
        except:
            text_left = text[0:position]
        try: 
            right_point_index = text.index('.', position, len(text))
        except:
            text_right = text[position:len(text)]
            
        if left_point_index != -1:
            text_left = text[left_point_index+1:position]
        if right_point_index != -1:
            text_right = text[position:right_point_index]
        value = text_left + text_right
        if key in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            position = position - (left_point_index+1 if left_point_index != -1 else 0)
            value_char_array = [char for char in value]
            value_char_array.insert(position, key)
            result_value = ''.join(char for char in value_char_array)
            return True if len(value) < 4 and int(result_value) < 256 else False
        elif key == "⌫":
            return True if text[position-1] != '.' else False
        return False

        
class NetmaskRule(BaseRule):
    @staticmethod
    def is_valid(entry, key):
        text = entry.get_text()
        position = entry.get_position()
        if position == 0:
            entry.set_position(1)
        value = text[1:len(text)]
        if key in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            position = position - 1
            value_char_array = [char for char in value]
            value_char_array.insert(position, key)
            result_value = ''.join(char for char in value_char_array)
            return True if len(value) < 3 and int(result_value) < 33 else False
        elif key == "⌫":
            return True if text[position - 1] != '/' else False
        return False
    
class TypedEntry(Gtk.Entry):
    def __init__(self, entry_type="base"):
        super().__init__()
        rules = {
            "base": BaseRule,
            "interface": InterfaceRule,
            "netmask": NetmaskRule
        }
        ruleClass = BaseRule
        if entry_type not in rules:
            ruleClass = BaseRule
            raise logging.error(f"Invalid rule: {entry_type}, using BaseClass")
        else:
            ruleClass = rules.get(entry_type)
        self.rule = ruleClass
        
    
    def check_rules(self, key):
        return self.rule.is_valid(self, key)
        
    def update_entry(self, key):
        if self.check_rules(key):
            if key == "⌫":
                Gtk.Entry.do_backspace(self)
            else:
                Gtk.Entry.do_insert_at_cursor(self, key)