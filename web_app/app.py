import io
import os
import sys
import tempfile
import uuid

from flask import Flask, jsonify, request, send_file, render_template

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gati_route_manager"))

from core.csv_exporter import export_route_csv, export_route_summary
from core.deduplicator import _normalize_key, deduplicate
from core.geocoder import geocode_routes
from core.pdf_parser import parse_pdf

app = Flask(__name__)
app.secret_key = "gati-route-manager"

_parsed: dict = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    file_id = str(uuid.uuid4())
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, f.filename)
    f.save(path)

    try:
        routes = parse_pdf(path)
        if not routes:
            return jsonify({"error": "No GATI routes found in this PDF"}), 400

        route_list = []
        for r in routes:
            dedup = deduplicate(r)
            route_list.append({
                "code": r.code,
                "date": r.date,
                "total_packages": r.total_packages,
                "unique_stops": dedup.unique_stops,
                "multi_package_count": len(dedup.multi_package_stops),
            })

        _parsed[file_id] = {"routes": routes, "tmpdir": tmp}
        return jsonify({"file_id": file_id, "routes": route_list, "filename": f.filename})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/export/<file_id>/<route_code>")
def export(file_id, route_code):
    data = _parsed.get(file_id)
    if not data:
        return jsonify({"error": "Session expired — re-upload the PDF"}), 404

    route = next((r for r in data["routes"] if r.code == route_code), None)
    if not route:
        return jsonify({"error": "Route not found"}), 404

    tmp = tempfile.mkdtemp()
    csv_path = export_route_csv(route, tmp)
    summary_path = export_route_summary(route, tmp)

    return send_file(csv_path, as_attachment=True, download_name=os.path.basename(csv_path), mimetype="text/csv")


@app.route("/geocode/<file_id>", methods=["POST"])
def geocode(file_id):
    data = _parsed.get(file_id)
    if not data:
        return jsonify({"error": "Session expired"}), 404

    body = request.get_json() or {}
    codes = body.get("routes", [r.code for r in data["routes"]])
    selected = [r for r in data["routes"] if r.code in codes]
    if not selected:
        return jsonify({"error": "No routes selected"}), 400

    coords = geocode_routes(selected)
    result = []
    for r in selected:
        seen = set()
        stops = []
        for pkg in r.packages:
            key = _normalize_key(pkg.street, pkg.postal_code)
            if key in seen:
                continue
            seen.add(key)
            c = coords.get(pkg.full_address)
            if c:
                stops.append({
                    "lat": c[0],
                    "lng": c[1],
                    "street": pkg.street,
                    "city": pkg.city,
                    "postal": pkg.postal_code,
                    "seq": pkg.seq,
                })
        dedup = deduplicate(r)
        result.append({
            "code": r.code,
            "stops": stops,
            "total_packages": r.total_packages,
            "unique_stops": dedup.unique_stops,
        })

    return jsonify({"routes": result})


@app.route("/summary/<file_id>")
def summary(file_id):
    data = _parsed.get(file_id)
    if not data:
        return jsonify({"error": "Session expired"}), 404

    result = []
    for r in data["routes"]:
        dedup = deduplicate(r)
        multi = [
            {"street": m.street, "city": m.city, "postal": m.postal_code,
             "count": m.package_count, "seqs": m.seqs}
            for m in dedup.multi_package_stops
        ]
        result.append({
            "code": r.code,
            "total_packages": r.total_packages,
            "unique_stops": dedup.unique_stops,
            "multi_package_stops": multi,
        })
    return jsonify({"routes": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
