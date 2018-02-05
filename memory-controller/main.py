from re import match
from flask import Flask, request, jsonify
import requests
import redis
import json
app = Flask(__name__)

r = redis.Redis(host='redis')


def get_mappings(controller):
    return json.loads(r.get('controller_{}'.format(controller)))


def set_mappings(controller, mappings):
    return r.set('controller_{}'.format(controller), json.dumps(mappings))


def get_device_for(controller, address):
    for mapping in get_mappings(controller):
        if address in range(mapping['start'], mapping['start'] + mapping['size']):
            return mapping


@app.route('/<controller>/Memory/<address>', methods=['GET', 'POST'])
def api_memory(controller, address):
    if match(r'0x[0-9A-Fa-f]{1,4}', address) is not None:
        address = int(address, 16)
    elif match(r'[0-9]{1,5}', address) is not None:
        address = int(address)
    else:
        raise Exception('Invalid number-format "{}"'.format(address))
    if address > 0xFFFF:
        raise Exception('Invalid address "{}", too high'.format(address))
    device = get_device_for(controller, address)
    if device is None:
        return str(0xFF)
    url = device['url'] + '/' + str(address - device['start'])
    if request.method == 'GET':
        return requests.get(url).text
    else:
        return requests.post(url, data=request.data)


@app.route('/<controller>/Device', methods=['GET', 'POST'])
@app.route('/<controller>/Device/<address>')
def api_device(controller, address=None):
    if request.method == 'GET':
        if address is None:
            return jsonify(get_mappings(controller))
        else:
            return jsonify(get_device_for(controller, address))
    elif request.method == 'POST':
        device = request.get_json()
        if device is None:
            return'ERR: device not specified'
        if not all([get_device_for(controller, _) is None for _ in range(device['start'], device['start'] + device['size'])]):
            raise Exception(
                'Can\'t register device, {} already registered'.format(_))
        m = get_mappings(controller)
        m.append(device)
        set_mappings(controller, m)
        return 'OK'


@app.route('/')
@app.route('/<controller_id>')
def api_controller(controller_id=None):
    if controller_id is not None:
        if match(r'[0-9]+', controller_id) is None:
            return ''
        return json.dumps(get_mappings(controller_id))
    controller_id = r.incr('controller_id') - 1
    set_mappings(controller_id, [])
    return str(controller_id)
