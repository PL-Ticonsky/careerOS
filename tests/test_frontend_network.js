// Exercise the actual browser request/polling functions with a dropped connection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');

function runtime(code, fetch) {
  const timers = new Map(), nodes = new Map(), notices = [];
  let counter = 0;
  const context = {
    AbortController, TypeError, Error, fetch, console,
    setTimeout(fn, delay) {
      const id = ++counter;
      if (delay === 500) queueMicrotask(fn);
      else timers.set(id, {fn, delay});
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
    $(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {disabled: false, textContent: '', classList: {toggle() {}, remove() {}}});
      return nodes.get(selector);
    },
    sourceName: id => id,
    notice: message => notices.push(message),
    refresh: async () => { context.refreshCount++; },
    refreshCount: 0, busyPolling: false, pollTimer: undefined
  };
  vm.createContext(context); vm.runInContext(code, context);
  return {context, timers, nodes, notices};
}

(async () => {
  const apiCode = source.slice(source.indexOf('async function api('), source.indexOf('\nfunction notice('));
  let calls = 0;
  const get = runtime(apiCode, async () => {
    if (++calls === 1) throw new TypeError('Failed to fetch');
    return {ok: true, json: async () => ({running: true})};
  });
  assert.equal((await get.context.api('sync/progress')).running, true);
  assert.equal(calls, 2, 'A read is retried after a transient failure');
  assert.equal(get.timers.size, 0, 'Request timeout timers are cleaned up');

  calls = 0;
  const post = runtime(apiCode, async () => { calls++; throw new TypeError('Failed to fetch'); });
  await assert.rejects(post.context.api('sync/start', {}), error => error.network === true && !error.message.includes('Failed to fetch'));
  assert.equal(calls, 1, 'A possibly accepted write is never replayed automatically');

  const pollCode = source.slice(source.indexOf('let syncConnectionLost'), source.indexOf("$('#add').onclick"));
  const poll = runtime(pollCode);
  const transient = Object.assign(new Error('Disconnected'), {network: true});
  poll.context.api = async () => { throw transient; };
  await poll.context.pollSync();
  assert.equal(poll.context.refreshCount, 0, 'A failed progress request is not treated as completion');
  const reconnect = [...poll.timers.values()].find(timer => timer.delay === 2000);
  assert.ok(reconnect, 'Polling schedules reconnection');
  poll.context.api = async () => ({running: false, results: [], completed: 3, total: 3});
  await reconnect.fn();
  assert.equal(poll.context.refreshCount, 1, 'Recovered polling refreshes the feed');
  assert.ok(poll.notices.some(message => message.includes('Actualización terminada')));

  const droppedStart = runtime(pollCode);
  let starts = 0, reads = 0;
  droppedStart.context.api = async path => {
    if (path === 'sync/start') { starts++; throw transient; }
    reads++;
    return {running: true, results: [], current: 'test', completed: 0, total: 3};
  };
  await droppedStart.nodes.get('#sync').onclick();
  assert.equal(starts, 1);
  assert.equal(reads, 1, 'A dropped start response is resolved by reading progress');
  assert.equal(droppedStart.nodes.get('#sync').disabled, true);
  console.log('Network recovery checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
