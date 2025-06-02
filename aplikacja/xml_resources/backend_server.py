# backend_server_py_v16_log_final_json.py
# Importowanie niezbędnych bibliotek
from flask import Flask, request, jsonify
from flask_cors import CORS
import xml.etree.ElementTree as ET
import sys
import os
import re 
import json # Import modułu json do sformatowania logu

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
        result_data = analyze_station_data(xml_content) # Zmieniono nazwę zmiennej na result_data
        
        # === DODANE LOGOWANIE FINALNEGO JSON ===
        try:
            json_output_for_log = json.dumps(result_data, indent=2, ensure_ascii=False)
            print(f"DEBUG_JSON_OUTPUT (v16): Finalny obiekt RESULT przygotowany do wysłania:\n{json_output_for_log}", file=sys.stderr)
        except Exception as json_log_e:
            print(f"BŁĄD_LOGOWANIA_JSON (v16): Nie udało się sformatować result_data do JSON dla logu: {json_log_e}", file=sys.stderr)
            print(f"DEBUG_JSON_OUTPUT (v16): Surowe result_data: {result_data}", file=sys.stderr)
        # === KONIEC LOGOWANIA FINALNEGO JSON ===
        
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
        # print(f"DEBUG_COJT (v16): Element o ID '{current_element_id}' (ścieżka: '{'/'.join(path_segments_list)}') nie znaleziony.", file=sys.stderr)
        return aggregated_cojt_data_from_this_branch

    current_element_name = get_name_from_element(current_element) or "ElementBezNazwy"
    # print(f"DEBUG_COJT (v16): Rekurencja dla: '{current_element_name}' (ID: {current_element_id}), Ścieżka: {path_segments_list}", file=sys.stderr)

    direct_cojt_files_in_current_element = [] 
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element: continue

        child_name = get_name_from_element(child_element) or "DzieckoBezNazwy"

        if child_element.tag == "Pm3DRep" and child_name.lower().endswith(".cojt"):
            direct_cojt_files_in_current_element.append(child_name)
            # print(f"DEBUG_COJT (v16): +++ Pm3DRep .cojt: '{child_name}' jako dziecko '{current_element_name}' +++", file=sys.stderr)
        
        elif child_element.tag != "PmCompoundResource": 
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
                                # print(f"DEBUG_COJT (v16): +++ .cojt ('{pm3drep_name}') przez <copies> z '{child_name}' (w '{current_element_name}') +++", file=sys.stderr)

    if direct_cojt_files_in_current_element:
        category_segment = current_element_name
        if robot_core_name and category_segment.startswith(robot_core_name):
            category_segment = category_segment[len(robot_core_name):].lstrip("-").lstrip("_")
        if not category_segment: category_segment = get_name_from_element(current_element) or "Folder_COJT"

        final_category_key_list = path_segments_list + [category_segment]
        final_category_key = "/".join(filter(None, final_category_key_list))
        if not final_category_key: final_category_key = "Root_COJT_Files"

        if final_category_key not in aggregated_cojt_data_from_this_branch:
            aggregated_cojt_data_from_this_branch[final_category_key] = []
        aggregated_cojt_data_from_this_branch[final_category_key].extend(direct_cojt_files_in_current_element)
        aggregated_cojt_data_from_this_branch[final_category_key] = list(set(aggregated_cojt_data_from_this_branch[final_category_key]))
        # print(f"DEBUG_COJT (v16): Kategoria COJT: '{final_category_key}', pliki: {direct_cojt_files_in_current_element}", file=sys.stderr)

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if child_element and child_element.tag == "PmCompoundResource": 
            current_folder_segment_for_path = current_element_name
            if robot_core_name and current_folder_segment_for_path.startswith(robot_core_name):
                 current_folder_segment_for_path = current_folder_segment_for_path[len(robot_core_name):].lstrip("-").lstrip("_")
            if not current_folder_segment_for_path: current_folder_segment_for_path = get_name_from_element(current_element) or "FolderPosredni"
            
            new_path_segments = path_segments_list + [current_folder_segment_for_path]
            sub_folder_cojt_data = find_cojt_data_recursive(child_id, robot_core_name, new_path_segments)

            for category_from_sub, files_from_sub in sub_folder_cojt_data.items():
                if category_from_sub in aggregated_cojt_data_from_this_branch:
                    aggregated_cojt_data_from_this_branch[category_from_sub].extend(files_from_sub)
                    aggregated_cojt_data_from_this_branch[category_from_sub] = list(set(aggregated_cojt_data_from_this_branch[category_from_sub]))
                else:
                    aggregated_cojt_data_from_this_branch[category_from_sub] = files_from_sub
    
    return aggregated_cojt_data_from_this_branch

def analyze_station_data(xml_content):
    global all_objects_map_by_id
    root = ET.fromstring(xml_content)
    all_objects_map_by_id = {}
    for elem in root.iter():
        external_id = elem.get("ExternalId")
        if external_id:
            all_objects_map_by_id[external_id.strip()] = elem
    
    # print(f"DEBUG (v16): Zbudowano mapę all_objects_map_by_id z {len(all_objects_map_by_id)} elementami.", file=sys.stderr)

    pr_station_element = root.find(".//PrStation")
    if not pr_station_element:
        print("BŁĄD: Nie znaleziono elementu PrStation.", file=sys.stderr)
        return {"station": "Błąd - PrStation nie znalezione", "robots": [], "all_cojt_column_headers": []}

    station_name = get_name_from_element(pr_station_element) or "Nieznana stacja"
    # print(f"INFO: Analizowana stacja: {station_name}", file=sys.stderr)

    robots_data_list = []
    all_cojt_headers_set = set() 
    station_children_ids = [item.text.strip() for item in pr_station_element.findall("./children/item") if item.text]

    for robot_external_id in station_children_ids:
        robot_element = all_objects_map_by_id.get(robot_external_id)
        if not robot_element or robot_element.tag != "PmCompoundResource":
            continue

        robot_full_name = get_name_from_element(robot_element)
        if not (robot_full_name and any(keyword in robot_full_name.upper() for keyword in ["IR", "ROBOT"])):
            continue

        robot_core_name = robot_full_name
        match = re.search(r"^(.*?IR\d{2})", robot_full_name.upper())
        if match:
            robot_core_name = robot_full_name[:len(match.group(1))]
        
        # print(f"INFO (v16): Zidentyfikowano robota: '{robot_core_name}'", file=sys.stderr)
        
        robot_cojt_data_aggregated_for_this_robot = {} 
        robot_main_children_ids = [item.text.strip() for item in robot_element.findall("./children/item") if item.text]

        for main_child_id in robot_main_children_ids: 
            main_child_element = all_objects_map_by_id.get(main_child_id)
            if main_child_element and main_child_element.tag == "PmCompoundResource": 
                # main_child_name = get_name_from_element(main_child_element) or "FolderGlownyBezNazwy"
                # print(f"DEBUG (v16): Wywołanie find_cojt_data_recursive dla '{main_child_name}'", file=sys.stderr)
                cojt_found_in_branch = find_cojt_data_recursive(main_child_id, robot_core_name, path_segments_list=[]) 
                
                for category, files in cojt_found_in_branch.items():
                    all_cojt_headers_set.add(category) 
                    if category in robot_cojt_data_aggregated_for_this_robot:
                        robot_cojt_data_aggregated_for_this_robot[category].extend(files)
                        robot_cojt_data_aggregated_for_this_robot[category] = list(set(robot_cojt_data_aggregated_for_this_robot[category]))
                    else:
                        robot_cojt_data_aggregated_for_this_robot[category] = files
            
        robots_data_list.append({
            "robot": robot_core_name,
            "cojt_data": robot_cojt_data_aggregated_for_this_robot
        })

    sorted_cojt_headers = sorted(list(all_cojt_headers_set))
    # print(f"INFO (v16): Końcowa nazwa stacji: {station_name}, znaleziono robotów: {len(robots_data_list)}", file=sys.stderr)
    # print(f"DEBUG (v16): Wykryte globalne nagłówki kolumn COJT: {sorted_cojt_headers}", file=sys.stderr)
    # for r_data in robots_data_list:
    #     print(f"DEBUG (v16): Robot: {r_data['robot']}, Finalne Dane COJT: {r_data['cojt_data']}", file=sys.stderr)

    return {"station": station_name, "robots": robots_data_list, "all_cojt_column_headers": sorted_cojt_headers}

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)
