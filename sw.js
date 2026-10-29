const CACHE="jaen-v4";
const ASSETS=["./","./index.html"];
self.addEventListener("install",e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).catch(()=>{}));});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith("jaen-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener("fetch",e=>{
  const req=e.request;
  if(req.method!=="GET")return;
  const url=new URL(req.url);
  // El tiempo va siempre a la red (la app ya guarda su propia copia de 1 h)
  if(url.hostname==="api.open-meteo.com"||url.hostname.endsWith("tile.openstreetmap.org"))return;
  // Páginas: red primero, y si no hay conexión, la copia guardada
  if(req.mode==="navigate"){
    e.respondWith(fetch(req).then(r=>{const c=r.clone();caches.open(CACHE).then(k=>k.put("./index.html",c));return r;})
      .catch(()=>caches.match("./index.html").then(r=>r||caches.match("./"))));
    return;
  }
  // Resto (fuentes, etc.): copia guardada al momento y se refresca por detrás
  e.respondWith(caches.open(CACHE).then(cache=>cache.match(req).then(cached=>{
    const network=fetch(req).then(resp=>{if(resp&&(resp.ok||resp.type==="opaque")){try{cache.put(req,resp.clone());}catch(_){}}return resp;}).catch(()=>cached);
    return cached||network;
  })));
});
