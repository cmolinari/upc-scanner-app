import streamlit as st
from pyzbar.pyzbar import decode
from PIL import Image, ImageOps
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
SHEET_NAME = "My Collection" # Rename your Google Sheet to this!

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
        # Check if we already have this UPC
        # (Note: For Hot Wheels, you might want duplicates, but we'll flag them)
        existing_upcs = sheet.col_values(4) # Column D is UPC
        
        # Formula for Image
        image_formula = f'=IMAGE("{car["image"]}")' if car["image"] else ""
        
        # Row: [Name, Brand/Series, Image, UPC]
        row = [car['title'], car['brand'], image_formula, car['upc']]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"✅ Parked '{car['title']}' in your garage!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- PRODUCT LOOKUP (UPC API) ---
def get_toy_data(upc_code):
    clean_upc = upc_code.strip()
    
    # We use the free UPCitemdb API
    url = "https://api.upcitemdb.com/prod/trial/lookup"
    params = {"upc": clean_upc}
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if "items" in data and len(data["items"]) > 0:
            item = data["items"][0]
            return {
                "title": item.get("title", "Unknown Hot Wheels"),
                "brand": item.get("brand", "Mattel"),
                "image": item.get("images", [""])[0] if item.get("images") else "",
                "upc": clean_upc
            }
        else:
            # Fallback for when API finds nothing
            return {
                "title": "Unknown Hot Wheels (Enter Name)",
                "brand": "Hot Wheels",
                "image": "",
                "upc": clean_upc
            }
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

# --- APP INTERFACE ---
st.title("🏎️ Hot Wheels Scanner")

if 'current_car' not in st.session_state:
    st.session_state['current_car'] = None

st.write("### Scan Card Back")
st.info("Upload photo of the Barcode")

uploaded_file = st.file_uploader("Upload Image", key="hw_uploader")

if uploaded_file:
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        if image.width > 1000:
            image.thumbnail((1000, 1000))
        
        st.image(image, caption="Scanning...", width=200)
        
        decoded_objects = decode(image)
        if decoded_objects:
            upc = decoded_objects[0].data.decode("utf-8")
            st.success(f"UPC Found: {upc}")
            
            if st.button(f"🔍 Look up Car"):
                with st.spinner('Checking Database...'):
                    car_info = get_toy_data(upc)
                    st.session_state['current_car'] = car_info
        else:
            st.warning("❌ No barcode detected.")
    except Exception as e:
        st.error(f"Error: {e}")

# --- DISPLAY & EDIT & SAVE ---
if st.session_state['current_car']:
    car = st.session_state['current_car']
    
    st.divider()
    st.subheader("Car Details")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        if car['image']:
            st.image(car['image'])
        else:
            st.info("No image found")
            
    with col2:
        # EDITABLE FIELDS (Crucial for Hot Wheels)
        new_title = st.text_input("Car Name", value=car['title'])
        new_brand = st.text_input("Series / Brand", value=car['brand'])
        
        # Update our session object if user types something new
        car['title'] = new_title
        car['brand'] = new_brand

        if st.button("💾 Add to Collection"):
            success, msg = save_to_sheet(car)
            if success:
                st.balloons()
                st.success(msg)
                st.session_state['current_car'] = None
            else:
                st.warning(msg)
