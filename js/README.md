# lino-rest-api (JavaScript)

REST API framework using Links Notation (LINO) instead of JSON.

## Installation

```bash
npm install lino-rest-api
# or
bun add lino-rest-api
```

## Quick Start

```javascript
import { createLinoApp } from "lino-rest-api";

const app = createLinoApp();

// GET endpoint - automatically encodes response as LINO
app.get("/hello", () => {
  return { message: "Hello, Links Notation!" };
});

// POST endpoint - automatically decodes LINO request body
app.post("/echo", (req) => {
  return { echoed: req.body };
});

app.listen(3000, () => {
  console.log("LINO REST API running on port 3000");
});
```

## Testing the API

```bash
# GET request
curl http://localhost:3000/hello

# POST request with LINO body
curl -X POST \
  -H "Content-Type: text/lino" \
  -d '(dict obj_0 ((str bmFtZQ==) (str QWxpY2U=)))' \
  http://localhost:3000/echo
```

## API Reference

### `createLinoApp()`

Creates a new LINO-enabled Express application.

### `LinoApp`

Class with methods:

- `get(path, handler)` - Register GET endpoint
- `post(path, handler)` - Register POST endpoint
- `put(path, handler)` - Register PUT endpoint
- `delete(path, handler)` - Register DELETE endpoint
- `patch(path, handler)` - Register PATCH endpoint
- `listen(port, callback)` - Start the server
- `getExpressApp()` - Get the underlying Express app

### Middleware

- `linoMiddleware()` - Combined body parser and response helper
- `linoBodyParser()` - Parse LINO request bodies
- `linoResponse(res, data, statusCode)` - Send LINO response

## Content Type

LINO requests and responses use `text/lino` content type.

## Running Tests

```bash
npm test
# or
bun test
```

## License

Unlicense
