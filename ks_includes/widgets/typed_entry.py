import logging
import os
import re
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GObject



class BaseRule:
    @staticmethod
    def is_valid(entry, key):
        return True
    

class InterfaceRule(BaseRule):
    @staticmethod
    def value_between_points(entry) -> str:
        text: str = entry.get_text()
        position: int = entry.get_position()
        left_point_index: int = -1
        right_point_index: int = -1
        text_left = text_right = ""
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
        return value
        
    
    @staticmethod
    def is_valid(entry, key):
        text = entry.get_text()
        value = InterfaceRule.value_between_points(entry)

        if re.match(r"[0-9]", key):
            # left_point_position = position - (left_point_index+1 if left_point_index != -1 else 0)
            result_value = value + key
            # value_char_array = [char for char in value]
            # value_char_array.insert(left_point_position, key)
            # result_value = ''.join(char for char in value_char_array)
            return True if int(result_value) < 256 else False
        elif key == '.':
            if text.count('.') >= 3:
                return False
            return True
        elif key == "⌫":
            return True
        return False
        
        

        
class NetmaskRule(BaseRule):
    @staticmethod
    def is_valid(entry, key):
        text = entry.get_text()
        position = entry.get_position()
        value = text[1:len(text)]
        if re.match(r"[0-9]", key):
            value_char_array = [char for char in value]
            value_char_array.insert(position, key)
            result_value = ''.join(char for char in value_char_array)
            return True if len(value) < 3 and int(result_value) < 33 else False
        elif key == "⌫":
            return True if text[position - 1] != '/' else False
        return False

class NumberRule(BaseRule):
    @staticmethod
    def is_valid(entry, key:str):
        if key == "⌫":
          return True
        if key == '0' and not entry.get_text():
            return False
        if entry.max:
          return ( re.match(r"[0-9]", key) and (int(entry.get_text() + key) < int(entry.max)))
        return re.match(r"[0-9]", key)

class SpaceRule(BaseRule):
    @staticmethod
    def is_valid(entry, key:str):
        if key == " ":
          return False
        return True


    
class TypedEntry(Gtk.Entry):
    def __init__(self, entry_type="base", update_callback=None, max=None):
        super().__init__()
        rules = {
            "base": BaseRule,
            "interface": InterfaceRule,
            "netmask": NetmaskRule,
            "number": NumberRule,
            "no_space": SpaceRule
        }
        self.update_callback = update_callback
        self.max = max
        ruleClass = BaseRule
        if entry_type not in rules:
            ruleClass = BaseRule
            logging.error(f"Invalid rule: {entry_type}, using BaseClass")
        else:
            ruleClass = rules.get(entry_type)
        self.rule = ruleClass
        # self.connect("delete-from-cursor", self.on_delete_text)
        # self.connect("cut-clipboard", self.on_cut_text)
        # self.connect("paste-clipboard", self.on_paste_text)
        
    
    # def on_paste_text(self, entry):
    #     logging.info("on paste")
    #     return False
    
    # def on_cut_text(self, entry):
    #     logging.info("on cut")
    #     return False
    
    # def on_delete_text(self, entry, type, count, user_data):
    #     logging.info("on delete")
    def automatic_insert(self, key):
        self.do_insert_at_cursor(self, key)
        self.set_position(self.get_position()+1)
    
    
    def check_rules(self, key):
      return self.rule.is_valid(self, key)
        
    def update_entry(self, key):
        if self.check_rules(key):
            if key == "⌫":
                self.do_backspace(self)
            else:
                self.do_insert_at_cursor(self, key)
                if hasattr(self.rule, "value_between_points"):
                    value = self.rule.value_between_points(self)
                    logging.info(value)
                    if len(value) == 3 and self.get_text().count('.') < 3:
                        self.automatic_insert('.')
            if self.update_callback:
                self.update_callback(self)
                
                    