import pandas as pd
import sympy as sp


# input
DATAFRAMES_TO_MERGE = [
    r"C:\Users\totos\Desktop\11 - arXiv_pcfs_dataframe_identified_limits_merged_cfs_and_recurrences\pcfs_0-154047.pkl",
    r"C:\Users\totos\Desktop\11 - arXiv_pcfs_dataframe_identified_limits_merged_cfs_and_recurrences\pcfs_154048-199999",
    r"C:\Users\totos\Desktop\11 - arXiv_pcfs_dataframe_identified_limits_merged_cfs_and_recurrences\pcfs_200000-349999",
    r"C:\Users\totos\Desktop\11 - arXiv_pcfs_dataframe_identified_limits_merged_cfs_and_recurrences\pcfs_421641-435736",
    r"C:\Users\totos\Desktop\11 - arXiv_pcfs_dataframe_identified_limits_merged_cfs_and_recurrences\pcfs_math.CA_0-22736",
    r"C:\Users\totos\Desktop\12 - manual_pcfs\manual_pcfs_from_29.10.24.pkl",
    r"C:\Users\totos\Desktop\12 - cmf_pcfs\cmf_pcfs-('pi_cmf', 'symmetric_pi_cmf', '2F1')-max_i=8-generate_folds=True.pkl",
]

# output
SAVE_FILE = r'pcfs_28.12.24.pkl'

# defaults
TEST = False
SAVE_DIR = r"C:\Users\totos\Desktop\13 - merge_dataframes_and_sources"
SAVE_PATH = SAVE_DIR + '\\' + SAVE_FILE
if TEST:
    SAVE_PATH = SAVE_PATH.replace('.pkl', '_test.pkl')




def normalize_a_b(sympy_exp):
    return str(sp.expand(sympy_exp))


def merge_sources(df, test=False, verbose=False):
    # Add stringified columns for grouping
    df['a_str'] = df['a'].apply(normalize_a_b)
    df['b_str'] = df['b'].apply(normalize_a_b)

    # Initialize a list to store results
    results = []

    # Group by the stringified (a, b) pairs
    for i, ((a_str, b_str), group) in enumerate(df.groupby(['a_str', 'b_str'])):
        
        if test and i > 3:
            break

        # Retrieve the original a and b from the first row of the group
        a = group['a'].iloc[0]
        b = group['b'].iloc[0]

        # Collect unique limits, excluding None
        if verbose:
            print('group `limit`', group['limit'].values)
        unique_limits = list({limit.subs({sp.Symbol('pi'): sp.pi}) for limit in list(group['limit'].values) if limit is not None})
        # apparently this does not fully work, need to compare floats because there are still different representations
        # of the same float
        # evaluating to floats did not work because instead of being sp.pi all instances of pi from LIReC were sp.Symbol('pi')
        # this has been corrected in utils.lirec_identify_result_to_sympy, and appears here too to correct the dataframes
        # already identified.
        if verbose:
            print('unique_limits:', unique_limits)
        lim2floats = {lim: lim.evalf(100) for lim in unique_limits}
        if verbose:
            print('lim2floats:', lim2floats)
        floats2lim = {v: k for k, v in lim2floats.items() if v is not None}
        if verbose:
            print('floats2lim:', floats2lim)
        unique_floats = list(set(floats2lim.keys()))
        if verbose:
            print('unique_floats:', unique_floats)
        num_floats = len(unique_floats)
        limit = floats2lim[unique_floats[0]] if num_floats == 1 else None
        if verbose:
            print(limit)

        # Gather sources as dictionaries
        source_types = group['source_type'].unique()
        sources = group[['origin_formula_type', 'source_type', 'source', 'metadata', 'limit']].to_dict(orient='records')
        
        # Append results
        results.append({
            'a': a,
            'b': b,
            'limit': sp.cancel(limit),
            'first20convergents' : group['first20convergents'].to_list()[0],
            'source_types': source_types,
            'limit_candidates': unique_limits,
            'sources': sources
        })

    # Convert the results into a new DataFrame
    processed_df = pd.DataFrame(results)

    # Clean up the temporary string columns
    df.drop(columns=['a_str', 'b_str'], inplace=True)
    return processed_df


def add_row_to_processed(processed_df, new_row):
    """
    Adds a new row from the original DataFrame to the processed DataFrame.

    Parameters:
        processed_df (pd.DataFrame): The processed DataFrame with unique (a, b) pairs.
        new_row (pd.Series): A row from the original DataFrame to add.

    Returns:
        pd.DataFrame: Updated processed DataFrame.
    """
    # Extract (a, b) pair from the new row
    a, b = new_row['a'], new_row['b']
    
    # Check if the pair already exists in the processed DataFrame
    existing_row = processed_df[(processed_df['a'].apply(normalize_a_b) == normalize_a_b(a)) & 
                                (processed_df['b'].apply(normalize_a_b) == normalize_a_b(b))]
    
    if not existing_row.empty:
        # Update existing row
        idx = existing_row.index[0]
        
        # Add unique limit to limit_candidates
        limit = new_row['limit']
        if limit is not None and limit not in processed_df.at[idx, 'limit_candidates']:
            processed_df.at[idx, 'limit_candidates'].append(limit)
        
        # Append new source details to sources
        new_source = {
            'origin_formula_type': new_row['origin_formula_type'],
            'source_type': new_row['source_type'],
            'source': new_row['source'],
            'metadata': new_row['metadata'],
            'limit': new_row['limit']
        }
        processed_df.at[idx, 'sources'].append(new_source)
    else:
        # Add new row to the processed DataFrame
        new_entry = {
            'a': a,
            'b': b,
            'limit': new_row['limit'],
            'first20convergents' : new_row['first20convergents'],
            'source_types': [new_row['source_type']],
            'limit_candidates': [new_row['limit']] if new_row['limit'] is not None else [],
            'sources': [{
                'origin_formula_type': new_row['origin_formula_type'],
                'source_type': new_row['source_type'],
                'source': new_row['source'],
                'metadata': new_row['metadata'],
                'limit': new_row['limit']
            }]
        }
        processed_df = pd.concat([processed_df, pd.DataFrame([new_entry])], ignore_index=True)
    
    return processed_df


if __name__ == "__main__":
    # Load the dataframes
    dataframes = [pd.read_pickle(file) for file in DATAFRAMES_TO_MERGE]

    # Merge the dataframes
    merged_df = pd.concat(dataframes, ignore_index=True)

    # Process the merged dataframe
    processed_df = merge_sources(merged_df, test=TEST, verbose=TEST)

    # Save the processed dataframe
    processed_df.to_pickle(SAVE_PATH)
    print("Merged and processed data saved successfully.")
