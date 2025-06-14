from extraction.extraction_gpt import extract_formula
from harvesting_utils.gather_utils import gather_equations
from harvesting_utils.misc_utils import normalize_file_name
from config import BASE_DIR, OPENAI_API_KEY, MAX_WORKERS
import json
import os
import time
from multiprocessing import Pool, cpu_count


# multiprocessing settings
NUM_WORKERS = max(4, min(cpu_count() - 8, MAX_WORKERS))

# directory paths
BASE_INPUT = os.path.join(BASE_DIR, '3_classification')         # classification directory
BASE_OUTPUT = os.path.join(BASE_DIR, '4_extraction')            # extraction output directory

# other options - normally no need to change
VERBOSE_EXTRACTION = False
PRINT_EVERY = 10
PRINT_SKIPS = True
SAVE_MESSAGES = False # whether to include the dialogue with GPT-4o / 4o mini in the output dictionaries

TEST = False
TEST_TO = 10


def process_eq(eqdict):
    r"""
    eqdict is a dictionary with keys
    'e' (equation)
    'l' (line)
    't' (text source - body/comment)
    'c' (classification by GPT-4o mini)
    """
    start = time.time()
    extraction = extract_formula(eqdict['e'], OPENAI_API_KEY,
                                 save_messages=SAVE_MESSAGES, verbose=VERBOSE_EXTRACTION)
    elapsed = time.time() - start
    line = eqdict['l']
    del eqdict['l']
    return {'l': line, **eqdict, 'extraction_time': elapsed, **extraction}


def process_arg_dict(arg_dict):
    if TEST and arg_dict['index'] % 10 == 0:
        print(f"{arg_dict['index']}, {arg_dict['file_origin']}")
    if not TEST and arg_dict['index'] % PRINT_EVERY == 0:
        print(f"{arg_dict['index']}, {arg_dict['file_origin']}")

    with open(arg_dict['file_origin'], 'r') as f:
        orig_gather = json.load(f)

    try:
        
        # skip if no equations
        if len(gather_equations(orig_gather)) == 0:
            if TEST:
                print(f"Skipping {arg_dict['file_origin']}: no equations")
            return
        
        else:
            created_dir = False
            for id, file_dict in orig_gather.items(): # there is only one id, so this is a loop of one iteration
                for file_name, eq_dict_list in file_dict.items():
                    i = 0
                    for eq_dict in eq_dict_list:
                        if not eq_dict['c']: # if classified as not calculating our constant, skip
                            if PRINT_SKIPS:
                                print(f"Skipping {arg_dict['file_origin']}: {eq_dict['e']}")
                            continue
                        if not created_dir:
                            os.makedirs(arg_dict['file_destin_dir'], exist_ok=True)
                            created_dir = True
                        result = {'id': id, 'file': file_name, **process_eq(eq_dict)}
                        saveto = arg_dict['file_destin'].replace('.json', f'__{normalize_file_name(file_name)}__{i}.json')
                        with open(saveto, 'w') as f:
                            json.dump(result, f)
                        i += 1
    
    except Exception as e:
        print(f"Error in {arg_dict['file_origin']}: {e}")
        return


if __name__ == "__main__":

    print('Building job...')

    job = []
    total = 0
    for subdir in os.listdir(BASE_INPUT):
        if TEST and total >= TEST_TO:
            break
        for file in os.listdir(os.path.join(BASE_INPUT, subdir)):
            if TEST and total >= TEST_TO:
                break
            file_destin = os.path.join(BASE_OUTPUT, subdir, file)
            if os.path.exists(file_destin):
                continue
            if file.endswith('.json'):
                file_origin = os.path.join(BASE_INPUT, subdir, file)
                file_destin_dir = os.path.join(BASE_OUTPUT, subdir)
                job.append({'file_origin': file_origin,
                            'file_destin_dir': file_destin_dir,
                            'file_destin': file_destin,
                            'index': total})
                total += 1
                if total % PRINT_EVERY == 0:
                    print(total, file.split('__')[1].replace('.json', '')) # this is the arxiv id

    print('Total number of gathers:', total)

    print('Running...')

    with Pool(NUM_WORKERS) as p:
        for _ in p.imap_unordered(process_arg_dict, job): # chunksize=1
            pass
