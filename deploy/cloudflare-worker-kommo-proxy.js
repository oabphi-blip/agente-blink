// Cloudflare Worker — Kommo API proxy
// Deploy em: kommo-proxy.oabphi.workers.dev
// Criado em 07/06/2026 pra contornar 403 nginx do Cloudflare/WAF do Kommo
// no IP do Easypanel (2.24.110.21). Worker roda nos IPs da Cloudflare
// (não blocklistados), faz fetch interno até univeja.kommo.com.
//
// Quando o IP do Easypanel for whitelistado pelo Kommo support, mudar
// voice_agent/kommo.py:_base de volta pra "https://univeja.kommo.com/api/v4".

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const target = "https://univeja.kommo.com" + url.pathname + url.search;
    return fetch(target, {
      method: request.method,
      headers: request.headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "follow",
    });
  },
};
