
import re
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from config import (
    PROC_DIR as SRC_DIR, VIS_DIR as OUT_DIR,
    PERIOD_MAP, PERIOD_ORDER,
    MAX_ROWS, MIN_SHARE,
)


# summary desc for all code
def summary_desc_mapping(code: str) -> str:
    code = str(code).strip().upper()
    if not re.fullmatch(r'[A-Z]\d{2}', code):
        return 'Other (unknown)'
    letter, num = code[0], int(code[1:])
    if letter in ('A', 'B'): return 'Infectious and parasitic (A00-B99)'
    if letter == 'C' or (letter == 'D' and num <= 48): return 'Neoplasms (C00-D48)'
    if letter == 'D': return 'Blood and immune (D50-D89)'
    if letter == 'E': return 'Endocrine/metabolic (E00-E90)'
    if letter == 'F': return 'Mental and behavioural (F00-F99)'
    if letter == 'G': return 'Nervous system (G00-G99)'
    if letter == 'H' and num <= 59: return 'Eye and adnexa (H00-H59)'
    if letter == 'H': return 'Ear and mastoid (H60-H95)'
    if letter == 'I': return 'Circulatory (I00-I99)'
    if letter == 'J': return 'Respiratory (J00-J99)'
    if letter == 'K': return 'Digestive (K00-K93)'
    if letter == 'L': return 'Skin/subcutaneous (L00-L99)'
    if letter == 'M': return 'Musculoskeletal (M00-M99)'
    if letter == 'N': return 'Genitourinary (N00-N99)'
    if letter == 'O': return 'Pregnancy/childbirth (O00-O99)'
    if letter == 'P': return 'Perinatal (P00-P96)'
    if letter == 'Q': return 'Congenital (Q00-Q99)'
    if letter == 'R': return 'Symptoms/signs (R00-R99)'
    if letter in ('S', 'T'): return 'Injury/poisoning (S00-T98)'
    if letter in ('V', 'W', 'X', 'Y'): return 'External causes (V01-Y98)'
    if letter == 'U': return 'Special purpose (U00-U99)'
    if letter == 'Z': return 'Health status/contact (Z00-Z99)'
    return 'Other (unknown)'


def ICD_sort_key(label: str) -> int:
    m = re.search(r'\(([A-Z]\d{2})', label)
    if not m:
        return 10 ** 9
    c = m.group(1)
    return (ord(c[0]) - ord('A')) * 100 + int(c[1:])


# Shortened labels for display — applied after best_description lookup
SHORT_DESC = {
    'B99': 'Other/unspecified infectious diseases',
    'C90': 'Multiple myeloma & plasma cell neoplasms',
    'C97': 'Multiple primary malignant neoplasms',
    'D12': 'Benign neoplasm: colon/rectum/anus',
    'E30': 'Disorders of puberty NEC',
    'F05': 'Delirium (non-substance-induced)',
    'I10': 'Essential hypertension',
    'I82': 'Other venous embolism/thrombosis',
    'J10': 'Influenza (identified seasonal virus)',
    'J13': 'Pneumococcal pneumonia',
    'J40': 'Bronchitis NOS (not acute/chronic)',
    'M20': 'Acquired deformities of fingers/toes',
    'N86': 'Erosion/ectropion of cervix uteri',
    'O28': 'Abnormal antenatal screening findings',
    'O36': 'Maternal care: suspected fetal problems',
    'R60': 'Oedema NEC',
    'U07': 'Emergency use of U07 - include COVID-19',
    'Z12': 'Special cancer screening examination',
    'Z38': 'Liveborn infants (place of birth)',
    'Z42': 'Follow-up care: plastic surgery',
    'Z75': 'Problems: medical facilities/health care',
}


def load_data() :
    frames = []
    for period, group in PERIOD_MAP.items():
        f = f'{SRC_DIR}/{period}.csv'
        assert os.path.isfile(f), f'File not found: {f}'

        # only load code, desc and admissions for fae
        df = pd.read_csv(f, usecols=['code', 'description', 'admissions'])
        df['period_group'] = group
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def best_description(df):
    # Pick the most common non-empty description per code across all loaded years.
    lookup = {}
    for code, g in df.groupby('code'):
        descs = g['description'].dropna().astype(str).str.strip() # all desc for same code
        descs = descs[descs != ''] # drop empty descriptions
        if descs.empty:
            lookup[code] = code  # fallback to code itself
        else:
            lookup[code] = descs.value_counts().idxmax()
    return lookup


# process data to get mean admission for three period groups (pre-lockdown, lockdown, post-lockdown)
def aggregate(df):
    # mean admissions across years within each period group, per code
    grp = df.groupby(['period_group', 'code'], as_index=False)['admissions'].mean()

    # ensure every code × every group is present (fill 0 if missing)
    codes = grp['code'].unique()
    full = pd.DataFrame(
        [(c, p) for c in codes for p in PERIOD_ORDER],
        columns=['code', 'period_group'],
    )
    grp = full.merge(grp, on=['code', 'period_group'], how='left')
    grp['admissions'] = grp['admissions'].fillna(0.0)

    # admission share within each group
    totals = grp.groupby('period_group')['admissions'].sum().rename('group_total')
    grp = grp.merge(totals, on='period_group')
    grp['share'] = np.where(grp['group_total'] > 0, grp['admissions'] / grp['group_total'], 0.0)

    # summary: one row per code
    aggregated_data = grp.pivot_table(index='code', columns='period_group',
                            values=['admissions', 'share'], fill_value=0.0,
                            ).reset_index()
    aggregated_data.columns = [c if isinstance(c, str) else (c[0] if c[1] == '' else f'{c[1]}_{c[0]}') 
                       for c in aggregated_data.columns]

    pre = aggregated_data['pre_lockdown_share'].astype(float)
    ok = pre >= MIN_SHARE
    aggregated_data['baseline_share'] = pre
    aggregated_data['lockdown_pct_change'] = np.where(ok, (aggregated_data['lockdown_share'] - pre) / pre * 100, np.nan)
    aggregated_data['post_pct_change'] = np.where(ok, (aggregated_data['post_lockdown_share'] - pre) / pre * 100, np.nan)
    aggregated_data['summary_desc'] = aggregated_data['code'].map(summary_desc_mapping)
    return aggregated_data


# select rows to show in the figure
def select_categories(df):
    # total 45 rows: 
    #   15 for top baseline share, 
    #   15 for top positive change, 
    #   15 for top negative change.
    n = MAX_ROWS // 3
    top_base = df.nlargest(n, 'baseline_share')
    fin = df[np.isfinite(df['lockdown_pct_change'])]
    top_pos  = fin.nlargest(n, 'lockdown_pct_change')
    top_neg  = fin.nsmallest(n, 'lockdown_pct_change')

    selected = pd.concat([top_base, top_pos, top_neg]).drop_duplicates('code')
    return selected.reset_index(drop=True)


# find boundaries between different summary_desc groups
def desc_boundaries(descs):
    bounds, centers = [], []
    start = 0
    for i in range(1, len(descs) + 1):
        if i == len(descs) or descs[i] != descs[start]:
            bounds.append(i)
            centers.append((descs[start], (start + i - 1) / 2.0))
            start = i
    return bounds, centers

# draw the figure
def draw(plot_df):
    sns.set_theme(style='white')
    rows = len(plot_df)

    fig = plt.figure(figsize=(12, 16))
    gs = fig.add_gridspec(1, 4, width_ratios=[1.2, 0.6, 1.8, 1.8], wspace=0.06)
    ax_grp = fig.add_subplot(gs[0, 0])
    ax_bar = fig.add_subplot(gs[0, 1], sharey=ax_grp)
    ax_lbl = fig.add_subplot(gs[0, 2], sharey=ax_grp)
    ax_hm = fig.add_subplot(gs[0, 3], sharey=ax_grp)

    y = np.arange(rows) + 0.5
    baseline_pct = plot_df['baseline_share'].to_numpy() * 100

    # diagnosis labels 
    ax_lbl.set_xlim(0, 1)
    ax_lbl.set_ylim(rows, 0)
    ax_lbl.axis('off')
    for yi, (code, desc) in zip(y, zip(plot_df['code'], plot_df['description'])):
        ax_lbl.text(0.96, yi, f'{desc} ({code})', ha='right', va='center', fontsize=11.0, color='#1a1a1a')

    # baseline bar chart on the left
    ax_bar.barh(y, baseline_pct, height=0.54, color='#6f8fa5', edgecolor='none')
    ax_bar.set_ylim(rows, 0); ax_bar.set_yticks([])
    ax_bar.set_xlabel('Pre-lockdown admission share (%)', fontsize=12)
    ax_bar.grid(axis='x', alpha=0.28, linewidth=0.7)
    mx = float(np.nanmax(baseline_pct)) if baseline_pct.size else 1.0
    ax_bar.set_xlim(-0.18 * mx, 1.05 * mx)
    for s in ('top', 'right', 'left'):
        ax_bar.spines[s].set_visible(False)

    # heatmap 
    hm_true = plot_df[['lockdown_pct_change', 'post_pct_change']].copy()
    hm_true.columns = ['Lockdown vs pre', 'Post-lockdown vs pre']

    vmax = 100.0
    hm_plot = hm_true.clip(-vmax, vmax)

    hm = sns.heatmap(
        hm_plot, ax=ax_hm, cmap='RdBu_r', center=0, vmin=-vmax, vmax=vmax,
        cbar_kws={'label': 'Share change vs pre-lockdown (%)', 'shrink': 1.0, 'fraction': 0.025, 'pad': 0.06, 'aspect': 50},
        yticklabels=False, linewidths=0.22, linecolor='#ececec',
    )
    ax_hm.set_xlabel(''); ax_hm.set_ylabel('')
    ax_hm.set_xticklabels(ax_hm.get_xticklabels(), rotation=0, fontsize=10)
    ax_hm.tick_params(axis='x', pad=8)
    ax_hm.tick_params(axis='y', left=False, labelleft=False)

    for i in range(hm_true.shape[0]):
        for j in range(hm_true.shape[1]):
            tv = float(hm_true.iat[i, j])
            pv = float(hm_plot.iat[i, j])
            if not np.isfinite(tv):
                continue
            txt = f'{tv:+.0f}%' + ('*' if abs(tv) >= vmax + 1e-9 else '')
            color = 'white' if abs(pv) > 0.48 * vmax else "#111111"
            fs = 10.5 if abs(tv) < 1000 else 9.5
            ax_hm.text(j + 0.5, i + 0.5, txt, ha='center', va='center',
                       fontsize=fs, color=color, fontweight='semibold')

    # description group lines & labels 
    summary_desc = plot_df['summary_desc'].tolist()
    bounds, centers = desc_boundaries(summary_desc)
    for b in bounds[:-1]:
        ax_hm.hlines(b, *ax_hm.get_xlim(), colors='#222', linewidth=1.0)
        ax_bar.hlines(b, *ax_bar.get_xlim(), colors='#222', linewidth=1.0)
        ax_lbl.hlines(b, 0, 1, colors='#222', linewidth=1.0)
        ax_grp.hlines(b, 0, 1, colors='#222', linewidth=1.0)

    ax_grp.set_xlim(0, 1); ax_grp.set_ylim(rows, 0); ax_grp.axis('off')
    for ch, cy in centers:
        ax_grp.text(0.98, cy + 0.5, ch, ha='right', va='center', fontsize=11.0, color='#222')

    cbar = hm.collections[0].colorbar
    cbar.ax.tick_params(labelsize=11)
    cbar.set_label('Share change vs pre-lockdown (%)', fontsize=12)

    os.makedirs(OUT_DIR, exist_ok=True)
    png = f'{OUT_DIR}/nhs_lockdown_hierarchical_matrix.png'
    fig.savefig(png, dpi=300, bbox_inches='tight')
    print(f'Saved {png}')

    # pdf = f'{OUT_DIR}/nhs_lockdown_hierarchical_matrix.pdf'
    # fig.savefig(pdf, bbox_inches='tight')
    # print(f'Saved {pdf}')

    plt.close(fig)



def main():
    df = load_data()
    desc_lookup = best_description(df)
    aggregated_data = aggregate(df)
    sel = select_categories(aggregated_data)

    # attach descriptions, then apply shortened labels where defined
    sel['description'] = sel['code'].map(desc_lookup).fillna(sel['code'])
    sel['description'] = sel['code'].map(SHORT_DESC).fillna(sel['description'])

    # sort by ICD  then baseline share descending
    sel['_csort'] = sel['summary_desc'].map(ICD_sort_key)
    sel = sel.sort_values(['_csort', 'baseline_share'], ascending=[True, False])
    sel = sel.drop(columns='_csort').reset_index(drop=True)

    print(f'{len(sel)} categories selected for plotting')
    draw(sel)


if __name__ == '__main__':
    main()
