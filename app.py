"""
DIVEROID Dive Point Manager
- Global open data collection (OSM, Wikidata)
- AI image extraction from dive shop maps
- Manual point entry / editing
- Developer CSV/JSON export
"""

import base64
import json
import os

import anthropic
import folium
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from db import init_db, insert_points, get_all_points, get_stats, delete_point
from fetcher import fetch_osm, fetch_wikidata, fetch_curated_seed, fetch_thediveapi

load_dotenv()
init_db()

st.set_page_config(page_title="DIVEROID Point Manager", page_icon="🤿", layout="wide")

# ── Sidebar
with st.sidebar:
    st.title("🤿 DIVEROID")
    st.caption("Global Dive Point Manager")
    st.divider()

    stats = get_stats()
    st.metric("Total Points", f"{stats['total']:,}")
    st.metric("Countries", f"{stats['countries']}")
    if stats["by_source"]:
        st.caption("By Source")
        for src, cnt in stats["by_source"].items():
            st.caption(f"  • {src}: {cnt:,}")

    st.divider()
    dive_api_key = st.text_input(
        "The Dive API Key (optional)",
        type="password",
        help="Get a free key at https://thediveapi.com",
    )
    anthropic_key = st.text_input(
        "Anthropic API Key (optional)",
        type="password",
        help="Required for AI image extraction. Falls back to environment variable.",
    )

# ── Tabs
tab1, tab2, tab3, tab4 = st.tabs(
    ["🗺️ World Map", "📥 Collect Data", "➕ Add Point", "📤 Export"]
)


# ════════════════════════════════
# TAB 1 — World Map
# ════════════════════════════════
with tab1:
    st.header("🗺️ Global Dive Point Map")

    all_points = get_all_points()

    if not all_points:
        st.info("No data yet. Go to the 'Collect Data' tab to fetch dive points.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            search = st.text_input("🔍 Search by name", "")
        with col2:
            sources = list({p["source"] for p in all_points if p["source"]})
            sel_source = st.multiselect("Filter by Source", sources, default=sources)
        with col3:
            countries = sorted({p["country"] for p in all_points if p["country"]})
            sel_country = st.multiselect("Filter by Country", countries)

        filtered = all_points
        if search:
            filtered = [
                p
                for p in filtered
                if search.lower() in (p["name"] or "").lower()
                or search.lower() in (p["name_en"] or "").lower()
            ]
        if sel_source:
            filtered = [p for p in filtered if p["source"] in sel_source]
        if sel_country:
            filtered = [p for p in filtered if p["country"] in sel_country]

        st.caption(f"Showing {len(filtered):,} of {len(all_points):,} points")

        if filtered:
            lats = [p["lat"] for p in filtered]
            lngs = [p["lng"] for p in filtered]
            m = folium.Map(
                location=[sum(lats) / len(lats), sum(lngs) / len(lngs)],
                zoom_start=3,
                tiles="CartoDB positron",
            )

            source_colors = {
                "OpenStreetMap": "blue",
                "Wikidata": "green",
                "The Dive API": "purple",
                "AI 이미지 추출": "orange",
                "curated_seed": "cadetblue",
                "jeju_shop_maps_seogwipo": "orange",
                "jeju_shop_maps_other": "orange",
                "bubble_tank_seogwipo": "orange",
                "jeju_shop_maps_other": "orange",
                "수동 입력": "red",
            }

            for p in filtered[:5000]:
                color = source_colors.get(p.get("source", ""), "gray")
                depth_str = f"{p.get('depth_max')}m" if p.get("depth_max") else "N/A"
                folium.CircleMarker(
                    location=[p["lat"], p["lng"]],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_opacity=0.7,
                    popup=folium.Popup(
                        f"<b>{p['name']}</b><br>"
                        f"{p.get('name_en','')}<br>"
                        f"📍 {p.get('country','')} · {p.get('region','')}<br>"
                        f"🌊 Max depth: {depth_str}<br>"
                        f"⚡ Difficulty: {p.get('difficulty','') or 'N/A'}<br>"
                        f"📝 {p.get('description','')}<br>"
                        f"Source: {p.get('source','')}",
                        max_width=240,
                    ),
                    tooltip=p["name"],
                ).add_to(m)

            legend = """
            <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
                        padding:10px;border-radius:8px;border:1px solid #ccc;font-size:12px;">
            <b>Source</b><br>
            🔵 OpenStreetMap<br>🟢 Wikidata<br>🟣 The Dive API<br>
            🔵 Curated Seeds<br>🟠 Shop Maps / AI<br>🔴 Manual Entry
            </div>"""
            m.get_root().html.add_child(folium.Element(legend))

            st_folium(m, width=None, height=600, use_container_width=True)
        else:
            st.warning("No points match the current filters.")


# ════════════════════════════════
# TAB 2 — Collect Data
# ════════════════════════════════
with tab2:
    st.header("📥 Collect Open Data")
    st.caption("Automatically fetch global dive points from free public databases.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🌍 OpenStreetMap")
        st.caption("Free · No API key · Community-contributed data")
        osm_scope = st.radio("Scope", ["Global", "Specific region"], key="osm_scope")
        osm_bbox = ""
        if osm_scope == "Specific region":
            st.caption("Bounding box: south,west,north,east")
            osm_bbox = st.text_input("e.g. Korea: 33,124,38,130", "33,124,38,130")

        if st.button("🔄 Fetch from OpenStreetMap", type="primary"):
            progress = st.empty()
            with st.spinner("Collecting... (global may take 1-2 min)"):
                points = fetch_osm(osm_bbox or None, lambda msg: progress.caption(msg))
                if points:
                    cnt = insert_points(points, "OpenStreetMap")
                    st.success(
                        f"✅ {cnt:,} new points saved! (fetched: {len(points):,})"
                    )
                else:
                    st.warning("No points collected.")

    with col2:
        st.subheader("🌟 Curated + Wikidata")
        st.caption("Free · No API key · ~55 famous sites + Wikidata wrecks/reefs")
        if st.button("🔄 Fetch Curated & Wikidata", type="primary"):
            progress = st.empty()
            with st.spinner("Collecting..."):
                seed = fetch_curated_seed(lambda msg: progress.caption(msg))
                cnt1 = insert_points(seed, "curated_seed")
                wiki = fetch_wikidata(lambda msg: progress.caption(msg))
                cnt2 = insert_points(wiki, "Wikidata")
                st.success(f"✅ Curated: {cnt1} + Wikidata: {cnt2} points saved!")

    st.divider()

    st.subheader("🔑 The Dive API (17,000+ sites)")
    st.caption("Free API key required → https://thediveapi.com")
    if not dive_api_key:
        st.info("Enter your Dive API key in the sidebar to use this feature.")
    else:
        if st.button("🔄 Fetch from The Dive API", type="primary"):
            progress = st.empty()
            with st.spinner("Collecting... (may take several minutes)"):
                points = fetch_thediveapi(
                    dive_api_key, lambda msg: progress.caption(msg)
                )
                if points:
                    cnt = insert_points(points, "The Dive API")
                    st.success(f"✅ {cnt:,} new points saved!")
                else:
                    st.warning("No data. Please check your API key.")


# ════════════════════════════════
# TAB 3 — Add Point
# ════════════════════════════════
with tab3:
    st.header("➕ Add Dive Point")

    add_tab1, add_tab2 = st.tabs(["🖼️ Extract from Shop Map (AI)", "✏️ Manual Entry"])

    with add_tab1:
        st.caption(
            "Upload a dive shop map image — AI will automatically extract dive points."
        )

        region_ai = st.text_input(
            "Region name", placeholder="e.g. Jeju Seogwipo, Komodo Indonesia"
        )
        uploaded = st.file_uploader(
            "Upload shop map image", type=["png", "jpg", "jpeg", "webp"]
        )

        if uploaded:
            st.image(uploaded, use_container_width=True)

        if uploaded and region_ai and st.button("🔍 Extract with AI", type="primary"):
            image_bytes = uploaded.read()
            b64 = base64.b64encode(image_bytes).decode()
            media_type = uploaded.type or "image/jpeg"

            client = anthropic.Anthropic(api_key=anthropic_key or None)

            with st.spinner("Analyzing image with AI..."):
                try:
                    resp = client.messages.create(
                        model="claude-opus-4-5",
                        max_tokens=4096,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": b64,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": f"""This image is a dive point map of the {region_ai} region.

Extract all dive point names (marked with flags or markers) and estimate GPS coordinates.
Base your estimates on real geographic features visible in the map (islands, ports, coastlines).

Respond ONLY with JSON:
{{"region":"{region_ai}","points":[{{"name":"name","name_en":"english name","lat":latitude,"lng":longitude,"confidence":"high/medium/low","note":"estimation basis"}}]}}""",
                                    },
                                ],
                            }
                        ],
                    )

                    raw = resp.content[0].text.strip()
                    data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
                    points = data.get("points", [])

                    if points:
                        st.session_state["ai_points"] = points
                        st.session_state["ai_region"] = region_ai
                        st.success(
                            f"✅ {len(points)} points extracted! Auto-correct coordinates below, then save."
                        )
                    else:
                        st.error("Could not extract points from this image.")

                except Exception as e:
                    st.error(f"Error: {e}")

        if "ai_points" in st.session_state:
            points = st.session_state["ai_points"]
            region_ai = st.session_state.get("ai_region", "")
            df = pd.DataFrame(points)

            col_a, col_b = st.columns([1, 2])
            with col_a:
                if st.button(
                    "🌍 Auto-correct Coordinates",
                    type="primary",
                    use_container_width=True,
                ):
                    from geopy.geocoders import Nominatim
                    from geopy.extra.rate_limiter import RateLimiter

                    geo = Nominatim(user_agent="DIVEROID/1.0")
                    geocode = RateLimiter(geo.geocode, min_delay_seconds=1.1)
                    improved = 0
                    prog = st.progress(0, text="Looking up coordinates...")
                    for i, row in df.iterrows():
                        prog.progress(
                            (i + 1) / len(df), text=f"Searching: {row['name']}"
                        )
                        for q in [
                            f"{row['name']} {region_ai}",
                            f"{row.get('name_en','')} {region_ai}",
                            row["name"],
                        ]:
                            if not q.strip():
                                continue
                            try:
                                loc = geocode(q)
                                if (
                                    loc
                                    and abs(loc.latitude - float(row["lat"])) < 1.5
                                    and abs(loc.longitude - float(row["lng"])) < 1.5
                                ):
                                    df.at[i, "lat"] = round(loc.latitude, 5)
                                    df.at[i, "lng"] = round(loc.longitude, 5)
                                    df.at[i, "confidence"] = "high"
                                    df.at[i, "note"] = f"✅ Auto-corrected: {q}"
                                    improved += 1
                                    break
                            except Exception:
                                continue
                    prog.empty()
                    st.session_state["ai_points"] = df.to_dict("records")
                    st.success(
                        f"✅ {improved} corrected / {len(df)-improved} kept as AI estimate"
                    )
                    st.rerun()
            with col_b:
                st.caption(
                    "💡 Known geographic features are auto-corrected; dive-specific names keep AI estimates."
                )

            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "lat": st.column_config.NumberColumn("Latitude", format="%.5f"),
                    "lng": st.column_config.NumberColumn("Longitude", format="%.5f"),
                    "confidence": st.column_config.TextColumn("Confidence"),
                },
            )

            if st.button("💾 Save to DB", type="primary", use_container_width=True):
                save_points = edited.to_dict("records")
                for p in save_points:
                    p["region"] = region_ai
                cnt = insert_points(save_points, "AI 이미지 추출")
                st.success(f"✅ {cnt} points saved!")
                del st.session_state["ai_points"]
                st.rerun()

    with add_tab2:
        st.caption(
            "Look up coordinates in Google Maps (right-click → copy coordinates) and enter them here."
        )

        with st.form("manual_add"):
            c1, c2 = st.columns(2)
            with c1:
                m_name = st.text_input("Point Name *", placeholder="Grand Canyon")
                m_name_en = st.text_input("English Name", placeholder="Grand Canyon")
                m_region = st.text_input("Region", placeholder="Jeju Seogwipo")
                m_country = st.text_input("Country", placeholder="South Korea")
            with c2:
                m_lat = st.number_input("Latitude *", format="%.5f", value=0.0)
                m_lng = st.number_input("Longitude *", format="%.5f", value=0.0)
                m_depth = st.number_input("Max Depth (m)", value=0.0)
                m_difficulty = st.selectbox(
                    "Difficulty",
                    ["", "beginner", "intermediate", "advanced", "technical"],
                )
            m_desc = st.text_area("Description")

            if st.form_submit_button("💾 Save", type="primary"):
                if not m_name or not m_lat or not m_lng:
                    st.error("Name, latitude, and longitude are required.")
                else:
                    cnt = insert_points(
                        [
                            {
                                "name": m_name,
                                "name_en": m_name_en,
                                "lat": m_lat,
                                "lng": m_lng,
                                "region": m_region,
                                "country": m_country,
                                "depth_max": m_depth or None,
                                "difficulty": m_difficulty,
                                "description": m_desc,
                                "confidence": "high",
                            }
                        ],
                        "Manual Entry",
                    )
                    if cnt:
                        st.success(f"✅ '{m_name}' saved!")
                        st.rerun()
                    else:
                        st.warning(
                            "A point with the same name and location already exists."
                        )


# ════════════════════════════════
# TAB 4 — Export
# ════════════════════════════════
with tab4:
    st.header("📤 Export Data")

    all_points = get_all_points()
    if not all_points:
        st.info("No data yet. Collect some dive points first.")
    else:
        df = pd.DataFrame(all_points)

        st.subheader("Preview")
        st.dataframe(
            df[
                [
                    "name",
                    "name_en",
                    "lat",
                    "lng",
                    "country",
                    "region",
                    "depth_max",
                    "difficulty",
                    "source",
                    "confidence",
                ]
            ].head(50),
            use_container_width=True,
        )

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("CSV Download")
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "📥 Download Full CSV",
                csv,
                "diveroid_dive_points.csv",
                "text/csv",
                use_container_width=True,
                type="primary",
            )

        with col2:
            st.subheader("JSON Download")
            json_data = df.to_json(orient="records", force_ascii=False, indent=2)
            st.download_button(
                "📥 Download Full JSON",
                json_data,
                "diveroid_dive_points.json",
                "application/json",
                use_container_width=True,
                type="primary",
            )

        st.divider()
        st.subheader("🗑️ Delete Point")
        del_id = st.number_input("Point ID to delete", min_value=1, step=1)
        if st.button("Delete", type="secondary"):
            delete_point(int(del_id))
            st.success(f"Point ID {del_id} deleted.")
            st.rerun()
