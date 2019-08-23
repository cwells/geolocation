#!/usr/bin/env python3

import sys
import dbus
import gi
import click

gi.require_version('Gtk',        '3.0')
gi.require_version('GtkClutter', '1.0') 
gi.require_version('Champlain',  '0.12')

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import GtkClutter
from gi.repository import GObject
from gi.repository import Champlain

from dbus.mainloop.glib import DBusGMainLoop
from cefpython3 import cefpython as cef


GEOCLUE         = 'org.freedesktop.GeoClue2'
DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'

GCLUE_ACCURACY_LEVEL_COUNTRY      = dbus.UInt32(1)
GCLUE_ACCURACY_LEVEL_CITY         = dbus.UInt32(4)
GCLUE_ACCURACY_LEVEL_NEIGHBORHOOD = dbus.UInt32(5)
GCLUE_ACCURACY_LEVEL_STREET       = dbus.UInt32(6)
GCLUE_ACCURACY_LEVEL_EXACT        = dbus.UInt32(8)

class Map:
  def __init__(self, map_type, bus):
    self.bus = bus
    self.display_map = {
      'osm': self.display_openstreetmap,
      'google': self.display_googlemap
    }.get(map_type, 'osm')

  def display_googlemap(self, latitude, longitude, accuracy):
    url = f'https://maps.google.com/maps?q={latitude},{longitude}'
    cef.Initialize()
    browser = cef.CreateBrowserSync(url=url)
    cef.MessageLoop()
    cef.Shutdown()

  def display_openstreetmap(self, latitude, longitude, accuracy):
    GtkClutter.init([])
    window = Gtk.Window()
    window.connect("delete-event", Gtk.main_quit)
    window.set_default_size(1000, 800)
    map_to_show = self.get_map(latitude, longitude)
    window.add(map_to_show)
    window.show_all()
    Gtk.main()

  def get_map(self, latitude, longitude):
    view = Champlain.View()
    view.set_kinetic_mode(True)
    view.set_property("zoom-level", 18)
    view.set_reactive(True)
    view.set_size(1000, 800)
    view.center_on(latitude, longitude)

    layer = Champlain.MarkerLayer()
    marker = Champlain.Point.new()
    marker.set_location(latitude, longitude)
    layer.add_marker(marker)
    view.add_layer(layer)

    embed = GtkClutter.Embed.new()
    embed.realize()
    stage = embed.get_stage()
    stage.add_actor(view)

    return embed

  def location_updated(self, old_path, new_path):
    location_object = self.bus.get_object(GEOCLUE, new_path)
    location_properties = dbus.Interface(location_object, DBUS_PROPERTIES)
    latitude = location_properties.Get(f'{GEOCLUE}.Location', 'Latitude')
    longitude = location_properties.Get(f'{GEOCLUE}.Location', 'Longitude')
    accuracy = location_properties.Get(f'{GEOCLUE}.Location', 'Accuracy')
    url = f'https://maps.google.com/maps?q={latitude},{longitude}'
    self.display_map(latitude, longitude, accuracy)


@click.command()
@click.option('--display', '-d', default='osm', type=click.Choice(['osm', 'google']), help='OpenStreetMaps or Google Maps')
def main(display):
  sys.excepthook = cef.ExceptHook 
  cef.Initialize(settings={})

  dbus_loop = DBusGMainLoop(set_as_default=True)
  bus = dbus.SystemBus(mainloop=dbus_loop)

  manager_path = f'/{GEOCLUE.replace(".", "/")}/Manager'
  manager_proxy = bus.get_object(GEOCLUE, manager_path)
  manager_iface = dbus.Interface(manager_proxy, f'{GEOCLUE}.Manager')

  client_path = manager_iface.CreateClient()
  client_proxy = bus.get_object(GEOCLUE, client_path)
  client_iface = dbus.Interface(client_proxy, f'{GEOCLUE}.Client')
  client_props_iface = dbus.Interface(client_iface, DBUS_PROPERTIES)
  client_props = client_props_iface.GetAll(f'{GEOCLUE}.Client')
  client_props_iface.Set(f'{GEOCLUE}.Client', 'DesktopId', 'geolocation.desktop')
  client_props_iface.Set(f'{GEOCLUE}.Client', 'RequestedAccuracyLevel', GCLUE_ACCURACY_LEVEL_EXACT)

  map = Map(display, bus)

  client_iface.Start()
  client_iface.connect_to_signal('LocationUpdated', map.location_updated)

  loop = GLib.MainLoop()
  GLib.timeout_add(10000, loop.quit)
  loop.run()

  client_iface.Stop()


if __name__ == '__main__':
  main()