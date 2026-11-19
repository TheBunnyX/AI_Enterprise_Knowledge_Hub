import {describe,expect,it,vi} from 'vitest';
import {api} from '../components/api';

describe('api()', () => {
  it('accepts an empty 204 answer (deleting a skill)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, {status: 204})));
    await expect(api('/skills/x', {method: 'DELETE'})).resolves.toBeUndefined();
  });
});
