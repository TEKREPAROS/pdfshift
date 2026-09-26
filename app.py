import base64
import os
import secrets
import tempfile
import time
from urllib.parse import quote
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import fitz
from flask import Flask, abort, jsonify, render_template, request, send_file
app = Flask(__name__, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 21 * 1024 * 1024
app.config["APPLICATION_ROOT"] = os.getenv("URL_PREFIX", "/xtoa4")
MAX_BYTES = 20 * 1024 * 1024
A4 = fitz.paper_rect("a4")
JOBS = {}
@app.post("/api/preview")
def preview():
    upload = request.files.get("pdf")
    if not upload or not upload.filename.lower().endswith(".pdf"):
        return jsonify(error="Selecione um arquivo PDF."), 400
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        phone = os.getenv("SUPPORT_WHATSAPP", "55984190295")
        msg = "Olá, preciso de ajuda para converter um PDF para A4. O arquivo excede 20 MB. Podem revisar?"
        return jsonify(error="O arquivo excede 20 MB e não foi processado.", whatsapp=f"https://wa.me/{phone}?text={quote(msg)}"), 413
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
        if not doc.page_count:
            raise ValueError("PDF sem páginas")
        pages = []
        feasible = True
        for page in doc:
            rect = page.rect
            scale = min(A4.width / rect.width, A4.height / rect.height)
            feasible &= scale >= 0.5
            pix = page.get_pixmap(matrix=fitz.Matrix(min(1.25, 1.25 * A4.width / rect.width, 1.25 * A4.height / rect.height), min(1.25, 1.25 * A4.width / rect.width, 1.25 * A4.height / rect.height)), alpha=False)
            pages.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
        job = secrets.token_urlsafe(24)
        JOBS[job] = (raw, time.time())
        return jsonify(job=job, pages=pages, page_count=doc.page_count, feasible=feasible, message="A conversão mantém todo o conteúdo vetorial e proporcional." if feasible else "Para caber em A4 sem cortes, o conteúdo precisaria ser reduzido a menos da metade. A conversão manterá tudo, mas poderá ficar difícil de ler.")
    except Exception:
        return jsonify(error="Não foi possível abrir este PDF. Verifique se o arquivo está íntegro e sem senha."), 400
@app.post("/api/convert/<job>")
def convert(job):
    item = JOBS.pop(job, None)
    if not item or time.time() - item[1] > 1800:
        abort(404)
    doc = fitz.open(stream=item[0], filetype="pdf")
    out = fitz.open()
    for page in doc:
        dst = out.new_page(width=A4.width, height=A4.height)
        rect = page.rect
        scale = min(A4.width / rect.width, A4.height / rect.height)
        target = fitz.Rect((A4.width - rect.width * scale) / 2, (A4.height - rect.height * scale) / 2, (A4.width + rect.width * scale) / 2, (A4.height + rect.height * scale) / 2)
        dst.show_pdf_page(target, doc, page.number)
    result = out.tobytes(garbage=4, deflate=True, deflate_fonts=True, deflate_images=True)
    doc.close(); out.close()
    from flask import Response
    return Response(result, mimetype="application/pdf", headers={"Content-Disposition": 'attachment; filename="documento_A4.pdf"'})
@app.get("/")
def index():
    return render_template("index.html")
@app.get("/<path:path>")
def subpath(path):
    if path == "api/preview" or path.startswith("api/convert/"):
        abort(404)
    return render_template("index.html")
application = DispatcherMiddleware(Flask("root"), {os.getenv("URL_PREFIX", "/xtoa4"): app})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
