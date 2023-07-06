from pymodbus.client import ModbusTcpClient
from config import NetData

net_data = NetData()

client = ModbusTcpClient(host=net_data.localhost, port=net_data.localport)
