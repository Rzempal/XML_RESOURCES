# backend_server_py_v19_aggressive_copies_debug.py            "robot": robot_core_name,
# Importowanie niezbędnych bibliotek
from flask import Flask, request, jsonify
from flask_cors import CORS
import xml.etree.ElementTree as ET
import sys
import os
import re 
import json 

# Inicjalizacja aplikacji Flask
app = Flask(__name__)
CORS(app)

# Ścieżka do pliku z hasłami
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASSWORD_FILE = os.path.join(BASE_DIR, "password")

VALID_PASSWORDS = []
try:
    with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
        VALID_PASSWORDS = [line.strip() for line in f if line.strip()]
    if VALID_PASSWORDS:
        print(f"INFO: Załadowano {len(VALID_PASSWORDS)} prawidłowych haseł.", file=sys.stderr)
    else:
        print(f"OSTRZEŻENIE: Nie załadowano żadnych haseł z pliku: {PASSWORD_FILE}.", file=sys.stderr)
except FileNotFoundError:
    print(f"BŁĄD KRYTYCZNY: Plik z hasłami '{PASSWORD_FILE}' nie został znaleziony.", file=sys.stderr)
except Exception as e:
    print(f"BŁĄD KRYTYCZNY: Nieoczekiwany błąd podczas ładowania pliku z hasłami '{PASSWORD_FILE}': {e}", file=sys.stderr)

all_objects_map_by_id = {}

@app.route("/analyze", methods=["POST"])
def analyze():
    print("INFO: Otrzymano żądanie do endpointu /analyze", file=sys.stderr)
    if "file" not in request.files or "password" not in request.form:
        return jsonify({"error": "Brak pliku lub hasła"}), 400

    file = request.files["file"]
    password = request.form["password"]
    if password not in VALID_PASSWORDS:
        print(f"BŁĄD: Nieprawidłowe hasło od użytkownika.", file=sys.stderr)
        return jsonify({"error": "Nieprawidłowe hasło"}), 403

    try:
        xml_content = file.read().decode("cp1252", errors="replace")
        result_data = analyze_station_data(xml_content)
        
        try:
            json_output_for_log = json.dumps(result_data, indent=2, ensure_ascii=False)
            print(f"DEBUG_JSON_OUTPUT (v18): Finalny obiekt RESULT przygotowany do wysłania:\n{json_output_for_log}", file=sys.stderr)
        except Exception as json_log_e:
            print(f"BŁĄD_LOGOWANIA_JSON (v18): Nie udało się sformatować result_data: {json_log_e}", file=sys.stderr)
            print(f"DEBUG_JSON_OUTPUT (v18): Surowe result_data: {result_data}", file=sys.stderr)
        
        return jsonify(result_data)
    except ET.ParseError as e:
        print(f"BŁĄD PARSOWANIA XML: {e}", file=sys.stderr)
        return jsonify({"error": f"Błąd parsowania pliku XML: {e}"}), 400
    except Exception as e:
        print(f"BŁĄD WEWNĘTRZNY: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Wewnętrzny błąd serwera."}), 500

def get_name_from_element(element):
    name_elem = element.find("name")
    return name_elem.text.strip() if name_elem is not None and name_elem.text else None

def find_cojt_data_recursive(current_element_id, robot_core_name, path_segments_list):
    global all_objects_map_by_id
    aggregated_cojt_data_from_this_branch = {} 
    current_element = all_objects_map_by_id.get(current_element_id)

    if not current_element:
        print(f"DEBUG_COJT (v18): Element o ID '{current_element_id}' (ścieżka: '{'/'.join(path_segments_list)}') nie znaleziony.", file=sys.stderr)
        return aggregated_cojt_data_from_this_branch

    current_element_name = get_name_from_element(current_element) or "ElementBezNazwy"
    print(f"DEBUG_COJT (v18): ===== Rekurencja dla: '{current_element_name}' (ID: {current_element_id}), Ścieżka: {path_segments_list} =====", file=sys.stderr)

    direct_cojt_files_in_current_element = [] 
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]
    # print(f"DEBUG_COJT (v18): Element '{current_element_name}' ma {len(children_ids)} dzieci ref: {children_ids}", file=sys.stderr)

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element: continue

        child_name = get_name_from_element(child_element) or "DzieckoBezNazwy"
        # print(f"DEBUG_COJT (v18): Analizuję dziecko ref: '{child_name}' (ID: {child_id}, Tag: {child_element.tag}) elementu '{current_element_name}'", file=sys.stderr)

        if child_element.tag == "Pm3DRep" and child_name.lower().endswith(".cojt"):
            direct_cojt_files_in_current_element.append(child_name)
            print(f"DEBUG_COJT (v18): +++ Znaleziono BEZPOŚREDNI Pm3DRep .cojt: '{child_name}' jako dziecko '{current_element_name}' +++", file=sys.stderr)
        
        elif child_element.tag != "PmCompoundResource": 
            # print(f"DEBUG_COJT (v18): Dziecko '{child_name}' ({child_element.tag}) nie jest PmCompoundResource. Sprawdzam <copies>...", file=sys.stderr)
            copies_element = child_element.find("copies") 
            if copies_element is not None:
                print(f"DEBUG_COJT (v18): Znaleziono tag <copies> w '{child_name}'. Iteruję po jego bezpośrednich dzieciach...", file=sys.stderr)
                found_items_in_copies_count = 0
                for sub_element_in_copies in copies_element: # === ZMIENIONA ITERACJA ===
                    print(f"DEBUG_COJT (v18):   Dziecko <copies>: Tag='{sub_element_in_copies.tag}', Text='{sub_element_in_copies.text}'", file=sys.stderr)
                    if sub_element_in_copies.tag == "item":
                        found_items_in_copies_count += 1
                        ref_ext_id = sub_element_in_copies.text.strip() if sub_element_in_copies.text else None
                        if ref_ext_id:
                            # print(f"DEBUG_COJT (v18):   Element '{child_name}' ma ref w <copies><item>: '{ref_ext_id}'", file=sys.stderr)
                            ref_obj = all_objects_map_by_id.get(ref_ext_id)
                            if ref_obj is not None and ref_obj.tag == "Pm3DRep":
                                pm3drep_name = get_name_from_element(ref_obj)
                                if pm3drep_name and pm3drep_name.lower().endswith(".cojt"):
                                    direct_cojt_files_in_current_element.append(pm3drep_name)
                                    print(f"DEBUG_COJT (v18):   +++ .cojt ('{pm3drep_name}') przez <copies><item> z '{child_name}' (w '{current_element_name}') +++", file=sys.stderr)
                                # else: print(f"DEBUG_COJT (v18):   Referowany Pm3DRep (ID: {ref_ext_id}) nie ma nazwy .cojt: '{pm3drep_name}'", file=sys.stderr)
                            # elif ref_obj is not None: print(f"DEBUG_COJT (v18):   Referowany obiekt (ID: {ref_ext_id}) nie jest Pm3DRep (Tag: {ref_obj.tag})", file=sys.stderr)
