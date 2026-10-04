import requests
import json
import zipfile
import os
import shutil
import time

def get_type_damage_relations(type_url):
    res = requests.get(type_url)
    if res.status_code != 200:
        return [], []
    data = res.json()
    weaknesses = [t['name'] for t in data['damage_relations']['double_damage_from']]
    strengths = [t['name'] for t in data['damage_relations']['double_damage_to']]
    return weaknesses, strengths

def get_evolution_chain(url):
    res = requests.get(url)
    if res.status_code != 200:
        return []

    chain_data = res.json().get('chain', {})
    evolutions = []

    def traverse_chain(node):
        evolutions.append(node['species']['name'])
        for evolve_to in node.get('evolves_to', []):
            traverse_chain(evolve_to)

    if chain_data:
        traverse_chain(chain_data)

    return evolutions

def fetch_pokemon_data():
    base_url = "https://pokeapi.co/api/v2"

    print("Fetching all pokemon list...")
    response = requests.get(f"{base_url}/pokemon?limit=10000")
    results = response.json().get('results', [])

    if os.path.exists("temp_data"):
        shutil.rmtree("temp_data")
    os.makedirs("temp_data/images", exist_ok=True)

    all_pokemon_details = []

    total = len(results)
    for i, p in enumerate(results):
        name = p['name']
        print(f"[{i+1}/{total}] Processing {name}...")

        try:
            p_res = requests.get(p['url'])
            if p_res.status_code != 200:
                continue
            p_data = p_res.json()

            p_id = p_data['id']

            s_res = requests.get(p_data['species']['url'])
            if s_res.status_code != 200:
                continue
            s_data = s_res.json()

            names_trans = {}
            for n in s_data['names']:
                if n['language']['name'] in ['es', 'en']:
                    names_trans[n['language']['name']] = n['name']

            es_name = names_trans.get('es', names_trans.get('en', name))
            en_name = names_trans.get('en', name)

            types = []
            weaknesses_set = set()
            strengths_set = set()
            for t in p_data['types']:
                t_name = t['type']['name']
                types.append(t_name)
                w, s = get_type_damage_relations(t['type']['url'])
                weaknesses_set.update(w)
                strengths_set.update(s)

            stats = {s['stat']['name']: s['base_stat'] for s in p_data['stats']}

            abilities = [a['ability']['name'] for a in p_data['abilities']]

            # Moves (limit to some to keep size reasonable, or take all)
            moves = [m['move']['name'] for m in p_data['moves']]

            # Evolutions
            evolution_url = s_data.get('evolution_chain', {}).get('url')
            evolutions = get_evolution_chain(evolution_url) if evolution_url else []

            img_url = p_data['sprites']['other']['official-artwork']['front_default']
            has_image = False
            if img_url:
                img_res = requests.get(img_url)
                if img_res.status_code == 200:
                    with open(f"temp_data/images/{p_id}.png", 'wb') as f:
                        f.write(img_res.content)
                    has_image = True

            poke_model = {
                "id": p_id,
                "name_en": en_name,
                "name_es": es_name,
                "types": types,
                "stats": stats,
                "abilities": abilities,
                "height": p_data['height'],
                "weight": p_data['weight'],
                "has_image": has_image,
                "weaknesses": list(weaknesses_set),
                "strengths": list(strengths_set),
                "moves": moves,
                "evolutions": evolutions
            }

            all_pokemon_details.append(poke_model)


            # Simple rate limiting logic to avoid 429
            time.sleep(0.5)

        except Exception as e:
            print(f"Error processing {name}: {e}")

    with open("temp_data/pokemon.json", 'w', encoding='utf-8') as f:
        json.dump(all_pokemon_details, f, ensure_ascii=False, indent=2)

    print("Creating temporary zip archive...")
    temp_zip_path = "temp_data.zip"
    with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write("temp_data/pokemon.json", "pokemon.json")
        for root, _, files in os.walk("temp_data/images"):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, f"images/{file}")

    # Remove existing data.zip and chunk files
    if os.path.exists("data.zip"):
        os.remove("data.zip")
    for old_file in os.listdir("."):
        if old_file.startswith("data_part") and old_file.endswith(".bin"):
            os.remove(old_file)

    CHUNK_SIZE = 50 * 1024 * 1024 # 50 MB
    zip_size = os.path.getsize(temp_zip_path)
    parts = []

    with open(temp_zip_path, "rb") as f:
        part_num = 1
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            part_filename = f"data_part{part_num}.bin"
            with open(part_filename, "wb") as pf:
                pf.write(chunk)
            parts.append(part_filename)
            part_num += 1

    os.remove(temp_zip_path)

    version_code = int(time.time())
    with open("version.json", 'w', encoding='utf-8') as f:
        json.dump({
            "version": version_code,
            "parts": parts,
            "total_size": zip_size
        }, f, indent=2)

    shutil.rmtree("temp_data")
    print(f"Data package created successfully with {len(parts)} part(s). Version: {version_code}")

if __name__ == "__main__":
    fetch_pokemon_data()
