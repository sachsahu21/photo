

# ============================================================
# FILE: web/streamlit_app.py  (#6 - NEW)
# ============================================================
"""
Streamlit Web Dashboard for Image Scanner.
Run with: streamlit run web/streamlit_app.py
"""

import sys
import pickle
from pathlib import Path
from collections import Counter

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import streamlit as st
    import pandas as pd
    ST_OK = True
except ImportError:
    ST_OK = False
    print("Streamlit not installed. Run: pip install streamlit")
    sys.exit(1)


def load_records(pkl_path='records_backup.pkl'):
    """Load records from pickle backup."""
    if not Path(pkl_path).exists():
        return None
    with open(pkl_path, 'rb') as f:
        return pickle.load(f)


def main():
    st.set_page_config(page_title="Image Scanner Dashboard", layout="wide", page_icon="📷")

    st.title("📷 Image Scanner Dashboard")
    st.markdown("---")

    # Sidebar
    st.sidebar.header("📁 Data Source")
    pkl_path = st.sidebar.text_input("Backup file path", value="records_backup.pkl")

    if st.sidebar.button("Load Data"):
        records = load_records(pkl_path)
        if records:
            st.session_state['records'] = records
            st.sidebar.success(f"Loaded {len(records)} records")
        else:
            st.sidebar.error("File not found or empty")

    if 'records' not in st.session_state:
        st.info("👈 Load a records backup file from the sidebar to get started.")
        st.markdown("""
        ### How to use:
        1. Run `python main.py` and complete Task 1 (Scan)
        2. This creates `records_backup.pkl`
        3. Enter the path above and click **Load Data**
        """)
        return

    records = st.session_state['records']
    df = pd.DataFrame(records)

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", "🖼️ Gallery", "🔍 Duplicates", "📸 Blurry", "🏷️ Tags & Faces", "📈 Analytics"
    ])

    with tab1:
        st.header("Overview")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Files", len(df))
        c2.metric("Images", len(df[df.get('file_type', pd.Series()) == 'image']) if 'file_type' in df.columns else 0)
        c3.metric("Videos", len(df[df.get('file_type', pd.Series()) == 'video']) if 'file_type' in df.columns else 0)
        c4.metric("Total Size", f"{df['size_mb'].sum():.0f} MB" if 'size_mb' in df.columns else "N/A")

        c5, c6, c7, c8 = st.columns(4)
        if 'is_duplicate' in df.columns:
            c5.metric("Duplicates", len(df[df['is_duplicate'] == 'YES']))
        if 'is_blurry' in df.columns:
            c6.metric("Blurry", len(df[df['is_blurry'] == True]))
        if 'quality_score' in df.columns:
            qs = df['quality_score'].dropna()
            c7.metric("Avg Quality", f"{qs.mean():.1f}%" if len(qs) > 0 else "N/A")
        if 'face_count' in df.columns:
            c8.metric("Total Faces", int(df['face_count'].fillna(0).sum()))

        # Format distribution
        if 'extension' in df.columns:
            st.subheader("Format Distribution")
            ext_counts = df['extension'].value_counts()
            st.bar_chart(ext_counts)

    with tab2:
        st.header("Image Gallery")
        if 'file_type' in df.columns:
            ft = st.selectbox("Filter by type", ['All', 'image', 'video'])
            filtered = df if ft == 'All' else df[df['file_type'] == ft]
        else:
            filtered = df

        # Quality filter
        if 'quality_score' in df.columns:
            min_q, max_q = st.slider("Quality range", 0, 100, (0, 100))
            mask = filtered['quality_score'].fillna(0).between(min_q, max_q)
            filtered = filtered[mask]

        st.write(f"Showing {len(filtered)} files")

        # Show as table with key columns
        display_cols = [c for c in ['filename', 'file_type', 'size_mb', 'quality_score',
                                     'blur_score', 'face_count', 'auto_tags', 'location_name',
                                     'date_taken', 'full_path'] if c in filtered.columns]
        if display_cols:
            st.dataframe(filtered[display_cols], use_container_width=True, height=500)

    with tab3:
        st.header("Duplicate Groups")
        if 'is_duplicate' in df.columns:
            dups = df[df['is_duplicate'] == 'YES'].copy()
            if len(dups) > 0:
                groups = dups['duplicate_group'].unique()
                st.write(f"**{len(groups)} duplicate groups**, {len(dups)} total files")

                selected_group = st.selectbox("Select group", sorted(groups))
                group_df = dups[dups['duplicate_group'] == selected_group]

                for _, row in group_df.iterrows():
                    is_best = str(row.get('is_best_in_group', '')).lower() == 'yes'
                    color = "🟢" if is_best else "🔴"
                    rec_text = row.get('recommendation', '')

                    col1, col2 = st.columns([1, 3])
                    with col1:
                        # Try to show thumbnail
                        thumb = row.get('thumbnail_path')
                        fp = row.get('full_path', '')
                        if thumb and Path(str(thumb)).exists():
                            st.image(str(thumb), width=150)
                        elif fp and Path(str(fp)).exists() and row.get('file_type') == 'image':
                            try:
                                st.image(str(fp), width=150)
                            except Exception:
                                st.write("🖼️ Preview unavailable")
                        else:
                            st.write("🖼️ No preview")

                    with col2:
                        st.write(f"{color} **{row.get('filename', '')}** - {rec_text}")
                        st.write(f"Size: {row.get('size_mb', 0)} MB | "
                                 f"Quality: {row.get('quality_score', 'N/A')}% | "
                                 f"Resolution: {row.get('width', '?')}x{row.get('height', '?')}")

                    st.markdown("---")
            else:
                st.success("No duplicates found!")
        else:
            st.info("No duplicate data available")

    with tab4:
        st.header("Blurry Images")
        if 'is_blurry' in df.columns:
            blurry = df[df['is_blurry'] == True].sort_values('blur_score')
            st.write(f"**{len(blurry)} blurry images**")
            if len(blurry) > 0:
                display_cols = [c for c in ['filename', 'blur_score', 'quality_rating',
                                             'quality_score', 'size_mb', 'full_path'] if c in blurry.columns]
                st.dataframe(blurry[display_cols], use_container_width=True)

                if 'blur_score' in blurry.columns:
                    st.subheader("Blur Score Distribution")
                    st.bar_chart(blurry['blur_score'].dropna())

    with tab5:
        st.header("Tags & Faces")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Face Categories")
            if 'face_category' in df.columns:
                fc = df['face_category'].value_counts()
                st.bar_chart(fc)

        with col2:
            st.subheader("Top Tags")
            if 'primary_tag' in df.columns:
                tags = df['primary_tag'].dropna().value_counts().head(15)
                if len(tags) > 0:
                    st.bar_chart(tags)

        # Location map
        if 'gps_lat' in df.columns and 'gps_lon' in df.columns:
            geo = df.dropna(subset=['gps_lat', 'gps_lon'])
            if len(geo) > 0:
                st.subheader(f"📍 Photo Locations ({len(geo)} geotagged)")
                map_df = geo[['gps_lat', 'gps_lon']].rename(columns={'gps_lat': 'lat', 'gps_lon': 'lon'})
                st.map(map_df)

    with tab6:
        st.header("Storage Analytics")

        if 'size_mb' in df.columns:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Size by Format")
                size_by_ext = df.groupby('extension')['size_mb'].sum().sort_values(ascending=False)
                st.bar_chart(size_by_ext)

            with c2:
                st.subheader("Files by Year")
                if 'date_taken' in df.columns:
                    df_copy = df.copy()
                    df_copy['year'] = pd.to_datetime(df_copy['date_taken'], errors='coerce').dt.year
                    by_year = df_copy['year'].dropna().value_counts().sort_index()
                    if len(by_year) > 0:
                        st.bar_chart(by_year)

        if 'quality_score' in df.columns:
            st.subheader("Quality Distribution")
            qs = df['quality_score'].dropna()
            if len(qs) > 0:
                st.bar_chart(qs.value_counts(bins=10).sort_index())


if __name__ == '__main__':
    main()
