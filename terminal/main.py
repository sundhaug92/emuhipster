import requests
from zipfile import ZipFile
from io import BytesIO


class MemoryDevice:
    BASE_URL = 'http://memorydevice:5000'

    def __init__(self, chip_id=None, size=None, write_enable=True, data=None):
        if data is None:
            data = [255 for _ in range(size)]
        elif size is None:
            size = len(data)
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


class MemoryController:
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


class Mainprocessor:
    BASE_URL = 'http://mainprocessor:5000'

    def __init__(self, processor_id=None, memory_controller=None):
        self.processor_id = processor_id if processor_id is not None else requests.post(
            self.BASE_URL, data=memory_controller.memory_url.encode()).text
        self.url = '/'.join([self.BASE_URL, str(self.processor_id)])

    def reset(self):
        r = requests.get(self.url + '/reset')
        if not r.ok:
            raise Exception(r.text)

    def dump(self):
        r = requests.get(self.url + '/dump')
        if not r.ok:
            raise Exception(r.text)

    def step(self):
        r = requests.get(self.url + '/step')
        if not r.ok:
            raise Exception(r.text)
        return r.text


def min_length_hex(i, l=2):
    c = hex(i)[2:]
    while len(c) < l:
        c = '0' + c
    return c


firmware_zip = ZipFile(BytesIO(requests.get(
    'http://www.callapple.org/soft/ap1/emul/Apple1_bios.zip').content))
wozmon_byte = firmware_zip.read('apple1.rom')
wozmon = [_ for _ in wozmon_byte]

ram = MemoryDevice(size=8192)
rom = MemoryDevice(write_enable=False, data=wozmon)
memory_controller = MemoryController()
memory_controller.register_device(0x0000, ram)
memory_controller.register_device(0xFF00, rom)
processor = Mainprocessor(memory_controller=memory_controller)
processor.reset()
for _ in range(1000):
    print(processor.step())
