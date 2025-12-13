/**
 * Basic usage example for lino-rest-api.
 *
 * This example demonstrates how to create a simple REST API
 * that uses Links Notation (LINO) instead of JSON.
 */

import { createLinoApp, encode, decode } from '../src/index.js';

// Create a new LINO-enabled Express app
const app = createLinoApp();

// Simple GET endpoint - returns data automatically encoded as LINO
app.get('/hello', () => {
  return {
    message: 'Hello, Links Notation!',
    timestamp: new Date().toISOString(),
  };
});

// POST endpoint - receives LINO-encoded body
app.post('/echo', (req) => {
  console.log('Received body:', req.body);
  return {
    echoed: req.body,
    receivedAt: new Date().toISOString(),
  };
});

// Example of manual encoding/decoding
console.log('\n=== Links Notation Encoding Demo ===\n');

const sampleData = {
  name: 'Alice',
  age: 30,
  active: true,
  tags: ['developer', 'nodejs'],
};

const encoded = encode(sampleData);
console.log('Original JavaScript object:');
console.log(JSON.stringify(sampleData, null, 2));
console.log('\nEncoded as Links Notation:');
console.log(encoded);

const decoded = decode(encoded);
console.log('\nDecoded back to JavaScript:');
console.log(JSON.stringify(decoded, null, 2));

// Start the server
const PORT = 3001;
app.listen(PORT, () => {
  console.log(`\n=== Server Running ===`);
  console.log(`LINO REST API example server running on port ${PORT}`);
  console.log(`\nTry these commands:`);
  console.log(`  curl http://localhost:${PORT}/hello`);
  console.log(`  curl -X POST -H "Content-Type: text/lino" -d '(dict obj_0)' http://localhost:${PORT}/echo`);
});
