from gi.repository import Gtk, Gdk
from OpenGL.GL import *
import math
import numpy as np

class BedMap3D(Gtk.GLArea):
    def __init__(self):
        super().__init__()
        self.grid_size = 16
        self.surface_range = 2.0
        
        # Параметры сферической камеры
        self.camera_radius = 5.0  # Радиус сферы
        self.camera_theta = math.radians(45)  # Угол theta (вертикальный)
        self.camera_phi = math.radians(45)    # Угол phi (горизонтальный)
        self.min_radius = 2.0    # Минимальное расстояние (зум внутрь)
        self.max_radius = 15.0   # Максимальное расстояние (зум наружу)
        
        self.dragging = False
        self.zooming = False
        self.last_x = 0
        self.last_y = 0
        self.last_distance = 0

        # Используем Core Profile
        self.set_required_version(3, 3)
        self.set_has_depth_buffer(True)
        self.set_has_stencil_buffer(False)
        self.set_auto_render(True)
        
        self.connect("realize", self.on_realize)
        self.connect("render", self.on_render)
        self.connect("resize", self.on_resize)
        self.set_hexpand(True)
        self.set_vexpand(True)
        
        # Обработка событий мыши и тач-жестов
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | 
                              Gdk.EventMask.BUTTON_RELEASE_MASK | 
                              Gdk.EventMask.POINTER_MOTION_MASK |
                              Gdk.EventMask.TOUCH_MASK)
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("motion-notify-event", self.on_motion_notify)
        self.connect("touch-event", self.on_touch_event)
        
        # Данные для современного OpenGL
        self.surface_vertices = None
        self.surface_indices = None
        self.axes_vertices = None
        self.axes_indices = None
        self.grid_vertices = None
        self.grid_indices = None
        
        self.surface_vao = 0
        self.surface_vbo = 0
        self.surface_ebo = 0
        
        self.axes_vao = 0
        self.axes_vbo = 0
        self.axes_ebo = 0
        
        self.grid_vao = 0
        self.grid_vbo = 0
        self.grid_ebo = 0
        
        self.shader_program = 0
        self.has_valid_context = False
        
        # Минимальная Z координата поверхности (для позиционирования осей)
        self.min_surface_z = 0.0
        
        # Матрицы
        self.projection_matrix = np.identity(4, dtype=np.float32)
        self.view_matrix = np.identity(4, dtype=np.float32)
        self.model_matrix = np.identity(4, dtype=np.float32)
        
        # Точки для мультитача
        self.touch_points = {}
        
        # Инициализируем геометрию с дефолтными данными
        self.init_default_geometry()
        
    def calculate_distance(self, point1, point2):
        """Вычисление расстояния между двумя точками"""
        dx = point1[0] - point2[0]
        dy = point1[1] - point2[1]
        return math.sqrt(dx*dx + dy*dy)
        
    def update_camera_position(self):
        """Обновление позиции камеры на основе сферических координат"""
        # Вычисляем позицию камеры в декартовых координатах
        x = self.camera_radius * math.sin(self.camera_theta) * math.cos(self.camera_phi)
        y = self.camera_radius * math.sin(self.camera_theta) * math.sin(self.camera_phi)
        z = self.camera_radius * math.cos(self.camera_theta)
        
        return np.array([x, y, z], dtype=np.float32)
    
    def init_default_geometry(self):
        """Инициализация геометрии с дефолтными данными (синусоидальная поверхность)"""
        x = np.linspace(-self.surface_range/2, self.surface_range/2, self.grid_size)
        y = np.linspace(-self.surface_range/2, self.surface_range/2, self.grid_size)
        
        # Создаем вершины поверхности: [x, y, z, r, g, b, a]
        self.surface_vertices = []
        min_z = float('inf')
        
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                xx = x[i]
                yy = y[j]
                r = math.sqrt(xx*xx + yy*yy)
                z = 0.1 * math.sin(r * 3) * math.exp(-r)
                min_z = min(min_z, z)
                
                # Цвет в зависимости от высоты
                if z >= 0:
                    t = min(z / 0.3, 1.0)
                    color = [1.0, 1.0 - t, 1.0 - t, 1.0]
                else:
                    t = min(-z / 0.3, 1.0)
                    color = [1.0 - t, 1.0 - t, 1.0, 1.0]
                
                self.surface_vertices.extend([xx, yy, z, *color])
        
        self.surface_vertices = np.array(self.surface_vertices, dtype=np.float32)
        self.min_surface_z = min_z
        
        # Создаем индексы для треугольников поверхности
        self.surface_indices = []
        for i in range(self.grid_size - 1):
            for j in range(self.grid_size - 1):
                # Два треугольника на квадрат
                v0 = i * self.grid_size + j
                v1 = v0 + 1
                v2 = (i + 1) * self.grid_size + j
                v3 = v2 + 1
                
                self.surface_indices.extend([v0, v1, v2])  # Первый треугольник
                self.surface_indices.extend([v1, v3, v2])  # Второй треугольник
        
        self.surface_indices = np.array(self.surface_indices, dtype=np.uint32)
        
        # Инициализируем оси и сетки после вычисления min_surface_z
        self.init_axes_geometry()
        self.init_grid_geometry()
        
    def init_surface_geometry_from_bm(self, bm_matrix):
        """Полная переинициализация геометрии поверхности из матрицы bed mesh"""
        print(f"=== FULL SURFACE REINIT ===")
        print(f"BM matrix dimensions: {len(bm_matrix)}x{len(bm_matrix[0])}")
        
        x = np.linspace(-self.surface_range/2, self.surface_range/2, self.grid_size)
        y = np.linspace(-self.surface_range/2, self.surface_range/2, self.grid_size)
        
        # Полностью пересоздаем вершины поверхности
        self.surface_vertices = []
        min_z = float('inf')
        
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                xx = x[i]
                yy = y[j]
                
                # Получаем Z из матрицы bed mesh
                if i < len(bm_matrix) and j < len(bm_matrix[i]):
                    z_value = bm_matrix[i][j]
                else:
                    z_value = 0
                
                min_z = min(min_z, z_value)
                
                # Цвет в зависимости от высоты
                if z_value >= 0:
                    t = min(z_value / 0.3, 1.0)
                    color = [1.0, 1.0 - t, 1.0 - t, 1.0]
                else:
                    t = min(-z_value / 0.3, 1.0)
                    color = [1.0 - t, 1.0 - t, 1.0, 1.0]
                
                self.surface_vertices.extend([xx, yy, z_value, *color])
        
        self.surface_vertices = np.array(self.surface_vertices, dtype=np.float32)
        self.min_surface_z = min_z
        
        print(f"New min_surface_z: {self.min_surface_z}")
        print(f"Surface vertices shape: {self.surface_vertices.shape}")
        
        # Полностью пересоздаем оси и сетки
        self.init_axes_geometry()
        self.init_grid_geometry()
        
        # Обновляем буферы если контекст готов
        if self.has_valid_context:
            self.update_all_buffers()
    
    def init_axes_geometry(self):
        """Инициализация геометрии осей координат"""
        axis_length = 2.5
        grid_size = self.surface_range
        
        # Начало координат - первая точка матрицы (левый нижний угол)
        origin_x = -self.surface_range / 2
        origin_y = -self.surface_range / 2
        origin_z_xy = self.min_surface_z - 1.0  # XY плоскость на -1 ниже минимальной точки
        
        # Оси: [x, y, z, r, g, b, a]
        self.axes_vertices = [
            # Ось X (красная) - начинается в origin, идет по XY плоскости
            origin_x, origin_y, origin_z_xy, 1.0, 0.0, 0.0, 1.0,
            origin_x + axis_length, origin_y, origin_z_xy, 1.0, 0.0, 0.0, 1.0,
            
            # Ось Y (зеленая) - начинается в origin, идет по XY плоскости
            origin_x, origin_y, origin_z_xy, 0.0, 1.0, 0.0, 1.0,
            origin_x, origin_y + axis_length, origin_z_xy, 0.0, 1.0, 0.0, 1.0,
            
            # Ось Z (синяя) - начинается в origin, идет вертикально
            origin_x, origin_y, origin_z_xy, 0.0, 0.0, 1.0, 1.0,
            origin_x, origin_y, origin_z_xy + axis_length, 0.0, 0.0, 1.0, 1.0,
        ]
        
        self.axes_vertices = np.array(self.axes_vertices, dtype=np.float32)
        self.axes_indices = np.array([0, 1, 2, 3, 4, 5], dtype=np.uint32)
    
    def init_grid_geometry(self):
        """Инициализация геометрии координатных сеток"""
        grid_size = self.surface_range
        steps = self.grid_size
        step_size = grid_size / (steps - 1)
        
        origin_x = -self.surface_range / 2
        origin_y = -self.surface_range / 2
        origin_z_xy = self.min_surface_z - 1.0
        
        self.grid_vertices = []
        
        # Более светлые и яркие цвета для сеток
        grid_color_xy = [0.7, 0.7, 0.7, 0.8]  # XY плоскость - почти непрозрачная
        grid_color_xz = [0.6, 0.6, 0.6, 0.7]  # XZ плоскость
        grid_color_yz = [0.6, 0.6, 0.6, 0.7]  # YZ плоскость
        
        # Сетка в плоскости XY (на уровне origin_z_xy)
        for i in range(steps):
            # Линии параллельные X
            x = origin_x + i * step_size
            self.grid_vertices.extend([x, origin_y, origin_z_xy, *grid_color_xy])
            self.grid_vertices.extend([x, origin_y + grid_size, origin_z_xy, *grid_color_xy])
            
            # Линии параллельные Y
            y = origin_y + i * step_size
            self.grid_vertices.extend([origin_x, y, origin_z_xy, *grid_color_xy])
            self.grid_vertices.extend([origin_x + grid_size, y, origin_z_xy, *grid_color_xy])
        
        # Сетка в плоскости XZ (на уровне origin_y)
        for i in range(steps):
            # Линии параллельные X
            x = origin_x + i * step_size
            self.grid_vertices.extend([x, origin_y, origin_z_xy, *grid_color_xz])
            self.grid_vertices.extend([x, origin_y, origin_z_xy + grid_size, *grid_color_xz])
            
            # Линии параллельные Z
            z = origin_z_xy + i * step_size
            self.grid_vertices.extend([origin_x, origin_y, z, *grid_color_xz])
            self.grid_vertices.extend([origin_x + grid_size, origin_y, z, *grid_color_xz])
        
        # Сетка в плоскости YZ (на уровне origin_x)
        for i in range(steps):
            # Линии параллельные Y
            y = origin_y + i * step_size
            self.grid_vertices.extend([origin_x, y, origin_z_xy, *grid_color_yz])
            self.grid_vertices.extend([origin_x, y, origin_z_xy + grid_size, *grid_color_yz])
            
            # Линии параллельные Z
            z = origin_z_xy + i * step_size
            self.grid_vertices.extend([origin_x, origin_y, z, *grid_color_yz])
            self.grid_vertices.extend([origin_x, origin_y + grid_size, z, *grid_color_yz])
        
        self.grid_vertices = np.array(self.grid_vertices, dtype=np.float32)
        self.grid_indices = np.array([i for i in range(len(self.grid_vertices) // 7)], dtype=np.uint32)
    
    def compile_shader(self, source, shader_type):
        """Компиляция шейдера"""
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)
        
        if not glGetShaderiv(shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(shader).decode()
            print(f"Shader compilation error: {error}")
            glDeleteShader(shader)
            return 0
            
        return shader
    
    def create_shader_program(self):
        """Создание шейдерной программы"""
        vertex_shader_source = """
        #version 330 core
        layout (location = 0) in vec3 aPos;
        layout (location = 1) in vec4 aColor;
        
        out vec4 vertexColor;
        
        uniform mat4 model;
        uniform mat4 view;
        uniform mat4 projection;
        
        void main()
        {
            gl_Position = projection * view * model * vec4(aPos, 1.0);
            vertexColor = aColor;
        }
        """
        
        fragment_shader_source = """
        #version 330 core
        in vec4 vertexColor;
        out vec4 FragColor;
        
        void main()
        {
            FragColor = vertexColor;
        }
        """
        
        vertex_shader = self.compile_shader(vertex_shader_source, GL_VERTEX_SHADER)
        fragment_shader = self.compile_shader(fragment_shader_source, GL_FRAGMENT_SHADER)
        
        if not vertex_shader or not fragment_shader:
            return 0
        
        shader_program = glCreateProgram()
        glAttachShader(shader_program, vertex_shader)
        glAttachShader(shader_program, fragment_shader)
        glLinkProgram(shader_program)
        
        if not glGetProgramiv(shader_program, GL_LINK_STATUS):
            error = glGetProgramInfoLog(shader_program).decode()
            print(f"Shader program linking error: {error}")
            return 0
        
        glDeleteShader(vertex_shader)
        glDeleteShader(fragment_shader)
        
        return shader_program

    def on_realize(self, area):
        self.make_current()
        try:
            print("OpenGL context created successfully")
            print(f"OpenGL version: {glGetString(GL_VERSION).decode()}")
            print(f"GLSL version: {glGetString(GL_SHADING_LANGUAGE_VERSION).decode()}")
            self.has_valid_context = True
        except Exception as e:
            print(f"OpenGL context error: {e}")
            self.has_valid_context = False
            return
        
        # Создаем шейдерную программу
        self.shader_program = self.create_shader_program()
        if not self.shader_program:
            print("Failed to create shader program")
            self.has_valid_context = False
            return
        
        # Инициализируем все буферы
        self.initialize_all_buffers()
        
        # Настройка OpenGL
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.41, 0.41, 0.41, 1.0)
        print("OpenGL initialized successfully")
        
        # Принудительно запрашиваем перерисовку после инициализации
        self.queue_render()

    def initialize_all_buffers(self):
        """Инициализация всех буферов OpenGL"""
        # Буферы для поверхности
        self.surface_vao = glGenVertexArrays(1)
        self.surface_vbo = glGenBuffers(1)
        self.surface_ebo = glGenBuffers(1)
        
        glBindVertexArray(self.surface_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.surface_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.surface_vertices.nbytes, self.surface_vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.surface_ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.surface_indices.nbytes, self.surface_indices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        
        # Буферы для осей
        self.axes_vao = glGenVertexArrays(1)
        self.axes_vbo = glGenBuffers(1)
        self.axes_ebo = glGenBuffers(1)
        
        glBindVertexArray(self.axes_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.axes_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.axes_vertices.nbytes, self.axes_vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.axes_ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.axes_indices.nbytes, self.axes_indices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        
        # Буферы для сетки
        self.grid_vao = glGenVertexArrays(1)
        self.grid_vbo = glGenBuffers(1)
        self.grid_ebo = glGenBuffers(1)
        
        glBindVertexArray(self.grid_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.grid_vertices.nbytes, self.grid_vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.grid_ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.grid_indices.nbytes, self.grid_indices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

    def update_all_buffers(self):
        """Полное обновление всех буферов после изменения геометрии"""
        if not self.has_valid_context:
            return
            
        print("Updating all OpenGL buffers...")
        
        # Обновляем VBO поверхности
        glBindBuffer(GL_ARRAY_BUFFER, self.surface_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.surface_vertices.nbytes, self.surface_vertices, GL_STATIC_DRAW)
        
        # Обновляем VBO осей
        glBindBuffer(GL_ARRAY_BUFFER, self.axes_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.axes_vertices.nbytes, self.axes_vertices, GL_STATIC_DRAW)
        
        # Обновляем VBO сетки
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, self.grid_vertices.nbytes, self.grid_vertices, GL_STATIC_DRAW)
        
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def on_resize(self, area, width, height):
        if width > 0 and height > 0:
            # Обновляем матрицу проекции
            aspect = width / height
            self.projection_matrix = self.perspective_matrix(45.0, aspect, 0.1, 50.0)
            self.queue_render()

    def perspective_matrix(self, fov, aspect, near, far):
        """Создание матрицы перспективной проекции"""
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        return np.array([
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (far + near) / (near - far), -1],
            [0, 0, (2 * far * near) / (near - far), 0]
        ], dtype=np.float32)

    def lookat_matrix(self, eye, target, up):
        """Создание видовой матрицы"""
        forward = (target - eye)
        forward = forward / np.linalg.norm(forward)
        
        right = np.cross(forward, up)
        right = right / np.linalg.norm(right)
        
        new_up = np.cross(right, forward)
        
        return np.array([
            [right[0], new_up[0], -forward[0], 0],
            [right[1], new_up[1], -forward[1], 0],
            [right[2], new_up[2], -forward[2], 0],
            [-np.dot(right, eye), -np.dot(new_up, eye), np.dot(forward, eye), 1]
        ], dtype=np.float32)

    def on_render(self, area, context):
        if not self.has_valid_context or not self.shader_program:
            return True
            
        try:
            # Очистка с серым фоном
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            
            # Получаем позицию камеры из сферических координат
            camera_pos = self.update_camera_position()
            target = np.array([0.0, 0.0, 0.0], dtype=np.float32)  # Центр сцены
            up = np.array([0.0, 0.0, 1.0], dtype=np.float32)      # Вектор "вверх"
            
            # Создаем видовую матрицу
            self.view_matrix = self.lookat_matrix(camera_pos, target, up)
            
            # Модельная матрица - единичная (без вращения объектов)
            self.model_matrix = np.identity(4, dtype=np.float32)
            
            # Используем шейдерную программу
            glUseProgram(self.shader_program)
            
            # Передаем uniform матрицы
            model_loc = glGetUniformLocation(self.shader_program, "model")
            view_loc = glGetUniformLocation(self.shader_program, "view")
            projection_loc = glGetUniformLocation(self.shader_program, "projection")
            
            glUniformMatrix4fv(model_loc, 1, GL_FALSE, self.model_matrix)
            glUniformMatrix4fv(view_loc, 1, GL_FALSE, self.view_matrix)
            glUniformMatrix4fv(projection_loc, 1, GL_FALSE, self.projection_matrix)
            
            # Рисуем координатные сетки (более толстые и яркие линии)
            glLineWidth(2.0)
            glBindVertexArray(self.grid_vao)
            glDrawElements(GL_LINES, len(self.grid_indices), GL_UNSIGNED_INT, None)
            
            # Рисуем координатные оси (толстые линии)
            glLineWidth(3.0)
            glBindVertexArray(self.axes_vao)
            glDrawElements(GL_LINES, len(self.axes_indices), GL_UNSIGNED_INT, None)
            
            # Рисуем поверхность (треугольники)
            glBindVertexArray(self.surface_vao)
            glDrawElements(GL_TRIANGLES, len(self.surface_indices), GL_UNSIGNED_INT, None)
            
            glBindVertexArray(0)
            
        except Exception as e:
            print(f"Render error: {e}")
            import traceback
            traceback.print_exc()
            
        return True

    def on_button_press(self, widget, event):
        # Если уже зумим - игнорируем мышь
        if self.zooming:
            return False
            
        if event.button == 1:
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
        # Если зумим - игнорируем движение мыши
        if self.zooming:
            return False
            
        if self.dragging:
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            
            # Чувствительность вращения
            sensitivity = 0.01
            
            # Горизонтальное движение - вращение по phi (влево/вправо)
            self.camera_phi -= dx * sensitivity
            
            # Вертикальное движение - вращение по theta (вверх/вниз) с инверсией
            self.camera_theta -= dy * sensitivity  # Инверсия: минус вместо плюса
            
            # Ограничиваем угол theta чтобы камера не переворачивалась
            self.camera_theta = max(0.1, min(math.pi - 0.1, self.camera_theta))
            
            # Нормализуем угол phi
            if self.camera_phi > 2 * math.pi:
                self.camera_phi -= 2 * math.pi
            elif self.camera_phi < 0:
                self.camera_phi += 2 * math.pi
            
            self.last_x = event.x
            self.last_y = event.y
            self.queue_render()
            return True
            
        return False

    def on_touch_event(self, widget, event):
        """Обработка мультитач-жестов для зума"""
        if event.type == Gdk.EventType.TOUCH_BEGIN:
            # Добавляем точку касания
            self.touch_points[event.sequence] = (event.x, event.y)
            
            # Если касаний стало 2 - начинаем зум и блокируем вращение
            if len(self.touch_points) == 2:
                self.zooming = True
                self.dragging = False  # Блокируем вращение
                points = list(self.touch_points.values())
                self.last_distance = self.calculate_distance(points[0], points[1])
                return True
                
        elif event.type == Gdk.EventType.TOUCH_UPDATE:
            # Обновляем позицию точки
            if event.sequence in self.touch_points:
                self.touch_points[event.sequence] = (event.x, event.y)
            
            # Если активно 2 касания - обрабатываем зум
            if self.zooming and len(self.touch_points) == 2:
                points = list(self.touch_points.values())
                current_distance = self.calculate_distance(points[0], points[1])
                
                # Вычисляем изменение расстояния
                distance_delta = current_distance - self.last_distance
                
                # Чувствительность зума
                zoom_sensitivity = 0.01
                
                # Изменяем радиус камеры (зум)
                new_radius = self.camera_radius - distance_delta * zoom_sensitivity
                
                # Ограничиваем радиус
                self.camera_radius = max(self.min_radius, min(self.max_radius, new_radius))
                
                self.last_distance = current_distance
                self.queue_render()
                return True
                
        elif event.type == Gdk.EventType.TOUCH_END or event.type == Gdk.EventType.TOUCH_CANCEL:
            # Удаляем точку касания
            if event.sequence in self.touch_points:
                del self.touch_points[event.sequence]
            
            # Если осталось меньше 2 касаний - заканчиваем зум
            if len(self.touch_points) < 2:
                self.zooming = False
                
        return False

    def update_bm(self, bm_matrix):
        """Полное обновление данных поверхности из матрицы bed mesh"""
        print(f"=== FULL BED MESH UPDATE ===")
        print(f"BM matrix provided: {bm_matrix is not None}")
        
        if bm_matrix is None:
            print("No BM matrix provided, using default geometry")
            # Если матрица None, используем дефолтную геометрию
            self.init_default_geometry()
        else:
            print(f"BM matrix dimensions: {len(bm_matrix)}x{len(bm_matrix[0])}")
            # Полная переинициализация геометрии из матрицы bed mesh
            self.init_surface_geometry_from_bm(bm_matrix)
        
        # Принудительная перерисовка
        self.queue_render()

    def queue_draw(self):
        """Запрос на перерисовку"""
        self.queue_render()