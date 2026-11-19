import {expect,it} from 'vitest';
import {ORB_RADIUS} from '../components/voice-orb';
it('draws the ball 30% larger than before and keeps it, with its wobble, inside the canvas',()=>{
 expect(ORB_RADIUS/0.252).toBeCloseTo(1.3,5);
 expect(ORB_RADIUS*1.25).toBeLessThan(0.5);  // the surface can swell by about 20% while the AI speaks
});
