"""Generate small finite packets that exceed each production binary work budget.

No unbounded codec or recursive stress probe is used. Graph-expansion fixtures
are a few hundred bytes and decoders must reject them at their finite budgets.
"""
import json
from pathlib import Path
from links_notation import ArityRange, BinaryLinoCodec, DecodeLimits, Link, LinksPacket


def leb(number):
    result = bytearray()
    while number >= 128:
        result.append((number & 127) | 128)
        number >>= 7
    return bytes(result + bytes([number]))


fixtures = [
    {'limit': 'links', 'hex': (b'\x10' + leb(65537)).hex()},
    {'limit': 'references', 'hex': (b'\x12' + leb(1) + leb((262145 << 4) | 4) + leb(5) + leb(1)).hex()},
]
# Direct addressed doublets double the number of anonymous AST nodes at each
# level; all references point backward and nesting stays below 64.
links = [(6, [0, 0])]
for address in range(7, 23):
    links.append((address, [address - 1, address - 1]))
packet = LinksPacket.pack(False, links)
fixtures.append({'limit': 'nodes', 'hex': packet.to_bytes().hex()})
# Repeated references to a single 1024-character string exceed expanded string
# bytes, while remaining below the link, reference, node and depth budgets.
node = Link('x' * 1024)
for _ in range(11):
    node = Link(None, [node, node])
codec = BinaryLinoCodec(limits=DecodeLimits(max_string_bytes=4 << 20))
fixtures.append({'limit': 'string', 'hex': codec.encode([node]).hex()})
node = Link('x')
for _ in range(70):
    node = Link(None, [node])
codec = BinaryLinoCodec(limits=DecodeLimits(max_depth=128))
fixtures.append({'limit': 'depth', 'hex': codec.encode([node]).hex()})
for directory in ['js/tests', 'python/tests/fixtures', 'rust/tests/fixtures']:
    (Path(directory) / 'binary-limits.json').write_text(json.dumps(fixtures, indent=2) + '\n')
