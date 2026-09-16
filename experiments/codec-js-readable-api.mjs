import * as codec from "lino-objects-codec";
const obj = {
  id: 1,
  name: "Hello, Links!",
  tags: ["a", "b"],
  nested: { ok: true, pi: 3.14, nil: null },
};
const enc = codec.encode({ obj });
console.log("--- encode (readable) ---");
console.log(enc);
console.log(
  "--- decode roundtrip ---",
  JSON.stringify(codec.decode({ notation: enc })),
);
const line = codec.encodeLine({ obj });
console.log("--- encodeLine ---");
console.log(line);
console.log(
  "decodeLine:",
  JSON.stringify(codec.decodeLine({ notation: line })),
);
const comp = codec.encodeCompact({ obj });
console.log("--- encodeCompact ---");
console.log(comp);
console.log(
  "decode(compact):",
  JSON.stringify(codec.decode({ notation: comp })),
);
console.log(
  "isCompactNotation:",
  codec.isCompactNotation({ notation: comp }),
  codec.isCompactNotation({ notation: enc }),
);
console.log("--- scalars ---");
for (const v of [null, true, 42, 3.5, "text", [1, 2], {}, []]) {
  const e = codec.encode({ obj: v });
  console.log(
    JSON.stringify(v),
    "=>",
    JSON.stringify(e),
    "=>",
    JSON.stringify(codec.decode({ notation: e })),
  );
}
