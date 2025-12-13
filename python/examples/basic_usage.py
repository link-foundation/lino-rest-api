"""
Basic usage example for lino-rest-api.

This example demonstrates how to create a simple REST API
that uses Links Notation (LINO) instead of JSON.
"""

from lino_rest_api.vendor import encode, decode

from lino_rest_api import LinoAPI


# Create a new LINO-enabled FastAPI app
api = LinoAPI(
    title="LINO Example API",
    description="Example REST API using Links Notation",
)


# Simple GET endpoint - returns data automatically encoded as LINO
@api.get("/hello")
def hello():
    from datetime import datetime

    return {
        "message": "Hello, Links Notation!",
        "timestamp": datetime.now().isoformat(),
    }


# POST endpoint - receives LINO-encoded body
@api.post("/echo")
async def echo(body):
    from datetime import datetime

    print(f"Received body: {body}")
    return {
        "echoed": body,
        "received_at": datetime.now().isoformat(),
    }


# Example of manual encoding/decoding
if __name__ == "__main__":
    print("\n=== Links Notation Encoding Demo ===\n")

    sample_data = {
        "name": "Alice",
        "age": 30,
        "active": True,
        "tags": ["developer", "python"],
    }

    encoded = encode(sample_data)
    print("Original Python object:")
    print(sample_data)
    print("\nEncoded as Links Notation:")
    print(encoded)

    decoded = decode(encoded)
    print("\nDecoded back to Python:")
    print(decoded)

    # Start the server
    import uvicorn

    print("\n=== Server Running ===")
    print("LINO REST API example server running on port 8001")
    print("\nTry these commands:")
    print("  curl http://localhost:8001/hello")
    print(
        "  curl -X POST -H 'Content-Type: text/lino' -d '(dict obj_0)' http://localhost:8001/echo"
    )

    uvicorn.run(api.get_fastapi_app(), host="0.0.0.0", port=8001)
