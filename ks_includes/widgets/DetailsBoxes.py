import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
import logging
from datetime import datetime

def DetailsDirty(v_info):
  details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
  try:
    for prog in v_info:
      if prog != 'system':
        prog_info = v_info[prog]
        if not prog_info['is_valid']:
          prog_label = Gtk.Label(label = prog, hexpand=True, halign=Gtk.Align.START)
          prog_label.get_style_context().add_class("details_prog_label")
          details_box.add(prog_label) 
          details_box.add(Gtk.Separator())
          vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
          vbox.get_style_context().add_class("ml-1rem")
          if prog_info['git_messages']:
            gm_label = Gtk.Label(label = prog_info['git_messages'], wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.LEFT)
            gm_label.get_style_context().add_class('text_error')
            vbox.add(gm_label)
          if prog_info['warnings']:
            warn_label = Gtk.Label(label = prog_info['warnings'], wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.LEFT)
            warn_label.get_style_context().add_class('text_warning')
            vbox.add(warn_label)
          details_box.add(vbox)
  except Exception as e:
    logging.error(f"Error on create DetailsDirty: {e}\n")
  return details_box

def DetailsActual(v_info):
  details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 10)
  try:
    for prog in v_info:
      if prog != 'system':
        prog_info = v_info[prog]
        prog_label = Gtk.Label(label = f"{prog}: {prog_info['version']}", hexpand=True, halign=Gtk.Align.START)
        prog_label.get_style_context().add_class("details_prog_label")
        details_box.add(prog_label) 
        details_box.add(Gtk.Separator())
  except Exception as e:
    logging.error(f"Error on create DetailsActual: {e}\n")
  return details_box

def DetailsUpdates(v_info):
  details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
  try:
    for prog in v_info:
      if prog != 'system':
        prog_info = v_info[prog]
        if prog_info['version'] != prog_info['remote_version']:
          prog_label = Gtk.Label(label = f"{prog}: {prog_info['version']} -> {prog_info['remote_version']}", hexpand=True, halign=Gtk.Align.START)
          prog_label.get_style_context().add_class("details_prog_label")
          details_box.add(prog_label)
          details_box.add(Gtk.Separator())
          if 'commits_behind' in prog_info:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            for commit in prog_info['commits_behind']:
              commit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
              title = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.CHAR, hexpand=True, halign=Gtk.Align.START)
              title.set_markup(f"\n<b>{commit['subject']}</b>\n<i>{commit['author']}</i>\n{datetime.fromtimestamp(float(commit['date'])).strftime('%d.%m.%Y %H:%M:%S')}")
              commit_box.add(title)
              details = Gtk.Label(label=commit['message'], wrap=True, hexpand=True, halign=Gtk.Align.START)
              commit_box.add(details)
              commit_box.add(Gtk.Separator())
              commit_box.get_style_context().add_class('ml-1rem')
              vbox.add(commit_box)  
            details_box.add(vbox) 
  except Exception as e:
    logging.error(f"Error on create DetailsUpdates: {e}\n")
  return details_box

def DetailsSystemBox(v_info, distribution_label=""):
  details_system_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing = 15)
  details_system_box.set_valign(Gtk.Align.START)
  try:
    sys_label = Gtk.Label(wrap=True, vexpand=True, halign=Gtk.Align.START)
    locale_text = ngettext("package waiting for update",
                             "packages waiting for update",
                             int(v_info['system']['package_count']))
    sys_label.set_markup(f"{distribution_label}: {v_info['system']['package_count']} {locale_text}")
    grid = Gtk.Grid(
        column_homogeneous=True,
        halign=Gtk.Align.START,
        valign=Gtk.Align.CENTER,
    )
    i = 0
    for j, c in enumerate(v_info['system']['package_list']):
        label = Gtk.Label(
            halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END
        )
        label.set_markup(f"  {c}  ")
        pos = j % 3
        grid.attach(label, pos, i, 1, 1)
        if pos == 2:
            i += 1
    details_system_box.add(sys_label)
    details_system_box.add(grid)
  except Exception as e:
    logging.error(f"Error on create DetailsSystemBox: {e}\n")
  return details_system_box
    