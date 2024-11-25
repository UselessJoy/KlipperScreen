from typing import Union
import nmcli
import subprocess
import logging
from ks_includes.wifi_nm import WifiManager

class AccessPoint():
  def __init__(self, wifi_dev, id):
      self.id = id
      self.wifi_dev:WifiManager = wifi_dev
  
  def get_ssid(self) -> str:
    return self.get_field('802-11-wireless.ssid')
  
  def get_psk(self) -> str:
     return self.get_field('802-11-wireless-security.psk')
  
  def is_autoconnect(self) -> bool:
     return False if self.get_field('connection.autoconnect') == 'no' else True
  
  def get_ip(self) -> str:
     return self.get_field('ipv4.addresses').partition('/')[0]

  def is_active(self) -> bool:
      return self.get_field('802-11-wireless.ssid') == self.wifi_dev.get_connected_ssid()
  
  def get_field(self, field):
    return subprocess.check_output("nmcli -f %s connection show -s %s | awk '{print $2}'" % (field, self.id), universal_newlines=True, shell=True)[:-1]
  
  def modify(self, ssid, psk, autoconnect) -> None:
    try:
      nmcli.connection.modify(self.id, {
              '802-11-wireless.ssid': ssid,
              '802-11-wireless-security.psk': psk,
              'connection.autoconnect': autoconnect
          })
    except Exception as e:
      logging.info(f"Connection modify error:\n{e}\n")
      raise e
     
  def up(self) -> None:
    try:
      nmcli.connection.up(self.id)
    except Exception as e:
      logging.info(f"Connection up error:\n{e}\n")
      raise e
  
  def down(self) -> None:
    try:
      nmcli.connection.down(self.id)
    except Exception as e:
      logging.info(f"Connection down error:\n{e}\n")
      raise e

def find_access_point(wifi) -> Union[AccessPoint, None]:
  for connection in nmcli.connection():
    if connection.conn_type == 'wifi':
      try:
        connectionData = nmcli.connection.show(connection.name)
        if connectionData['802-11-wireless.mode'] == 'ap':
            return AccessPoint(wifi, connectionData['connection.id'])
      except Exception as e:
        logging.info(f"Get connection error:\n{e}\n")
  return None           