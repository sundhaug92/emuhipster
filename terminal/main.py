import requests
import json


class MemoryDevice():
    BASE_URL = 'http://memorydevice:5000'

    def __init__(self, chip_id=None, size=None, write_enable=True, data=None):
        if data is None:
            data = [255 for _ in range(size)]
        o = {'write_enable': write_enable, 'data': data}
        self.write_enable, self.size = write_enable, size
        self.chip_id = chip_id if chip_id is not None else int(requests.post(
            self.BASE_URL, json=o).text)
        self.url = self.BASE_URL + '/{}/Memory'.format(self.chip_id)

    def read(self, address):
        return int(requests.get(self.url + '/{}'.format(address)).text)

    def write(self, address, byte):
        requests.post(self.url + '/{}'.format(address),
                      data=str(byte).encode())


class MemoryController():
    BASE_URL = 'http://memorycontroller:5000'

    def __init__(self, controller_id=None):
        self.controller_id = controller_id if controller_id is not None else requests.get(
            self.BASE_URL).text
        self.device_url = '/'.join(
            [self.BASE_URL, str(self.controller_id), 'Device'])
        self.memory_url = '/'.join(
            [self.BASE_URL, str(self.controller_id), 'Memory'])

    def register_device(self, start_address, device):
        return requests.post(self.device_url, json={'start': start_address, 'size': device.size, 'url': device.url}).text == 'OK'

    def read(self, address):
        return int(requests.get(self.memory_url + '/' + str(address)).text)

    def write(self, address, byte):
        requests.post(self.memory_url + '/' + str(address),
                      data=str(byte).encode())


print('> Doing RAM test...')
print('>> Creating device')
ramTest = MemoryDevice(size=8192)
print('>> Testing original value')
assert ramTest.read(0) == 255
print('>> Writing to device')
ramTest.write(1, 127)
print('>> Reading back')
assert ramTest.read(0) == 255
assert ramTest.read(1) == 127
print('>> RAM TEST GO')

print('> Doing ROM test')
print('>> Creating device')
romTest = MemoryDevice(size=256, write_enable=False)
print('>> Testing original value')
assert romTest.read(0) == 255
romTest.write(1, 127)
print('>> Reading back')
assert romTest.read(0) == 255
assert romTest.read(1) == 255
print('>> ROM TEST GO')

print('> Starting memory controller test')
controller = MemoryController()
print('>> Registering devices')
controller.register_device(0x0000, ramTest)
controller.register_device(0xFF00, romTest)
print('>> Reading back from ram-test')
assert controller.read(0x0001) == 127
print('>> Reading back from rom-test')
assert controller.read(0xFF01) == 255
