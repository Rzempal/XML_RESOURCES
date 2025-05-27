from flask import Flask, request, jsonify
from flask_cors import CORS
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

PASSWORD_FILE = "password"
with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
    VALID_PASSWORDS = [line.strip() for line in f if line.strip()]

@app.route("/api/xml_resources/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files or "password" not in request.form:
        return jsonify({"error": "Brak pliku lub hasła"}), 400

    file = request.files["file"]
    password = request.form["password"]

    if password not in VALID_PASSWORDS:
        return jsonify({"error": "Nieprawidłowe hasło"}), 403

    try:
        xml_content = file.read().decode("utf-8", errors="ignore")
        result = analyze_station_data(xml_content)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Błąd przetwarzania XML: {str(e)}"}), 500

def analyze_station_data(xml_content):
    global all_objects_map
    root = ET.fromstring(xml_content)

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

                if child_name and "Applicationtools" in child_name:
                    for tool in child_elem.findall(".//ApplicationTool/name"):
                        resources[robot_name]["ApplicationTools"].append(tool.text)
                elif child_name and "Components" in child_name:
                    for comp in child_elem.findall(".//Component/name"):
                        resources[robot_name]["Components"].append(comp.text)

                parse_robot_resources(child_elem, robot_name)

    for comp_res in root.findall(".//PmCompoundResource"):
        robot_name = comp_res.findtext("name")
        if robot_name and any(keyword in robot_name for keyword in ["IR", "Robot"]):
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
    return {"station": station_name, "robots": robots_list}

if __name__ == "__main__":
    app.run(debug=True)
