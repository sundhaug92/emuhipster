from re import match
from flask import Flask, request, jsonify
import requests
import redis
import json
import sys
app = Flask(__name__)

r = redis.Redis(host='redis')

FLAG_NEGATIVE = 7
FLAG_OVERFLOW = 6
FLAG_ALWAYS = 5
FLAG_BREAK = 4
FLAG_DECIMAL = 3
FLAG_INTERUPT_DISABLE = 2
FLAG_ZERO = 1
FLAG_CARRY = 0


def min_length_hex(i, l=2):
    c = hex(i)[2:]
    while len(c) < l:
        c = '0' + c
    return c.upper()


def get_bit(byte, bit_number):
    return (byte & (1 << bit_number)) > 0


def set_bit(byte, bit_number, value=1):
    if value not in [0, 1, True, False]:
        raise Exception('Value non-boolean')
    if value in [1, True]:
        return byte | (1 << bit_number)
    return byte & (255 - (1 << bit_number))


def decode_status(byte):
    s = ''
    names = 'NO1BDIZC'[::-1]
    for bit in range(8):
        s += names[bit] if get_bit(byte, bit) else '-'
    return s[::-1]


def tosigned8(byte):
    if byte < 0x80:
        return byte
    return (byte & 0x7F) - (byte & ~0x7F)


class Processor:
    def __init__(self, processor_id=None, memory_url=None):
        if processor_id is None:
            self.processor_id = r.incr('processor_id') - 1
            self.Accumulator = 0
            self.IndexX = 0
            self.IndexY = 0
            self.StackPointer = 255
            self.ProcessorStatus = set_bit(0, FLAG_ALWAYS)
            self.ProgramCounter = 0
            self.MemoryURL = memory_url
            self.store()
        else:
            self.processor_id = processor_id
            state = json.loads(r.get('processor_{}'.format(processor_id)))
            for k in state.keys():
                setattr(self, k, state[k])

    def store(self):
        s = {}
        for k in ['Accumulator', 'IndexX', 'IndexY', 'StackPointer', 'ProcessorStatus', 'ProgramCounter', 'MemoryURL']:
            s[k] = getattr(self, k)
        r.set('processor_{}'.format(self.processor_id),
              json.dumps(s))

    def read8(self, address):
        return int(requests.get(self.MemoryURL + '/' + str(address)).text)

    def read16(self, address):
        return (self.read8(address + 1) << 8) + self.read8(address)

    def write8(self, address, data):
        requests.post(self.MemoryURL + '/' + str(address), str(data).encode())

    def write16(self, address, data):
        self.write8(self, address + 1, data >> 8)
        self.write8(self, address, data & 255)

    def next_pc(self, times=1):
        print('Stepping {} from {}'.format(
            times, min_length_hex(self.ProgramCounter)), file=sys.stderr)
        pc = self.ProgramCounter
        for _ in range(times):
            self.ProgramCounter = (self.ProgramCounter + 1) & 0xFFFF
        return pc

    def load_program_counter_from(self, address):
        self.ProgramCounter = self.read16(address)

    def reset(self):
        self.load_program_counter_from(0xFFFC)

    def GetProcessorFlag(self, flag_bit):
        return get_bit(self.ProcessorStatus, flag_bit)

    def SetProcessorFlag(self, flag_bit, value=1):
        self.ProcessorStatus = set_bit(self.ProcessorStatus, flag_bit, value)

    def ClearProcessorFlag(self, flag_bit):
        self.SetProcessorFlag(flag_bit, 0)

    def Branch(self, flag_bit, value=True):
        offset_u = self.read8(self.ProgramCounter)
        offset_s = tosigned8(offset_u)
        print(min_length_hex(self.ProgramCounter),
              min_length_hex(offset_u), offset_s, file=sys.stderr)
        if self.GetProcessorFlag(flag_bit) == value:
            self.ProgramCounter += offset_s
        else:
            self.next_pc()

    def LoadRegister(self, register, mode):
        v = None
        if mode == 'imm':
            v = self.read8(self.next_pc())
        elif mode == 'abs':
            v = self.read8(self.read16(self.next_pc(2)))
        elif mode == 'zero':
            v = self.read8(self.read8(self.next_pc()))
        else:
            raise Exception('Invalid mode {}'.format(mode))
        self.SetProcessorFlag(FLAG_NEGATIVE, get_bit(v, 7))
        self.SetProcessorFlag(FLAG_ZERO, v == 0)
        if register == 'A':
            self.Accumulator = v
        elif register == 'X':
            self.IndexX = v
        elif register == 'Y':
            self.IndexY = v
        else:
            raise Exception('Invalid register {}'.format(register))

    def StoreRegister(self, register, mode):
        v = None
        if register == 'A':
            v = self.Accumulator
        elif register == 'Y':
            v = self.IndexY
        elif register == 'X':
            v = self.IndexX
        if mode == 'zero':
            self.write8(self.read8(self.next_pc()), v)
        elif mode == 'abs':
            self.write8(self.read16(self.next_pc(2)), v)

    def validate_state(self, throw=True):
        msg = ''
        for byteSizedRegister in ['Accumulator', 'IndexX', 'IndexY', 'StackPointer', 'ProcessorStatus']:
            if getattr(self, byteSizedRegister) < 0 or getattr(self, byteSizedRegister) > 255:
                msg += '^ERR: {} Out of range'.format(byteSizedRegister) + '\n'
        if get_bit(self.ProcessorStatus, FLAG_ALWAYS) == 0:
            msg += '^ERR: ProcessorStatus flag invalidly set\n'
        if self.ProgramCounter < 0 or self.ProgramCounter > 0xFFFF:
            msg += '^ERR: Program counter out of range\n'
        if throw and msg != '':
            raise Exception(msg.strip())
        return msg

    def step(self):
        msg = ''
        opcode = self.read8(self.ProgramCounter)
        msg += '{}:{} A={} X={} Y={} SP={} ST={}({})\n'.format(
            min_length_hex(self.ProgramCounter, 4),
            min_length_hex(opcode),
            min_length_hex(self.Accumulator),
            min_length_hex(self.IndexX),
            min_length_hex(self.IndexY),
            min_length_hex(self.StackPointer),
            min_length_hex(self.ProcessorStatus),
            decode_status(self.ProcessorStatus))
        msg += self.validate_state(throw=False)
        print(msg.strip())
        if '^ERR:' in msg:
            return msg.strip()
        self.next_pc()
        """
        Op-code handling
        """
        if opcode == 0x10:
            msg += 'BPL'
            self.Branch(FLAG_NEGATIVE, False)
        elif opcode == 0x18:
            msg += 'CLC'
            self.ClearProcessorFlag(FLAG_CARRY)
        elif opcode == 0x30:
            msg += 'BMI'
            self.Branch(FLAG_NEGATIVE)
        elif opcode == 0x38:
            msg += 'SEC'
            self.SetProcessorFlag(FLAG_CARRY)
        elif opcode == 0x50:
            msg += 'BVC'
            self.Branch(FLAG_OVERFLOW, False)
        elif opcode == 0x58:
            msg += 'CLI'
            self.ClearProcessorFlag(FLAG_INTERUPT_DISABLE)
        elif opcode == 0x70:
            msg += 'BVS'
            self.Branch(FLAG_OVERFLOW)
        elif opcode == 0x78:
            msg += 'SEI'
            self.SetProcessorFlag(FLAG_INTERUPT_DISABLE)
        elif opcode == 0x84:
            msg += 'STY zero'
            self.StoreRegister('Y', 'zero')
        elif opcode == 0x85:
            msg += 'STA zero'
            self.StoreRegister('A', 'zero')
        elif opcode == 0x86:
            msg += 'STX zero'
            self.StoreRegister('X', 'zero')
        elif opcode == 0x8C:
            msg += 'STY abs'
            self.StoreRegister('Y', 'abs')
        elif opcode == 0x8D:
            msg += 'STA abs'
            self.StoreRegister('A', 'abs')
        elif opcode == 0x8E:
            msg += 'STX abs'
            self.StoreRegister('X', 'abs')
        elif opcode == 0x90:
            msg += 'BCC'
            self.Branch(FLAG_CARRY, False)
        elif opcode == 0xA0:
            msg += 'LDY imm'
            self.LoadRegister('Y', 'imm')
        elif opcode == 0xA2:
            msg += 'LDX imm'
            self.LoadRegister('X', 'imm')
        elif opcode == 0xA4:
            msg += 'LDY zero'
            self.LoadRegister('Y', 'zero')
        elif opcode == 0xA5:
            msg += 'LDA zero'
            self.LoadRegister('A', 'zero')
        elif opcode == 0xA6:
            msg += 'LDX zero'
            self.LoadRegister('X', 'zero')
        elif opcode == 0xA9:
            msg += 'LDA imm'
            self.LoadRegister('A', 'imm')
        elif opcode == 0xAC:
            msg += 'LDY abs'
            self.LoadRegister('Y', 'abs')
        elif opcode == 0xAD:
            msg += 'LDA abs'
            self.LoadRegister('A', 'abs')
        elif opcode == 0xAE:
            msg += 'LDX abs'
            self.LoadRegister('X', 'abs')
        elif opcode == 0xB0:
            msg += 'BCS'
            self.Branch(FLAG_CARRY)
        elif opcode == 0xB8:
            msg += 'CLV'
            self.SetProcessorFlag(FLAG_OVERFLOW)
        elif opcode == 0xD0:
            msg += 'BNE'
            self.Branch(FLAG_ZERO, False)
        elif opcode == 0xF0:
            msg += 'BEQ'
            self.Branch(FLAG_ZERO)
        elif opcode == 0xD8:
            msg += 'CLD'
            self.ClearProcessorFlag(FLAG_DECIMAL)
        elif opcode == 0xF8:
            msg += 'SED'
            self.SetProcessorFlag(FLAG_DECIMAL)
        else:
            msg += '^ERR: Unknown OP-code'
        """
        """
        print('\n'.join(msg.split('\n')[1:]).strip())
        return msg.strip()


@app.route('/', methods=['POST'])
def api_processor():
    p = Processor(memory_url=request.data if type(
        request.data) is str else request.data.decode())
    return str(p.processor_id)


@app.route('/<processor_id>/reset')
def api_reset(processor_id):
    p = Processor(processor_id)
    p.reset()
    p.store()
    return ''


@app.route('/<processor_id>/step')
def api_step(processor_id):
    p = Processor(processor_id)
    msg = p.step()
    p.store()
    return msg, 500 if '^ERR:' in msg else 200


@app.route('/<processor_id>/validate')
def api_validate(processor_id):
    p = Processor(processor_id)
    p.validate_state()


@app.route('/<processor_id>/dump')
def api_dump(processor_id):
    p = Processor(processor_id)
    return r.get('processor_{}'.format(processor_id))
