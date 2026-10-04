import requests
import json
import zipfile
import os
import shutil
import time

type_cache = {}
evolution_cache = {}

def get_type_damage_relations(type_url, session):
    if not type_url:
        return [], []
    if type_url in type_cache:
        return type_cache[type_url]
    try:
        res = session.get(type_url, timeout=15)
        if res.status_code != 200:
            return [], []
        data = res.json()
        weaknesses = [t['name'] for t in data.get('damage_relations', {}).get('double_damage_from', []) if 'name' in t]
        strengths = [t['name'] for t in data.get('damage_relations', {}).get('double_damage_to', []) if 'name' in t]
        type_cache[type_url] = (weaknesses, strengths)
        return weaknesses, strengths
    except Exception as e:
        print(f"Error fetching type {type_url}: {e}")
        return [], []

def get_evolution_chain(url, session):
    if not url:
        return []
    if url in evolution_cache:
        return evolution_cache[url]
    try:
        res = session.get(url, timeout=15)
        if res.status_code != 200:
            return []

        chain_data = res.json().get('chain', {})
        evolutions = []

        def traverse_chain(node):
            if not node:
                return
            species = node.get('species')
            if species and 'name' in species:
                evolutions.append(species['name'])
            for evolve_to in node.get('evolves_to', []):
                traverse_chain(evolve_to)

        if chain_data:
            traverse_chain(chain_data)

        evolution_cache[url] = evolutions
        return evolutions
    except Exception as e:
        print(f"Error fetching evolution chain {url}: {e}")
        return []

def fetch_pokemon_data():
    base_url = "https://pokeapi.co/api/v2"
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'PokemonDataCollector/1.0'
    })

    print("Fetching all pokemon list...")
    response = session.get(f"{base_url}/pokemon?limit=10000", timeout=30)
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
            p_res = session.get(p['url'], timeout=15)
            if p_res.status_code != 200:
                continue
            p_data = p_res.json()

            p_id = p_data['id']

            species_url = (p_data.get('species') or {}).get('url')
            s_data = {}
            if species_url:
                s_res = session.get(species_url, timeout=15)
                if s_res.status_code == 200:
                    s_data = s_res.json()

            names_trans = {}
            for n in s_data.get('names', []):
                lang = (n.get('language') or {}).get('name')
                if lang in ['es', 'en']:
                    names_trans[lang] = n.get('name')

            es_name = names_trans.get('es', names_trans.get('en', name))
            en_name = names_trans.get('en', name)

            types = []
            weaknesses_set = set()
            strengths_set = set()
            for t in p_data.get('types', []):
                t_obj = t.get('type') or {}
                t_name = t_obj.get('name')
                t_url = t_obj.get('url')
                if t_name:
                    types.append(t_name)
                if t_url:
                    w, s = get_type_damage_relations(t_url, session)
                    weaknesses_set.update(w)
                    strengths_set.update(s)

            stats = {s['stat']['name']: s['base_stat'] for s in p_data.get('stats', []) if 'stat' in s and 'name' in s['stat']}
            abilities = [a['ability']['name'] for a in p_data.get('abilities', []) if 'ability' in a and 'name' in a['ability']]
            moves = [m['move']['name'] for m in p_data.get('moves', []) if 'move' in m and 'name' in m['move']]

            evolution_url = (s_data.get('evolution_chain') or {}).get('url')
            evolutions = get_evolution_chain(evolution_url, session) if evolution_url else []

            sprites = p_data.get('sprites') or {}
            other_sprites = sprites.get('other') or {}
            official_artwork = other_sprites.get('official-artwork') or {}
            img_url = official_artwork.get('front_default') or sprites.get('front_default')

            has_image = False
            if img_url:
                img_res = session.get(img_url, timeout=15)
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
                "height": p_data.get('height'),
                "weight": p_data.get('weight'),
                "has_image": has_image,
                "weaknesses": list(weaknesses_set),
                "strengths": list(strengths_set),
                "moves": moves,
                "evolutions": evolutions
            }

            all_pokemon_details.append(poke_model)

            time.sleep(0.1)

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
