const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');
const readline = require('node:readline');
const { test } = require('node:test');

async function fixture(t, reply) {
  const requests = [];
  const sockets = new Set();
  const server = http.createServer((req, res) => {
    requests.push(req.url);
    reply(req, res, requests.length);
  });
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const child = spawn(process.execPath, [path.join(__dirname, '../mcp-bridge.js')], {
    env: { ...process.env, BURP_MCP_HOST: '127.0.0.1', BURP_MCP_PORT: String(server.address().port) },
    stdio: ['pipe', 'pipe', 'pipe']
  });
  t.after(async () => {
    child.kill();
    for (const socket of sockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
  });
  let stderr = '';
  const pending = new Map();
  readline.createInterface({ input: child.stdout }).on('line', line => {
    const response = JSON.parse(line);
    const request = pending.get(response.id);
    assert.ok(request, `Unexpected stdout response: ${line}`);
    pending.delete(response.id);
    clearTimeout(request.timer);
    request.resolve(response);
  });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('bridge startup timed out')), 5000);
    child.stderr.on('data', data => {
      stderr += data;
      if (/Connected|WARNING/.test(stderr)) { clearTimeout(timer); resolve(); }
    });
  });
  return {
    requests, stderr: () => stderr,
    rpc(method, id, params) {
      return this.raw(JSON.stringify({ jsonrpc: '2.0', id, method, params }), id);
    },
    raw(line, id = null, split = false) {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`No response for ${id}`)), 5000);
        pending.set(id, { resolve, timer });
        const frame = Buffer.from(line + '\n');
        if (split) {
          for (const byte of frame) child.stdin.write(Buffer.from([byte]));
        } else child.stdin.write(frame);
      });
    }
  };
}

test('completed malformed frames cannot poison later frames, including split stdin writes', async t => {
  const f = await fixture(t, (req, res) => res.end('[]'));
  for (const line of [']', '{', '', 'broken JSON']) {
    const response = await f.raw(line);
    assert.equal(response.id, null);
    assert.equal(response.error.code, -32700);
    assert.ok((await f.rpc('initialize', `after-${line}`)).result);
  }
  for (let id = 0; id < 1000; id++) assert.ok((await f.rpc('initialize', id)).result);
  const response = await f.raw('{"jsonrpc":"2.0","id":"unicode","method":"initialize","params":{"value":"汉字\\ntext"}}', 'unicode', true);
  assert.ok(response.result);
  assert.equal(f.requests.length, 1);
});

test('late backend recovers once; loaded tools stay cached; stdout remains JSON-RPC', async t => {
  const f = await fixture(t, (req, res, count) => res.end(count === 1 ? 'starting' : '["proxy_history"]'));
  const result = await f.rpc('tools/list', 'recovery');
  assert.equal(result.id, 'recovery');
  assert.equal(result.result.tools[0].name, 'burp_proxy_history');
  await f.rpc('tools/list', 2);
  assert.equal(f.requests.length, 2);
  assert.match(f.stderr(), /WARNING.*retry tools\/list/);
});

test('persistent invalid content returns one bounded retry and recovery action', async t => {
  const f = await fixture(t, (req, res) => res.end('{"unexpected":true}'));
  const result = await f.rpc('tools/list', 3);
  assert.equal(result.id, 3);
  assert.match(result.error.message, /array of tool names.*retry tools\/list/);
  assert.equal(f.requests.length, 2);
});

test('hanging backend returns by total 3 second discovery deadline', async t => {
  const f = await fixture(t, () => {});
  const started = Date.now();
  const result = await f.rpc('tools/list', 4);
  assert.match(result.error.message, /timed out/);
  assert.ok(Date.now() - started < 4500);
  assert.equal(f.requests.length, 2);
});

test('normal startup, explicit operation errors and ordinary business data retain semantics', async t => {
  let response = { error: 'fixture request rejected' };
  let status = 200;
  const f = await fixture(t, (req, res) => {
    res.statusCode = req.url === '/tools' ? 200 : status;
    res.end(JSON.stringify(req.url === '/tools' ? ['encode'] : response));
  });
  assert.equal((await f.rpc('tools/list', 5)).result.tools[0].name, 'burp_encode');
  for (const code of [200, 500]) {
    status = code;
    const result = await f.rpc('tools/call', code, { name: 'burp_encode', arguments: {} });
    assert.equal(result.id, code);
    assert.equal(result.result.isError, true);
    assert.deepEqual(JSON.parse(result.result.content[0].text), response);
  }
  status = 200;
  for (const data of [{ result: { error: 'business field' } }, { status: 500, body: 'normal HTTP response' }, { error: null, success: true }, { errors: 2, results: [] }]) {
    response = data;
    const result = await f.rpc('tools/call', 'success', { name: 'burp_encode' });
    assert.equal(result.result.isError, undefined);
    assert.deepEqual(JSON.parse(result.result.content[0].text), data);
  }
});

test('invalid tool response and connection failure remain protocol errors with request IDs', async t => {
  const f = await fixture(t, (req, res) => req.url === '/tools' ? res.end('["encode"]') : res.end('broken JSON'));
  const invalid = await f.rpc('tools/call', 'invalid', { name: 'burp_encode' });
  assert.equal(invalid.id, 'invalid');
  assert.match(invalid.error.message, /Invalid Burp response/);
});

test('connection reset keeps the request ID and does not pretend operation success', async t => {
  const f = await fixture(t, (req, res) => req.url === '/tools' ? res.end('["encode"]') : req.socket.destroy());
  const result = await f.rpc('tools/call', 'offline', { name: 'burp_encode' });
  assert.equal(result.id, 'offline');
  assert.ok(result.error);
  assert.equal(result.result, undefined);
});
