from flask import Flask, render_template, request, jsonify
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# ── PÁGINA 1: Búsqueda ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── PÁGINA 2: Información ─────────────────────────────────────────────────────
@app.route("/informacion")
def informacion():
    return render_template("informacion.html")


# ── API: Consulta principal ───────────────────────────────────────────────────
@app.route("/api/consulta", methods=["POST"])
def consulta():
    data  = request.get_json()
    tipo  = data.get("tipo", "cedula")
    valor = data.get("valor", "").strip()

    if not valor:
        return jsonify({"error": "Ingrese un valor de búsqueda"}), 400

    try:
        conn = get_conn()
        cur  = conn.cursor()

        # ── Buscar persona ────────────────────────────────────────────────────
        if tipo == "cedula":
            cur.execute("SELECT * FROM persona WHERE cedula = %s", (valor,))
        elif tipo == "nombre":
            like = f"%{valor}%"
            cur.execute(
                "SELECT * FROM persona WHERE nombres ILIKE %s OR apellidos ILIKE %s",
                (like, like)
            )
        else:
            return jsonify({"error": "Tipo de búsqueda no válido"}), 400

        persona = cur.fetchone()
        if not persona:
            return jsonify({"error": "No se encontraron resultados para ese valor"}), 404

        id_persona = persona["id_persona"]

        # ── Licencia más reciente ─────────────────────────────────────────────
        cur.execute(
            """SELECT l.*, pl.saldo_puntos AS puntos
               FROM licencia l
               LEFT JOIN puntos_licencia pl ON pl.id_persona = l.id_persona
               WHERE l.id_persona = %s
               ORDER BY l.fecha_emision DESC LIMIT 1""",
            (id_persona,)
        )
        licencia = cur.fetchone()

        # ── Citaciones con nombre de contravención ────────────────────────────
        cur.execute(
            """SELECT c.*, cv.nombre AS nombre_contravencion, cv.clase,
                      c.fecha_emision AS fecha
               FROM citacion c
               JOIN contravencion cv ON c.id_contravencion = cv.id_contravencion
               WHERE c.id_persona = %s
               ORDER BY c.fecha_emision DESC""",
            (id_persona,)
        )
        citaciones = cur.fetchall()

        # ── Historial de puntos ───────────────────────────────────────────────
        cur.execute(
            """SELECT hp.id_historial, hp.fecha, hp.observacion,
                      hp.puntos_anterior, hp.cantidad_puntos, hp.saldo_puntos,
                      hp.tipo_movimiento
               FROM historial_puntos hp
               WHERE hp.id_persona = %s
               ORDER BY hp.fecha DESC""",
            (id_persona,)
        )
        historial_puntos = cur.fetchall()

        cur.close()
        conn.close()

        def por_estado(estado):
            return [dict(c) for c in citaciones if c["estado"].upper() == estado.upper()]

        total_pendiente = sum(
            float(c["total_pagar"] or 0)
            for c in citaciones if c["estado"].upper() == "PENDIENTE"
        )

        return jsonify({
            "persona":         dict(persona),
            "licencia":        dict(licencia) if licencia else None,
            "citaciones":      [dict(c) for c in citaciones],
            "pendientes":      por_estado("PENDIENTE"),
            "pagadas":         por_estado("PAGADA"),
            "anuladas":        por_estado("ANULADA"),
            "impugnadas":      por_estado("IMPUGNADA"),
            "total_pendiente": round(total_pendiente, 2),
            "historial_puntos": [dict(h) for h in historial_puntos],
        })

    except psycopg2.Error as e:
        return jsonify({"error": f"Error de base de datos: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error inesperado: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)