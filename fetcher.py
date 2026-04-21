"""
다이빙 포인트 데이터 수집기
- OpenStreetMap Overpass API (무료, 키 불필요)
- Dive Vibe 오픈소스 JSON (무료)
- The Dive API (API키 필요)
"""

import json
import time
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DIVEVIBE_URL = (
    "https://raw.githubusercontent.com/dancrake1/divevibe/main/data/dive_sites.json"
)
OSM_HEADERS = {"User-Agent": "DIVEROID-DivePointMapper/1.0 (contact: jay@diveroid.com)"}


# ──────────────────────────────
# OpenStreetMap (Overpass API)
# ──────────────────────────────


def fetch_osm(region_bbox: str = None, progress_cb=None) -> list[dict]:
    """
    OpenStreetMap에서 다이빙 포인트 수집
    region_bbox: "south,west,north,east" 형식 (None이면 전세계)
    """
    bbox = region_bbox or "-90,-180,90,180"

    query = f"""
    [out:json][timeout:120];
    (
      node["sport"="scuba_diving"]({bbox});
      node["sport"="diving"]({bbox});
      node["leisure"="diving"]({bbox});
      node["scuba_diving"="divespot"]({bbox});
    );
    out body;
    """

    if progress_cb:
        progress_cb("OpenStreetMap 서버에 요청 중...")

    try:
        resp = requests.post(
            OVERPASS_URL, data={"data": query}, headers=OSM_HEADERS, timeout=130
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as e:
        return []

    points = []
    for el in elements:
        tags = el.get("tags", {})
        name = (
            tags.get("name:ko") or tags.get("name") or tags.get("name:en") or "Unknown"
        )
        name_en = tags.get("name:en", "")
        lat = el.get("lat")
        lng = el.get("lon")
        if not lat or not lng:
            continue

        # 국가/지역 정보
        country = tags.get("addr:country", "")
        region = tags.get("addr:state", tags.get("addr:region", ""))

        points.append(
            {
                "name": name,
                "name_en": name_en,
                "lat": lat,
                "lng": lng,
                "country": country,
                "region": region,
                "depth_max": tags.get("depth"),
                "difficulty": tags.get("difficulty", ""),
                "description": tags.get("description", tags.get("note", "")),
                "confidence": "high",
            }
        )

    if progress_cb:
        progress_cb(f"OpenStreetMap: {len(points)}개 수집 완료")

    return points


# ──────────────────────────────
# Dive Vibe 오픈소스
# ──────────────────────────────


def fetch_wikidata(progress_cb=None) -> list[dict]:
    """Wikidata SPARQL — 공개 다이빙 포인트/난파선/산호초 데이터"""
    if progress_cb:
        progress_cb("Wikidata에서 다이빙 포인트 수집 중...")

    # 난파선, 다이빙 포인트, 산호초 (좌표 있는 것만)
    sparql = """
SELECT ?item ?itemLabel ?lat ?lng ?countryLabel WHERE {
  { ?item wdt:P31 wd:Q11990 . }       # shipwreck
  UNION
  { ?item wdt:P31 wd:Q184358 . }      # coral reef
  UNION
  { ?item wdt:P31/wdt:P279* wd:Q11990 . }
  ?item wdt:P625 ?coord .
  BIND(geof:latitude(?coord) AS ?lat)
  BIND(geof:longitude(?coord) AS ?lng)
  OPTIONAL { ?item wdt:P17 ?country . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ko". }
}
LIMIT 3000
"""
    try:
        resp = requests.get(
            "https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
            headers={
                "User-Agent": "DIVEROID/1.0 (jay@diveroid.com)",
                "Accept": "application/json",
            },
            timeout=60,
        )
        results = resp.json().get("results", {}).get("bindings", [])
    except Exception as e:
        if progress_cb:
            progress_cb(f"⚠️ Wikidata 오류: {e}")
        return []

    points = []
    for r in results:
        try:
            lat = float(r["lat"]["value"])
            lng = float(r["lng"]["value"])
            name = r.get("itemLabel", {}).get("value", "Unknown")
            if not lat or not lng or name.startswith("Q"):
                continue
            points.append(
                {
                    "name": name,
                    "name_en": name,
                    "lat": lat,
                    "lng": lng,
                    "country": r.get("countryLabel", {}).get("value", ""),
                    "region": "",
                    "depth_max": None,
                    "difficulty": "",
                    "description": "",
                    "confidence": "high",
                }
            )
        except Exception:
            continue

    if progress_cb:
        progress_cb(f"Wikidata: {len(points)}개 수집 완료")
    return points


def fetch_curated_seed(progress_cb=None) -> list[dict]:
    """전세계 유명 다이빙 포인트 큐레이션 시드 데이터 (~150개)"""
    if progress_cb:
        progress_cb("큐레이션 시드 데이터 로드 중...")

    points = [
        # 동남아
        {
            "name": "Sipadan Island",
            "name_en": "Sipadan Island",
            "lat": 4.1141,
            "lng": 118.6289,
            "country": "Malaysia",
            "region": "Sabah",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Tubbataha Reef",
            "name_en": "Tubbataha Reef",
            "lat": 8.9667,
            "lng": 119.9167,
            "country": "Philippines",
            "region": "Palawan",
            "depth_max": 30,
            "difficulty": "advanced",
        },
        {
            "name": "Komodo National Park",
            "name_en": "Komodo",
            "lat": -8.5500,
            "lng": 119.4900,
            "country": "Indonesia",
            "region": "East Nusa Tenggara",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Raja Ampat",
            "name_en": "Raja Ampat",
            "lat": -0.5833,
            "lng": 130.5167,
            "country": "Indonesia",
            "region": "West Papua",
            "depth_max": 40,
            "difficulty": "all",
        },
        {
            "name": "Similan Islands",
            "name_en": "Similan Islands",
            "lat": 8.6500,
            "lng": 97.6500,
            "country": "Thailand",
            "region": "Phang Nga",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Richelieu Rock",
            "name_en": "Richelieu Rock",
            "lat": 9.3617,
            "lng": 97.8700,
            "country": "Thailand",
            "region": "Surin Islands",
            "depth_max": 35,
            "difficulty": "advanced",
        },
        {
            "name": "Koh Tao",
            "name_en": "Koh Tao",
            "lat": 10.0957,
            "lng": 99.8401,
            "country": "Thailand",
            "region": "Surat Thani",
            "depth_max": 20,
            "difficulty": "beginner",
        },
        {
            "name": "Bunaken Marine Park",
            "name_en": "Bunaken",
            "lat": 1.6167,
            "lng": 124.7500,
            "country": "Indonesia",
            "region": "North Sulawesi",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Liberty Wreck Tulamben",
            "name_en": "USAT Liberty",
            "lat": -8.2880,
            "lng": 115.5830,
            "country": "Indonesia",
            "region": "Bali",
            "depth_max": 29,
            "difficulty": "beginner",
        },
        {
            "name": "Manta Point Bali",
            "name_en": "Manta Point",
            "lat": -8.7440,
            "lng": 115.1630,
            "country": "Indonesia",
            "region": "Bali",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Barracuda Point Sipadan",
            "name_en": "Barracuda Point",
            "lat": 4.1190,
            "lng": 118.6280,
            "country": "Malaysia",
            "region": "Sabah",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Malapascua Island",
            "name_en": "Malapascua",
            "lat": 11.3301,
            "lng": 124.1104,
            "country": "Philippines",
            "region": "Cebu",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Apo Island",
            "name_en": "Apo Island",
            "lat": 9.0667,
            "lng": 123.2667,
            "country": "Philippines",
            "region": "Negros Oriental",
            "depth_max": 25,
            "difficulty": "beginner",
        },
        {
            "name": "Moalboal Sardine Run",
            "name_en": "Moalboal",
            "lat": 9.9304,
            "lng": 123.3992,
            "country": "Philippines",
            "region": "Cebu",
            "depth_max": 20,
            "difficulty": "beginner",
        },
        # 태평양
        {
            "name": "Great Blue Hole Belize",
            "name_en": "Great Blue Hole",
            "lat": 17.3158,
            "lng": -87.5347,
            "country": "Belize",
            "region": "Lighthouse Reef",
            "depth_max": 125,
            "difficulty": "advanced",
        },
        {
            "name": "Great Barrier Reef",
            "name_en": "Great Barrier Reef",
            "lat": -18.2861,
            "lng": 147.6992,
            "country": "Australia",
            "region": "Queensland",
            "depth_max": 30,
            "difficulty": "all",
        },
        {
            "name": "Cod Hole Great Barrier Reef",
            "name_en": "Cod Hole",
            "lat": -14.6667,
            "lng": 145.4500,
            "country": "Australia",
            "region": "Coral Sea",
            "depth_max": 20,
            "difficulty": "beginner",
        },
        {
            "name": "SS Yongala Wreck",
            "name_en": "SS Yongala",
            "lat": -19.3000,
            "lng": 147.6167,
            "country": "Australia",
            "region": "Queensland",
            "depth_max": 30,
            "difficulty": "advanced",
        },
        {
            "name": "Poor Knights Islands",
            "name_en": "Poor Knights Islands",
            "lat": -35.4833,
            "lng": 174.7333,
            "country": "New Zealand",
            "region": "Northland",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Palau Blue Corner",
            "name_en": "Blue Corner",
            "lat": 7.1833,
            "lng": 134.3667,
            "country": "Palau",
            "region": "Koror",
            "depth_max": 30,
            "difficulty": "advanced",
        },
        {
            "name": "Truk Lagoon",
            "name_en": "Truk Lagoon",
            "lat": 7.4167,
            "lng": 151.7833,
            "country": "Micronesia",
            "region": "Chuuk",
            "depth_max": 60,
            "difficulty": "advanced",
        },
        {
            "name": "Bikini Atoll",
            "name_en": "Bikini Atoll",
            "lat": 11.5833,
            "lng": 165.3833,
            "country": "Marshall Islands",
            "region": "Bikini",
            "depth_max": 55,
            "difficulty": "technical",
        },
        {
            "name": "Christmas Island",
            "name_en": "Christmas Island",
            "lat": -10.4833,
            "lng": 105.6333,
            "country": "Australia",
            "region": "Christmas Island",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Rangiroa Blue Lagoon",
            "name_en": "Rangiroa",
            "lat": -14.9667,
            "lng": -147.6500,
            "country": "French Polynesia",
            "region": "Tuamotu",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Fakarava South Pass",
            "name_en": "Fakarava",
            "lat": -16.3500,
            "lng": -145.6333,
            "country": "French Polynesia",
            "region": "Tuamotu",
            "depth_max": 25,
            "difficulty": "intermediate",
        },
        # 인도양
        {
            "name": "Maldives Maaya Thila",
            "name_en": "Maaya Thila",
            "lat": 3.8833,
            "lng": 72.5833,
            "country": "Maldives",
            "region": "Ari Atoll",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Maldives Shark Point",
            "name_en": "Shark Point",
            "lat": 4.1667,
            "lng": 73.5000,
            "country": "Maldives",
            "region": "North Male Atoll",
            "depth_max": 25,
            "difficulty": "intermediate",
        },
        {
            "name": "Sodwana Bay",
            "name_en": "Sodwana Bay",
            "lat": -27.5500,
            "lng": 32.6833,
            "country": "South Africa",
            "region": "KwaZulu-Natal",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Seychelles Aldabra Atoll",
            "name_en": "Aldabra Atoll",
            "lat": -9.4167,
            "lng": 46.3333,
            "country": "Seychelles",
            "region": "Aldabra",
            "depth_max": 30,
            "difficulty": "advanced",
        },
        {
            "name": "Andaman Islands",
            "name_en": "Andaman Islands",
            "lat": 12.7500,
            "lng": 92.7500,
            "country": "India",
            "region": "Andaman",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        # 홍해
        {
            "name": "Ras Mohammed National Park",
            "name_en": "Ras Mohammed",
            "lat": 27.7333,
            "lng": 34.2333,
            "country": "Egypt",
            "region": "Sinai",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "SS Thistlegorm Wreck",
            "name_en": "SS Thistlegorm",
            "lat": 27.8167,
            "lng": 33.9167,
            "country": "Egypt",
            "region": "Red Sea",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Blue Hole Dahab",
            "name_en": "Blue Hole Dahab",
            "lat": 28.5667,
            "lng": 34.5500,
            "country": "Egypt",
            "region": "South Sinai",
            "depth_max": 130,
            "difficulty": "technical",
        },
        {
            "name": "Brother Islands Egypt",
            "name_en": "Brother Islands",
            "lat": 26.3167,
            "lng": 34.8500,
            "country": "Egypt",
            "region": "Red Sea",
            "depth_max": 60,
            "difficulty": "advanced",
        },
        {
            "name": "Daedalus Reef",
            "name_en": "Daedalus Reef",
            "lat": 24.9333,
            "lng": 35.8667,
            "country": "Egypt",
            "region": "Red Sea",
            "depth_max": 50,
            "difficulty": "advanced",
        },
        # 카리브해
        {
            "name": "Grand Cayman Stingray City",
            "name_en": "Stingray City",
            "lat": 19.3667,
            "lng": -81.3500,
            "country": "Cayman Islands",
            "region": "Grand Cayman",
            "depth_max": 5,
            "difficulty": "beginner",
        },
        {
            "name": "Bloody Bay Wall Little Cayman",
            "name_en": "Bloody Bay Wall",
            "lat": 19.7000,
            "lng": -80.0833,
            "country": "Cayman Islands",
            "region": "Little Cayman",
            "depth_max": 50,
            "difficulty": "intermediate",
        },
        {
            "name": "Bonaire Salt Pier",
            "name_en": "Salt Pier",
            "lat": 12.1000,
            "lng": -68.2833,
            "country": "Netherlands Antilles",
            "region": "Bonaire",
            "depth_max": 20,
            "difficulty": "beginner",
        },
        {
            "name": "Cozumel Palancar Reef",
            "name_en": "Palancar Reef",
            "lat": 20.3500,
            "lng": -87.0833,
            "country": "Mexico",
            "region": "Quintana Roo",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Cenote Dos Ojos",
            "name_en": "Dos Ojos Cenote",
            "lat": 20.3983,
            "lng": -87.3419,
            "country": "Mexico",
            "region": "Quintana Roo",
            "depth_max": 10,
            "difficulty": "intermediate",
        },
        # 유럽·지중해
        {
            "name": "Bonne Terre Mine Missouri",
            "name_en": "Bonne Terre Mine",
            "lat": 37.9209,
            "lng": -90.5540,
            "country": "USA",
            "region": "Missouri",
            "depth_max": 18,
            "difficulty": "beginner",
        },
        {
            "name": "Blue Grotto Malta",
            "name_en": "Blue Grotto",
            "lat": 35.8167,
            "lng": 14.4333,
            "country": "Malta",
            "region": "Qrendi",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "Vis Island Croatia",
            "name_en": "Vis Island",
            "lat": 43.0667,
            "lng": 16.1833,
            "country": "Croatia",
            "region": "Dalmatia",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "Lustica Peninsula Montenegro",
            "name_en": "Lustica",
            "lat": 42.3500,
            "lng": 18.5833,
            "country": "Montenegro",
            "region": "Bay of Kotor",
            "depth_max": 30,
            "difficulty": "beginner",
        },
        # 한국
        {
            "name": "제주 문섬",
            "name_en": "Munseom Island",
            "lat": 33.2167,
            "lng": 126.5500,
            "country": "Korea",
            "region": "Jeju",
            "depth_max": 30,
            "difficulty": "intermediate",
        },
        {
            "name": "제주 범섬",
            "name_en": "Beomseom Island",
            "lat": 33.2000,
            "lng": 126.5833,
            "country": "Korea",
            "region": "Jeju",
            "depth_max": 35,
            "difficulty": "intermediate",
        },
        {
            "name": "제주 섶섬",
            "name_en": "Seopseom Island",
            "lat": 33.2500,
            "lng": 126.5167,
            "country": "Korea",
            "region": "Jeju",
            "depth_max": 25,
            "difficulty": "intermediate",
        },
        {
            "name": "제주 침선 (서귀포)",
            "name_en": "Jeju Wreck",
            "lat": 33.2250,
            "lng": 126.5600,
            "country": "Korea",
            "region": "Jeju Seogwipo",
            "depth_max": 40,
            "difficulty": "advanced",
        },
        {
            "name": "거제 홍도",
            "name_en": "Hongdo Geoje",
            "lat": 34.7167,
            "lng": 128.7000,
            "country": "Korea",
            "region": "Gyeongnam",
            "depth_max": 25,
            "difficulty": "intermediate",
        },
        {
            "name": "울릉도 저동 포인트",
            "name_en": "Ulleungdo",
            "lat": 37.5000,
            "lng": 130.8667,
            "country": "Korea",
            "region": "Gyeongbuk",
            "depth_max": 30,
            "difficulty": "advanced",
        },
        {
            "name": "속초 조도",
            "name_en": "Jodo Sokcho",
            "lat": 38.2167,
            "lng": 128.6000,
            "country": "Korea",
            "region": "Gangwon",
            "depth_max": 20,
            "difficulty": "beginner",
        },
        # 일본
        {
            "name": "요나구니 해저 유적",
            "name_en": "Yonaguni Monument",
            "lat": 24.4300,
            "lng": 123.0000,
            "country": "Japan",
            "region": "Okinawa",
            "depth_max": 27,
            "difficulty": "advanced",
        },
        {
            "name": "쿠메지마 트라이앵글",
            "name_en": "Kume Island",
            "lat": 26.3333,
            "lng": 126.8000,
            "country": "Japan",
            "region": "Okinawa",
            "depth_max": 40,
            "difficulty": "intermediate",
        },
        {
            "name": "이시가키 만타 스크램블",
            "name_en": "Manta Scramble Ishigaki",
            "lat": 24.3667,
            "lng": 124.1500,
            "country": "Japan",
            "region": "Okinawa",
            "depth_max": 20,
            "difficulty": "intermediate",
        },
        {
            "name": "이즈 해양공원",
            "name_en": "Izu Ocean Park",
            "lat": 34.8500,
            "lng": 139.1167,
            "country": "Japan",
            "region": "Shizuoka",
            "depth_max": 25,
            "difficulty": "beginner",
        },
    ]

    for p in points:
        p.setdefault("confidence", "high")
        p.setdefault("description", "")

    if progress_cb:
        progress_cb(f"큐레이션 시드: {len(points)}개 로드 완료")
    return points


# ──────────────────────────────
# The Dive API (API키 필요)
# ──────────────────────────────


def fetch_thediveapi(api_key: str, progress_cb=None) -> list[dict]:
    """The Dive API — https://thediveapi.com (무료 API키 필요)"""
    if not api_key:
        return []

    if progress_cb:
        progress_cb("The Dive API 데이터 수집 중...")

    headers = {"x-api-key": api_key}
    points = []
    page = 1

    while True:
        try:
            resp = requests.get(
                "https://api.thediveapi.com/v1/sites",
                params={"page": page, "limit": 100},
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get("data", data.get("sites", []))
            if not items:
                break

            for item in items:
                lat = item.get("lat", item.get("latitude"))
                lng = item.get("lng", item.get("longitude"))
                if not lat or not lng:
                    continue
                points.append(
                    {
                        "name": item.get("name", "Unknown"),
                        "name_en": item.get("name_en", item.get("name", "")),
                        "lat": float(lat),
                        "lng": float(lng),
                        "country": item.get("country", ""),
                        "region": item.get("region", ""),
                        "depth_max": item.get("max_depth"),
                        "difficulty": item.get("difficulty", ""),
                        "description": item.get("description", ""),
                        "confidence": "high",
                    }
                )

            if len(items) < 100:
                break
            page += 1
            time.sleep(0.3)

        except Exception:
            break

    if progress_cb:
        progress_cb(f"The Dive API: {len(points)}개 수집 완료")

    return points
