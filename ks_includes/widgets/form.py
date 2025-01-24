from gi import Gtk

def get_container_data(container) -> dict:
  for widget in container:
    if isinstance(widget, Gtk.Container):
      data = get_container_data(widget)
    elif isinstance(widget, Gtk.Entry):
      data['entry']
def get_data_as_dict(form):
  data = {}
  for widget in form:
    if isinstance(widget, Gtk.Container):
      data['container'] = {}
      data['container'] = get_container_data(widget)
      