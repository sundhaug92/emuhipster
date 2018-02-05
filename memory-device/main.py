from flask import Flask, request
from re import match
import redis
import json
app = Flask(__name__)

r = redis.Redis(host='redis')


def get_memory(chip_id):
    return json.loads(r.get('memory_{}'.format(chip_id)))


def set_memory(chip_id, memory):
    r.set('memory_{}'.format(chip_id), json.dumps(memory))


@app.route('/', methods=['POST'])
def api_create():
    chip_id = r.incr('memory_id') - 1
    set_memory(chip_id, request.json)
    return str(chip_id)


@app.route('/<chip_id>/Memory/<address>', methods=['GET', 'POST'])
def api_memory(chip_id, address):
    memory = get_memory(chip_id)
    if match(r'0x[0-9A-Fa-f]{1,4}', address) is not None:
        address = int(address, 16)
    elif match(r'[0-9]{1,5}', address) is not None:
        address = int(address)
    else:
        raise Exception('Invalid number-format "{}"'.format(address))
    if request.method == 'GET':
        return str(memory['data'][address] & 0xFF)
    if memory['write_enable']:
        memory['data'][address] = int(request.data) & 0xFF
        set_memory(chip_id, memory)
    return ''
