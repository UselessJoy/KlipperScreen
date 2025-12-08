# import logging
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class BedMap(Gtk.DrawingArea):
    def __init__(self, font_size, bm):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.connect('draw', self.draw_graph)
        self.font_size = font_size
        self.font_spacing = round(self.font_size * 1.5)

        new_bm = []
        if bm is not None:
          for row in list(reversed(bm)):
              new_bm.append([point for point in row])
        self.bm = new_bm
        # logging.info(f"real bm {list(reversed(bm)) if bm is not None else None}")
        # logging.info(f"bm after -1 {self.bm}")
        # self.bm = list(bm) if bm is not None else None

    def update_bm(self, bm):
        new_bm = []
        if bm is not None:
          for row in list(reversed(bm)):
              new_bm.append([point for point in row])
        self.bm = new_bm
        # logging.info(f"real bm {list(reversed(bm)) if bm is not None else None}")
        # logging.info(f"bm after -1 {self.bm}")
        # self.bm = list(bm) if bm is not None else None

    def draw_graph(self, drawing_area, cairo_type):
        width = drawing_area.get_allocated_width()
        height = drawing_area.get_allocated_height()
        # Styling
        cairo_type.set_line_width(1)
        cairo_type.set_font_size(self.font_size)

        if self.bm is None:
            cairo_type.move_to(self.font_spacing, height / 2)
            cairo_type.set_source_rgb(0.5, 0.5, 0.5)
            cairo_type.stroke()
            return

        rows = len(self.bm)
        columns = len(self.bm[0])
        for i, row in enumerate(self.bm):
            topY = height / rows * i
            bottomY = topY + height / rows
            for j, column in enumerate(row):
                leftX = width / columns * j
                rightX = leftX + width / columns
                # Colors
                cairo_type.set_source_rgb(*self.colorbar(column))
                cairo_type.move_to(leftX, topY)
                cairo_type.line_to(leftX, bottomY - 2)
                cairo_type.line_to(rightX - 2, bottomY - 2)
                cairo_type.line_to(rightX - 2, topY)
                cairo_type.close_path()
                cairo_type.fill()
                cairo_type.stroke()
                if rows > 16 or columns > 8:
                    continue
                # Numbers
                cairo_type.set_source_rgb(0, 0, 0)
                if column > 0:
                    cairo_type.move_to((leftX + rightX) / 2 - self.font_size, (topY + bottomY + self.font_size) / 2)
                else:
                    cairo_type.move_to((leftX + rightX) / 2 - self.font_size * 1.2, (topY + bottomY + self.font_size) / 2)
                cairo_type.show_text(f"{column:.2f}")
                cairo_type.stroke()

    @staticmethod
    def colorbar(value):
        rmax = 0.25
        color = min(1, max(0, 1 - 1 / rmax * abs(value)))
        if value > 0:
            return [1, color, color]
        if value < 0:
            return [color, color, 1]
        return [1, 1, 1]
