"""
SERVIDOR DE TRACKING — tracking_server.py
Subí este archivo a Render.com junto con requirements.txt
"""

from flask import Flask, request, send_file, jsonify
import sqlite3, io, datetime, base64, csv

app = Flask(__name__)
DB = "aperturas.db"

def db():
    return sqlite3.connect(DB)

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS envios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT, nombre TEXT, enviado_en TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS aperturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT, abierto_en TEXT, ip TEXT, user_agent TEXT)""")
    c.commit(); c.close()

# ── Pixel de tracking ─────────────────────────────────────────────────────────

@app.route("/t/<eid>.gif")
def pixel(eid):
    try:
        email = base64.urlsafe_b64decode(eid + "==").decode()
    except Exception:
        email = eid
    c = db()
    c.execute("INSERT INTO aperturas (email, abierto_en, ip, user_agent) VALUES (?,?,?,?)",
              (email, datetime.datetime.utcnow().isoformat(),
               request.remote_addr, request.headers.get("User-Agent", "")))
    c.commit(); c.close()
    gif = bytes([0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,0x80,0x00,
                 0x00,0xFF,0xFF,0xFF,0x00,0x00,0x00,0x21,0xF9,0x04,0x00,0x00,
                 0x00,0x00,0x00,0x2C,0x00,0x00,0x00,0x00,0x01,0x00,0x01,0x00,
                 0x00,0x02,0x02,0x44,0x01,0x00,0x3B])
    return send_file(io.BytesIO(gif), mimetype="image/gif")

# ── Registrar envío (lo llama enviar.py) ──────────────────────────────────────

@app.route("/reg", methods=["POST"])
def registrar():
    d = request.json
    c = db()
    c.execute("INSERT INTO envios (email, nombre, enviado_en) VALUES (?,?,?)",
              (d["email"], d.get("nombre",""), datetime.datetime.utcnow().isoformat()))
    c.commit(); c.close()
    return jsonify({"ok": True})

# ── Reporte HTML ──────────────────────────────────────────────────────────────

@app.route("/reporte")
def reporte():
    c = db()
    total = c.execute("SELECT COUNT(*) FROM envios").fetchone()[0]
    filas = c.execute("""
        SELECT e.email, e.nombre, e.enviado_en,
               COUNT(a.id) AS veces,
               MIN(a.abierto_en) AS primera
        FROM envios e
        LEFT JOIN aperturas a ON e.email = a.email
        GROUP BY e.email
        ORDER BY primera DESC NULLS LAST
    """).fetchall()
    c.close()

    abrieron = sum(1 for r in filas if r[3] > 0)
    tasa = round(abrieron / total * 100, 1) if total else 0

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Reporte mailing</title>
<style>
  body{{font-family:Arial,sans-serif;margin:32px;color:#222}}
  h1{{color:#2a5bd7}}
  .stats{{display:flex;gap:20px;margin:20px 0 28px}}
  .stat{{background:#f0f4ff;border-radius:10px;padding:18px 28px;text-align:center}}
  .stat .n{{font-size:2.2em;font-weight:700;color:#2a5bd7}}
  .stat .l{{font-size:.85em;color:#555;margin-top:4px}}
  table{{border-collapse:collapse;width:100%;font-size:14px}}
  th{{background:#2a5bd7;color:#fff;padding:10px 12px;text-align:left}}
  td{{padding:8px 12px;border-bottom:1px solid #eee}}
  tr:nth-child(even){{background:#f9f9f9}}
  .si{{color:#1a7a4a;font-weight:600}}
  .no{{color:#aaa}}
  .badge{{display:inline-block;background:#e6f4ee;color:#1a7a4a;border-radius:20px;padding:2px 10px;font-size:12px}}
</style></head><body>
<h1>📊 Reporte de mailing</h1>
<div class="stats">
  <div class="stat"><div class="n">{total}</div><div class="l">Enviados</div></div>
  <div class="stat"><div class="n">{abrieron}</div><div class="l">Abrieron</div></div>
  <div class="stat"><div class="n">{total - abrieron}</div><div class="l">No abrieron</div></div>
  <div class="stat"><div class="n">{tasa}%</div><div class="l">Tasa apertura</div></div>
</div>
<p><a href="/exportar" style="color:#2a5bd7">⬇ Descargar CSV</a></p>
<table>
<tr><th>Email</th><th>Nombre</th><th>Abrió</th><th>Veces</th><th>Primera apertura</th></tr>"""

    for email, nombre, enviado, veces, primera in filas:
        if veces > 0:
            html += f'<tr><td>{email}</td><td>{nombre or "-"}</td><td class="si">✓ Sí</td><td><span class="badge">{veces}x</span></td><td>{primera[:19] if primera else "-"}</td></tr>'
        else:
            html += f'<tr><td>{email}</td><td>{nombre or "-"}</td><td class="no">No</td><td>-</td><td>-</td></tr>'

    html += "</table></body></html>"
    return html

# ── Exportar CSV ──────────────────────────────────────────────────────────────

@app.route("/exportar")
def exportar():
    c = db()
    filas = c.execute("""
        SELECT e.email, e.nombre,
               CASE WHEN COUNT(a.id)>0 THEN 'Sí' ELSE 'No' END AS abrio,
               COUNT(a.id), MIN(a.abierto_en)
        FROM envios e
        LEFT JOIN aperturas a ON e.email = a.email
        GROUP BY e.email
    """).fetchall()
    c.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["email","nombre","abrio","veces","primera_apertura"])
    w.writerows(filas)
    return app.response_class(out.getvalue(), mimetype="text/csv",
           headers={"Content-Disposition":"attachment;filename=aperturas.csv"})

@app.route("/")
def home():
    return "Servidor de tracking activo ✓"

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
