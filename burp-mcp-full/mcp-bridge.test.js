const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const readline = require('node:readline');
const { spawn } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');
const test = require('node:test');

const MAX_IN_FLIGHT = 16;
const HTTP_TIMEOUT_MS = 30_000;
const TOOL_NAMES = ['proxy_history', 'log', 'unknown_tool'];

async function waitFor(predicate, timeout = 5_000) {
  const deadline = Date.now() + timeout;
  while (!predicate() && Date.now() < deadline) await delay(10);
  assert.ok(predicate(), 'Expected bridge/server event before timeout');
}

async function startBridge(t, handleTool, handleDiscovery) {
  let discoveries = 0;
  const server = http.createServer((req, res) => {
    req.resume();
    if (req.url === '/tools') {
      discoveries++;
      if (handleDiscovery) handleDiscovery(req, res);
      else res.end(JSON.stringify(TOOL_NAMES));
    } else {
      handleTool(req, res);
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  });
  const child = spawn(process.execPath, [path.join(__dirname, 'mcp-bridge.js')], {
    env: { ...process.env, BURP_MCP_HOST: '127.0.0.1', BURP_MCP_PORT: String(server.address().port) },
    stdio: ['pipe', 'pipe', 'pipe']
  });
  let exited = false;
  let exitCode;
  let spawnError;
  let stderr = '';
  const responses = [];
  child.on('error', error => { spawnError = error; });
  child.on('exit', code => { exited = true; exitCode = code; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  const output = readline.createInterface({ input: child.stdout });
  output.on('line', line => responses.push(JSON.parse(line)));
  t.after(async () => {
    if (!exited) {
      child.kill();
      await waitFor(() => exited || spawnError);
    }
    output.close();
  });
  return {
    child,
    responses,
    send(message) { child.stdin.write(JSON.stringify(message) + '\n'); },
    async ready() {
      await waitFor(() => spawnError || /Connected to Burp|WARNING: Cannot connect/.test(stderr), HTTP_TIMEOUT_MS + 5_000);
      assert.ifError(spawnError);
    },
    get discoveries() { return discoveries; },
    get exited() { return exited; },
    get stderr() { return stderr; },
    get exitCode() { return exitCode; },
  };
}

function toolCall(id) {
  return { jsonrpc: '2.0', id, method: 'tools/call', params: { name: 'burp_log', arguments: { message: 'test' } } };
}

test('malformed complete frames do not contaminate subsequent JSONL requests', async t => {
  const bridge = await startBridge(t, (_req, res) => res.end('{}'));
  await bridge.ready();
  const initialize = { jsonrpc: '2.0', id: 7, method: 'initialize' };
  bridge.child.stdin.write('{"jsonrpc":\n' + JSON.stringify(initialize) + '\n');
  await waitFor(() => bridge.responses.length === 2);
  assert.deepEqual(bridge.responses[0], {
    jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' }
  });
  assert.equal(bridge.responses[1].id, 7);
  assert.equal(bridge.responses[1].result.protocolVersion, '2024-11-05');
  assert.equal(bridge.exited, false);
  bridge.send({ jsonrpc: '2.0', id: 8, method: 'missing' });
  await waitFor(() => bridge.responses.length === 3);
  assert.equal(bridge.responses[2].id, 8);
  assert.equal(bridge.responses[2].error.code, -32601);
});

test('a single stdin burst is capped, resumes after failures, and drains before EOF exit', async t => {
  let active = 0;
  let peak = 0;
  let arrivals = 0;
  let holding = true;
  const held = [];
  const bridge = await startBridge(t, (req, res) => {
    arrivals++;
    active++;
    peak = Math.max(peak, active);
    res.once('close', () => { active--; });
    if (holding) held.push({ req, res });
    else res.end('{"ok":true}');
  });
  await bridge.ready();
  const count = MAX_IN_FLIGHT * 2 + 5;
  const frames = Array.from({ length: count }, (_, id) => JSON.stringify(toolCall(id)));
  frames.push('{');
  frames.push(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }));
  frames.push(JSON.stringify({ jsonrpc: '2.0', id: 999, method: 'initialize' }));
  bridge.child.stdin.end(frames.join('\n') + '\n');
  await waitFor(() => arrivals >= MAX_IN_FLIGHT);
  await delay(100);
  assert.equal(arrivals, MAX_IN_FLIGHT, 'No extra HTTP calls may start while capacity is full');
  holding = false;
  held.forEach(({ req, res }, index) => {
    if (index < 2) req.socket.destroy();
    else res.end('{"ok":true}');
  });
  try {
    await waitFor(() => bridge.responses.length === count + 2 && bridge.exited);
  } catch {
    assert.fail(
      `EOF drain stalled: responses=${bridge.responses.length}, arrivals=${arrivals}, active=${active}, ` +
      `exited=${bridge.exited}, stderr=${bridge.stderr}`
    );
  }
  assert.equal(arrivals, count);
  assert.ok(peak <= MAX_IN_FLIGHT, `Observed ${peak} concurrent HTTP calls`);
  assert.equal(bridge.exitCode, 0);
  const calls = bridge.responses.filter(response => Number.isInteger(response.id) && response.id < count);
  assert.equal(new Set(calls.map(response => response.id)).size, count);
  assert.equal(calls.filter(response => response.error && response.error.code === -1).length, 2);
  for (const response of calls.filter(response => response.result)) {
    assert.deepEqual(JSON.parse(response.result.content[0].text), { ok: true });
  }
  assert.equal(bridge.responses.find(response => response.id === null).error.code, -32700);
  assert.equal(bridge.responses.find(response => response.id === 999).result.serverInfo.name, 'burpsuite-mcp');
});

test('wall-clock deadlines destroy idle/dripping HTTP calls and allow initialization after stalled discovery', { timeout: HTTP_TIMEOUT_MS + 15_000 }, async t => {
  await Promise.all([
    (async () => {
      let arrivals = 0;
      let destroyed = 0;
      let complete = false;
      const bridge = await startBridge(t, (_req, res) => {
        if (complete) {
          res.end('{"ok":true}');
          return;
        }
        arrivals++;
        // The second response has no idle interval long enough for an inactivity timeout.
        let drip;
        if (arrivals === 2) {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.write(' ');
          drip = setInterval(() => res.write(' '), 100);
        }
        res.once('close', () => {
          clearInterval(drip);
          destroyed++;
        });
      });
      await bridge.ready();
      const started = Date.now();
      for (let id = 1; id <= MAX_IN_FLIGHT; id++) bridge.send(toolCall(id));
      bridge.send({ jsonrpc: '2.0', id: 99, method: 'tools/list' });
      await waitFor(() => arrivals === MAX_IN_FLIGHT);
      await waitFor(() => bridge.responses.length === MAX_IN_FLIGHT + 1 && destroyed === MAX_IN_FLIGHT, HTTP_TIMEOUT_MS + 5_000);
      assert.ok(Date.now() - started < HTTP_TIMEOUT_MS + 5_000, 'Deadline must be wall-clock bounded');
      const timedOut = bridge.responses.filter(response => response.id !== 99);
      for (const response of timedOut) {
        assert.equal(response.error.code, -1);
        assert.match(response.error.message, /timed out/);
      }
      assert.deepEqual(timedOut.map(response => response.id).sort((a, b) => a - b),
        Array.from({ length: MAX_IN_FLIGHT }, (_, index) => index + 1));
      assert.equal(bridge.responses.find(response => response.id === 99).result.tools.length, TOOL_NAMES.length);
      complete = true;
      bridge.send(toolCall(100));
      await waitFor(() => bridge.responses.length === MAX_IN_FLIGHT + 2);
      const success = bridge.responses.find(response => response.id === 100);
      assert.deepEqual(JSON.parse(success.result.content[0].text), { ok: true });
    })(),
    (async () => {
      let destroyed = false;
      const bridge = await startBridge(t, (_req, res) => res.end('{}'), (_req, res) => {
        res.once('close', () => { destroyed = true; });
      });
      // Queue initialization while discovery is stalled; it must eventually be read.
      bridge.send({ jsonrpc: '2.0', id: 10, method: 'initialize' });
      await waitFor(() => bridge.responses.length === 1 && destroyed, HTTP_TIMEOUT_MS + 5_000);
      assert.equal(bridge.responses[0].id, 10);
      assert.equal(bridge.responses[0].result.serverInfo.name, 'burpsuite-mcp');
      bridge.send({ jsonrpc: '2.0', id: 11, method: 'tools/list' });
      await waitFor(() => bridge.responses.length === 2);
      assert.deepEqual(bridge.responses[1].error, { code: -1, message: 'Tools not loaded. Is Burp running?' });
    })()
  ]);
});

test('repeated tool listings preserve discovery order, metadata, fallback schema, and call behavior', async t => {
  const bridge = await startBridge(t, (_req, res) => res.end('{"ok":true}'));
  await bridge.ready();
  bridge.send({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
  await waitFor(() => bridge.responses.length === 1);
  const tools = bridge.responses[0].result.tools;
  assert.deepEqual(tools.map(tool => tool.name), TOOL_NAMES.map(name => 'burp_' + name));
  assert.equal(tools[0].description, 'Get Burp proxy history with optional filtering by URL, method, status code');
  assert.deepEqual(tools[0].inputSchema.properties.limit, { type: 'number', description: 'Max items (default 100)' });
  assert.deepEqual(tools[1].inputSchema.properties.message, { type: 'string' });
  assert.deepEqual(tools[2], {
    name: 'burp_unknown_tool', description: 'Burp Suite tool: unknown_tool',
    inputSchema: { type: 'object', properties: {} }
  });
  bridge.send(toolCall(2));
  await waitFor(() => bridge.responses.length === 2);
  assert.deepEqual(JSON.parse(bridge.responses[1].result.content[0].text), { ok: true });
  for (let id = 3; id < 8; id++) bridge.send({ jsonrpc: '2.0', id, method: 'tools/list' });
  await waitFor(() => bridge.responses.length === 7);
  for (const response of bridge.responses.slice(2)) assert.deepEqual(response.result.tools, tools);
  assert.equal(bridge.discoveries, 1);
});
