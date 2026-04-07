
# Input and output paths
RAW_DIR  = 'NHS Hospital Admissions'
PROC_DIR = 'f_processed_data'
VIS_DIR  = 'f_vis'      

###################### Step 1: data process ######################
# Standard output columns written to every per-year CSV
OUT_COLS = [
    "period", "code", "description",
    "fce", "admissions", "males", "females",
    "emergency_admissions", "waiting_list", "planned_admissions",
    "mean_wait_days", "median_wait_days",
    "mean_los_days", "median_los_days", "mean_age",
]

# Sheet name for 3-char primary
SHEET_KEYWORDS = [
    "primary diagnosis 3 char",
    "primary diagnosis - 3 char",
    "primary diagnosis - 3-char",
    "primary diagnosis 3 character",
    "3cha",
    "3char",
]

###################### Step 2: filter and draw figure ######################
PERIOD_MAP = {
    "2017-18": "pre_lockdown",
    "2018-19": "pre_lockdown",
    "2019-20": "pre_lockdown",
    "2020-21": "lockdown",
    "2021-22": "post_lockdown",
    "2022-23": "post_lockdown",
    "2023-24": "post_lockdown",
}
PERIOD_ORDER = ["pre_lockdown", "lockdown", "post_lockdown"]

# Figure parameters
MAX_ROWS    = 45     # max diagnosis rows shown in the figure
MIN_SHARE   = 1e-4   # floor value for stable % change calculation
