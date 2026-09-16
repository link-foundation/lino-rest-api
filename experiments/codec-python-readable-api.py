import link_notation_objects_codec as c
print("exports:", [n for n in dir(c) if not n.startswith("_")])
obj = {"id": 1, "name": "Hello, Links!", "tags": ["a","b"], "nested": {"ok": True, "pi": 3.14, "nil": None}}
enc = c.encode(obj=obj)
print("--- readable ---"); print(enc)
print("roundtrip:", c.decode(notation=enc))
print("--- line ---"); print(c.encode_line(obj=obj))
print("--- compact ---"); print(c.encode_compact(obj=obj))
