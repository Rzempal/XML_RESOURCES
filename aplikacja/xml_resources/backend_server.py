# Importowanie niezbędnych bibliotek
from flask import Flask, request, jsonify
from flask_cors import CORS
import xml.etree.ElementTree as ET
import sys
import os
import re # Import modułu re do obsługi wyrażeń regularnych

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

# Globalna mapa obiektów XML dla szybkiego dostępu po ID
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
        result = analyze_station_data(xml_content)
        return jsonify(result)
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

def find_cojt_data_recursive(current_element_id, robot_core_name, path_prefix=""):
    """
    Rekurencyjnie przeszukuje strukturę w poszukiwaniu plików .cojt i ich folderów nadrzędnych.
    """
    global all_objects_map_by_id
    collected_cojt_data = {}
    current_element = all_objects_map_by_id.get(current_element_id)

    if not current_element:
        print(f"DEBUG_COJT (v12): Element o ID '{current_element_id}' nie znaleziony w mapie. Zwracam puste dane.", file=sys.stderr)
        return collected_cojt_data

    current_element_name = get_name_from_element(current_element)
    print(f"DEBUG_COJT (v12): ===== Rozpoczynam rekurencję dla folderu: '{current_element_name}' (ID: {current_element_id}), PathPrefix: '{path_prefix}' =====", file=sys.stderr)

    direct_cojt_files = []
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]
    print(f"DEBUG_COJT (v12): Folder '{current_element_name}' ma {len(children_ids)} dzieci ID: {children_ids}", file=sys.stderr)

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element:
            print(f"DEBUG_COJT (v12): Dziecko o ID '{child_id}' (folderu '{current_element_name}') nie znalezione w mapie.", file=sys.stderr)
            continue

        child_name = get_name_from_element(child_element)
        print(f"DEBUG_COJT (v12): Analizuję dziecko: '{child_name}' (ID: {child_id}, Tag: {child_element.tag}) folderu '{current_element_name}'", file=sys.stderr)

        if child_name and child_name.lower().endswith(".cojt"):
            is_cojt_file_representative = False
            if child_element.tag == "Pm3DRep":
                is_cojt_file_representative = True
                print(f"DEBUG_COJT (v12): Dziecko '{child_name}' jest Pm3DRep.", file=sys.stderr)
            else:
                node_info_family = child_element.findtext("NodeInfo/family")
                if node_info_family == "ExternalDocument":
                    is_cojt_file_representative = True
                    print(f"DEBUG_COJT (v12): Dziecko '{child_name}' ma rodzinę ExternalDocument.", file=sys.stderr)
                else:
                    print(f"DEBUG_COJT (v12): Dziecko '{child_name}' nie jest Pm3DRep ani ExternalDocument (Tag: {child_element.tag}, Family: {node_info_family}).", file=sys.stderr)
            
            if is_cojt_file_representative:
                direct_cojt_files.append(child_name)
                print(f"DEBUG_COJT (v12): +++ Znaleziono bezpośredni plik .cojt: '{child_name}' w folderze '{current_element_name}' +++", file=sys.stderr)

    if direct_cojt_files:
        category_name = current_element_name
        if robot_core_name and category_name and category_name.startswith(robot_core_name):
            category_name = category_name[len(robot_core_name):].lstrip("-").lstrip("_")
        
        if not category_name: category_name = get_name_from_element(current_element) # Fallback na oryginalną nazwę
        if not category_name: category_name = "Pliki_COJT_BezNazwyRodzica" # Ostateczny fallback
            
        column_name = f"{path_prefix}{category_name}" if path_prefix else category_name
        
        collected_cojt_data[column_name] = direct_cojt_files
        print(f"DEBUG_COJT (v12): Dla folderu '{current_element_name}', wygenerowana kategoria COJT: '{column_name}', pliki: {direct_cojt_files}", file=sys.stderr)

    # Rekurencja dla podfolderów (PmCompoundResource)
    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if child_element and child_element.tag == "PmCompoundResource":
            print(f"DEBUG_COJT (v12): Znaleziono podfolder (PmCompoundResource): '{get_name_from_element(child_element)}' (ID: {child_id}) w '{current_element_name}'. Rozpoczynam rekurencję.", file=sys.stderr)
            
            folder_name_for_path = get_name_from_element(child_element) or "FolderBezNazwy"
            if robot_core_name and folder_name_for_path.startswith(robot_core_name):
                folder_name_for_path = folder_name_for_path[len(robot_core_name):].lstrip("-").lstrip("_")
            
            # Jeśli bieżący folder (current_element) miał bezpośrednie pliki .cojt, to jego nazwa już utworzyła kategorię.
            # Dla jego dzieci (podfolderów) chcemy, aby tworzyły własne, nowe kategorie, a nie były dołączane do ścieżki rodzica.
            # Dlatego path_prefix dla rekurencyjnego wywołania jest resetowany do "" jeśli direct_cojt_files były znalezione.
            # Jeśli direct_cojt_files nie było, to kontynuujemy budowanie ścieżki.
            new_path_prefix_for_recursion = "" if direct_cojt_files else (f"{path_prefix}{folder_name_for_path}/" if path_prefix else f"{folder_name_for_path}/")
            
            # Jeśli bieżący folder (current_element) NIE miał bezpośrednich plików .cojt,
            # to jego nazwa powinna być częścią ścieżki dla plików znalezionych głębiej.
            if not direct_cojt_files:
                 current_folder_name_for_path = current_element_name
                 if robot_core_name and current_folder_name_for_path and current_folder_name_for_path.startswith(robot_core_name):
                     current_folder_name_for_path = current_folder_name_for_path[len(robot_core_name):].lstrip("-").lstrip("_")
                 if not current_folder_name_for_path: current_folder_name_for_path = get_name_from_element(current_element) or "FolderNadrzednyBezNazwy"

                 new_path_prefix_for_recursion = f"{path_prefix}{current_folder_name_for_path}/"


            print(f"DEBUG_COJT (v12): Wywołanie rekurencyjne dla podfolderu '{get_name_from_element(child_element)}' z path_prefix: '{new_path_prefix_for_recursion}'", file=sys.stderr)
            sub_folder_cojt_data = find_cojt_data_recursive(child_id, robot_core_name, new_path_prefix_for_recursion)

            for category, files in sub_folder_cojt_data.items():
                final_category_key = category # category już powinno zawierać pełną ścieżkę z rekurencji
                if final_category_key in collected_cojt_data:
                    collected_cojt_data[final_category_key].extend(files)
                    collected_cojt_data[final_category_key] = list(set(collected_cojt_data[final_category_key])) # Usuń duplikaty
                else:
                    collected_cojt_data[final_category_key] = files
                print(f"DEBUG_COJT (v12): Połączono dane z podfolderu. Kategoria: '{final_category_key}', Pliki: {files}", file=sys.stderr)
    
    print(f"DEBUG_COJT (v12): ===== Zakończono rekurencję dla folderu: '{current_element_name}'. Zebrane dane: {collected_cojt_data} =====", file=sys.stderr)
    return collected_cojt_data


def analyze_station_data(xml_content):
    global all_objects_map_by_id
    root = ET.fromstring(xml_content)
    all_objects_map_by_id = {}
    for elem in root.iter():
        external_id = elem.get("ExternalId")
        if external_id:
            all_objects_map_by_id[external_id.strip()] = elem
    
    print(f"DEBUG (v12): Zbudowano mapę all_objects_map_by_id z {len(all_objects_map_by_id)} elementami.", file=sys.stderr)

    pr_station_element = root.find(".//PrStation")
    if not pr_station_element:
        print("BŁĄD: Nie znaleziono elementu PrStation.", file=sys.stderr)
        return {"station": "Błąd - PrStation nie znalezione", "robots": [], "all_cojt_column_headers": []}

    station_name = get_name_from_element(pr_station_element) or "Nieznana stacja"
    print(f"INFO: Analizowana stacja: {station_name}", file=sys.stderr)

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
        
        print(f"INFO (v12): Zidentyfikowano robota: '{robot_core_name}' (Pełna nazwa: '{robot_full_name}')", file=sys.stderr)
        
        robot_cojt_data_aggregated = {} # Słownik na wszystkie dane .cojt dla tego robota
        
        robot_main_children_ids = [item.text.strip() for item in robot_element.findall("./children/item") if item.text]
        print(f"DEBUG (v12): Robot '{robot_core_name}' ma {len(robot_main_children_ids)} głównych dzieci/folderów do analizy COJT.", file=sys.stderr)

        for main_child_id in robot_main_children_ids:
            main_child_element = all_objects_map_by_id.get(main_child_id)
            if main_child_element and main_child_element.tag == "PmCompoundResource": 
                main_child_name = get_name_from_element(main_child_element)
                print(f"DEBUG (v12): Wywołanie find_cojt_data_recursive dla głównego folderu '{main_child_name}' (ID: {main_child_id}) robota '{robot_core_name}'", file=sys.stderr)
                
                # Dla głównych folderów robota, path_prefix jest pusty, bo ich nazwy (po oczyszczeniu) staną się początkiem kategorii
                cojt_found_in_main_folder = find_cojt_data_recursive(main_child_id, robot_core_name, path_prefix="")
                
                print(f"DEBUG (v12): Dane COJT zwrócone z find_cojt_data_recursive dla '{main_child_name}': {cojt_found_in_main_folder}", file=sys.stderr)
                for category, files in cojt_found_in_main_folder.items():
                    all_cojt_headers_set.add(category)
                    if category in robot_cojt_data_aggregated:
                        robot_cojt_data_aggregated[category].extend(files)
                        robot_cojt_data_aggregated[category] = list(set(robot_cojt_data_aggregated[category])) # Usuń duplikaty
                    else:
                        robot_cojt_data_aggregated[category] = files
            else:
                if main_child_element:
                    print(f"DEBUG (v12): Główne dziecko robota '{get_name_from_element(main_child_element)}' (ID: {main_child_id}) nie jest PmCompoundResource. Tag: {main_child_element.tag}. Pomijam dla COJT.", file=sys.stderr)
                else:
                    print(f"DEBUG (v12): Główne dziecko robota o ID '{main_child_id}' nie znalezione w mapie. Pomijam dla COJT.", file=sys.stderr)

        robots_data_list.append({
            "robot": robot_core_name,
            "cojt_data": robot_cojt_data_aggregated
        })

    sorted_cojt_headers = sorted(list(all_cojt_headers_set))
    print(f"INFO (v12): Końcowa nazwa stacji: {station_name}, znaleziono robotów: {len(robots_data_list)}", file=sys.stderr)
    print(f"DEBUG (v12): Wykryte globalne nagłówki kolumn COJT: {sorted_cojt_headers}", file=sys.stderr)
    for r_data in robots_data_list:
        print(f"DEBUG (v12): Robot: {r_data['robot']}, Finalne Dane COJT: {r_data['cojt_data']}", file=sys.stderr)

    return {"station": station_name, "robots": robots_data_list, "all_cojt_column_headers": sorted_cojt_headers}

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)
