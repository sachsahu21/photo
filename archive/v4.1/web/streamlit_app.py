"""Dashboard v4.1"""

from pathlib import Path

try:
    import streamlit as st
    import pandas as pd
    ST_OK = True
except ImportError:
    ST_OK = False


def main():
    if not ST_OK:
        print('pip install streamlit pandas')
        return
    st.set_page_config(page_title='Image Scanner v4.1', layout='wide')
    st.title('Image Scanner v4.1')
    pkl = Path('records-backup.pkl')
    if not pkl.exists():
        st.warning('No data. Run main.py first.')
        return
    import pickle
    with open(pkl, 'rb') as f:
        df = pd.DataFrame(pickle.load(f))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Total', len(df))
    c2.metric('Images', len(df[df['file_type'] == 'image']))
    c3.metric('Videos', len(df[df['file_type'] == 'video']))
    c4.metric('Dups', len(df[df['is_duplicate'] == 'YES']))
    c5.metric('Similar', len(df[df['is_similar'] == 'YES']))
    t1, t2, t3 = st.tabs(['Overview', 'Duplicates', 'Similar'])
    with t1:
        if 'extension' in df.columns:
            st.bar_chart(df['extension'].value_counts().head(15))
    with t2:
        d = df[df['is_duplicate'] == 'YES']
        st.dataframe(
            d[['filename', 'duplicate_group', 'is_best_in_group', 'size_mb', 'recommendation']].head(100)
        ) if len(d) > 0 else st.info('None')
    with t3:
        s = df[df['is_similar'] == 'YES']
        st.dataframe(
            s[['filename', 'similar_group', 'similar_score', 'similar_methods']].head(100)
        ) if len(s) > 0 else st.info('None')


if __name__ == '__main__':
    main()

