import * as codec from "lino-objects-codec";
console.log(
  "isCompactNotation str:",
  codec.isCompactNotation("(object ((str aWQ=) (int 1)))"),
  codec.isCompactNotation("(\n  id 1\n)"),
);
console.log("--- scalars ---");
for (const v of [
  null,
  true,
  42,
  3.5,
  "text",
  "multi\nline",
  [1, 2],
  {},
  [],
  "",
  { a: { b: { c: 1 } } },
]) {
  let e, d;
  try {
    e = codec.encode({ obj: v });
    d = codec.decode({ notation: e });
  } catch (err) {
    e = "ERR " + err.message;
    d = null;
  }
  console.log(
    JSON.stringify(v),
    "=>",
    JSON.stringify(e),
    "=>",
    JSON.stringify(d),
  );
}
console.log(
  "--- empty notation decode ---",
  JSON.stringify(codec.decode({ notation: "" })),
);
console.log("--- jsonToLino ---");
try {
  console.log(codec.jsonToLino({ json: { a: 1 } }));
} catch (e) {
  console.log("ERR", e.message);
}
