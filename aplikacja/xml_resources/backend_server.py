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

def find_cojt_data_recursive(current_element_id, robot_core_name, current_path=""):
    """
    Rekurencyjnie przeszukuje strukturę w poszukiwaniu plików .cojt.
    Kluczem w zwracanym słowniku jest oczyszczona nazwa folderu BEZPOŚREDNIO zawierającego pliki .cojt.
    """
    global all_objects_map_by_id
    collected_cojt_data_for_branch = {} # Dane .cojt zebrane w tej gałęzi rekurencji
    current_element = all_objects_map_by_id.get(current_element_id)

    if not current_element:
        print(f"DEBUG_COJT (v14): Element o ID '{current_element_id}' (ścieżka: '{current_path}') nie znaleziony w mapie.", file=sys.stderr)
        return collected_cojt_data_for_branch

    current_element_name = get_name_from_element(current_element) or "ElementBezNazwy"
    print(f"DEBUG_COJT (v14): ===== Rekurencja dla: '{current_element_name}' (ID: {current_element_id}), BieżącaŚcieżka: '{current_path}' =====", file=sys.stderr)

    direct_cojt_files_in_this_element = [] # Pliki .cojt znalezione jako dzieci TEGO current_element
    
    children_ids = [item.text.strip() for item in current_element.findall("./children/item") if item.text]
    print(f"DEBUG_COJT (v14): Element '{current_element_name}' ma {len(children_ids)} dzieci referencyjnych (item): {children_ids}", file=sys.stderr)

    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if not child_element:
            print(f"DEBUG_COJT (v14): Dziecko referencyjne o ID '{child_id}' (elementu '{current_element_name}') nie znalezione w mapie.", file=sys.stderr)
            continue

        child_name = get_name_from_element(child_element) or "DzieckoBezNazwy"
        print(f"DEBUG_COJT (v14): Analizuję dziecko referencyjne: '{child_name}' (ID: {child_id}, Tag: {child_element.tag}) elementu '{current_element_name}'", file=sys.stderr)

        # Przypadek 1: Dziecko samo w sobie jest Pm3DRep i plikiem .cojt
        if child_element.tag == "Pm3DRep" and child_name.lower().endswith(".cojt"):
            direct_cojt_files_in_this_element.append(child_name)
            print(f"DEBUG_COJT (v14): +++ Znaleziono BEZPOŚREDNI Pm3DRep .cojt: '{child_name}' jako dziecko '{current_element_name}' +++", file=sys.stderr)
        
        # Przypadek 2: Dziecko jest innym typem (np. PmToolInstance) i może *zawierać referencje* do plików .cojt
        # Ta sekcja jest kluczowa do debugowania
        elif child_element.tag != "PmCompoundResource": # Jeśli nie jest folderem do dalszej rekurencji
            print(f"DEBUG_COJT (v14): Dziecko '{child_name}' (Tag: {child_element.tag}) nie jest PmCompoundResource. Sprawdzam jego tag <copies>...", file=sys.stderr)
            copies_element = child_element.find("copies") 
            if copies_element is not None:
                print(f"DEBUG_COJT (v14): Znaleziono tag <copies> w '{child_name}'. Liczba <item> w <copies>: {len(copies_element.findall('item'))}", file=sys.stderr)
                for item_tag_in_copies in copies_element.findall("item"): 
                    referenced_external_id = item_tag_in_copies.text.strip() if item_tag_in_copies.text else None
                    if referenced_external_id:
                        print(f"DEBUG_COJT (v14): Element '{child_name}' ma referencję w <copies><item>: '{referenced_external_id}'", file=sys.stderr)
                        referenced_object = all_objects_map_by_id.get(referenced_external_id)
                        if referenced_object is not None and referenced_object.tag == "Pm3DRep":
                            pm3drep_name = get_name_from_element(referenced_object)
                            if pm3drep_name and pm3drep_name.lower().endswith(".cojt"):
                                direct_cojt_files_in_this_element.append(pm3drep_name)
                                print(f"DEBUG_COJT (v14): +++ Znaleziono .cojt ('{pm3drep_name}') przez referencję <copies> z '{child_name}' (w folderze '{current_element_name}') +++", file=sys.stderr)
                            else: print(f"DEBUG_COJT (v14): Referowany Pm3DRep (ID: {referenced_external_id}) nie ma nazwy .cojt: '{pm3drep_name}'", file=sys.stderr)
                        elif referenced_object is not None: print(f"DEBUG_COJT (v14): Referowany obiekt (ID: {referenced_external_id}) nie jest Pm3DRep (Tag: {referenced_object.tag})", file=sys.stderr)
                        else: print(f"DEBUG_COJT (v14): Referowany obiekt o ID '{referenced_external_id}' nie znaleziony w mapie.", file=sys.stderr)
                    else: print(f"DEBUG_COJT (v14): Pusty <item> w <copies> elementu '{child_name}'.", file=sys.stderr)
            else:
                print(f"DEBUG_COJT (v13): Element '{child_name}' (Tag: {child_element.tag}) nie ma tagu <copies>.", file=sys.stderr)


    # Jeśli znaleziono pliki .cojt bezpośrednio pod current_element, zapisz je
    if direct_cojt_files_in_this_element:
        # Nazwa kategorii to oczyszczona nazwa bieżącego folderu (current_element_name)
        category_name_for_current_folder = current_element_name
        if robot_core_name and category_name_for_current_folder.startswith(robot_core_name):
            category_name_for_current_folder = category_name_for_current_folder[len(robot_core_name):].lstrip("-").lstrip("_")
        
        if not category_name_for_current_folder: category_name_for_current_folder = get_name_from_element(current_element) or "FolderGlowny_COJT" # Fallback
        if not category_name_for_current_folder: category_name_for_current_folder = "Pliki_COJT_BezNazwyRodzica" # Ostateczny fallback

        # Budujemy klucz kategorii używając current_path + nazwa obecnego folderu
        # Jeśli current_path jest puste, używamy tylko category_name_for_current_folder
        final_category_key = f"{current_path}{category_name_for_current_folder}" if current_path else category_name_for_current_folder
        
        if final_category_key not in collected_cojt_data_for_branch:
            collected_cojt_data_for_branch[final_category_key] = []
        collected_cojt_data_for_branch[final_category_key].extend(direct_cojt_files_in_this_element)
        collected_cojt_data_for_branch[final_category_key] = list(set(collected_cojt_data_for_branch[final_category_key]))
        print(f"DEBUG_COJT (v14): Dla folderu '{current_element_name}', kategoria COJT: '{final_category_key}', pliki: {direct_cojt_files_in_this_element}", file=sys.stderr)

    # Rekurencja dla podfolderów (PmCompoundResource)
    for child_id in children_ids:
        child_element = all_objects_map_by_id.get(child_id)
        if child_element and child_element.tag == "PmCompoundResource": # Jeśli dziecko jest folderem
            child_folder_name_raw = get_name_from_element(child_element) or "FolderBezNazwy"
            print(f"DEBUG_COJT (v14): Znaleziono podfolder (PmCompoundResource): '{child_folder_name_raw}' (ID: {child_id}) w '{current_element_name}'. Rozpoczynam rekurencję.", file=sys.stderr)
            
            # Tworzenie nowej ścieżki dla rekurencji: current_path + oczyszczona nazwa obecnego folderu + "/"
            current_folder_name_cleaned_for_path = current_element_name
            if robot_core_name and current_folder_name_cleaned_for_path.startswith(robot_core_name):
                 current_folder_name_cleaned_for_path = current_folder_name_cleaned_for_path[len(robot_core_name):].lstrip("-").lstrip("_")
            if not current_folder_name_cleaned_for_path: current_folder_name_cleaned_for_path = get_name_from_element(current_element) or "FolderNadrzedny"

            # new_path_for_recursion = f"{current_path}{current_folder_name_cleaned_for_path}/"
            # UPROSZCZENIE: Nazwa kolumny to tylko bezpośredni folder nadrzędny pliku .cojt
            # Dlatego path_prefix przekazujemy jako pusty, a kategoria będzie budowana w momencie znalezienia plików.
            # ZMIANA: Wracamy do budowania ścieżki, jeśli chcemy hierarchiczne nazwy kolumn
            
            # Jeśli current_element (ten folder) sam w sobie *nie* miał plików .cojt,
            # to jego nazwa staje się częścią ścieżki dla dzieci.
            # Jeśli current_element *miał* pliki .cojt, to jego nazwa już utworzyła kategorię,
            # a jego podfoldery powinny tworzyć nowe, niezależne kategorie (bez dziedziczenia ścieżki od rodzica, który już jest kategorią).
            
            path_for_next_level = ""
            if not direct_cojt_files_in_this_element: # Jeśli TEN folder nie jest kategorią .cojt
                path_for_next_level = f"{current_path}{current_folder_name_cleaned_for_path}/"
            # Jeśli TEN folder JEST kategorią .cojt, to jego podfoldery tworzą nowe kategorie od zera (pusty prefix)
            # LUB, jeśli chcemy pełną ścieżkę zawsze, to:
            # path_for_next_level = f"{current_path}{current_folder_name_cleaned_for_path}/"


            print(f"DEBUG_COJT (v14): Wywołanie rekurencyjne dla podfolderu '{child_folder_name_raw}' z current_path: '{path_for_next_level}'", file=sys.stderr)
            sub_folder_cojt_data = find_cojt_data_recursive(child_id, robot_core_name, path_for_next_level)

            for category_from_subfolder, files_from_subfolder in sub_folder_cojt_data.items():
                # category_from_subfolder już zawiera pełną ścieżkę z rekurencji
                if category_from_subfolder in collected_cojt_data_for_branch:
                    collected_cojt_data_for_branch[category_from_subfolder].extend(files_from_subfolder)
                    collected_cojt_data_for_branch[category_from_subfolder] = list(set(collected_cojt_data_for_branch[category_from_subfolder]))
                else:
                    collected_cojt_data_for_branch[category_from_subfolder] = files_from_subfolder
                # print(f"DEBUG_COJT (v14): Połączono dane z podfolderu. Kategoria: '{category_from_subfolder}', Pliki: {files_from_subfolder}", file=sys.stderr)
    
    print(f"DEBUG_COJT (v14): ===== Zakończono rekurencję dla folderu: '{current_element_name}'. Zebrane dane w tej gałęzi: {collected_cojt_data_for_branch} =====", file=sys.stderr)
    return collected_cojt_data_for_branch


def analyze_station_data(xml_content):
    global all_objects_map_by_id
    root = ET.fromstring(xml_content)
    all_objects_map_by_id = {}
    for elem in root.iter():
        external_id = elem.get("ExternalId")
        if external_id:
            all_objects_map_by_id[external_id.strip()] = elem
    
    print(f"DEBUG (v14): Zbudowano mapę all_objects_map_by_id z {len(all_objects_map_by_id)} elementami.", file=sys.stderr)

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
        
        print(f"INFO (v14): Zidentyfikowano robota: '{robot_core_name}' (Pełna nazwa: '{robot_full_name}')", file=sys.stderr)
        
        robot_cojt_data_aggregated = {} 
        
        robot_main_children_ids = [item.text.strip() for item in robot_element.findall("./children/item") if item.text]
        print(f"DEBUG (v14): Robot '{robot_core_name}' ma {len(robot_main_children_ids)} głównych dzieci/folderów do analizy COJT.", file=sys.stderr)

        for main_child_id in robot_main_children_ids: 
            main_child_element = all_objects_map_by_id.get(main_child_id)
            # Główne "foldery" pod robotem to PmCompoundResource. Inne elementy (np. PmEquipmentInstance dla modelu robota) pomijamy na tym etapie.
            if main_child_element and main_child_element.tag == "PmCompoundResource": 
                main_child_name = get_name_from_element(main_child_element) or "FolderGlownyBezNazwy"
                print(f"DEBUG (v14): Wywołanie find_cojt_data_recursive dla głównego folderu '{main_child_name}' (ID: {main_child_id}) robota '{robot_core_name}'", file=sys.stderr)
                
                # Dla głównych folderów robota, current_path na początku jest pusty.
                # Funkcja find_cojt_data_recursive zbuduje nazwy kategorii.
                cojt_found_in_branch = find_cojt_data_recursive(main_child_id, robot_core_name, current_path="") 
                
                print(f"DEBUG (v14): Dane COJT zwrócone z find_cojt_data_recursive dla '{main_child_name}': {cojt_found_in_branch}", file=sys.stderr)
                for category, files in cojt_found_in_branch.items():
                    all_cojt_headers_set.add(category) 
                    if category in robot_cojt_data_aggregated:
                        robot_cojt_data_aggregated[category].extend(files)
                        robot_cojt_data_aggregated[category] = list(set(robot_cojt_data_aggregated[category]))
                    else:
                        robot_cojt_data_aggregated[category] = files
            
        robots_data_list.append({
            "robot": robot_core_name,
            "cojt_data": robot_cojt_data_aggregated
        })

    sorted_cojt_headers = sorted(list(all_cojt_headers_set))
    print(f"INFO (v14): Końcowa nazwa stacji: {station_name}, znaleziono robotów: {len(robots_data_list)}", file=sys.stderr)
    print(f"DEBUG (v14): Wykryte globalne nagłówki kolumn COJT: {sorted_cojt_headers}", file=sys.stderr)
    for r_data in robots_data_list:
        print(f"DEBUG (v14): Robot: {r_data['robot']}, Finalne Dane COJT: {r_data['cojt_data']}", file=sys.stderr)

    return {"station": station_name, "robots": robots_data_list, "all_cojt_column_headers": sorted_cojt_headers}

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)

