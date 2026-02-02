from flask import Flask, render_template, request, send_file
import fitz  # PyMuPDF
import os
from decimal import Decimal

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
ORIGINAL_PDF = os.path.join(UPLOAD_FOLDER, "original.pdf")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ==========================
# RECT HELPERS
# ==========================
def wipe_rect(page, rect):
    r = fitz.Rect(rect)
    page.add_redact_annot(r, fill=(1, 1, 1))
    page.apply_redactions()


def write_in_rect(page, rect, text, fontsize=8):
    r = fitz.Rect(rect)
    page.insert_text(
        (r.x0 + 1, r.y1 - 2),
        str(text),
        fontsize=fontsize,
        fontname="helv"
    )


# ==========================
# COORDINATES
# ==========================
HEADER_COORDS = {
    "customer_name": (125.84, 110.15, 272.87, 122.43),
    "address": (125.84, 124.65, 347.06, 134.70),
    "invoice_no": (482.60, 110.13, 524.41, 120.18),
    "date": (479.85, 120.98, 523.99, 131.03),
    "license_no": (75.06, 181.90, 173.89, 191.95),
}

TABLE_COLS = {
    "sr": 54.7,
    "name": 72.1,
    "qty": 208.5,
    "batch": 249.7,
    "expiry": 330.3,
    "price": 388.6,
    "discount": 505.6,
    "amount": 546.0,
}

ROW_START_Y = 221.4
ROW_HEIGHT = 9.5

# ==========================
# TOTAL / VALUE RECTANGLES
# ==========================
GROSS_RECT = (
    438.29998779296875,
    265.5940246582031,
    463.9139709472656,
    275.6470031738281
)

GROSS_VALUE_RECT = (
    540.8499755859375,
    265.3440246582031,
    567.8770141601562,
    275.3970031738281
)

NET_RECT = (
    434.2040100097656,
    325.49798583984375,
    450.3139953613281,
    336.66796875
)

NET_PAYABLE_WIPE_RECT = (
    530.0,                 # x0 → thora left
    323.0,                 # y0
    580.0,                 # x1 → thora right
    340.0                  # y1
)


PAYABLE_RECT = (
    540.8499755859375,
    325.49798583984375,
    567.8770141601562,
    336.66796875
)


TOTAL_RECT = (539.33, 242.04, 573.66, 252.09)

# ==========================
# MAIN PROCESS
# ==========================
def process_invoice(data):

    if not os.path.exists(ORIGINAL_PDF):
        return None

    doc = fitz.open(ORIGINAL_PDF)
    page = doc[0]

    # -------- HEADER --------
    for key, rect in HEADER_COORDS.items():
        wipe_rect(page, rect)
        write_in_rect(page, rect, data.get(key, ""), fontsize=8.5)

    # -------- ITEMS --------
    table_rect = fitz.Rect(
        50,
        ROW_START_Y - 2,
        580,
        ROW_START_Y + (len(data["items"]) * ROW_HEIGHT) + 2
    )
    wipe_rect(page, table_rect)

    total_gross = Decimal("0.00")
    total_net_payable = Decimal("0.00")

    for i, item in enumerate(data["items"]):
        y = ROW_START_Y + i * ROW_HEIGHT

        qty = Decimal(item["qty"] or 0)
        price = Decimal(item["price"] or 0)
        disc = Decimal(item["discount"] or 0)

        total_gross += price * qty

        discounted_price = price - (price * disc / Decimal("100"))
        amount = discounted_price * qty
        total_net_payable += amount

        page.insert_text((TABLE_COLS["sr"], y + ROW_HEIGHT), str(i + 1), fontsize=8)
        page.insert_text((TABLE_COLS["name"], y + ROW_HEIGHT), item["name"], fontsize=8)
        page.insert_text((TABLE_COLS["qty"], y + ROW_HEIGHT), str(int(qty)), fontsize=8)
        page.insert_text((TABLE_COLS["batch"], y + ROW_HEIGHT), item["batch"], fontsize=8)
        page.insert_text((TABLE_COLS["expiry"], y + ROW_HEIGHT), item["expiry"], fontsize=8)
        page.insert_text((TABLE_COLS["price"], y + ROW_HEIGHT), f"{price:.2f}", fontsize=8)
        page.insert_text((TABLE_COLS["discount"], y + ROW_HEIGHT), f"{disc}%", fontsize=8)
        page.insert_text((TABLE_COLS["amount"], y + ROW_HEIGHT), f"{amount:.2f}", fontsize=8)

    # -------- TOTALS (CORRECT WAY) --------

    # GROSS → replace static printed value only
    wipe_rect(page, GROSS_VALUE_RECT)
    write_in_rect(
    page,
    GROSS_VALUE_RECT,
    f"{total_gross:.2f}",
    fontsize=9
    )

    # NET PAYABLE → replace static printed value only
    # NET PAYABLE → exact purani value replace
    wipe_rect(page, NET_PAYABLE_WIPE_RECT)
    write_in_rect(
    page,
    PAYABLE_RECT,
    f"{total_net_payable:.2f}",
    fontsize=9
    )

    # COMPANY TOTAL
    wipe_rect(page, TOTAL_RECT)
    write_in_rect(
        page,
        TOTAL_RECT,
        f"{total_net_payable:.2f}",
        fontsize=9
    )

    # -------- SAVE PDF --------
    output_path = os.path.join(
        OUTPUT_FOLDER,
        f"Invoice_{data['invoice_no']}.pdf"
    )

    doc.save(output_path)
    doc.close()

    return output_path



# ==========================
# ROUTES
# ==========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():

    items = []

    names = request.form.getlist("item_name[]")
    qtys = request.form.getlist("qty[]")
    batches = request.form.getlist("batch[]")
    expiries = request.form.getlist("expiry[]")
    prices = request.form.getlist("price[]")
    discounts = request.form.getlist("discount[]")

    for i in range(len(names)):
        if names[i]:
            items.append({
                "name": names[i],
                "qty": qtys[i],
                "batch": batches[i],
                "expiry": expiries[i],
                "price": prices[i],
                "discount": discounts[i],
            })

    data = {
        "customer_name": request.form.get("customer_name"),
        "address": request.form.get("address"),
        "invoice_no": request.form.get("invoice_no"),
        "date": request.form.get("date"),
        "license_no": request.form.get("license_no"),
        "items": items,
    }

    pdf_path = process_invoice(data)
    return send_file(pdf_path, as_attachment=True)


# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    app.run(debug=True, port=4000)
