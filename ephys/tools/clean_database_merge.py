import pandas as pd
from pathlib import Path
from typing import Union
from ephys.tools import parse_ages

"""Perform a merge of the main pickled database and a coding file,
using the coding sheet. 
Clean up the groups and ages

"""
def clean_database_merge(pkl_file: Union[str, Path], coding_file: Union[str, Path], coding_sheet:str):

    def mapdate(row):
        if not pd.isnull(row["Date"]):
            row["Date"] = row["Date"] + "_000"
        return row
    def sanitize_age(row):
        print(row.keys())
        row.age = parse_ages.ISO8601_age(row.age)
        return row
    
    print(pkl_file)
    df = pd.read_pickle(pkl_file, compression={'method': 'gzip', 'compresslevel': 5, 'mtime': 1})
    df = df.apply(sanitize_age, axis=1)
    
    df["cell_type"] = df["cell_type"].values.astype(str)
    
    def _cell_type_lower(row):
        row.cell_type = row.cell_type.lower()
        return row
        
    df = df.apply(_cell_type_lower, axis=1)
    df.reset_index(drop=True)

    
    if coding_sheet is not None:
        df_c = pd.read_excel(
            Path(coding_file),
            sheet_name=coding_sheet,
            )
        print(f"Successfully Read Coding sheet {str(coding_file)}.pkl")
        gr = list(set(df_c.Group.values))
        print(f"    With these Groups: {str(gr):s}")

        df_c["Group"] = df_c['Group'].values.astype(str)
        # df_c["age"] = df_c["age"].values.astype(str)
        df_c = df_c.apply(mapdate, axis=1)
        df_c = df_c.apply(sanitize_age, axis=1)
        df_c["Group"] = df_c['Group'].values.astype(str)

        df_i = pd.merge(
                        df,
                        df_c,
                        left_on=["date"],  # , "slice_slice", "cell_cell"],
                        right_on=["Date"],  # , "slice_slice", "cell_cell"],
                    )
        return df_i
    else:
        return df