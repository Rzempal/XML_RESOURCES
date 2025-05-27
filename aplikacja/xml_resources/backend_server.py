from flask import Flask, request, jsonify from flask_cors import CORS import xml.etree.ElementTree as ET import sys

app = Flask(name) CORS(app)

PASSWORD_FILE = "password" with open(PASSWORD_FILE, "r", encoding="utf-8") as f: VALID_PASSWORDS = [line.strip() for line in f if line.strip()] print(f"Loaded {len(VALID_PASSWORDS)} valid passwords", file=sys.stderr)

@app.route("/api/xml_resources/analyze", methods=["POST"]) def analyze(): print("Received request to /analyze", file=sys.stderr) if "file" not in request.files or "password" not in request.form: print("Missing file or password in request", file=sys.stderr) return jsonify({"error": "Brak pliku lub hasła"}), 400

file = request.files["file"]
password = request.form["password"]
print(f"Password received: {password}", file=sys.stderr)

if password not in VALID_PASSWORDS:
    print("Invalid password", file=sys.stderr)
    return jsonify({"error": "Nieprawidłowe hasło"}), 403

try:
    xml_content = file.read().decode("utf-8", errors="ignore")
    print("XML content loaded", file=sys.stderr)
    result = analyze_station_data(xml_content)
    print("XML analysis complete", file=sys.stderr)
    return jsonify(result)
except Exception as e:
    print(f"Exception occurred: {str(e)}", file=sys.stderr)
    return jsonify({"error": f"Błąd przetwarzania XML: {str(e)}"}), 500

def analyze_station_data(xml_content): global all_objects_map root = ET.fromstring(xml_content)

all_objects_map = {}
for elem in root.iter():
    node_id = elem.findtext("NodeInfo/Id")
    if node_id:
        all_objects_map[node_id] = elem

resources = {}

def parse_robot_resources(element, robot_name):
    for child in element.findall("./children/item"):
        child_elem = all_objects_map.get(child.text)
        if child_elem is not None:
            child_name = child_elem.findtext("name")
            print(f"Parsing child element: {child_name} for robot {robot_name}", file=sys.stderr)

            if child_name and "Applicationtools" in child_name:
                for tool in child_elem.findall(".//ApplicationTool/name"):
                    print(f"Found tool: {tool.text} for robot {robot_name}", file=sys.stderr)
                    resources[robot_name]["ApplicationTools"].append(tool.text)
            elif child_name and "Components" in child_name:
                for comp in child_elem.findall(".//Component/name"):
                    print(f"Found component: {comp.text} for robot {robot_name}", file=sys.stderr)
                    resources[robot_name]["Components"].append(comp.text)

            parse_robot_resources(child_elem, robot_name)

for comp_res in root.findall(".//PmCompoundResource"):
    robot_name = comp_res.findtext("name")
    print(f"DEBUG: Found compound resource: '{robot_name}'", file=sys.stderr)
    if robot_name and any(keyword in robot_name.upper() for keyword in ["IR", "ROBOT"]):
        print(f"Identified robot: {robot_name}", file=sys.stderr)
        resources[robot_name] = {"ApplicationTools": [], "Components": []}
        parse_robot_resources(comp_res, robot_name)

robots_list = []
for robot, data in resources.items():
    robots_list.append({
        "robot": robot,
        "application_tools": data["ApplicationTools"] if data["ApplicationTools"] else ["Brak danych"],
        "components": data["Components"] if data["Components"] else ["Brak danych"]
    })

station_name = root.findtext(".//PrStation/name") or "Nieznana stacja"
print(f"Final station name: {station_name}, robots found: {len(robots_list)}", file=sys.stderr)
return {"station": station_name, "robots": robots_list}

if name == "main": app.run(debug=True)

