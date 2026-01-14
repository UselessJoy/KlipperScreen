import traceback
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import cairo
import numpy as np
import math
import time
import logging

class FastBedMap(Gtk.DrawingArea):
    """
    Ультра-быстрый bed map рендерер
    Фиксированная сетка, простейшая проекция, минимум вычислений
    """
    
    def __init__(self, width=400, height=400):
        super().__init__()
        
        # Размеры
        self.width = width
        self.height = height
        self.set_size_request(width, height)
        self.z_min = -0.25
        self.z_max = 0.25
        # Центр виджета (центр экрана)
        self.widget_center_x = width // 2
        self.widget_center_y = height // 2

        # Вид (фиксированная изометрия для скорости)
        self.angle = 45
        self.elevation = 30
        self.scale = 80

        # Центр вращения (будет установлен в auto_center_view)
        self.rotation_center = (0, 0, 0)

        # Параметры для скорости
        self.GRID_SIZE = 16  # Фиксированный размер! 16x16 = 144 вершины
        self.QUALITY = 1     # 1=треугольники, 2=с подразделением (используем 1)
        
        # Данные
        self.heights = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)
        self.colors = np.zeros((self.GRID_SIZE, self.GRID_SIZE, 3), dtype=np.float32)
        self.visible = False
        
        # Кэш проекций (ОЧЕНЬ важно!)
        self.proj_cache = None
        self.cache_valid = False
        
        # FPS контроль
        self.last_draw = 0
        self.fps = 0
        self.frame_count = 0
        self.target_fps = 15
        
        # Состояние
        self.dragging = False
        self.last_x = 0
        self.last_y = 0
        
        # Цвета (как в Pseudo3D)
        self.bg_color = (0.41, 0.41, 0.41)  # Серый фон как в Pseudo3D
        self.text_color = (0.9, 0.9, 0.9)   # Светлый текст
        self.grid_color = (0.7, 0.7, 0.7, 0.6)  # Полупрозрачная сетка
        self.axes_colors = [
            (1.0, 0.0, 0.0),  # X - красный
            (0.0, 1.0, 0.0),  # Y - зеленый
            (0.0, 0.0, 1.0)   # Z - синий
        ]
        self.plane_color = (0.5, 0.5, 0.5, 0.3)  # Полупрозрачная плоскость
        
        # Флаги отображения
        self.show_grid = True
        self.show_axes = True
        self.show_info = True
        self.show_plane = True  # Показать плоскость
        
        # Параметры системы координат
        self.bed_size = 1.0
        self.axis_length = self.bed_size  # Длина осей X и Y
        self.z_height = 4.0     # УВЕЛИЧЕНА высота оси Z (было 1.0)
        
        # Начало координат (левый нижний угол)
        self.origin = (-self.z_height / 2, -self.z_height / 2, self.z_height / 2)
        
        # Мультитач состояние
        self.touch_state = {
            'active': False,
            'start_distance': 0,
            'start_scale': self.scale,
            'touch1': None,
            'touch2': None
        }
        
        # Словарь для отслеживания точек касания
        self._touch_points = {}

        # Подключение
        self.connect("draw", self.on_draw)
        # Подключаем обработчик изменения размера
        self.connect("size-allocate", self.on_size_allocate)
        
        # Настраиваем события
        self.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.SCROLL_MASK |
            Gdk.EventMask.SMOOTH_SCROLL_MASK |  # Для плавной прокрутки
            Gdk.EventMask.TOUCH_MASK            # Для touch событий
        )
        
        # Подключаем обработчики
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("motion-notify-event", self.on_motion_notify)
        self.connect("scroll-event", self.on_scroll)
        self.connect("touch-event", self.on_touch_event)
        
        # Предварительные вычисления для скорости
        self.precompute_grid_coords()
        
        # Инициализация осей
        self.init_axes()
        
        logging.info(f"FastBedMap initialized: {self.GRID_SIZE}x{self.GRID_SIZE}")

    def on_size_allocate(self, widget, allocation):
        """Обработчик изменения размера виджета"""
        new_width = allocation.width
        new_height = allocation.height
        
        if new_width != self.width or new_height != self.height:
            self.width = new_width
            self.height = new_height
            self.widget_center_x = new_width // 2
            self.widget_center_y = new_height // 2
            self.cache_valid = False
            self.queue_draw()

    def init_axes(self):
        """Инициализация данных осей координат"""
        # Оси координат (начинаются от начала координат)
        self.axes = [
            # X ось (красная) - вдоль нижнего края
            # {
            #     'start': (self.origin[0], self.origin[1], 0),
            #     'end': (self.origin[0] + self.axis_length, self.origin[1], 0),#self.origin[2]),
            #     'color': self.axes_colors[0],
            #     'label': 'X'
            # },
            # # Y ось (зеленая) - вдоль левого края
            # {
            #     'start': (self.origin[0], self.origin[1] + self.axis_length, 0),
            #     'end': (self.origin[0], self.origin[1], 0),#self.origin[2]),
            #     'color': self.axes_colors[1],
            #     'label': 'Y',
            #     'arrow_direction': 'down'
            # },
            # Z ось (синяя) - вертикально от начала координат ВВЕРХ
            {
                'start': self.origin,
                'end': (self.origin[0], self.origin[1], self.z_height),  # Используем увеличенную высоту
                'color': self.axes_colors[2],
                'label': 'Z',
                'arrow_direction': 'up'  # Направление стрелки вверх
            },
            # Z ось (синяя) - вертикально от начала координат ВНИЗ
            {
                'start': self.origin,
                'end': (self.origin[0], self.origin[1], 0),  # Ось Z вниз (до полупрозрачной сетки)
                'color': self.axes_colors[2],
                'label': '-Z',
                'arrow_direction': 'down'  # Направление стрелки вниз
            }
        ]
    
    def on_touch_event(self, widget, event):
        """Обработка мультитач жестов (pinch-to-zoom и pan)"""
        event_type = event.type
        
        if event_type == Gdk.EventType.TOUCH_BEGIN:
            # Начало касания
            sequence = event.sequence
            
            # Сохраняем точку касания
            self._touch_points[sequence] = (event.x, event.y, time.time())
            
            # Проверяем количество активных касаний
            active_touches = len(self._touch_points)
            
            if active_touches == 1:
                # Одно касание - начало pan жеста (перетаскивание)
                self.dragging = True
                self.last_x = event.x
                self.last_y = event.y
                return True
                
            elif active_touches == 2:
                # Два касания - начало pinch жеста (масштабирование)
                self.touch_state['active'] = True
                
                # Получаем координаты двух точек
                points = list(self._touch_points.values())
                self.touch_state['touch1'] = (points[0][0], points[0][1])
                self.touch_state['touch2'] = (points[1][0], points[1][1])
                
                # Вычисляем начальное расстояние между пальцами
                dx = self.touch_state['touch2'][0] - self.touch_state['touch1'][0]
                dy = self.touch_state['touch2'][1] - self.touch_state['touch1'][1]
                self.touch_state['start_distance'] = math.sqrt(dx*dx + dy*dy)
                self.touch_state['start_scale'] = self.scale
                
                # Отключаем dragging при pinch жесте
                self.dragging = False
                return True
            
            return True
                
        elif event_type == Gdk.EventType.TOUCH_UPDATE:
            sequence = event.sequence
            
            if sequence in self._touch_points:
                # Обновляем позицию точки
                self._touch_points[sequence] = (event.x, event.y, time.time())
                
                # Проверяем количество активных касаний
                active_touches = len(self._touch_points)
                
                if active_touches == 2 and self.touch_state['active']:
                    # Pinch жест (масштабирование двумя пальцами)
                    points = list(self._touch_points.values())
                    touch1 = (points[0][0], points[0][1])
                    touch2 = (points[1][0], points[1][1])
                    
                    # Вычисляем текущее расстояние между пальцами
                    dx = touch2[0] - touch1[0]
                    dy = touch2[1] - touch1[1]
                    current_distance = math.sqrt(dx*dx + dy*dy)
                    
                    if self.touch_state['start_distance'] > 0 and current_distance > 0:
                        # Вычисляем коэффициент масштабирования
                        scale_factor = current_distance / self.touch_state['start_distance']
                        
                        # Применяем масштабирование с плавностью
                        new_scale = self.touch_state['start_scale'] * scale_factor
                        
                        # Ограничиваем масштаб
                        self.scale = max(30, min(300, new_scale))
                        
                        # Инвалидируем кэш
                        self.cache_valid = False
                        self.queue_draw()
                    
                    return True
                    
                elif active_touches == 1 and self.dragging:
                    # Pan жест (перетаскивание одним пальцем)
                    dx = event.x - self.last_x
                    dy = event.y - self.last_y
                    
                    # Вращение - инвертируем горизонталь
                    self.angle -= dx * 0.5
                    self.elevation += dy * 0.5
                    
                    # Ограничения углов
                    self.angle = self.angle % 360
                    self.elevation = max(10, min(80, self.elevation))
                    
                    # Инвалидируем кэш
                    self.cache_valid = False
                    
                    self.last_x = event.x
                    self.last_y = event.y
                    
                    self.queue_draw()
                    return True
            
            return True
                
        elif event_type == Gdk.EventType.TOUCH_END or event_type == Gdk.EventType.TOUCH_CANCEL:
            sequence = event.sequence
            
            if sequence in self._touch_points:
                # Удаляем точку касания
                del self._touch_points[sequence]
                
                # Проверяем количество оставшихся касаний
                remaining_touches = len(self._touch_points)
                
                if remaining_touches == 0:
                    # Все касания завершены - сбрасываем состояние
                    self.dragging = False
                    self.touch_state['active'] = False
                    self.touch_state['touch1'] = None
                    self.touch_state['touch2'] = None
                    self.touch_state['start_distance'] = 0
                    
                elif remaining_touches == 1 and self.touch_state['active']:
                    # Был pinch жест, осталось одно касание - переключаемся на pan
                    self.touch_state['active'] = False
                    self.touch_state['touch1'] = None
                    self.touch_state['touch2'] = None
                    self.touch_state['start_distance'] = 0
                    
                    # Активируем dragging для оставшегося касания
                    self.dragging = True
                    points = list(self._touch_points.values())
                    self.last_x = points[0][0]
                    self.last_y = points[0][1]
                
                return True
        
        return False

    def precompute_grid_coords(self):
        """Предварительное вычисление координат сетки (делается 1 раз!)"""
        self.grid_x = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)
        self.grid_y = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)
        
        for i in range(self.GRID_SIZE):
            for j in range(self.GRID_SIZE):
                # Координаты относительно начала координат
                self.grid_x[i, j] = self.origin[0] + (j / (self.GRID_SIZE - 1)) * self.bed_size
                self.grid_y[i, j] = self.origin[1] + (i / (self.GRID_SIZE - 1)) * self.bed_size
    
    def project_3d_to_2d(self, x, y, z):
        """Проекция 3D точки в 2D (изометрическая) с центром вращения в середине плоскости"""
        # Смещаем координаты относительно центра вращения
        x_centered = x - self.rotation_center[0]
        y_centered = y - self.rotation_center[1]
        z_centered = z - self.rotation_center[2]
        
        angle_rad = math.radians(self.angle)
        elev_rad = math.radians(self.elevation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        sin_e = math.sin(elev_rad)
        
        # Изометрическая проекция смещенных координат
        # И центрируем в середине виджета
        screen_x = (x_centered * cos_a - y_centered * sin_a) * self.scale + self.widget_center_x
        screen_y = (x_centered * sin_a + y_centered * cos_a) * sin_e * self.scale - z_centered * self.scale * 0.3 + self.widget_center_y
        
        return screen_x, screen_y
    
    def draw_coordinate_grids(self, cr):
        """Рисование координатных сеток на всех плоскостях"""
        if not self.show_grid:
            return
        
        cr.set_line_width(0.5)
        
        # Сетка на плоскости XY (Z=0)
        if len(self.grid_color) == 4:
            cr.set_source_rgba(*self.grid_color)
        else:
            cr.set_source_rgb(*self.grid_color)
        
        # Сетка XY (горизонтальная плоскость на Z=0)
        grid_steps = 8
        step_size = self.bed_size / (grid_steps - 1)
        
        for i in range(grid_steps):
            # Линии параллельные X (горизонтальные)
            y = self.origin[1] + i * step_size
            x_start = self.origin[0]
            x_end = self.origin[0] + self.bed_size
            z_level = 0  # Z=0
            
            sx, sy = self.project_3d_to_2d(x_start, y, z_level)
            ex, ey = self.project_3d_to_2d(x_end, y, z_level)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
            
            # Линии параллельные Y (вертикальные на плоскости XY)
            x = self.origin[0] + i * step_size
            y_start = self.origin[1]
            y_end = self.origin[1] + self.bed_size
            
            sx, sy = self.project_3d_to_2d(x, y_start, z_level)
            ex, ey = self.project_3d_to_2d(x, y_end, z_level)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
        
        # Более светлый цвет для вертикальных плоскостей
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.4)
        
        # Сетка на плоскости XZ (вертикальная плоскость по X, на Y = origin[1])
        y_fixed = self.origin[1]  # Фиксированная Y для плоскости XZ
        z_steps = 8  # Увеличили количество шагов по Z
        
        for i in range(z_steps):
            # Горизонтальные линии на разных уровнях Z
            z = (i / (z_steps - 1)) * self.z_height
            x_start = self.origin[0]
            x_end = self.origin[0] + self.bed_size
            
            sx, sy = self.project_3d_to_2d(x_start, y_fixed, z)
            ex, ey = self.project_3d_to_2d(x_end, y_fixed, z)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
        
        for i in range(grid_steps):
            # Вертикальные линии на разных позициях X
            x = self.origin[0] + i * step_size
            z_start = 0
            z_end = self.z_height
            
            sx, sy = self.project_3d_to_2d(x, y_fixed, z_start)
            ex, ey = self.project_3d_to_2d(x, y_fixed, z_end)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
        
        # Сетка на плоскости YZ (вертикальная плоскость по Y, на X = origin[0])
        x_fixed = self.origin[0]  # Фиксированная X для плоскости YZ
        
        for i in range(z_steps):
            # Горизонтальные линии на разных уровнях Z
            z = (i / (z_steps - 1)) * self.z_height
            y_start = self.origin[1]
            y_end = self.origin[1] + self.bed_size
            
            sx, sy = self.project_3d_to_2d(x_fixed, y_start, z)
            ex, ey = self.project_3d_to_2d(x_fixed, y_end, z)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
        
        for i in range(grid_steps):
            # Вертикальные линии на разных позициях Y
            y = self.origin[1] + i * step_size
            z_start = 0
            z_end = self.z_height
            
            sx, sy = self.project_3d_to_2d(x_fixed, y, z_start)
            ex, ey = self.project_3d_to_2d(x_fixed, y, z_end)
            
            cr.move_to(sx, sy)
            cr.line_to(ex, ey)
            cr.stroke()
    
    def draw_axes(self, cr):
        """Рисование осей координат"""
        if not self.show_axes:
            return
        
        cr.set_line_width(2.0)
        
        for axis in self.axes:
            # Проекция точек оси
            start_x, start_y = self.project_3d_to_2d(*axis['start'])
            end_x, end_y = self.project_3d_to_2d(*axis['end'])
            
            # Рисуем линию оси
            cr.set_source_rgb(*axis['color'])
            cr.move_to(start_x, start_y)
            cr.line_to(end_x, end_y)
            cr.stroke()
            
            # Рисуем стрелку только если ось достаточно длинная
            arrow_length = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
            if arrow_length > 5:
                self.draw_arrow(cr, (end_x, end_y), (start_x, start_y), axis['color'])
            
            # Подпись оси - по центру оси со смещением
            cr.set_source_rgb(*axis['color'])
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, 
                              cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(12)
            
            # Вычисляем середину оси
            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            
            # Смещение для подписи
            label_offset = 20
            
            # Для каждой оси своя логика смещения относительно направления
            # if axis['label'] == 'X':
            #     # Для оси X - смещение перпендикулярно вниз
            #     dx = end_x - start_x
            #     dy = end_y - start_y
            #     length = math.sqrt(dx*dx + dy*dy)
                
            #     if length > 0:
            #         # Перпендикулярный вектор (повернутый на 90 градусов)
            #         perp_dx = -dy / length
            #         perp_dy = dx / length
                    
            #         # Смещаем перпендикулярно вниз от центра
            #         label_x = mid_x - perp_dx * label_offset
            #         label_y = mid_y - perp_dy * label_offset
                    
            #         # Выравниваем текст
            #         extents = cr.text_extents('X')
            #         cr.move_to(label_x - extents.width/2, label_y + extents.height/2)
            #         cr.show_text('X')
            
            # elif axis['label'] == 'Y':
            #     # Для оси Y - смещение перпендикулярно влево
            #     dx = end_x - start_x
            #     dy = end_y - start_y
            #     length = math.sqrt(dx*dx + dy*dy)
                
            #     if length > 0:
            #         # Перпендикулярный вектор (повернутый на 90 градусов)
            #         perp_dx = -dy / length
            #         perp_dy = dx / length
                    
            #         # Смещаем перпендикулярно влево от центра
            #         label_x = mid_x - perp_dx * label_offset
            #         label_y = mid_y - perp_dy * label_offset
                    
            #         # Выравниваем текст
            #         extents = cr.text_extents('Y')
            #         cr.move_to(label_x - extents.width/2, label_y + extents.height/2)
            #         cr.show_text('Y')
            
            if axis['label'] == 'Z':
                # Для оси Z вверх - смещение вправо и вверх от центра
                dx = end_x - start_x
                dy = end_y - start_y
                length = math.sqrt(dx*dx + dy*dy)
                
                if length > 0:
                    # Направляющий вектор оси
                    dir_dx = dx / length
                    dir_dy = dy / length
                    
                    # Перпендикулярный вектор
                    perp_dx = -dir_dy
                    perp_dy = dir_dx
                    
                    # Смещаем перпендикулярно и немного вдоль оси
                    label_x = mid_x + perp_dx * label_offset - dir_dx * 5
                    label_y = mid_y + perp_dy * label_offset - dir_dy * 5
                    
                    # Выравниваем текст
                    extents = cr.text_extents('Z')
                    cr.move_to(label_x - extents.width/2, label_y + extents.height/2)
                    cr.show_text('Z')
            
            # elif axis['label'] == '-Z':
            #     # Для оси Z вниз - смещение влево и вниз от центра
            #     dx = end_x - start_x
            #     dy = end_y - start_y
            #     length = math.sqrt(dx*dx + dy*dy)
                
            #     if length > 0:
            #         # Направляющий вектор оси
            #         dir_dx = dx / length
            #         dir_dy = dy / length
                    
            #         # Перпендикулярный вектор
            #         perp_dx = -dir_dy
            #         perp_dy = dir_dx
                    
            #         # Смещаем перпендикулярно и немного вдоль оси
            #         label_x = mid_x + perp_dx * label_offset + dir_dx * 5
            #         label_y = mid_y + perp_dy * label_offset + dir_dy * 5
                    
                    # Выравниваем текст
                    # extents = cr.text_extents('-Z')
                    # cr.move_to(label_x - extents.width/2, label_y + extents.height/2)
                    # cr.show_text('-Z')
            self.draw_origin_label(cr)
    
    def draw_origin_label(self, cr):
        """Рисование подписи (0, 0) в точке начала сетки с высотой bed mesh"""
        if not self.show_axes:
            return
        
        # Проверяем, есть ли данные bed mesh
        if not self.visible or np.all(self.heights == 0):
            # Если нет данных, используем Z=0
            origin_z = 0
        else:
            # Используем высоту первой точки bed mesh
            origin_z = self.heights[self.GRID_SIZE - 1, 0] + self.z_height / 2
        
        # Левая нижняя точка сетки стола с высотой bed mesh
        origin_point = (self.grid_x[self.GRID_SIZE - 1, 0], self.grid_y[self.GRID_SIZE - 1, 0], origin_z)
        
        # Проекция точки
        x, y = self.project_3d_to_2d(*origin_point)
        
        # Рисуем подпись (0, 0)
        cr.set_source_rgb(*self.text_color)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, 
                          cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(16)
        
        # Вычисляем размеры текста
        extents = cr.text_extents("(0, 0)")
        
        # Смещение для подписи - адаптивное в зависимости от направления осей
        
        # Определяем, куда направлены оси относительно этой точки
        # 1. Направление оси X (следующая точка по X)
        next_x = (self.grid_x[0, 1], self.grid_y[0, 1], origin_z)
        x_proj = self.project_3d_to_2d(*next_x)
        dx_x = x_proj[0] - x
        dy_x = x_proj[1] - y
        
        # 2. Направление оси Y (следующая точка по Y)
        next_y = (self.grid_x[1, 0], self.grid_y[1, 0], origin_z)
        y_proj = self.project_3d_to_2d(*next_y)
        dx_y = y_proj[0] - x
        dy_y = y_proj[1] - y
        
        # 3. Направление оси Z (точка выше по Z)
        up_z = (self.grid_x[0, 0], self.grid_y[0, 0], origin_z + 0.1)
        z_proj = self.project_3d_to_2d(*up_z)
        dx_z = z_proj[0] - x
        dy_z = z_proj[1] - y
        
        # Вычисляем среднее направление, куда "смотрят" оси
        avg_dx = (dx_x + dx_y + dx_z) / 3
        avg_dy = (dy_x + dy_y + dy_z) / 3
        avg_length = math.sqrt(avg_dx*avg_dx + avg_dy*avg_dy)
        
        if avg_length > 0:
            # Нормализуем средний вектор
            avg_dx /= avg_length
            avg_dy /= avg_length
            
            # Смещаем подпись в противоположную сторону от направления осей
            offset_distance = 25
            label_x = x - avg_dx * offset_distance - extents.width / 2
            label_y = y - avg_dy * offset_distance + extents.height / 2
        else:
            # Дефолтное смещение: влево и вниз
            label_x = x - extents.width - 8
            label_y = y + 15
        
        cr.move_to(label_x, label_y)
        cr.show_text("(0, 0)")
        
        # Рисуем маленькую точку в этой позиции
        cr.set_source_rgb(1.0, 1.0, 0.9)  # Светло-желтый
        cr.arc(x, y, 2.5, 0, 2 * math.pi)
        cr.fill()
    
    def draw_arrow(self, cr, tip, base, color):
        """Рисование стрелки"""
        dx = tip[0] - base[0]
        dy = tip[1] - base[1]
        length = math.sqrt(dx*dx + dy*dy)
        
        if length < 5:
            return
        
        dx /= length
        dy /= length
        
        arrow_size = max(8, min(15, length * 0.2))
        perp_dx = -dy
        perp_dy = dx
        
        left = (
            tip[0] - dx * arrow_size + perp_dx * arrow_size * 0.4,
            tip[1] - dy * arrow_size + perp_dy * arrow_size * 0.4
        )
        
        right = (
            tip[0] - dx * arrow_size - perp_dx * arrow_size * 0.4,
            tip[1] - dy * arrow_size - perp_dy * arrow_size * 0.4
        )
        
        cr.set_source_rgb(*color)
        cr.move_to(left[0], left[1])
        cr.line_to(tip[0], tip[1])
        cr.line_to(right[0], right[1])
        cr.fill()
    
    def on_draw(self, widget, cr):
        """Отрисовка"""
        current_time = time.time()
        
        # FPS расчет
        if self.last_draw > 0:
            elapsed = current_time - self.last_draw
            if elapsed > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / elapsed)
        
        self.last_draw = current_time
        self.frame_count += 1
        
        # Фон (как в Pseudo3D)
        cr.set_source_rgb(*self.bg_color)
        cr.paint()
        
        # Автоматическое центрирование при первом отображении
        if not hasattr(self, '_centered'):
            self.auto_center_view()
            self._centered = True
        
        # ВСЕГДА рисуем координатные сетки (даже если нет данных)
        # 1. Координатные сетки на всех плоскостях
        self.draw_coordinate_grids(cr)
        
        # Рисуем в правильном порядке (сзади наперед):
        
        # 2. Оси координат
        self.draw_axes(cr)
        
        # 3. Полигоны поверхности (bed mesh) - если есть (они над плоскостью)
        if self.visible and not np.all(self.heights == 0):
            self.draw_polygons_fast(cr)
        
        # 4. Информация поверх всего
        # if self.show_info:
        #     self.draw_info(cr)
        #     if self.visible and hasattr(self, 'z_min') and hasattr(self, 'z_max'):
        #         self.draw_legend(cr)
        
        # Если нет данных - рисуем сообщение
        if not self.visible or np.all(self.heights == 0):
            cr.set_source_rgb(*self.text_color)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, 
                              cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(16)
            text = "Нет данных bed mesh"
            extents = cr.text_extents(text)
            cr.move_to(self.width/2 - extents.width/2, self.height/2)
            cr.show_text(text)
        
        return False
    
    def auto_center_view(self):
        """Автоматически центрирует вид"""
        self.angle = 45
        self.elevation = 30
        self.scale = min(self.width, self.height) * 0.6
        self.cache_valid = False
        
        # Обновляем центр виджета (на случай изменения размеров)
        self.widget_center_x = self.width // 2
        self.widget_center_y = self.height // 2
        
        # Устанавливаем центр вращения в середину плоскости bed mesh
        self.rotation_center = (
            self.origin[0] + self.bed_size / 2,
            self.origin[1] + self.bed_size / 2,
            1.5  # плоскость на высоте 1.5
        )
    
    def draw_polygons_fast(self, cr):
        """Быстрая отрисовка полигонов плоским цветом"""
        # Кэшируем синусы и косинусы для скорости
        angle_rad = math.radians(self.angle)
        elev_rad = math.radians(self.elevation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        sin_e = math.sin(elev_rad)
        
        # Предварительно вычисляем проекции всех вершин
        if self.proj_cache is None or not self.cache_valid:
            self.proj_cache = self.precompute_projections(cos_a, sin_a, sin_e)
            self.cache_valid = True
        
        # Рисуем полигоны
        for i in range(self.GRID_SIZE - 1):
            for j in range(self.GRID_SIZE - 1):
                # Получаем проекции 4 вершин квадрата
                proj1 = self.proj_cache[i, j]
                proj2 = self.proj_cache[i, j+1]
                proj3 = self.proj_cache[i+1, j]
                proj4 = self.proj_cache[i+1, j+1]
                
                # Средний цвет для квадрата
                color = (
                    (self.colors[i, j, 0] + self.colors[i, j+1, 0] + 
                    self.colors[i+1, j, 0] + self.colors[i+1, j+1, 0]) / 4 / 255.0,
                    (self.colors[i, j, 1] + self.colors[i, j+1, 1] + 
                    self.colors[i+1, j, 1] + self.colors[i+1, j+1, 1]) / 4 / 255.0,
                    (self.colors[i, j, 2] + self.colors[i, j+1, 2] + 
                    self.colors[i+1, j, 2] + self.colors[i+1, j+1, 2]) / 4 / 255.0
                )
                
                # Рисуем 2 треугольника
                cr.set_source_rgb(*color)
                
                # Треугольник 1
                cr.move_to(proj1[0], proj1[1])
                cr.line_to(proj2[0], proj2[1])
                cr.line_to(proj4[0], proj4[1])
                cr.fill()
                
                # Треугольник 2
                cr.move_to(proj1[0], proj1[1])
                cr.line_to(proj4[0], proj4[1])
                cr.line_to(proj3[0], proj3[1])
                cr.fill()
    
    def precompute_projections(self, cos_a, sin_a, sin_e):
        """Предварительное вычисление проекций всех вершин"""
        cache = np.zeros((self.GRID_SIZE, self.GRID_SIZE, 2), dtype=np.float32)
        
        for i in range(self.GRID_SIZE):
            for j in range(self.GRID_SIZE):
                x = self.grid_x[i, j]
                y = self.grid_y[i, j]
                z = self.heights[i, j] + self.z_height / 2  # ПОДНИМАЕМ НА self.z_height / 2
                
                # Смещаем координаты относительно центра вращения
                x_centered = x - self.rotation_center[0]
                y_centered = y - self.rotation_center[1]
                z_centered = z - self.rotation_center[2]
                
                # Изометрическая проекция
                screen_x = (x_centered * cos_a - y_centered * sin_a) * self.scale + self.widget_center_x
                screen_y = (x_centered * sin_a + y_centered * cos_a) * sin_e * self.scale - z_centered * self.scale * 0.3 + self.widget_center_y
                
                cache[i, j] = [screen_x, screen_y]
        
        return cache
    
    def draw_info(self, cr):
        """Рисование информации"""
        cr.set_source_rgb(*self.text_color)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, 
                          cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        
        # FPS
        fps_text = f"FPS: {self.fps:.1f}"
        cr.move_to(10, 20)
        cr.show_text(fps_text)
        
        # Информация о сетке
        grid_text = f"Grid: {self.GRID_SIZE}x{self.GRID_SIZE}"
        cr.move_to(10, 40)
        cr.show_text(grid_text)
        
        # Информация о высотах
        if hasattr(self, 'z_min') and hasattr(self, 'z_max'):
            delta = self.z_max - self.z_min
            avg_z = (self.z_min + self.z_max) / 2
            plane_level = max(0, self.z_max / 2) if self.z_max > 0 else 0
            z_text = f"Min: {self.z_min:.3f}  Max: {self.z_max:.3f}  Plane: {plane_level:.3f}"
            cr.move_to(10, 60)
            cr.show_text(z_text)
        
        # Углы камеры
        angle_text = f"Angle: {self.angle:.0f}°  Elev: {self.elevation:.0f}°  Scale: {self.scale:.0f}"
        cr.move_to(10, 80)
        cr.show_text(angle_text)
        
        # Подсказки управления
        hint_text = "ЛКМ: вращать | Колесо: масштаб | Двойной клик: сброс | Touch: панорамирование и масштабирование"
        cr.move_to(self.width - 450, self.height - 10)
        cr.show_text(hint_text)
    
    def draw_legend(self, cr):
        """Рисует легенду цветов"""
        if not hasattr(self, 'z_min') or not hasattr(self, 'z_max'):
            return
        
        legend_width = 15
        legend_height = 120
        legend_x = self.width - legend_width - 20
        legend_y = 20
        
        # Градиентная полоса
        gradient = cairo.LinearGradient(legend_x, legend_y, 
                                       legend_x, legend_y + legend_height)
        # Градиент от синего к красному через белый
        gradient.add_color_stop_rgb(0.0, 0.0, 0.0, 1.0)    # Синий
        gradient.add_color_stop_rgb(0.25, 0.0, 0.5, 0.5)   # Бирюзовый
        gradient.add_color_stop_rgb(0.5, 1.0, 1.0, 1.0)    # Белый
        gradient.add_color_stop_rgb(0.75, 1.0, 0.5, 0.0)   # Оранжевый
        gradient.add_color_stop_rgb(1.0, 1.0, 0.0, 0.0)    # Красный
        
        cr.set_source(gradient)
        cr.rectangle(legend_x, legend_y, legend_width, legend_height)
        cr.fill()
        
        # Рамка
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.set_line_width(0.5)
        cr.rectangle(legend_x, legend_y, legend_width, legend_height)
        cr.stroke()
        
        # Подписи
        cr.set_source_rgb(*self.text_color)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, 
                          cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)
        
        # Верхняя подпись (макс)
        cr.move_to(legend_x - 65, legend_y + 10)
        cr.show_text(f"Max: {self.z_max:+.3f}")
        
        # Нижняя подпись (мин)
        cr.move_to(legend_x - 65, legend_y + legend_height - 3)
        cr.show_text(f"Min: {self.z_min:+.3f}")
        
        # Разница
        delta = self.z_max - self.z_min
        cr.move_to(legend_x - 60, legend_y + legend_height/2 + 4)
        cr.show_text(f"Δ: {delta:.3f}")
        
        # Уровень плоскости
        plane_level = max(0, self.z_max / 2) if self.z_max > 0 else 0
        cr.move_to(legend_x - 60, legend_y + legend_height/2 + 16)
        cr.show_text(f"Plane: {plane_level:+.3f}")
    
    def set_bed_mesh_data(self, bm_matrix):
        """Установка данных bed mesh"""
        if not bm_matrix:
            self.reset_data()
            return
        
        try:
            rows = len(bm_matrix)
            cols = len(bm_matrix[0]) if rows > 0 else 0
            
            if rows < 2 or cols < 2:
                logging.warning("Bed mesh too small")
                return
            
            # Простейшая интерполяция на нашу сетку
            self.simple_interpolation(bm_matrix, rows, cols)
            
            # Обновляем цвета
            self.update_colors_simple()
            
            # Автоматически подстраиваем высоту оси Z под данные
            if hasattr(self, 'z_max') and self.z_max > 0:
                # Устанавливаем высоту оси Z в 2 раза больше максимальной высоты bed mesh
                # но не менее минимальной высоты
                self.z_height = max(self.z_height, abs(self.z_max) * 2.5)
                # Обновляем ось Z
                self.axes[0]['end'] = (self.origin[0], self.origin[1], self.z_height)
            
            # Инвалидируем кэш
            self.cache_valid = False
            
            self.visible = True
            self.queue_draw()
            
            logging.info(f"Data set: {rows}x{cols} -> {self.GRID_SIZE}x{self.GRID_SIZE}, Z height: {self.z_height:.3f}")
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            logging.error(f"Error setting data: {e}\nTraceback:\n{error_traceback}")
    
    def simple_interpolation(self, bm_matrix, rows, cols):
        """Простейшая интерполяция (масштабирование)"""
        # Очищаем высоты
        self.heights.fill(0)
        
        # Простое масштабирование
        for i in range(self.GRID_SIZE):
            for j in range(self.GRID_SIZE):
                # Находим ближайшую точку в исходной матрице
                src_i = min(int(i * rows / self.GRID_SIZE), rows - 1)
                src_j = min(int(j * cols / self.GRID_SIZE), cols - 1)
                
                # Берем значение
                if src_i < rows and src_j < cols:
                    self.heights[i, j] = float(bm_matrix[src_i][src_j])
    
    def update_colors_simple(self):
        """Простейшее обновление цветов - синий -> белый -> красный"""
        # Находим min/max Z (без смещения)
        raw_heights = self.heights
        # self.z_min = np.min(raw_heights)
        # self.z_max = np.max(raw_heights)
        
        # Если все значения одинаковые, добавляем небольшой диапазон
        if self.z_max == self.z_min:
            self.z_max += 0.001
            self.z_min -= 0.001
        
        # Нормализуем высоты (для цветов) от 0 до 1
        normalized = (raw_heights - self.z_min) / (self.z_max - self.z_min)
        
        for i in range(self.GRID_SIZE):
            for j in range(self.GRID_SIZE):
                n = normalized[i, j]  # от 0 до 1
                
                if n < 0.5:
                    # 0.0-0.5: Синий -> Белый
                    t = n * 2  # масштабируем до 0-1
                    # От синего (0, 0, 255) к белому (255, 255, 255)
                    self.colors[i, j] = [
                        int(t * 255),    # R увеличивается
                        int(t * 255),    # G увеличивается
                        255              # B остается 255
                    ]
                else:
                    # 0.5-1.0: Белый -> Красный
                    t = (n - 0.5) * 2  # масштабируем до 0-1
                    # От белого (255, 255, 255) к красному (255, 0, 0)
                    self.colors[i, j] = [
                        255,              # R остается 255
                        int((1 - t) * 255),  # G уменьшается
                        int((1 - t) * 255)   # B уменьшается
                    ]
    
    def reset_data(self):
        """Сброс данных"""
        self.heights.fill(0)
        self.colors.fill(0)
        self.visible = False
        if hasattr(self, 'z_min'):
            self.z_min = -0.25
        if hasattr(self, 'z_max'):
            self.z_max = 0.25
        self.cache_valid = False
        self.queue_draw()
    
    # Обработчики событий мыши
    
    def on_button_press(self, widget, event):
        if event.button == 1:
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self.reset_view()
                return True
            self.dragging = True
            self.last_x = event.x
            self.last_y = event.y
            return True
        return False
    
    def on_button_release(self, widget, event):
        if event.button == 1:
            self.dragging = False
            return True
        return False
    
    def on_motion_notify(self, widget, event):
        if self.dragging:
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            
            # Вращение - инвертируем горизонталь (меняем знак у dx)
            self.angle -= dx * 0.5  # МИНУС вместо ПЛЮС
            self.elevation += dy * 0.5
            
            # Ограничения углов
            self.angle = self.angle % 360
            self.elevation = max(10, min(80, self.elevation))
            
            # Инвалидируем кэш
            self.cache_valid = False
            
            self.last_x = event.x
            self.last_y = event.y
            
            self.queue_draw()
            return True
        return False
    
    def on_scroll(self, widget, event):
        """Обработчик прокрутки для zoom жеста"""
        # Определяем направление прокрутки
        if event.direction == Gdk.ScrollDirection.UP:
            # Zoom in - приближение
            self.scale *= 1.1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            # Zoom out - отдаление
            self.scale *= 0.9
        # Также обрабатываем smooth scrolling если есть
        elif hasattr(event, 'delta_y') and event.delta_y != 0:
            # Smooth scrolling от тачпада
            if event.delta_y > 0:
                self.scale *= 1.1
            else:
                self.scale *= 0.9
        
        # Ограничения масштаба
        self.scale = max(30, min(300, self.scale))
        
        # Инвалидируем кэш и перерисовываем
        self.cache_valid = False
        self.queue_draw()
        
        return True
    
    def reset_view(self):
        """Сброс вида"""
        self.auto_center_view()
        self.queue_draw()
    
    def toggle_grid(self):
        """Переключает отображение сетки"""
        self.show_grid = not self.show_grid
        self.queue_draw()
    
    def toggle_axes(self):
        """Переключает отображение осей"""
        self.show_axes = not self.show_axes
        self.queue_draw()
    
    def toggle_info(self):
        """Переключает отображение информации"""
        self.show_info = not self.show_info
        self.queue_draw()
    
    def toggle_plane(self):
        """Переключает отображение плоскости"""
        self.show_plane = not self.show_plane
        self.queue_draw()