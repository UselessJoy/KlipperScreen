import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject
import math
import cairo

class ColorPicker(Gtk.Box):
    def __init__(self, with_palette = True):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        self.color_wheel = ColorWheel()
        self.color_palette = None
        if with_palette:
          self.color_palette = ColorPalette(self)
          self.pack_start(self.color_palette, False, False, 0)
        # Вертикальный контейнер для ползунка яркости
        brightness_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        # Ползунок яркости
        self.brightness_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.VERTICAL,
            0, 1, 0.01
        )
        self.brightness_scale.set_inverted(True)  # 0 внизу, 1 вверху
        self.brightness_scale.set_value(1.0)  # начальное значение - максимальная яркость
        self.brightness_scale.set_draw_value(False)  # не показывать значения
        self.brightness_scale.set_size_request(30, 200)
        self.brightness_scale.get_style_context().add_class("media")
        self.brightness_scale.get_style_context().add_class("vertical")
        self.brightness_scale.connect("value-changed", self.on_brightness_changed)
        
        # Метки для ползунка
        label_100 = Gtk.Label(label="100%", margin_bottom = 14)
        label_0 = Gtk.Label(label="0%", margin_top = 14)
        brightness_box.pack_start(label_100, False, False, 0)
        brightness_box.pack_start(self.brightness_scale, True, True, 0)
        brightness_box.pack_start(label_0, False, False, 0)

        self.pack_start(self.color_wheel, True, True, 0)
        self.pack_start(brightness_box, False, False, 0)
        
    def on_brightness_changed(self, scale):
        # Обновление яркости в цветовом круге
        brightness = scale.get_value()
        self.color_wheel.set_brightness(brightness)
    
    def set_rgb(self, r, g, b):
      self.color_wheel.set_rgb(r, g, b)
      # Обновление значений ползунка яркости
      _, _, v = self.color_wheel.get_hsv()
      self.brightness_scale.set_value(v)

class ColorPalette(Gtk.Box):
    def __init__(self, color_picker: ColorPicker):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.color_picker = color_picker

        grid = Gtk.Grid(vexpand=True, valign=Gtk.Align.CENTER)
        grid.set_row_spacing(12)
        grid.set_column_spacing(12)
        # self.rgb_label = Gtk.Label(label = f"color = {self.color_picker.color_wheel.get_current_rgb()}", width_chars=21)
        
        
        colors = [
            (254,180,180), # Красный светлый
            (255, 242, 179), # Желтый светлый
            (180,254,200), # Зеленый светлый

            (179,255,255), # Белый
            (179, 192, 255), # Голубой светлый
            (213,179,255), # Синий светлый

            (255,179,233), # Бледно-лазурный
            (255,255,255), # еще зеленый
            (255, 0, 0),      # Красный
            
            (255, 165, 0),    # Оранжевый
            (255, 255, 0),    # Желтый
            (0, 255, 0),      # Зеленый

            (0, 167, 255),   # Голубой
            (0, 0, 255),      # Синий
            (158, 0, 255),    # Фиолетовый
        ]

        for i, color in enumerate(colors):
            r, g, b = color
            button = Gtk.Button()
            button.get_style_context().add_class("color_button")
            button.set_size_request(48, 48)
            button.set_tooltip_text(f"RGB: {r}, {g}, {b}")

            rgba = Gdk.RGBA(r/255.0, g/255.0, b/255.0, 1.0)
            button.override_background_color(Gtk.StateFlags.NORMAL, rgba)

            button.connect("clicked", self.on_palette_color_clicked, (r, g, b))

            row = i // 3
            col = i % 3
            grid.attach(button, col, row, 1, 1)
        self.pack_start(grid, False, False, 0)
        # self.pack_end(self.rgb_label, False, False, 0)

    def on_palette_color_clicked(self, button, color):
        r, g, b = color
        self.color_picker.set_rgb(r/255.0, g/255.0, b/255.0)

class ColorWheel(Gtk.DrawingArea):
    __gsignals__ = {
        'color-changed': (GObject.SIGNAL_RUN_FIRST, None,
                      (GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT))
    }
    def __init__(self):
        super().__init__()
        self.set_size_request(300, 300)
        
        # Обработчики событий мыши
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.BUTTON_MOTION_MASK |
            Gdk.EventMask.TOUCH_MASK
        )
        
        self.radius = 0
        self.center_x = 0
        self.center_y = 0
        self.hue = 0.0       # Тон (0-360)
        self.saturation = 1.0  # Насыщенность (0-1)
        self.brightness = 1.0  # Яркость (0-1)
        self.inner_radius_ratio = 0.3
        self.outer_fade_ratio = 0.9
        self.marker_radius = 8  # Размер индикатора выбранного цвета
        self.is_dragging = False  # Флаг перетаскивания
        self.cached_wheel = None  # Кэш для цветового круга

        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("motion-notify-event", self.on_motion_notify)
        self.connect("size-allocate", self.on_size_allocate)
    
    def on_size_allocate(self, widget, allocation):
        # При изменении размера сбрасывается кэш
        self.cached_wheel = None
        self.queue_draw()
    
    def on_draw(self, widget, cr):
        allocation = self.get_allocation()
        width = allocation.width
        height = allocation.height
        
        # Вычисление центра и радиуса
        self.radius = min(width, height) * 0.45
        self.center_x = width / 2
        self.center_y = height / 2
        
        # Рисование цветового круга с плавными переходами
        if self.cached_wheel is None or self.cached_wheel.get_width() != width or self.cached_wheel.get_height() != height:
            # Создание кэша цветового круга
            self.cached_wheel = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            cache_cr = cairo.Context(self.cached_wheel)
            
            # Рисуется цветовой круг в кэш
            for angle in range(0, 360, 1):
                cache_cr.save()
                
                # Основной цвет для угла
                r, g, b = self.hsv_to_rgb(angle, 1.0, 1.0)
                
                # Создание радиального градиента для плавных переходов
                pattern = cairo.RadialGradient(
                    self.center_x, self.center_y, 0,
                    self.center_x, self.center_y, self.radius
                )
                
                # Центр: плавный переход к белому
                pattern.add_color_stop_rgb(0, 1.0, 1.0, 1.0)
                pattern.add_color_stop_rgb(1, r, g, b)
                
                # Край: плавный переход к черному
                # pattern.add_color_stop_rgb(1.0, r, g, b)
                
                cache_cr.set_source(pattern)
                
                # Создание конусообразного сегмента
                cache_cr.move_to(self.center_x, self.center_y)
                cache_cr.arc(self.center_x, self.center_y, self.radius, 
                           math.radians(angle - 1.2), math.radians(angle + 1.2))  # Увеличиваем перекрытие
                cache_cr.close_path()
                cache_cr.fill()
                cache_cr.restore()
        
        # Копируем кэшированный круг на экран
        cr.set_source_surface(self.cached_wheel, 0, 0)
        cr.paint()
        
        # Применяем яркость поверх всего круга
        if self.brightness < 1.0:
            cr.save()
            cr.arc(self.center_x, self.center_y, self.radius + 1, 0, 2 * math.pi)
            cr.clip()
            
            # Более плавное затемнение - квадратичная функция
            # alpha = (1 - self.brightness) ** 2
            # cr.set_source_rgba(0, 0, 0, alpha)
            cr.paint()
            cr.restore()
        
        # Рисуем индикатор выбранного цвета
        self.draw_marker(cr)
        
        return True

    def draw_marker(self, cr):
        # Вычисляем позицию маркера на основе текущего тона и насыщенности
        angle_rad = math.radians(self.hue)
        distance = min(self.saturation, 1.0) * self.radius  # Ограничиваем расстояние
        
        marker_x = self.center_x + distance * math.cos(angle_rad)
        marker_y = self.center_y + distance * math.sin(angle_rad)
        
        # Рисуем внешнее кольцо (черное или белое в зависимости от яркости)
        cr.arc(marker_x, marker_y, self.marker_radius + 2, 0, 2 * math.pi)
        if self.brightness > 0.4:
            cr.set_source_rgb(0, 0, 0)
        else:
            cr.set_source_rgb(1, 1, 1)
        cr.fill()
        
        # Рисуем внутренний круг с текущим цветом
        cr.arc(marker_x, marker_y, self.marker_radius, 0, 2 * math.pi)
        r, g, b = self.get_current_rgb()
        cr.set_source_rgb(r, g, b)
        cr.fill()

    def on_button_press(self, widget, event):
        if event.button == 1:
            self.is_dragging = True
            self.update_color_from_position(event.x, event.y)
        return True

    def on_button_release(self, widget, event):
        if event.button == 1:
            self.is_dragging = False
        return True

    def on_motion_notify(self, widget, event):
        if self.is_dragging:
            self.update_color_from_position(event.x, event.y)
        return True

    def update_color_from_position(self, x, y):
        dx = x - self.center_x
        dy = y - self.center_y
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Ограничиваем расстояние радиусом круга
        max_radius = self.radius
        normalized_distance = min(1.0, distance / max_radius)
        
        # Вычисляем угол
        angle = math.degrees(math.atan2(dy, dx)) % 360
        
        # Обновляем только тон и насыщенность
        self.hue = angle
        self.saturation = normalized_distance
        
        # Обновляем только индикатор (не перерисовываем весь круг)
        self.queue_draw()
        
        # Отправляем сигнал с текущим цветом (с учетом яркости)
        self.emit_color_changed()
    
    def set_brightness(self, brightness):
        self.brightness = brightness
        # При изменении яркости нужно перерисовать весь круг
        self.queue_draw()
        self.emit_color_changed()
    
    def set_current_color(self, r, g, b):
        self.emit("color-changed", r, g, b)

    def emit_color_changed(self):
        r, g, b = self.get_current_rgb()
        self.emit("color-changed", r, g, b)
    
    def get_current_rgb(self):
        return self.hsv_to_rgb(self.hue, self.saturation, 1 - (1 - self.brightness) ** 2)
    
    def get_hsv(self):
        return self.hue, self.saturation, 1 - (1 - self.brightness) ** 2

    def set_rgb(self, r, g, b):
      h, s, v = self.rgb_to_hsv(r, g, b)
      # Обновление значений
      self.hue = h
      self.saturation = s
      self.brightness = v
      # Перерисовка
      self.queue_draw()
      # Сигнал об изменении цвета
      self.emit_color_changed()

    @staticmethod
    def hsv_to_rgb(h, s, v):
        h = h / 60.0
        i = int(h)
        f = h - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))
        
        if i == 0: r, g, b = v, t, p
        elif i == 1: r, g, b = q, v, p
        elif i == 2: r, g, b = p, v, t
        elif i == 3: r, g, b = p, q, v
        elif i == 4: r, g, b = t, p, v
        else: r, g, b = v, p, q
        
        return r, g, b
    
    @staticmethod
    def rgb_to_hsv(r, g, b):
      max_val = max(r, g, b)
      min_val = min(r, g, b)
      delta = max_val - min_val
      
      # Вычисление Hue (тон)
      if delta == 0:
          h = 0
      elif max_val == r:
          h = 60 * (((g - b) / delta) % 6)
      elif max_val == g:
          h = 60 * (((b - r) / delta) + 2)
      else:  # max_val == b
          h = 60 * (((r - g) / delta) + 4)
      
      # Нормализация тона в диапазон 0-360
      h = h % 360
      if h < 0:
          h += 360
      
      # Saturation (насыщенность)
      s = delta / max_val if max_val > 0 else 0
      
      # Value (яркость)
      v = max_val
      
      return h, s, v