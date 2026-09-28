import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor

APPID_FIXES = {
    'Ghostrunner 2': 2144740,
    'Like a Dragon: Ishin!': 1805480,
    "Death Stranding: Director's Cut": 1850570,
    'Smite 2': 2437170,
    'Returnal': 1649240,
    'Street Fighter 6': 1364780,
    'Triangle Strategy': 1850510,
    'Sword Art Online: FB': 626690,
    'Eiyuden Chronicle: Hundred Heroes': 1658280,
    'Observer: System Redux': 1386900,
    'Endling: Extinction is Forever': 898890,
    'Somerville': 1671410,
    'The Callisto Protocol': 1544020,
    'Hard West 2': 1282410,
    'Galactic Civilizations IV': 1357210,
    'Manifold Garden': 473950,
    'Roguebook': 1076200,
    'Steep': 460920,
    'BPM: Bullets Per Minute': 1286350,
    'My Time at Sandrock': 1084600,
    'Tavern Master': 1525700,
    'Alchemy Garden': 935400,
    'Emily is Away Too': 523780,
    'Zenless Zone Zero': None,
    'XDefiant': None,
}

def verify_url(url):
    if not url or not url.startswith('http'):
        return False
    try:
        r = requests.head(url, timeout=3, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        return r.status_code == 200
    except:
        return False

def resolve_best_image(g):
    gid, title, appid, img = g
    new_appid = APPID_FIXES.get(title, appid)
    
    # If appid exists, test library -> header -> capsule
    if new_appid:
        lib = f'https://cdn.akamai.steamstatic.com/steam/apps/{new_appid}/library_600x900.jpg'
        hdr = f'https://cdn.akamai.steamstatic.com/steam/apps/{new_appid}/header.jpg'
        cap = f'https://cdn.akamai.steamstatic.com/steam/apps/{new_appid}/capsule_616x353.jpg'
        
        if verify_url(lib):
            return (gid, title, new_appid, lib)
        if verify_url(hdr):
            return (gid, title, new_appid, hdr)
        if verify_url(cap):
            return (gid, title, new_appid, cap)

    # If current img is valid and not placehold.co
    if img and 'placehold.co' not in img and verify_url(img):
        return (gid, title, new_appid, img)

    # Search Steam store API for title
    try:
        clean = title.split(':')[0].split('-')[0].strip()
        sr = requests.get('https://store.steampowered.com/api/storesearch/', params={'term': clean, 'l': 'english', 'cc': 'US'}, timeout=4).json()
        items = sr.get('items', [])
        if items:
            sid = items[0]['id']
            lib = f'https://cdn.akamai.steamstatic.com/steam/apps/{sid}/library_600x900.jpg'
            hdr = f'https://cdn.akamai.steamstatic.com/steam/apps/{sid}/header.jpg'
            if verify_url(lib):
                return (gid, title, sid, lib)
            if verify_url(hdr):
                return (gid, title, sid, hdr)
    except:
        pass

    # Fallback to local SVG placeholder
    return (gid, title, new_appid, '/static/img/placeholder.svg')

def main():
    conn = sqlite3.connect('game_deals.db')
    c = conn.cursor()
    c.execute('SELECT id, title, steam_app_id, cover_image FROM games')
    games = c.fetchall()

    print(f'Processing {len(games)} games...')
    with ThreadPoolExecutor(max_workers=25) as pool:
        updated = list(pool.map(resolve_best_image, games))

    placeholder_count = 0
    steam_count = 0

    # Get all existing steam_app_ids mapped to gid to prevent duplicate conflict
    c.execute('SELECT id, steam_app_id FROM games')
    existing_appids = {row[1]: row[0] for row in c.fetchall() if row[1] is not None}

    for gid, title, appid, final_img in updated:
        # Check if assigning this appid would violate uniqueness
        target_appid = appid
        if target_appid is not None and target_appid in existing_appids and existing_appids[target_appid] != gid:
            # Another game already has this steam_app_id
            target_appid = None

        c.execute('UPDATE games SET steam_app_id = ?, cover_image = ? WHERE id = ?', (target_appid, final_img, gid))
        if target_appid is not None:
            existing_appids[target_appid] = gid

        if final_img.startswith('/static'):
            placeholder_count += 1
        else:
            steam_count += 1

    conn.commit()
    conn.close()
    print(f'SUCCESS! Steam valid images: {steam_count}, Local placeholder: {placeholder_count}')

if __name__ == '__main__':
    main()
