"""
SERVIDOR DE TRACKING — tracking_server.py  v3 (PostgreSQL persistente)
La base de datos ahora vive en Supabase (gratis), no en el disco de Render.
Así los datos NUNCA se pierden aunque el servidor se duerma o redeploya.

En Render tenés que agregar una variable de entorno:
  DATABASE_URL = (la connection string de Supabase)
"""

from flask import Flask, request, send_file, jsonify
import psycopg2
import psycopg2.extras
import io, datetime, base64, csv, os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS envios (
        id SERIAL PRIMARY KEY,
        email TEXT,
        nombre TEXT,
        enviado_en TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS aperturas (
        id SERIAL PRIMARY KEY,
        email TEXT,
        abierto_en TIMESTAMP,
        ip TEXT,
        user_agent TEXT
    )""")
    conn.commit()
    cur.close()
    conn.close()

# ── Pixel de tracking ─────────────────────────────────────────────────────────

@app.route("/t/<eid>.gif")
def pixel(eid):
    try:
        email = base64.urlsafe_b64decode(eid + "==").decode()
    except Exception:
        email = eid
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO aperturas (email, abierto_en, ip, user_agent) VALUES (%s,%s,%s,%s)",
            (email, datetime.datetime.utcnow(),
             request.remote_addr, request.headers.get("User-Agent", ""))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
    gif = bytes([
        0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,0x80,0x00,
        0x00,0xFF,0xFF,0xFF,0x00,0x00,0x00,0x21,0xF9,0x04,0x00,0x00,
        0x00,0x00,0x00,0x2C,0x00,0x00,0x00,0x00,0x01,0x00,0x01,0x00,
        0x00,0x02,0x02,0x44,0x01,0x00,0x3B
    ])
    return send_file(io.BytesIO(gif), mimetype="image/gif")

# ── Registrar envío ───────────────────────────────────────────────────────────

@app.route("/reg", methods=["POST"])
def registrar():
    try:
        d = request.get_json(force=True)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO envios (email, nombre, enviado_en) VALUES (%s,%s,%s)",
            (d.get("email",""), d.get("nombre",""), datetime.datetime.utcnow())
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── Reporte HTML ──────────────────────────────────────────────────────────────

@app.route("/reporte")
def reporte():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT COUNT(*) FROM envios")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT
            e.email,
            MIN(e.nombre)       AS nombre,
            COUNT(a.id)         AS veces,
            MIN(a.abierto_en)   AS primera
        FROM envios e
        LEFT JOIN aperturas a ON lower(e.email) = lower(a.email)
        GROUP BY e.email
        ORDER BY MIN(a.abierto_en) DESC NULLS LAST
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()

    abrieron = sum(1 for r in filas if r["veces"] > 0)
    no_abr   = total - abrieron
    tasa     = round(abrieron / total * 100, 1) if total else 0

    rows_html = ""
    for r in filas:
        email   = r["email"] or ""
        nombre  = r["nombre"] or "-"
        veces   = r["veces"]
        primera = r["primera"].strftime("%Y-%m-%d %H:%M:%S") if r["primera"] else ""
        if veces > 0:
            rows_html += (
                f'<tr><td>{email}</td><td>{nombre}</td>'
                f'<td class="si">✓ Sí</td>'
                f'<td><span class="badge">{veces}x</span></td>'
                f'<td>{primera}</td></tr>'
            )
        else:
            rows_html += (
                f'<tr><td>{email}</td><td>{nombre}</td>'
                f'<td class="no">No</td><td>—</td><td>—</td></tr>'
            )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Reporte mailing</title>
<style>
  body{{font-family:Arial,sans-serif;margin:32px;color:#222;max-width:1100px}}
  h1{{color:#1d4ed8;margin-bottom:4px}}
  .sub{{color:#6b7280;margin-bottom:24px;font-size:14px}}
  .stats{{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}}
  .stat{{background:#eff6ff;border-radius:10px;padding:20px 32px;text-align:center;min-width:120px}}
  .stat .n{{font-size:2.4em;font-weight:700;color:#1d4ed8;line-height:1}}
  .stat .l{{font-size:13px;color:#6b7280;margin-top:6px}}
  table{{border-collapse:collapse;width:100%;font-size:14px}}
  th{{background:#1d4ed8;color:#fff;padding:10px 14px;text-align:left;font-weight:600}}
  td{{padding:9px 14px;border-bottom:1px solid #f0f0f0}}
  tr:hover{{background:#f9fafb}}
  .si{{color:#065f46;font-weight:600}}
  .no{{color:#9ca3af}}
  .badge{{background:#dcfce7;color:#065f46;border-radius:20px;padding:2px 10px;font-size:12px;font-weight:600}}
  a{{color:#1d4ed8;text-decoration:none;font-size:14px}}
  a:hover{{text-decoration:underline}}
</style></head><body>
<h1>📊 Reporte de mailing</h1>
<p class="sub">Actualizado en tiempo real · <a href="/exportar">⬇ Descargar CSV para Excel</a></p>
<div class="stats">
  <div class="stat"><div class="n">{total}</div><div class="l">Enviados</div></div>
  <div class="stat"><div class="n">{abrieron}</div><div class="l">Abrieron</div></div>
  <div class="stat"><div class="n">{no_abr}</div><div class="l">No abrieron</div></div>
  <div class="stat"><div class="n">{tasa}%</div><div class="l">Tasa apertura</div></div>
</div>
<table>
  <tr><th>Email</th><th>Nombre</th><th>Abrió</th><th>Veces</th><th>Primera apertura</th></tr>
  {rows_html}
</table>
</body></html>"""
    return html

# ── Exportar CSV ──────────────────────────────────────────────────────────────

@app.route("/exportar")
def exportar():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT
            e.email,
            MIN(e.nombre) AS nombre,
            CASE WHEN COUNT(a.id) > 0 THEN 'Si' ELSE 'No' END AS abrio,
            COUNT(a.id) AS veces,
            MIN(a.abierto_en) AS primera
        FROM envios e
        LEFT JOIN aperturas a ON lower(e.email) = lower(a.email)
        GROUP BY e.email
        ORDER BY abrio DESC
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()

    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["email", "nombre", "abrio", "veces", "primera_apertura"])
    for r in filas:
        primera = r["primera"].strftime("%Y-%m-%d %H:%M:%S") if r["primera"] else ""
        w.writerow([r["email"], r["nombre"], r["abrio"], r["veces"], primera])

    return app.response_class(
        out.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=aperturas.csv"}
    )

# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return "Servidor de tracking activo ✓ (PostgreSQL)"

# ── Init ──────────────────────────────────────────────────────────────────────

if DATABASE_URL:
    try:
        init_db()
    except Exception as e:
        print(f"Error inicializando DB: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
