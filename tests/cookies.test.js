const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'app.js'), 'utf8');

function load(cookie = '', hasBanner = true) {
    const banner = hasBanner ? { style: { display: 'none' } } : null;
    const writes = [];
    const document = { getElementById: () => banner, addEventListener() {} };
    Object.defineProperty(document, 'cookie', {
        get: () => cookie,
        set: value => { writes.push(value); }
    });
    const context = vm.createContext({ document });
    vm.runInContext(source, context);
    return { context, banner, writes };
}

test('visiting a page shows the notice without persisting dismissal', () => {
    const { banner, writes } = load();
    assert.equal(banner.style.display, 'block');
    assert.deepEqual(writes, []);
});

test('a previous explicit dismissal keeps the notice hidden', () => {
    const { banner, writes } = load('other=hello; avisocookies=1');
    assert.equal(banner.style.display, 'none');
    assert.deepEqual(writes, []);
});

test('cookie names must match exactly, not a suffix of another name', () => {
    const { context, banner } = load('noavisocookies=1; another=2');
    assert.equal(context.getCookie('avisocookies'), null);
    assert.equal(banner.style.display, 'block');
    assert.equal(Object.hasOwn(context, 'begin'), false);
    assert.equal(Object.hasOwn(context, 'end'), false);
});

test('a value other than the dismissal marker does not hide the notice', () => {
    assert.equal(load('avisocookies=0').banner.style.display, 'block');
});

test('pages without a notice do not crash or write cookies', () => {
    assert.deepEqual(load('', false).writes, []);
});

test('the existing OK handler still persists a root-scoped cookie and hides the notice', () => {
    const { context, banner, writes } = load();
    vm.runInContext("var expiration = new Date(); expiration.setTime(expiration.getTime() + (60000 * 60 * 24 * 365)); setCookie('avisocookies', '1', expiration, '/');document.getElementById('barracookies').style.display = 'none';", context);
    assert.equal(banner.style.display, 'none');
    assert.equal(writes.length, 1);
    assert.match(writes[0], /^avisocookies=1; expires=.+; path=\/$/);
});

test('cookie values support Unicode and delimiters, including old escape-encoded values', () => {
    const { context, writes } = load();
    context.setCookie('example', 'café;✓=1', null, '/', null, false);
    assert.equal(writes[0], 'example=caf%C3%A9%3B%E2%9C%93%3D1; path=/');
    assert.equal(load('example=caf%C3%A9%3B%E2%9C%93%3D1').context.getCookie('example'), 'café;✓=1');
    assert.equal(load('example=caf%E9%3B%u2713%3D1').context.getCookie('example'), 'café;✓=1');
});

test('empty cookies can be deleted and an explicit secure flag is respected', () => {
    const { context, writes } = load('empty=');
    context.delCookie('empty', '/');
    assert.match(writes[0], /^empty=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=\/$/);
    context.setCookie('secure', '1', null, '/', null, true);
    assert.equal(writes[1], 'secure=1; path=/; secure');
});
