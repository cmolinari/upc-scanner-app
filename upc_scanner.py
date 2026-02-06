import streamlit as st
from pyzbar.pyzbar import decode
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import base64

# --- CONFIGURATION ---
SHEET_NAME = "My Collection"

# --- GOOGLE SHEETS SETUP ---
def get_sheet_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        return None

def save_to_sheet(car):
    sheet = get_sheet_connection()
    if not sheet:
        return False, "❌ Error: Could not connect to Google Sheet."
    try:
        image_formula = f'=IMAGE("{car["image"]}")' if car["image"] else ""
        row = [car['title'], car['brand'], image_formula, car['upc'], car['model_code']]
        sheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"✅ Parked '{car['title']}'!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- URL GENERATOR (No Scraping) ---
def generate_collecthw_url(code):
    """Generates the search URL without visiting it (avoids 403 block)"""
    try:
        clean_code = code.split("-")[0].strip()
        encoded_bytes = base64.b64encode(clean_code.encode("utf-8"))
        encoded_str = encoded_bytes.decode("utf-8")
        return f"https://collecthw.com/hw/search/{encoded_str}"
    except:
        return None

# --- UPC LOGIC ---
def lookup_upc(upc_code):
    url = "https://api.upcitemdb.com/prod/trial/lookup"
    try:
        response = requests.get(url, params={"upc": upc_code})
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            item = data["items"][0]
            return {
                "title": item.get("title", ""),
                "brand": item.get("brand", "Hot Wheels"),
                "image": item.get("images", [""])[0] if item.get("images") else "",
                "upc": upc_code
            }
    except:
        pass
    return {"title": "", "brand": "Hot Wheels", "image": "", "upc": upc_code}

def extract_model_code(image):
    gray = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(gray)
    clean_img = enhancer.enhance(2.5)
    text = pytesseract.image_to_string(clean_img)
    
    # Pattern: 5 chars, dash, 4 chars (e.g. JBC19-N7C6)
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4}'
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return None

# --- APP INTERFACE ---
st.title("🏎️ HW Quick-Link Scanner")

if 'current_car' not in st.session_state:
    st.session_state['current_car'] = {
        "title": "", "brand": "Hot Wheels", "image": "", "upc": "", "model_code": ""
    }

st.info("Upload card back. We generate the database link for you.")
uploaded_file = st.file_uploader("Upload Image", key="final_uploader")

if uploaded_file:
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        if image.width > 1000:
            image.thumbnail((1000, 1000))
        
        st.image(image, caption="Scanning...", width=200)
        
        # 1. UPC Scan
        decoded_objects = decode(image)
        if decoded_objects:
            found_upc = decoded_objects[0].data.decode("utf-8")
            st.caption(f"UPC: {found_upc}")
            api_result = lookup_upc(found_upc)
            st.session_state['current_car'].update(api_result)

        # 2. Text Code Scan
        found_code = extract_model_code(image)
        if found_code:
            st.success(f"🔹 Found Code: {found_code}")
            st.session_state['current_car']['model_code'] = found_code
            
            # GENERATE LINK
            db_link = generate_collecthw_url(found_code)
            if db_link:
                st.markdown(f"### 👉 [Identify on CollectHW]({db_link})")
                st.caption("Click above to see the car name, then type it below.")

    except Exception as e:
        st.error(f"Error: {e}")

# --- DISPLAY & EDIT ---
car = st.session_state['current_car']

st.divider()
col1, col2 = st.columns([1, 2])
with col1:
    if car['image']:
        st.image(car['image'])

with col2:
    new_title = st.text_input("Car Name", value=car['title'])
    new_brand = st.text_input("Series", value=car['brand'])
    new_code = st.text_input("Model Code", value=car['model_code'])
    
    car['title'] = new_title
    car['brand'] = new_brand
    car['model_code'] = new_code

    if st.button("💾 Save to Collection"):
        if not car['title']:
            st.error("Enter a Name first!")
        else:
            success, msg = save_to_sheet(car)
            if success:
                st.success(msg)
                st.session_state['current_car'] = {
                    "title": "", "brand": "Hot Wheels", "image": "", "upc": "", "model_code": ""
                }
                st.rerun()
            else:
                st.warning(msg)
