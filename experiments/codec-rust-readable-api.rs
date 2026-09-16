use lino_objects_codec::*;

fn main() {
    let nested = LinoValue::Object(vec![
        ("ok".to_string(), LinoValue::Bool(true)),
        ("pi".to_string(), LinoValue::Float(3.14)),
        ("nil".to_string(), LinoValue::Null),
    ]);
    let value = LinoValue::Object(vec![
        ("id".to_string(), LinoValue::Int(1)),
        ("name".to_string(), LinoValue::String("Hello, Links!".to_string())),
        ("tags".to_string(), LinoValue::Array(vec![LinoValue::String("a".into()), LinoValue::String("b".into())])),
        ("nested".to_string(), nested),
    ]);
    let enc = encode(&value);
    println!("--- readable ---\n{enc}");
    let dec = decode(&enc).unwrap();
    println!("roundtrip eq: {}", dec == value);
    println!("--- line ---\n{}", encode_line(&value));
    println!("--- compact ---\n{}", encode_compact(&value));
}
