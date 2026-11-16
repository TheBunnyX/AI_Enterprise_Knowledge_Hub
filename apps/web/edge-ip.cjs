// Preloaded before server.js (node -r). Next's rewrite proxy does not tell the API who the browser is, and it forwards
// whatever X-Forwarded-For the client sent, which anyone can forge. Here the web server states the truth itself:
//   - directly exposed:           X-Forwarded-For = the socket's remote address (client value discarded)
//   - behind a reverse proxy (WEB_BEHIND_PROXY=1): keep the proxy's header and append the socket address
// The API then reads the entry counted from the right (TRUSTED_PROXY_HOPS).
const http = require('http');
const create = http.createServer;
http.createServer = function (...args) {
  const i = args.findIndex((a) => typeof a === 'function');
  if (i >= 0) {
    const handler = args[i];
    args[i] = function (req, res) {
      const peer = (req.socket.remoteAddress || '').replace(/^::ffff:/, '');
      const kept = process.env.WEB_BEHIND_PROXY === '1' ? req.headers['x-forwarded-for'] : '';
      req.headers['x-forwarded-for'] = kept ? `${kept}, ${peer}` : peer;
      return handler.call(this, req, res);
    };
  }
  return create.apply(this, args);
};
