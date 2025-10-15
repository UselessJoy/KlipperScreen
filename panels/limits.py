import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.limits = {}
        self.options = None
        self.values = {}
        self.grid = Gtk.Grid()

        conf = self._printer.get_config_section("printer")
        extruder = self._printer.get_stat("extruder")
        self.options = [
          {
            "name": _("Max Acceleration"),
            "option": "max_accel",
            "units": _("mm/s²"),
            "value": int(float(conf['max_accel'])),
            "max": int(float(conf['max_accel'])),
          },
          {
            "name": _("Max Velocity"),
            "option": "max_velocity",
            "units": _("mm/s"),
            "value": int(float(conf["max_velocity"])),
            "max": int(float(conf['max_velocity']))
          },
          {
            "name": _("Square Corner Velocity"),
            "option": "square_corner_velocity",
            "units": _("mm/s"),
            "value": int(float(conf['square_corner_velocity'])) if "square_corner_velocity" in conf else 5,
            "max": int(float(conf['square_corner_velocity'])) if "square_corner_velocity" in conf else 5
          },
          {
            "name": _("Minimum Cruise Ratio"),
            "option": "minimum_cruise_ratio",
            "units": "",
            "value": float(conf['minimum_cruise_ratio']) if "minimum_cruise_ratio" in conf else 0.5,
            "min": 0,
            "max": 0.99,
            "step": 0.05,
            "page": 0.05,
            "scale_factor": 100,
            "format": "{:.2f}"
          },
          {
            "name": _("Pressure Advance"),
            "option": "pressure_advance",
            "units": _("s"),
            "value": float(extruder['pressure_advance']) if "pressure_advance" in extruder else 0.03,
            "min": 0,
            "max": 2,
            "step": 0.01,
            "page": 0.05,
            "scale_factor": 1000,
            "format": "{:.3f}"
          },
          {
            "name": _("Smooth Time P. Advance"),
            "option": "pressure_smooth_time",
            "units": _("s"),
            "value": float(extruder['smooth_time']) if "smooth_time" in extruder else 0.04,
            "min": 0,
            "max": 0.2,
            "step": 0.001,
            "page": 0.01,
            "scale_factor": 10000,
            "format": "{:.4f}"
          }
        ]

        for opt in self.options:
            self.add_option(opt)

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.grid)
        self.content.add(scroll)
        self.content.show_all()

    def process_update(self, action, data):
        if action != "notify_status_update":
            return

        for opt in self.limits:
            if "toolhead" in data and opt in data["toolhead"]:
                self.update_option(opt, data["toolhead"][opt])

    def update_option(self, option, value):
        logging.info(f"{option} {value}")
        if option not in self.limits:
            logging.debug("not in self limits")
            return

        if self.limits[option]['scale'].has_grab():
            return
        
        # Сохраняем реальное значение
        self.values[option] = float(value)
        
        # Преобразуем для отображения в слайдере
        scale_factor = self.limits[option].get('scale_factor', 1)
        display_value = self.values[option] * scale_factor
        
        for opt_config in self.options:
            if opt_config["option"] == option and 'max' not in opt_config:
                if self.values[option] > opt_config["value"]:
                    self.limits[option]['scale'].get_style_context().add_class("option_slider_max")
                    self.limits[option]['adjustment'].set_upper(display_value * 1.5)
                else:
                    self.limits[option]['scale'].get_style_context().remove_class("option_slider_max")
                    self.limits[option]['adjustment'].set_upper(opt_config["value"] * scale_factor * 1.5)
        
        self.limits[option]['scale'].disconnect_by_func(self.set_opt_value)
        self.limits[option]['scale'].set_value(display_value)
        
        # Обновляем значение в label
        self.update_value_label(option, self.values[option])
        
        self.limits[option]['scale'].connect("button-release-event", self.set_opt_value, option)
        self.limits[option]['scale'].connect("value-changed", self.on_scale_value_changed, option)

    def update_value_label(self, option, real_value):
        """Обновляет label с реальным значением"""
        format_str = self.limits[option].get('format', "{:.0f}")
        value_str = format_str.format(real_value)
        self.limits[option]['value_label'].set_markup(f"<b>{value_str}</b> ")

    def on_scale_value_changed(self, scale, option):
        """Обработчик изменения значения слайдера в реальном времени"""
        scale_factor = self.limits[option].get('scale_factor', 1)
        display_value = scale.get_value()
        real_value = display_value / scale_factor
        
        # Обновляем label в реальном времени
        self.update_value_label(option, real_value)

    def add_option(self, option):
        logging.info(f"Adding option: {option['option']}")

        name = Gtk.Label()
        name.set_markup(f"<big><b>{option['name']}</b></big>")
        name.set_hexpand(True)
        name.set_vexpand(True)
        name.set_halign(Gtk.Align.START)
        name.set_valign(Gtk.Align.CENTER)
        name.set_line_wrap(True)
        name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

        # Вычисляем значения для слайдера
        scale_factor = option.get('scale_factor', 1)
        display_value = option['value'] * scale_factor
        min_display = option.get('min', 1) * scale_factor
        max_display = option.get('max', option['value'] * 1.5) * scale_factor
        step_display = option.get('step', 1) * scale_factor
        page_display = option.get('page', 5) * scale_factor

        adj = Gtk.Adjustment(display_value, min_display, max_display, step_display, page_display, 0)
        scale = Gtk.Scale(adjustment=adj, digits=0, hexpand=True, has_origin=True)
        scale.set_digits(0)
        scale.set_hexpand(True)
        scale.set_has_origin(True)
        scale.get_style_context().add_class("option_slider")
        
        # Отключаем встроенное отображение значения
        scale.set_draw_value(False)
        
        # Создаем отдельный label для отображения значения
        value_label = Gtk.Label()
        format_str = option.get('format', "{:.0f}")
        initial_value = format_str.format(option['value'])
        value_label.set_markup(f"<b>{initial_value}</b> ")
        # value_label.set_halign(Gtk.Align.END)
        # value_label.set_valign(Gtk.Align.CENTER)
        # value_label.set_hexpand(False)

        value_unit  = Gtk.Label()
        unit = option.get('units', '')
        value_unit.set_markup(f"<b>{unit}</b>")
        # value_unit.set_halign(Gtk.Align.END)
        # value_unit.set_valign(Gtk.Align.CENTER)
        # value_unit.set_hexpand(False)

        value_box = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        value_box.add(value_label)
        value_box.add(value_unit)
        scale.connect("button-release-event", self.set_opt_value, option['option'])
        scale.connect("value-changed", self.on_scale_value_changed, option['option'])
        
        self.values[option['option']] = float(option['value'])

        reset = self._gtk.Button("refresh", style="color1")
        reset.connect("clicked", self.reset_value, option['option'])
        reset.set_hexpand(False)

        # Создаем контейнер для слайдера и label значения
        slider_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        slider_container.pack_start(scale, True, True, 0)
        slider_container.pack_start(value_box, False, False, 0)

        item = Gtk.Grid()
        item.attach(name, 0, 0, 2, 1)
        item.attach(slider_container, 0, 1, 1, 1)
        item.attach(reset, 1, 1, 1, 1)

        self.limits[option['option']] = {
            "row": item,
            "scale": scale,
            "adjustment": adj,
            "value_label": value_label,
            "scale_factor": scale_factor,
            "format": format_str
        }

        # limits = sorted(self.limits)
        # pos = limits.index(option['option'])

        self.grid.insert_row(len(self.limits))
        self.grid.attach(self.limits[option['option']]['row'], 0, len(self.limits), 1, 1)
        self.grid.show_all()

    def reset_value(self, widget, option):
        for x in self.options:
            if x["option"] == option:
                self.update_option(option, x["value"])
                logging.debug(f"Reset {option} to {x['value']}")
        self.set_opt_value(None, None, option)

    def set_opt_value(self, widget, event, opt: str):
        # Получаем значение из слайдера и преобразуем обратно
        display_value = self.limits[opt]['scale'].get_value()
        scale_factor = self.limits[opt].get('scale_factor', 1)
        real_value = display_value / scale_factor
        
        # Сохраняем реальное значение
        self.values[opt] = real_value

        if opt == "max_accel":
            self._screen._ws.klippy.gcode_script(f"SET_VELOCITY_LIMIT ACCEL={int(real_value)}")
        elif opt == "minimum_cruise_ratio":
            self._screen._ws.klippy.gcode_script(f"SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO={real_value:.3f}")
        elif opt == "max_velocity":
            self._screen._ws.klippy.gcode_script(f"SET_VELOCITY_LIMIT VELOCITY={int(real_value)}")
        elif opt == "square_corner_velocity":
            self._screen._ws.klippy.gcode_script(f"SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY={int(real_value)}")
        elif opt == "pressure_advance":
            self._screen._ws.klippy.gcode_script(f"SET_PRESSURE_ADVANCE ADVANCE={real_value:.4f}")
        elif opt == "pressure_smooth_time":
            self._screen._ws.klippy.gcode_script(f"SET_PRESSURE_ADVANCE SMOOTH_TIME={real_value:.5f}")