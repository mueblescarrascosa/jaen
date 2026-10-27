#!/usr/bin/env python3
"""Comprobación de la guía antes de publicar.

Abre index.html en un navegador sin pantalla (Playwright + Chromium), sin
depender de la red, y verifica que la guía arranca y pinta lo esencial.
Uso:  python3 comprobar.py [ruta/a/index.html]
Sale con código 0 si todo va bien y 1 si algo falla (y explica qué).
"""
import asyncio, json, pathlib, re, sys, datetime

RUTA = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "index.html").resolve()


def tiempo_falso(n):
    hoy = datetime.date.today()
    dias = [str(hoy + datetime.timedelta(i)) for i in range(8)]
    d = {"time": dias, "weather_code": [1] * 8, "temperature_2m_max": [22] * 8,
         "temperature_2m_min": [10] * 8, "precipitation_probability_max": [10] * 8,
         "sunset": [x + "T19:20" for x in dias], "snowfall_sum": [0] * 8,
         "wind_gusts_10m_max": [20] * 8}
    return [{"daily": d} for _ in range(n)]


async def main():
    from playwright.async_api import async_playwright
    html = RUTA.read_text(encoding="utf-8")
    n_sitios = len(re.findall(r'\{ id:"\w+", z:"Z\d"', html))
    fallos = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 390, "height": 844})
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))

        async def meteo(r):
            u = r.request.url
            n = u.split("latitude=")[1].split("&")[0].count(",") + 1
            await r.fulfill(status=200, body=json.dumps(tiempo_falso(n)),
                            headers={"content-type": "application/json", "access-control-allow-origin": "*"})
        await pg.route("https://api.open-meteo.com/**", meteo)
        await pg.route(re.compile(r"^https://(?!api\.open-meteo).*"), lambda r: r.abort())
        await pg.goto(RUTA.as_uri())
        await pg.wait_for_timeout(1500)

        def comprobar(cond, msg):
            if not cond:
                fallos.append(msg)

        tarjetas = await pg.evaluate('document.querySelectorAll(".card").length')
        comprobar(n_sitios > 0 and tarjetas == n_sitios, f"Se pintan {tarjetas} fichas y DATA tiene {n_sitios}")
        hoy = await pg.inner_text("#todaybox")
        comprobar(len(hoy.strip()) > 20, "El bloque «Hoy y mañana» sale vacío")
        finde = await pg.evaluate('document.getElementById("findebox").innerHTML.length')
        comprobar(finde > 200, "El bloque «Este finde» sale vacío")
        wx = await pg.evaluate('!document.getElementById("todayWx").hidden')
        comprobar(wx, "No se pinta el tiempo")
        esc = await pg.evaluate('document.querySelectorAll("[data-esc]").length')
        comprobar(esc >= 5, f"Solo hay {esc} escapadas")
        bares = await pg.evaluate('document.querySelectorAll("#barlist .barcard").length')
        comprobar(bares >= 5, f"Solo hay {bares} bares en la lista")
        rutas = await pg.evaluate('document.querySelectorAll("#routes .route").length')
        comprobar(rutas >= 5, f"Solo hay {rutas} rutas")
        copas = await pg.evaluate('document.querySelectorAll("#cplist .barcard").length')
        comprobar(copas == 0, "No debería haber copas")
        nav = await pg.evaluate('document.querySelectorAll("#bnav [data-nav]").length')
        comprobar(nav == 6, "Falta la barra de navegación")
        # interacción básica: marcar, añadir al plan y filtrar
        primero = await pg.evaluate('document.querySelector(".card").getAttribute("data-id")')
        await pg.evaluate(f'document.querySelector(\'.card[data-id="{primero}"] [data-toggle]\').click()')
        await pg.evaluate(f'document.querySelector(\'.card[data-id="{primero}"] [data-plan]\').click()')
        await pg.wait_for_timeout(200)
        marcado = await pg.evaluate(f'document.querySelector(\'.card[data-id="{primero}"]\').classList.contains("done")')
        comprobar(marcado, "Marcar como visitado no funciona")
        plan = await pg.evaluate('!document.getElementById("planbar").hidden')
        comprobar(plan, "Añadir al plan no funciona")
        # pantallas: cada botón enseña una sola vista
        for nav, vista in [("sitios","sitios"),("mapa","mapa"),("bares","comer"),("escapadas","escapadas"),("plan","plan"),("agenda","hoy")]:
            await pg.evaluate(f'document.querySelector(\'#bnav [data-nav="{nav}"]\').click()')
            await pg.wait_for_timeout(120)
            vis_v = await pg.evaluate('[...document.querySelectorAll(".view")].filter(v=>!v.hidden).map(v=>v.dataset.view)')
            comprobar(vis_v == [vista], f"El botón {nav} enseña {vis_v} en vez de {vista}")
        # saltar desde una ruta a su ficha cambia de pantalla
        await pg.evaluate('document.querySelector("#routes [data-jump]").click()')
        await pg.wait_for_timeout(300)
        vis_v = await pg.evaluate('[...document.querySelectorAll(".view")].filter(v=>!v.hidden).map(v=>v.dataset.view)')
        comprobar(vis_v == ["sitios"], f"Tocar una parada de ruta no lleva a la ficha (vista {vis_v})")
        # pestañas de Comer y beber
        await pg.evaluate('document.querySelector(\'#bnav [data-nav="bares"]\').click()')
        for cm, sec in [("especial","especial"),("bares","bares")]:
            await pg.evaluate(f'document.querySelector(\'[data-cm="{cm}"]\').click()')
            ok = await pg.evaluate(f'!!document.getElementById("{sec}").offsetParent')
            comprobar(ok, f"La pestaña {cm} no enseña su sección")
        await pg.evaluate('document.querySelector(\'#bnav [data-nav="sitios"]\').click()')
        await pg.wait_for_timeout(120)
        await pg.fill("#q", "castillo")
        await pg.wait_for_timeout(200)
        vis = await pg.evaluate('[...document.querySelectorAll(".card")].filter(c=>c.offsetParent).length')
        comprobar(0 < vis < tarjetas, f"El buscador no filtra (visibles: {vis})")
        comprobar(not errores, "Errores de JavaScript: " + " | ".join(errores[:3]))
        await b.close()
    if fallos:
        print("FALLA la comprobación:")
        for f in fallos:
            print(" -", f)
        sys.exit(1)
    print(f"OK: {tarjetas} fichas, {esc} escapadas, {bares} bares, {rutas} rutas; sin errores de JavaScript.")


asyncio.run(main())
