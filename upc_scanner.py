import streamlit as st
from pyzbar.pyzbar import decode
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

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
        # Row: [Name, Brand, Image, UPC, Model Code]
        image_formula = f'=IMAGE("{car["image"]}")' if car["image"] else ""
        row = [car['title'], car['brand'], image_formula, car['upc'], car['model_code']]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"✅ Parked '{car['title']}'!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- SEARCH LOGIC ---
def lookup_upc(upc_code):
    """Checks UPC database."""
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
                "upc": upc_code,
                "model_code": ""
            }
    except:
        pass
    # Fallback if not found
    return {"title": "", "brand": "Hot Wheels", "image": "", "upc": upc_code, "model_code": ""}

def extract_model_code(image):
    """OCR to find patterns like JBB49-N7C5"""
    # 1. Pre-process (Make it black and white, high contrast)
    gray = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(gray)
    clean_img = enhancer.enhance(2.5) # Crank up contrast
    
    # 2. Read text
    text = pytesseract.image_to_string(clean_img)
    
    # 3. Regex Pattern: 5 alphanumeric, hyphen, 4 alphanumeric
    # Looks for: JBB49-N7C5 or similar
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4}'
    match = re.search(pattern, text)
    
    if match:
        return match.group(0)
    return None

# --- APP INTERFACE ---
st.title("🏎️ Hybrid HW Scanner")

if 'current_car' not in st.session_state:
    st.session_state['current_car'] = {
        "title": "", "brand": "Hot Wheels", "image": "", "upc": "", "model_code": ""
    }

st.write("### 1. Scan Car")
st.info("Upload back of card. We look for Barcodes AND Codes (e.g. JBB49-N7C5)")

uploaded_file = st.file_uploader("Upload Image", key="hybrid_uploader")

if uploaded_file:
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        if image.width > 1000:
            image.thumbnail((1000, 1000))
        
        st.image(image, caption="Scanning...", width=200)
        
        # A. TRY BARCODE
        decoded_objects = decode(image)
        if decoded_objects:
            found_upc = decoded_objects[0].data.decode("utf-8")
            st.success(f"🔹 Barcode: {found_upc}")
            
            # Auto-lookup UPC
            with st.spinner('Checking UPC DB...'):
                api_result = lookup_upc(found_upc)
                st.session_state['current_car'].update(api_result)

        # B. TRY TEXT CODE (OCR)
        with st.spinner('Reading text codes...'):
            found_code = extract_model_code(image)
            if found_code:
                st.success(f"🔹 Model Code: {found_code}")
                st.session_state['current_car']['model_code'] = found_code
            else:
                st.caption("No 'XXXXX-XXXX' code found in text.")

    except Exception as e:
        st.error(f"Error: {e}")

# --- DISPLAY & EDIT ---
car = st.session_state['current_car']

st.divider()
st.subheader("Car Details")

# EDITABLE FIELDS
col1, col2 = st.columns([1, 2])
with col1:
    if car['image']:
        st.image(car['image'])
    else:
        st.caption("No Image")

with col2:
    # If we found a Model Code but no Title, offer a Google Search link
    if car['model_code'] and not car['title']:
        st.info(f"💡 Found Code **{car['model_code']}** but no Name.")
        search_url = f"https://www.google.com/search?q=hot+wheels+{car['model_code']}"
        st.markdown(f"[👉 Click to ID this car on Google]({search_url})")

    new_title = st.text_input("Car Name", value=car['title'])
    new_brand = st.text_input("Series", value=car['brand'])
    new_code = st.text_input("Model Code", value=car['model_code'])
    
    # Update state
    car['title'] = new_title
    car['brand'] = new_brand
    car['model_code'] = new_code

    if st.button("💾 Add to Collection"):
        if not car['title']:
            st.error("Please enter a Car Name first!")
        else:
            success, msg = save_to_sheet(car)
            if success:
                st.balloons()
                st.success(msg)
                # Reset
                st.session_state['current_car'] = {
                    "title": "", "brand": "Hot Wheels", "image": "", "upc": "", "model_code": ""
                }
            else:
                st.warning(msg)
