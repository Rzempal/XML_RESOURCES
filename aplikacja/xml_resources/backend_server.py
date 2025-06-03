# backend_server_py_v20_cojt_parsing_fix.py
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
    VALID_PASSWORDS = ["dev"] # Fallback dla środowiska deweloperskiego bez pliku
    print(f"OSTRZEŻENIE: Użyto domyślnego hasła 'dev' z powodu braku pliku haseł.", file=sys.stderr)
except Exception as e:
    print(f"BŁĄD KRYTYCZNY: Nieoczekiwany błąd podczas ładowania pliku z hasłami '{PASSWORD_FILE}': {e}", file=sys.stderr)
    VALID_PASSWORDS = ["dev"]
    print(f"OSTRZEŻENIE: Użyto domyślnego hasła 'dev' z powodu błędu ładowania pliku haseł.", file=sys.stderr)

all_objects_map_by_id = {}

@app.route("/analyze", methods=["POST"])
def analyze():
    print("INFO (v20): Otrzymano żądanie do endpointu /analyze", file=sys.stderr)
    if "file" not in request.files or "password" not in request.form:
        print("BŁĄD (v20): Brak pliku lub hasła w żądaniu.", file=sys.stderr)
        return jsonify({"error": "Brak pliku lub hasła"}), 400

    file = request.files["file"]
    password = request.form["password"]
    if not VALID_PASSWORDS:
        print("BŁĄD KRYTYCZNY (v20): Lista VALID_PASSWORDS jest pusta. Nie można zweryfikować hasła.", file=sys.stderr)
        return jsonify({"error": "Błąd konfiguracji serwera - brak zdefiniowanych haseł."}), 500
        
    if password not in VALID_PASSWORDS:
        print(f"BŁĄD (v20): Nieprawidłowe hasło od użytkownika.", file=sys.stderr)
        return jsonify({"error": "Nieprawidłowe hasło"}), 403

    try:
        xml_content = file.read().decode("cp1252", errors="replace")
        # Inicjalizacja globalnej mapy obiektów dla każdego żądania
        global all_objects_map_by_id
        all_objects_map_by_id = {} 
        root = ET.fromstring(xml_content)
        for elem in root.iter():
            external_id = elem.get("ExternalId")
            if external_id:
                all_objects_map_by_id[external_id.strip()] = elem
        
        print(f"DEBUG (v20): Zbudowano mapę all_objects_map_by_id z {len(all_objects_map_by_id)} elementami.", file=sys.stderr)

        result_data = analyze_station_data(root) # Przekazujemy sparsowany root zamiast xml_content
        
        try:
            json_output_for_log = json.dumps(result_data, indent=2, ensure_ascii=False)
            print(f"DEBUG_JSON_OUTPUT (v20): Finalny obiekt RESULT przygotowany do wysłania:\n{json_output_for_log}", file=sys.stderr)
        except Exception as json_log_e:
            print(f"BŁĄD_LOGOWANIA_JSON (v20): Nie udało się sformatować result_data: {json_log_e}", file=sys.stderr)
            print(f"DEBUG_JSON_OUTPUT (v20): Surowe result_data: {result_data}", file=sys.stderr)
        
        return jsonify(result_data)
    except ET.ParseError as e:
        print(f"BŁĄD PARSOWANIA XML (v20): {e}", file=sys.stderr)
        return jsonify({"error": f"Błąd parsowania pliku XML: {e}"}), 400
    except Exception as e:
        print(f"BŁĄD WEWNĘTRZNY (v20): {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Wewnętrzny błąd serwera."}), 500

def get_name_from_element(element):
    # Helper function to get the name from an XML element
    name_elem = element.find("name")
    return name_elem.text.strip() if name_elem is not None and name_elem.text else None

def find_cojt_data_recursive(current_element_id, robot_core_name):
    # Recursively finds .cojt files under a given PmCompoundResource element.
    # Returns a dictionary where keys are cleaned "compound names" (tool names)
    # and values are lists of .cojt filenames.
    # path_segments_list is removed as column name is determined by the direct parent PmCompoundResource.
    
    global all_objects_map_by_id
    aggregated_cojt_data_for_this_node = {} 
    current_element = all_objects_map_by_id.get(current_element_id)

    if not current_element:
        print(f"DEBUG_COJT (v20): Element o ID '{current_element_id}' nie znaleziony w mapie.", file=sys.stderr)
        return aggregated_cojt_data_for_this_node

    current_element_name = get_name_from_element(current_element) or "ElementBezNazwy"
    # print(f"DEBUG_COJT (v20): Analizuję PmCompoundResource: '{current_element_name}' (ID: {current_element_id}) dla robota '{robot_core_name}'", file=sys.stderr)

    direct_cojt_files_in_current_element = [] 
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]

    # First pass: find direct .cojt files and Pm3DRep files linked via <copies>
    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element: continue

        child_name = get_name_from_element(child_element) or "DzieckoBezNazwy"
        
        if child_element.tag == "Pm3DRep" and child_name and child_name.lower().endswith(".cojt"):
            direct_cojt_files_in_current_element.append(child_name)
            print(f"DEBUG_COJT (v20): +++ Znaleziono BEZPOŚREDNI Pm3DRep .cojt: '{child_name}' jako dziecko '{current_element_name}'", file=sys.stderr)
        
        # Logic for <copies> - kept for potential other XML structures, though not effective for 03_HB1600.xml
        elif child_element.tag != "PmCompoundResource": # Only look for copies if not a compound itself
            copies_element = child_element.find("copies") 
            if copies_element is not None:
                # print(f"DEBUG_COJT (v20): Element '{child_name}' (ID: {child_id}) ma tag <copies>. Sprawdzam referencje...", file=sys.stderr)
                # Using findall('.//item') as it was the "most aggressive" in v19, though likely empty for 03_HB1600.xml
                all_descendant_items = copies_element.findall('.//item')
                if not all_descendant_items:
                    # Log if <copies> is present but empty, only once per <copies> tag
                    # print(f"DEBUG_COJT (v20): Tag <copies> w '{child_name}' (ID: {child_id}) nie zawiera elementów <item>.", file=sys.stderr)
                    pass

                for item_tag_from_descendants in all_descendant_items:
                    if item_tag_from_descendants.tag == "item": 
                        ref_ext_id = item_tag_from_descendants.text.strip() if item_tag_from_descendants.text else None
                        if ref_ext_id:
                            ref_obj = all_objects_map_by_id.get(ref_ext_id)
                            if ref_obj is not None and ref_obj.tag == "Pm3DRep":
                                pm3drep_name = get_name_from_element(ref_obj)
                                if pm3drep_name and pm3drep_name.lower().endswith(".cojt"):
                                    direct_cojt_files_in_current_element.append(pm3drep_name)
                                    print(f"DEBUG_COJT (v20):   +++ .cojt ('{pm3drep_name}') przez <copies> z '{child_name}' (w '{current_element_name}') +++", file=sys.stderr)

    # If direct .cojt files were found under this current_element (PmCompoundResource),
    # then current_element_name (cleaned) becomes a column header.
    if direct_cojt_files_in_current_element:
        column_key = current_element_name
        if robot_core_name and column_key and column_key.startswith(robot_core_name):
            column_key = column_key[len(robot_core_name):].lstrip("-").lstrip("_")
        
        if not column_key: # Handle cases where stripping leaves an empty string or name was initially empty
            column_key = "NarzędzieBezNazwy" # Default name if cleaning results in empty
        
        print(f"DEBUG_COJT (v20): Generowany klucz kolumny: '{column_key}' dla plików: {direct_cojt_files_in_current_element} (Rodzic: '{current_element_name}')", file=sys.stderr)

        if column_key not in aggregated_cojt_data_for_this_node:
            aggregated_cojt_data_for_this_node[column_key] = []
        aggregated_cojt_data_for_this_node[column_key].extend(direct_cojt_files_in_current_element)
        # Remove duplicates that might have been added (e.g. if a .cojt was listed twice)
        aggregated_cojt_data_for_this_node[column_key] = sorted(list(set(aggregated_cojt_data_for_this_node[column_key])))

    # Second pass: recurse for child PmCompoundResources and merge their results
    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if child_element and child_element.tag == "PmCompoundResource": 
            # Recursively call for child compounds
            sub_folder_cojt_data = find_cojt_data_recursive(child_id, robot_core_name)

            # Merge results from sub-folders
            for category_from_sub, files_from_sub in sub_folder_cojt_data.items():
                if category_from_sub not in aggregated_cojt_data_for_this_node:
                    aggregated_cojt_data_for_this_node[category_from_sub] = []
                aggregated_cojt_data_for_this_node[category_from_sub].extend(files_from_sub)
                # Ensure uniqueness and sort for consistent output
                aggregated_cojt_data_for_this_node[category_from_sub] = sorted(list(set(aggregated_cojt_data_for_this_node[category_from_sub])))
    
    return aggregated_cojt_data_for_this_node

def analyze_station_data(root): # Takes parsed XML root as input
    # Analyzes the XML data for a station, its robots, and their .cojt resources.
    global all_objects_map_by_id # Ensure it uses the pre-populated map

    pr_station_element = root.find(".//PrStation")
    if not pr_station_element:
        print("BŁĄD (v20): Nie znaleziono elementu PrStation.", file=sys.stderr)
        return {"station": "Błąd - PrStation nie znalezione", "robots": [], "all_cojt_column_headers": []}

    station_name = get_name_from_element(pr_station_element) or "Nieznana stacja"
    print(f"INFO (v20): Analizowana stacja: {station_name}", file=sys.stderr)

    robots_data_list = []
    all_cojt_headers_set = set() 
    station_children_ids = [item.text.strip() for item in pr_station_element.findall("./children/item") if item.text]

    for robot_external_id in station_children_ids:
        robot_element = all_objects_map_by_id.get(robot_external_id)
        # Ensure it's a PmCompoundResource and likely a robot by name convention
        if not robot_element or robot_element.tag != "PmCompoundResource":
            continue

        robot_full_name = get_name_from_element(robot_element)
        # Basic check if the name suggests it's a robot
        if not (robot_full_name and any(keyword in robot_full_name.upper() for keyword in ["IR", "ROBOT"])):
            continue # Skip if not clearly a robot

        # Attempt to extract a more "core" robot name, e.g., HB1610IR01
        robot_core_name = robot_full_name # Default to full name
        # Regex to find patterns like "XXXXIRYY" or "XXXXROBOTYY"
        # This specific regex looks for a pattern ending in IR followed by digits. Adjust if robot naming is different.
        match = re.search(r"([A-Z0-9_]+IR\d+)", robot_full_name.upper())
        if match:
            # Find the part of the original name that matches the uppercase pattern
            # This is a bit more robust if casing is mixed
            core_name_candidate = ""
            pattern_to_find = match.group(1)
            original_name_upper = robot_full_name.upper()
            start_index = original_name_upper.find(pattern_to_find)
            if start_index != -1:
                 core_name_candidate = robot_full_name[start_index : start_index + len(pattern_to_find)]
                 # Further refinement: if the original name had more after this pattern (e.g. " HB1610IR01 Tool"),
                 # we might only want "HB1610IR01". The regex above should handle common cases.
                 # For now, we use the matched part directly from original casing if possible.
                 robot_core_name = core_name_candidate if core_name_candidate else robot_full_name[:len(pattern_to_find)]


        print(f"INFO (v20): Zidentyfikowano robota: '{robot_core_name}' (Pełna nazwa: '{robot_full_name}')", file=sys.stderr)
        
        robot_cojt_data_aggregated = {} 
        # Iterate through the direct children of the robot element
        # These children are typically PmCompoundResources representing toolsets or main folders
        robot_main_children_ids = [item.text.strip() for item in robot_element.findall("./children/item") if item.text]

        for main_child_id_under_robot in robot_main_children_ids: 
            main_child_element = all_objects_map_by_id.get(main_child_id_under_robot)
            # We are interested in PmCompoundResource children of the robot
            if main_child_element and main_child_element.tag == "PmCompoundResource": 
                # Call the recursive function for this main child (e.g., "HB1610IR01-Applicationtools")
                # The robot_core_name is passed for cleaning sub-folder names if they start with it.
                cojt_found_in_branch = find_cojt_data_recursive(main_child_id_under_robot, robot_core_name) 
                
                # Merge results from this branch into the robot's total COJT data
                for category, files in cojt_found_in_branch.items():
                    all_cojt_headers_set.add(category) # Add to global set of headers
                    if category not in robot_cojt_data_aggregated:
                        robot_cojt_data_aggregated[category] = []
                    robot_cojt_data_aggregated[category].extend(files)
                    # Ensure uniqueness and sort
                    robot_cojt_data_aggregated[category] = sorted(list(set(robot_cojt_data_aggregated[category])))
            
        robots_data_list.append({
            "robot": robot_core_name, # Use the cleaned robot_core_name
            "cojt_data": robot_cojt_data_aggregated
        })

    sorted_cojt_headers = sorted(list(all_cojt_headers_set))
    
    print(f"INFO (v20): Końcowa nazwa stacji: {station_name}, znaleziono robotów: {len(robots_data_list)}", file=sys.stderr)
    print(f"DEBUG (v20): Wykryte globalne nagłówki kolumn COJT: {sorted_cojt_headers}", file=sys.stderr)
    for r_data in robots_data_list:
        print(f"DEBUG (v20): Robot: {r_data['robot']}, Finalne Dane COJT: {r_data['cojt_data']}", file=sys.stderr)

    return {"station": station_name, "robots": robots_data_list, "all_cojt_column_headers": sorted_cojt_headers}

if __name__ == "__main__":
    # Uruchomienie serwera Flask do celów deweloperskich
    # W środowisku produkcyjnym Passenger lub inny serwer WSGI będzie zarządzał aplikacją.
    print("INFO (v20): Uruchamianie serwera deweloperskiego Flask...", file=sys.stderr)
    app.run(debug=True, host='0.0.0.0', port=5001)
