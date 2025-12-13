# lino-rest-api (Python)

REST API framework using Links Notation (LINO) instead of JSON.

## Installation

```bash
pip install lino-rest-api
```

## Quick Start

```python
from lino_rest_api import LinoAPI

api = LinoAPI()

# GET endpoint - automatically encodes response as LINO
@api.get("/hello")
def hello():
    return {"message": "Hello, Links Notation!"}

# POST endpoint - automatically decodes LINO request body
@api.post("/echo")
async def echo(body):
    return {"echoed": body}

# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api.get_fastapi_app(), host="0.0.0.0", port=8000)
```

## Testing the API

```bash
# GET request
curl http://localhost:8000/hello

# POST request with LINO body
curl -X POST \
  -H "Content-Type: text/lino" \
  -d '(dict obj_0 ((str bmFtZQ==) (str QWxpY2U=)))' \
  http://localhost:8000/echo
```

## API Reference

### `LinoAPI`

Class with decorator methods:

- `@api.get(path)` - Register GET endpoint
- `@api.post(path)` - Register POST endpoint
- `@api.put(path)` - Register PUT endpoint
- `@api.delete(path)` - Register DELETE endpoint
- `@api.patch(path)` - Register PATCH endpoint
- `get_fastapi_app()` - Get the underlying FastAPI app

### Handler Arguments

Handlers can accept these special arguments:

- `request` - The FastAPI request object
- `body` - The decoded LINO request body

### Response Classes

- `LinoResponse(content, status_code)` - Create a LINO-encoded response

## Content Type

LINO requests and responses use `text/lino` content type.

## Running Tests

```bash
pytest tests/ -v
```

## License

Unlicense
