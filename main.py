from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from supabase import create_client, Client
from datetime import date
from datetime import datetime
from weasyprint import HTML as WeasyHTML
import os
import json

# Configura tus credenciales de Supabase (usa variables de entorno o colócalas directamente)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://groeopgrcwrdwezosihk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdyb2VvcGdyY3dyZHdlem9zaWhrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3ODM3NDAsImV4cCI6MjA3MjM1OTc0MH0.eY77OAWesw9YtDugKF--O_0QI3a7nXdl7YA_7Ghofhw")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


app = FastAPI(title="Cotizador Supabase")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

from collections import defaultdict

@app.get("/", response_class=HTMLResponse)
def list_quotes(request: Request, search: str = None, status: str = None):
    query = supabase.table("quotes").select("*")

    if status and status != "Todas":
        query = query.eq("status", status)

   response = query.order("date", desc=True).execute()

if not response or not response.data:
    quotes = []
else:
    quotes = response.data

    # ✅ Obtener todos los items de todas las cotizaciones en una sola consulta
 items_response = supabase.table("items").select("*").execute()

if not items_response or not items_response.data:
    all_items = []
else:
    all_items = items_response.data

    # ✅ Agrupar por quote_id usando defaultdict
    items_por_cotizacion = defaultdict(list)
    for item in all_items:
        items_por_cotizacion[item["quote_id"]].append(item)

    filtered_quotes = []

    for q in quotes:
        q["folio"] = f"SE{800 + q['id']:05d}"

        # Formateo de fecha
        if isinstance(q.get("date"), str):
            try:
                fecha = datetime.fromisoformat(q["date"])
                q["formatted_date"] = fecha.strftime('%d-%m-%Y')
            except ValueError:
                q["formatted_date"] = "Fecha inválida"
        else:
            q["formatted_date"] = "Sin fecha"

        # ✅ Asociar los items ya agrupados
        q["servicios"] = items_por_cotizacion[q["id"]]

        # 🔍 Lógica del buscador
        if search:
            search_lower = search.lower()
            cliente_ok = search_lower in q["client_name"].lower()
            servicio_ok = any(search_lower in it["description"].lower() for it in q["servicios"])
            if cliente_ok or servicio_ok:
                filtered_quotes.append(q)
        else:
            filtered_quotes.append(q)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "quotes": filtered_quotes,
        "search": search,
        "status": status or "Todas"
    })




@app.get("/quotes/new", response_class=HTMLResponse)
def new_quote_form(request: Request):
    return templates.TemplateResponse("quote_new.html", {"request": request})

@app.get("/quotes/{quote_id}/edit", response_class=HTMLResponse)
def edit_quote(quote_id: int, request: Request):
    # Obtener la cotización
    quote = supabase.table("quotes").select("*").eq("id", quote_id).single().execute().data
    if not quote:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    # Obtener servicios relacionados
    items = supabase.table("items").select("*").eq("quote_id", quote_id).execute().data
    quote["folio"] = f"SE{800 + quote['id']:05d}"
    
    # Serializar los items para JS
    items_json = json.dumps(items)

    return templates.TemplateResponse("quote_edit.html", {
        "request": request,
        "quote": quote,
        "items_json": items_json
    })
@app.post("/quotes/{quote_id}/update")
async def update_quote(
    quote_id: int,
    request: Request,
    client_name: str = Form(...),
    client_company: str = Form(""),
    client_email: str = Form(""),
    client_phone: str = Form(""),
    client_address: str = Form(""),
    currency: str = Form("MXN"),
    tax_rate: float = Form(0.0),
    discount_rate: float = Form(0.0),
    notes: str = Form(""),
    validity: str = Form("7 días."),
    payment_terms: str = Form(""),
    warranty: str = Form(""),
    status: str = Form(""),
    items_json: str = Form("[]")
):
    # Calcular totales
    items = json.loads(items_json or "[]")
    subtotal = sum([float(it.get("quantity", 0)) * float(it.get("unit_price", 0)) for it in items])
    discount_amount = subtotal * (discount_rate / 100)
    base = subtotal - discount_amount
    tax_amount = base * (tax_rate / 100)
    total = base + tax_amount

    # Actualizar cotización
    supabase.table("quotes").update({
        "client_name": client_name,
        "client_company": client_company,
        "client_email": client_email,
        "client_phone": client_phone,
        "client_address": client_address,
        "currency": currency,
        "tax_rate": tax_rate,
        "discount_rate": discount_rate,
        "notes": notes,
        "validity": validity,
        "payment_terms": payment_terms,
        "warranty": warranty,
        "status": status,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "total": total
    }).eq("id", quote_id).execute()

    # Eliminar servicios anteriores
    supabase.table("items").delete().eq("quote_id", quote_id).execute()

    # Insertar servicios nuevos
    for it in items:
        it["quote_id"] = quote_id
        it["amount"] = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))

    supabase.table("items").insert(items).execute()

    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)


@app.post("/quotes/create")
async def create_quote(
    request: Request,
    client_name: str = Form(...),
    client_company: str = Form(""),
    client_email: str = Form(""),
    client_phone: str = Form(""),
    client_address: str = Form(""),
    currency: str = Form("MXN"),
    tax_rate: float = Form(0.0),
    discount_rate: float = Form(0.0),
    notes: str = Form(""),
    validity: str = Form("7 días."),
    payment_terms: str = Form(""),
    warranty: str = Form(""),
    items_json: str = Form("[]")
):
    items = json.loads(items_json or "[]")
    subtotal = sum([float(it.get("quantity", 0)) * float(it.get("unit_price", 0)) for it in items])
    discount_amount = subtotal * (discount_rate / 100)
    base = subtotal - discount_amount
    tax_amount = base * (tax_rate / 100)
    total = base + tax_amount

    quote_data = {
        "client_name": client_name,
        "client_company": client_company,
        "client_email": client_email,
        "client_phone": client_phone,
        "client_address": client_address,
        "currency": currency,
        "tax_rate": tax_rate,
        "discount_rate": discount_rate,
        "notes": notes,
        "validity": validity,
        "payment_terms": payment_terms,
        "warranty": warranty,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "total": total,
        "date": date.today().isoformat()
    }

    result = supabase.table("quotes").insert(quote_data).execute()
    quote = result.data[0]
    quote_id = quote["id"]

    for it in items:
        it["quote_id"] = quote_id
        it["amount"] = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))

    supabase.table("items").insert(items).execute()

    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)

@app.get("/quotes/{quote_id}", response_class=HTMLResponse)
def view_quote(quote_id: int, request: Request):
    quote = supabase.table("quotes").select("*").eq("id", quote_id).single().execute().data
    items = supabase.table("items").select("*").eq("quote_id", quote_id).execute().data
    quote["folio"] = f"SE{800 + quote['id']:05d}"

    # ✅ Formatear la fecha para evitar .strftime en el template
    if isinstance(quote.get("date"), str):
        try:
            fecha = datetime.fromisoformat(quote["date"])
            quote["formatted_date"] = fecha.strftime('%d-%m-%Y')
        except ValueError:
            quote["formatted_date"] = "Fecha inválida"
    else:
        quote["formatted_date"] = "Sin fecha"

    return templates.TemplateResponse("quote_view.html", {
        "request": request,
        "quote": quote,
        "items": items,
        "settings": {}
    })


@app.get("/quotes/{quote_id}/pdf")
def generate_pdf(quote_id: int):
    quote = supabase.table("quotes").select("*").eq("id", quote_id).single().execute().data
    items = supabase.table("items").select("*").eq("quote_id", quote_id).execute().data
    quote["folio"] = f"SE{800 + quote['id']:05d}"

    if isinstance(quote.get("date"), str):
        try:
            fecha = datetime.fromisoformat(quote["date"])
            quote["formatted_date"] = fecha.strftime('%d-%m-%Y')
        except ValueError:
            quote["formatted_date"] = "Fecha inválida"
    else:
        quote["formatted_date"] = "Sin fecha"

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    logo_path = os.path.join(static_dir, "logo.png")

    html_content = templates.get_template("quote_pdf.html").render(
        quote=quote,
        items=items,
        settings={},
        logo_path=f"file://{logo_path}"  # O cámbialo si falla
    )

    output_path = f"/tmp/cotizacion_{quote['folio']}.pdf"  # Mejor usar /tmp en Render
    WeasyHTML(string=html_content).write_pdf(output_path)

    return FileResponse(output_path, media_type="application/pdf", filename=f"Cotización_{quote['folio']}.pdf")


@app.post("/quotes/{quote_id}/status")
def update_status(quote_id: int, status: str = Form(...)):
    supabase.table("quotes").update({"status": status}).eq("id", quote_id).execute()
    return RedirectResponse(url="/", status_code=303)

@app.post("/quotes/{quote_id}/delete")
def delete_quote(quote_id: int):
    supabase.table("items").delete().eq("quote_id", quote_id).execute()
    supabase.table("quotes").delete().eq("id", quote_id).execute()
    return RedirectResponse(url="/", status_code=303)

    

@app.get("/api/clientes")
def get_clients_autocomplete():
    data = supabase.table("quotes").select("client_name,client_company,client_email,client_phone,client_address").execute().data
    seen = set()
    result = []
    for c in data:
        key = tuple(c.values())
        if key not in seen:
            seen.add(key)
            result.append({
                "name": c["client_name"],
                "company": c["client_company"],
                "email": c["client_email"],
                "phone": c["client_phone"],
                "address": c["client_address"]
            })
    return result
