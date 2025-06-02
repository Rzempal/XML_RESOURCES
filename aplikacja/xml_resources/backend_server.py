# v18_enhanced_debugging_logs
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
        # Sprawdźmy różne kodowania
        raw_content = file.read()
        print(f"DEBUG_ENCODING (v18): Rozmiar pliku: {len(raw_content)} bajtów", file=sys.stderr)
        print(f"DEBUG_ENCODING (v18): Pierwsze 200 bajtów (raw): {raw_content[:200]}", file=sys.stderr)
        
        # Próbujemy różne kodowania
        xml_content = None
        encodings_to_try = ['utf-8', 'cp1252', 'utf-16', 'iso-8859-1']
        
        for encoding in encodings_to_try:
            try:
                xml_content = raw_content.decode(encoding)
                print(f"DEBUG_ENCODING (v18): Pomyślnie zdekodowano z {encoding}", file=sys.stderr)
                break
            except UnicodeDecodeError as e:
                print(f"DEBUG_ENCODING (v18): Błąd dekodowania z {encoding}: {e}", file=sys.stderr)
                continue
        
        if xml_content is None:
            xml_content = raw_content.decode('utf-8', errors='replace')
            print(f"DEBUG_ENCODING (v18): Użyto UTF-8 z errors='replace'", file=sys.stderr)
        
        print(f"DEBUG_ENCODING (v18): Pierwsze 500 znaków XML: {xml_content[:500]}", file=sys.stderr)
        
        result_data = analyze_station_data(xml_content)
        
        try:
            json_output_for_log = json.dumps(result_data, indent=2, ensure_ascii=False)
            print(f"DEBUG_JSON_OUTPUT (v18): Finalny obiekt RESULT:\n{json_output_for_log}", file=sys.stderr)
        except Exception as json_log_e:
            print(f"BŁĄD_LOGOWANIA_JSON (v18): {json_log_e}", file=sys.stderr)
        
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
        print(f"DEBUG_COJT (v18): Element o ID '{current_element_id}' nie znaleziony.", file=sys.stderr)
        return aggregated_cojt_data_from_this_branch

    current_element_name = get_name_from_element(current_element) or "ElementBezNazwy"
    print(f"DEBUG_COJT (v18): ===== Analizuję element: '{current_element_name}' (ID: {current_element_id}, Tag: {current_element.tag}) =====", file=sys.stderr)

    # NOWE: Sprawdźmy wszystkie atrybuty elementu
    print(f"DEBUG_STRUCTURE (v18): Atrybuty elementu '{current_element_name}': {current_element.attrib}", file=sys.stderr)
    
    # NOWE: Sprawdźmy wszystkie bezpośrednie dzieci
    direct_children = list(current_element)
    print(f"DEBUG_STRUCTURE (v18): Element '{current_element_name}' ma {len(direct_children)} bezpośrednich dzieci:", file=sys.stderr)
    for child in direct_children:
        child_name = get_name_from_element(child) or "BezNazwy"
        print(f"DEBUG_STRUCTURE (v18):   - Tag: {child.tag}, Nazwa: '{child_name}', Atrybuty: {child.attrib}", file=sys.stderr)

    direct_cojt_files_in_current_element = [] 
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]
    print(f"DEBUG_COJT (v18): Element '{current_element_name}' ma {len(children_ids)} dzieci referencyjnych: {children_ids}", file=sys.stderr)

    # NOWE: Sprawdźmy czy istnieją elementy Pm3DRep bezpośrednio w XML
    pm3drep_elements = current_element.findall(".//Pm3DRep")
    print(f"DEBUG_STRUCTURE (v18): Znaleziono {len(pm3drep_elements)} elementów Pm3DRep w poddrzewie '{current_element_name}'", file=sys.stderr)
    for pm3d in pm3drep_elements:
        pm3d_name = get_name_from_element(pm3d) or "BezNazwy"
        print(f"DEBUG_STRUCTURE (v18):   - Pm3DRep: '{pm3d_name}', ID: {pm3d.get('ExternalId', 'BrakID')}", file=sys.stderr)
        if pm3d_name.lower().endswith('.cojt'):
            print(f"DEBUG_STRUCTURE (v18):     ^^^ TO JEST PLIK .COJT! ^^^", file=sys.stderr)

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element: 
            print(f"DEBUG_COJT (v18): Dziecko ref. o ID '{child_id}' nie znalezione w mapie.", file=sys.stderr)
            continue

        child_name = get_name_from_element(child_element) or "DzieckoBezNazwy"
        print(f"DEBUG_COJT (v18): Analizuję dziecko: '{child_name}' (ID: {child_id}, Tag: {child_element.tag})", file=sys.stderr)

        if child_element.tag == "Pm3DRep" and child_name.lower().endswith(".cojt"):
            direct_cojt_files_in_current_element.append(child_name)
            print(f"DEBUG_COJT (v18): +++ ZNALEZIONO .cojt: '{child_name}' +++", file=sys.stderr)
        
        elif child_element.tag != "PmCompoundResource": 
            # Sprawdźmy copies
            copies_element = child_element.find("copies") 
            if copies_element is not None:
                for item_tag_in_copies in copies_element.findall("item"): 
                    ref_ext_id = item_tag_in_copies.text.strip() if item_tag_in_copies.text else None
                    if ref_ext_id:
                        ref_obj = all_objects_map_by_id.get(ref_ext_id)
                        if ref_obj is not None and ref_obj.tag == "Pm3DRep":
                            pm3drep_name = get_name_from_element(ref_obj)
                            if pm3drep_name and pm3drep_name.lower().endswith(".cojt"):
                                direct_cojt_files_in_current_element.append(pm3drep_name)
                                print(f"DEBUG_COJT (v18): +++ .cojt przez <copies>: '{pm3drep_name}' +++", file=sys.stderr)

    if direct_cojt_files_in_current_element:
        category_segment = current_element_name
        if robot_core_name and category_segment and category_segment.startswith(robot_core_name):
            category_segment = category_segment[len(robot_core_name):].lstrip("-").lstrip("_")
        if not category_segment: 
            category_segment = get_name_from_element(current_element) or "Folder_COJT"

        final_category_key_list = path_segments_list + [category_segment]
        final_category_key = "/".join(filter(None, final_category_key_list))
        if not final_category_key: 
            final_category_key = "Root_COJT_Files"

        if final_category_key not in aggregated_cojt_data_from_this_branch:
            aggregated_cojt_data_from_this_branch[final_category_key] = []
        aggregated_cojt_data_from_this_branch[final_category_key].extend(direct_cojt_files_in_current_element)
        aggregated_cojt_data_from_this_branch[final_category_key] = list(set(aggregated_cojt_data_from_this_branch[final_category_key]))
        print(f"DEBUG_COJT (v18): KATEGORIA: '{final_category_key}', PLIKI: {direct_cojt_files_in_current_element}", file=sys.stderr)

    # Rekurencja dla PmCompoundResource
    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if child_element and child_element.tag == "PmCompoundResource": 
            child_folder_name_raw = get_name_from_element(child_element) or "PodfolderBezNazwy"
            
            current_folder_segment_for_path = current_element_name
            if robot_core_name and current_folder_segment_for_path and current_folder_segment_for_path.startswith(robot_core_name):
                 current_folder_segment_for_path = current_folder_segment_for_path[len(robot_core_name):].lstrip("-").lstrip("_")
            if not current_folder_segment_for_path: 
                current_folder_segment_for_path = get_name_from_element(current_element) or "FolderPosredni"
            
            new_path_segments = path_segments_list + [current_folder_segment_for_path]
            
            print(f"DEBUG_COJT (v18): Rekurencja dla podfolderu '{child_folder_name_raw}', ścieżka: {new_path_segments}", file=sys.stderr)
            sub_folder_cojt_data = find_cojt_data_recursive(child_id, robot_core_name, new_path_segments)

            for category_from_sub, files_from_sub in sub_folder_cojt_data.items():
                if category_from_sub in aggregated_cojt_data_from_this_branch:
                    aggregated_cojt_data_from_this_branch[category_from_sub].extend(files_from_sub)
                    aggregated_cojt_data_from_this_branch[category_from_sub] = list(set(aggregated_cojt_data_from_this_branch[category_from_sub]))
                else:
                    aggregated_cojt_data_from_this_branch[category_from_sub] = files_from_sub
    
    print(f"DEBUG_COJT (v18): Zakończono dla '{current_element_name}'. Dane: {aggregated_cojt_data_from_this_branch}", file=sys.stderr)
    return aggregated_cojt_data_from_this_branch

def analyze_station_data(xml_content):
    global all_objects_map_by_id
    
    # NOWE: Sprawdźmy podstawową strukturę XML
    print(f"DEBUG_XML_STRUCTURE (v18): Długość XML: {len(xml_content)} znaków", file=sys.stderr)
    
    root = ET.fromstring(xml_content)
    print(f"DEBUG_XML_STRUCTURE (v18): Root tag: {root.tag}, atrybuty: {root.attrib}", file=sys.stderr)
    
    # NOWE: Sprawdźmy wszystkie typy elementów w XML
    all_tags = set()
    element_count = 0
    for elem in root.iter():
        all_tags.add(elem.tag)
        element_count += 1
    print(f"DEBUG_XML_STRUCTURE (v18): Znaleziono {element_count} elementów, unikalne tagi: {sorted(all_tags)}", file=sys.stderr)
    
    all_objects_map_by_id = {}
    for elem in root.iter():
        external_id = elem.get("ExternalId")
        if external_id:
            all_objects_map_by_id[external_id.strip()] = elem
    
    print(f"DEBUG (v18): Zbudowano mapę all_objects_map_by_id z {len(all_objects_map_by_id)} elementami.", file=sys.stderr)

    # NOWE: Sprawdźmy wszystkie Pm3DRep w całym XML
    all_pm3drep = root.findall(".//Pm3DRep")
    print(f"DEBUG_PM3DREP (v18): Znaleziono {len(all_pm3drep)} elementów Pm3DRep w całym XML:", file=sys.stderr)
    cojt_count = 0
    for pm3d in all_pm3drep:
        name = get_name_from_element(pm3d) or "BezNazwy"
        if name.lower().endswith('.cojt'):
            cojt_count += 1
            print(f"DEBUG_PM3DREP (v18):   COJT #{cojt_count}: '{name}' (ID: {pm3d.get('ExternalId', 'BrakID')})", file=sys.stderr)
        else:
            print(f"DEBUG_PM3DREP (v18):   Inne: '{name}' (ID: {pm3d.get('ExternalId', 'BrakID')})", file=sys.stderr)

    pr_station_element = root.find(".//PrStation")
    if not pr_station_element:
        print("BŁĄD: Nie znaleziono elementu PrStation.", file=sys.stderr)
        return {"station": "Błąd - PrStation nie znalezione", "robots": [], "all_cojt_column_headers": []}

    station_name = get_name_from_element(pr_station_element) or "Nieznana stacja"
    print(f"INFO: Analizowana stacja: {station_name}", file=sys.stderr)

    robots_data_list = []
    all_cojt_headers_set = set() 
    station_children_ids = [item.text.strip() for item in pr_station_element.findall("./children/item") if item.text]
    print(f"DEBUG (v18): Stacja ma {len(station_children_ids)} dzieci: {station_children_ids}", file=sys.stderr)

    for robot_external_id in station_children_ids:
        robot_element = all_objects_map_by_id.get(robot_external_id)
        if not robot_element:
            print(f"DEBUG (v18): Robot ID '{robot_external_id}' nie znaleziony w mapie", file=sys.stderr)
            continue
            
        if robot_element.tag != "PmCompoundResource":
            print(f"DEBUG (v18): Element '{robot_external_id}' nie jest PmCompoundResource (tag: {robot_element.tag})", file=sys.stderr)
            continue

        robot_full_name = get_name_from_element(robot_element)
        print(f"DEBUG (v18): Sprawdzam element: '{robot_full_name}' (tag: {robot_element.tag})", file=sys.stderr)
        
        if not (robot_full_name and any(keyword in robot_full_name.upper() for keyword in ["IR", "ROBOT"])):
            print(f"DEBUG (v18): Element '{robot_full_name}' nie zawiera IR ani ROBOT - pomijam", file=sys.stderr)
            continue

        robot_core_name = robot_full_name
        match = re.search(r"^(.*?IR\d{2})", robot_full_name.upper())
        if match:
            robot_core_name = robot_full_name[:len(match.group(1))]
        
        print(f"INFO (v18): ROBOT ZNALEZIONY: '{robot_core_name}' (Pełna nazwa: '{robot_full_name}')", file=sys.stderr)
        
        robot_cojt_data_aggregated_for_this_robot = {} 
        robot_main_children_ids = [item.text.strip() for item in robot_element.findall("./children/item") if item.text]
