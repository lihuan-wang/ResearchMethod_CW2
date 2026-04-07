import re
import os
import glob

import numpy as np
import pandas as pd

from config import RAW_DIR, PROC_DIR as OUT_DIR, OUT_COLS, SHEET_KEYWORDS


# some utils 
def check_code(code):
    return re.compile(r'^[A-Z]\d{2}$').fullmatch(code)

def clean_code(raw) -> str:
    # Strip leading footnote markers (‡, *, §, etc.) and whitespace from a code cell.
    s = str(raw).strip()
    s = re.sub(r'^[^A-Za-z0-9]+', '', s).strip().upper()
    return s

def clean_feature(v):
    return str(v).strip().lower().replace('–', '-').replace('—', '-') if str(v).lower() != 'nan' else ''

def find_3char_sheet(sheet_names):
    for name in sheet_names:
        low = clean_feature(name)
        if any(kw in low for kw in SHEET_KEYWORDS):
            return name
    return None


def detect_header_row(raw_data):
    # find the header row since some file start with some other information rows
    for i in range(min(30, len(raw_data))):
        row_str = ' '.join(str(v).lower() for v in raw_data.iloc[i] if str(v).lower() != 'nan')
        if 'diagnosis' in row_str and ('episode' in row_str or 'admission' in row_str):
            return i
    return 0

# main logic to process the data
def map_columns(header):
    # Return standard id for features mapping from a header row.
    col_map = {}
    for i, h in enumerate(header):
        t = clean_feature(h)
        if not t:
            continue
        if ('3 character' in t and 'description' not in t and 'code' not in t) or \
                'code and description' in t or '3 character code' in t:
            col_map.setdefault('code', i)   # combined cell: desc extracted at parse time via split_code_desc
        if 'finished consultant' in t or t == 'fce':
            col_map['fce'] = i
        if 'admission' in t and 'emergency' not in t and 'waiting' not in t and 'planned' not in t:
            col_map.setdefault('admissions', i)
        t0 = t.split()[0] if t else ''  # first token handles 'Male xxx' style headers
        if t0 in ('male', 'males') and 'female' not in t:
            col_map['males'] = i
        if t0 in ('female', 'females'):
            col_map['females'] = i
        if 'emergency' in t and 'admission' in t and 'bed' not in t:
            col_map['emergency_admissions'] = i
        if ('waiting list' in t or t == 'waiting list') and 'admission' not in t:
            col_map['waiting_list'] = i
        if 'planned' in t:
            col_map['planned_admissions'] = i
        if 'mean time waited' in t or ('mean' in t and 'wait' in t and 'median' not in t):
            col_map['mean_wait_days'] = i
        if 'median time waited' in t or ('median' in t and 'wait' in t):
            col_map['median_wait_days'] = i
        if ('mean length' in t or ('mean' in t and 'stay' in t)) and 'median' not in t:
            col_map['mean_los_days'] = i
        if ('median length' in t or ('median' in t and 'stay' in t)):
            col_map['median_los_days'] = i
        if 'mean age' in t:
            col_map['mean_age'] = i
    return col_map


def split_code_desc(cell):
    # Split 'A00 Some description' or 'A00 - Some description' into (code, desc).
    cell = cell.strip()
    m = re.match(r'^([A-Z]\d{2})\s*[-:]?\s*(.*)', cell, re.I)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return '', cell

def parse_excel_file(path, period):

    p_excel = pd.ExcelFile(path)
    sheet = find_3char_sheet(p_excel.sheet_names)
    assert sheet is not None, f'No sheet with 3-char primary diagnosis found in {path.name}'

    raw_data = pd.read_excel(path, sheet_name=sheet)
    hdr_idx = detect_header_row(raw_data)
    header  = raw_data.iloc[hdr_idx].tolist()
    col_map = map_columns(header)

    data_rows = raw_data.iloc[hdr_idx + 1 :].reset_index(drop=True)

    # If col 0 of data rows is a valid 3-char code, code and desc are in separate columns.
    # otherwise, code and desc are combined in the same column and need to be split.
    for i in range(len(data_rows)):
        if check_code(clean_code(data_rows.iloc[i, 0])):
            col_map['code'] = 0
            col_map['desc'] = 1
            break

    records = []
    for _, row in data_rows.iterrows():
        vals = row.tolist()
        row_text = ' '.join(str(v) for v in vals if str(v).lower() != 'nan').strip()
        # skip empty/note/copyright/total rows
        if not row_text or re.search(r'copyright|source:|nhs|field desc|introduction|total|primary diagnosis', row_text, re.I):
            continue

        code_i = col_map.get('code', 0)
        desc_i = col_map.get('desc')
        if desc_i is not None: # separate code and desc columns
            code = clean_code(vals[code_i]) if str(vals[code_i]).lower() != 'nan' else ''
            desc = str(vals[desc_i]).strip() if desc_i < len(vals) and str(vals[desc_i]).lower() != 'nan' else ''
        else: # combined code and desc column, need to split
            cell = str(vals[code_i]) if code_i < len(vals) else ''
            if cell.lower() == 'nan':
                continue
            code, desc = split_code_desc(cell)

        # check id
        if not check_code(code):
            continue

        # get value for each column (feature)
        def get(key):
            if key not in col_map:
                return np.nan
            idx = col_map[key]
            val = vals[idx]
            try:
                return float(val)
            except ValueError:
                return np.nan

        records.append({
            'period': period,
            'code': code,
            'description': desc,
            'fce': get('fce'),
            'admissions': get('admissions'),
            'males': get('males'),
            'females': get('females'),
            'emergency_admissions': get('emergency_admissions'),
            'waiting_list': get('waiting_list'),
            'planned_admissions': get('planned_admissions'),
            'mean_wait_days': get('mean_wait_days'),
            'median_wait_days': get('median_wait_days'),
            'mean_los_days': get('mean_los_days'),
            'median_los_days': get('median_los_days'),
            'mean_age': get('mean_age'),
        })

    df = pd.DataFrame(records, columns=OUT_COLS)
    return df


def period_label(path):
    # from file name to period label (e.g. '2010-11')

    # for old data with year folder
    foldername = os.path.basename(os.path.dirname(path))
    if re.fullmatch(r'(19|20)\d{2}', foldername):
        y = int(foldername)
        return f'{y}-{str(y + 1)[-2:]}'
    
    # for new data with year in file name
    filename = os.path.basename(path)
    m = re.search(r'((?:19|20)\d{2}[-_]\d{2})', filename)
    if m:
        return m.group(1).replace('_', '-')
    
    assert False, f'Cannot parse period from path: {path}'


def list_excel_files():
    old_files = glob.glob(f'{RAW_DIR}/*/*3cha*.xls')
    new_files = glob.glob(f'{RAW_DIR}/*.xlsx')

    all_files = sorted(old_files + new_files, key=lambda p: period_label(p))
    return all_files


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    all_files = list_excel_files()
    print(f'Found {len(all_files)} Excel files to process\n')

    seen_periods = set()  # only use first file for same period (year)
    for p in all_files:
        period = period_label(p)
        out = f'{OUT_DIR}/{period}.csv'
        if period in seen_periods: # repeated period
            print(f'repeated period {period} from file {p}, skipping')
            continue
        df = parse_excel_file(p, period)

        df.to_csv(out, index=False)
        seen_periods.add(period)
        print(f'Processed {period}: {p} -> {out}')

if __name__ == '__main__':
    main()
