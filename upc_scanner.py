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
        image_formula = f'=IMAGE("{car["image"]}")' if car["image"] else ""
        row = [car['title'], car['brand'], image_formula, car['upc'], car['model_code']]
        sheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"✅ Parked '{car['title']}'!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- OFFICIAL WIKI API (The "Secret Door") ---
def search_wiki_api(code):
    """Asks the Wiki API directly for the page title. No scraping."""
    
    # Clean the code (JBC19-N7C6 -> "JBC19")
    clean_code = code.split("-")[0].strip()
    
    # The API Endpoint
    url = "https://hotwheels.fandom.com/api.php"
    
    # The parameters asking for a search
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": clean_code,  # What we are looking for
        "srlimit": 1             # Just give us the #1 best match
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        # Dig into the JSON response
        if "query" in data and "search" in data["query"]:
            results = data["query"]["search"]
            if len(results) > 0:
                # The 'title' of the page is usually the car name!
                # e.g. "Mazda Savanna RX-7 FC3S (2025)"
                title = results[0]["title"]
                
                # Construct a clean link to that page
                # Wiki titles use underscores instead of spaces in URLs
                wiki_link = f"https://hotwheels.fandom.com/wiki/{title.replace(' ', '_')}"
                
                return title, wiki_link
    except:
        pass
        
    return None, None

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
    
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4}'
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return None

# --- APP INTERFACE ---
st.title("🏎️ HW Bot Scanner (API Edition)")

if 'current_car' not in st.session_state:
    st.session_state['current_car'] = {
        "title": "", "brand": "Hot Wheels", "image": "", "upc": "", "model_code": ""
    }

st.info("Upload card back. We use the Official Wiki API to find the name.")
uploaded_file = st.file_uploader("Upload Image", key="api_uploader")

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
            
            # 3. ASK THE WIKI API
            if not st.session_state['current_car']['title']:
                with st.spinner(f"Asking Wiki Database for {found_code}..."):
                    wiki_title, wiki_link = search_wiki_api(found_code)
                    
                    if wiki_title:
                        st.balloons()
                        st.success(f"✨ Identified: {wiki_title}")
                        st.session_state['current_car']['title'] = wiki_title
                        st.markdown(f"[View Wiki Page]({wiki_link})")
                    else:
                        st.warning("Code valid, but no exact Wiki match found.")

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
