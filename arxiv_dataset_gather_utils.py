# Contains functions used for gathering LaTeX from given arXiv IDs and processing the LaTeX content.
#


import io
import tarfile
import gzip
import urllib.request
import re
import time
from typing import Dict, List, Tuple, Callable, Optional
import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display
from IPython.core.display import HTML
from copy import deepcopy
import json

from arxiv_dataset_filter_utils import \
    equation_patterns, commented_block_patterns, clean_equation, remove_equation_wrapper, split_equation


# Gathering LaTeX content from arXiv - main function


def gather_latex(arxiv_ids, queries=[], all_latex=False, remove_version=False,
                 search_comments=True, clean_equations=False,
                 limit_time=None, limit_size=None,
                 sleep=1, sleep_burst=5, verbose=False, miniverbose=False, save='') -> Tuple[Dict[str, Dict[str, List[Dict[str, str]]]], int]:
    """
    Args:
        * arxiv_ids: list of arXiv IDs
        * queries: regular expression to search for in each latex file.
        Default is regular expression for equations.
        * all_latex: if True, returns all the latex content of the .gz / tar.gz files
        * remove_version: if True, remove the version number from the arXiv ID
        * search_comments: if True, search for the queries in latex comments as well
        * clean_equations: if True, clean each equation using the clean_equation function
        (these may not compile so results may be less reliable for equation gathering).
        Default is False.

        # TODO: ? Important to prevent getting stuck on a giant paper.
        * limit_time: if not None, limit the time of the function to this number of seconds,
        before returning None.
        * limit_size: if not None, limit the size of fetched content. Return None if the size is exceeded.
        Use getsize from arxiv_dataset_getsize_util.py to get the size of the content.
        Normal papers should have a size of order 200,000 bytes. The example that got stuck
        (1409.8356) has a size of 23,449,538 bytes

        * sleep: time to wait between API requests
        * sleep_burst: number of requests to make before waiting
        * verbose: if True, print more information
        * miniverbose: if True, only print the index of the paper being handled
        and its arXiv ID
    Returns:
        A tuple containing
        1. LaTeX content of the arXiv papers in the following format:
            * if all_latex=True, returns a dictionary of dictionaries:
                { id: { file_name: content } }
            * if all_latex=False, returns a dictionary of dictionaries of lists of dictionaries:
                { id: { file_name: [{'e': str, 'l': int, 't': str}] } }
                containing the regular expression matches in the latex content,
                the corresponding line numbers, and the type of the part of content
                ('b' - latex body or 'c' - latex comment) in which the equation was found
        2. number of failed accesses to papers.
    """

    if not queries and not all_latex:
        queries = [equation_patterns()]

    contents = {}
    fails = 0

    for i, paper_id in enumerate(arxiv_ids):
        if verbose or miniverbose:
            print(f'{i + 1}: {paper_id}')
        if i % sleep_burst == 0 and i != 0:
            time.sleep(sleep)
        try:
            if 'v' in paper_id[-4:] and remove_version:
                paper_id = paper_id[:-2]
                if verbose:
                    print(f'{i + 1} Removed version to get {paper_id}')
            if all_latex:
                contents[paper_id] = fetch_arxiv_latex(paper_id, verbose=verbose)
            else:
                latex_dict = fetch_arxiv_latex(paper_id, verbose=verbose)
                contents[paper_id] = gather_from_latex(latex_dict, queries, clean_equations=clean_equations, search_comments=search_comments)
        except Exception as x:
            if verbose:
                print(i + 1, ':', paper_id, ':', x)
            fails += 1

    if save:
        with open(save+'.json', 'w') as f:
            json.dump(contents, f)

    return contents, fails


# Fetching LaTeX content from arXiv


def get_gzip_name(data):
    r"""
    Gets the name of a gzip from its bytes.
    """
    with io.BytesIO(data) as file:
        # Read GZIP header
        header = file.read(10)
        # Check if there is an original filename flag
        flags = header[3]
        if flags & 0x08:  # FNAME flag is set
            # Extract the filename until the null byte
            filename = b""
            while True:
                byte = file.read(1)
                if byte == b"\x00":  # Null-terminated string
                    break
                filename += byte
            return filename.decode('utf-8')
        else:
            return 'NO_NAME'


def decode_gz(data, verbose=False):
    """
    Decodes a .gz or .tar.gz file and returns a dictionary of
    { tex_file_name (string) : content (string) }.
    Tries decoding with utf-8 and latin-1.
    Args:
        data: bytes
    """
    latex_files_content = {}
    decoders = ['utf-8', 'latin-1']
    try:
        # Try to open as tar.gz
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            if verbose:
                print(f"Extracting members")
            # Extract and read all the files
            for i, member in enumerate(tar.getmembers()):
                if verbose:
                    print(f'Member {i}: {member.name}')
                # Check if it's a file, not a directory
                if member.isfile() and member.name.split('.')[-1].lower() == 'tex': # in ['tex', 'TeX', 'TEX']:
                    file_data = tar.extractfile(member).read()
                    # Decode
                    decoded = False
                    i = 0
                    while not decoded and i <= 1:
                        decoder = decoders[i]
                        try:
                            file_content = file_data.decode(decoder) # ("latin-1")
                            decoded = True
                        except UnicodeDecodeError:
                            i += 1
                    latex_files_content[member.name] = file_content
    except tarfile.ReadError:
        # If it's not a tar.gz, try to open as gz
        name = get_gzip_name(data)
        if name.split('.')[-1].lower() == 'tex':
            with gzip.open(io.BytesIO(data), mode='rb') as gz:
                file_data = gz.read()
                decoded = False
                i = 0
                while not decoded and i <= 1:
                    decoder = decoders[i]
                    try:
                        file_content = file_data.decode(decoder) # ("latin-1")
                        decoded = True
                    except UnicodeDecodeError:
                        i += 1
                latex_files_content[name] = file_content
    return latex_files_content


def fetch_arxiv_latex(arxiv_id, verbose=False):
    """
    Returns a dictionary tex_file_name (string) : content (string)
    for the given arXiv ID.
    """
    # Construct the LaTeX source URL
    latex_url = f"https://arxiv.org/e-print/{arxiv_id}"

    if verbose:
        print(f'{arxiv_id}: Fetching LaTeX source from {latex_url}')

    # Open the URL and read the content into memory
    response = urllib.request.urlopen(latex_url)
    if verbose:
        print(f"Response code: {response.getcode()}")
    
    latex_files_content = {}

    if response.getcode() == 200:
        # Read the data from the response
        data = response.read()
        if verbose:
            print(f"Read response data")
        
        content_type = response.info().get_content_type()

        if content_type == 'application/gzip':
            if verbose:
                print('Is gzip')
            
            try:
                latex_files_content = decode_gz(data, verbose=verbose)

            except Exception as e:
                if verbose:
                    print(f"Error extracting tar.gz / gz: {e}")
        else:
            if verbose:
                print('Is not gzip')

    return latex_files_content


# Processing LaTeX document


def split_latex(txt: str):
    r"""
    Splits latex text into actual latex code and comments.
    Keeps the original line breaks.
    """
    pattern = r'((?:\\%|[^%\n])*)(%.*)?(\n?)' # originally r'((?:\\%|[^%\n])*)(%.*)?(\n?)', fixed this so that it does not split at escaped % - \\%:
    onlytxt = re.sub(pattern, lambda m: m.group(3) if m.group(2) and not m.group(1) else m.group(1) + m.group(3), txt)
    onlycomments = re.sub(pattern, lambda m: m.group(3) if not m.group(2) else m.group(2) + m.group(3), txt)
    return onlytxt, onlycomments


def compare_split_latex(txt, verbose=False):
    """
    Compare original line to components: latex code, comment.
    """
    onlylatex, onlycomments = split_latex(txt)

    original_lines = txt.splitlines()
    latex_lines = onlylatex.splitlines()
    comment_lines = onlycomments.splitlines()

    dataforframe = []
    for i, line in enumerate(original_lines):
        dataforframe.append([i, line, latex_lines[i], comment_lines[i]])

    return pd.DataFrame(dataforframe, columns=['line_number', 'original_line', 'latex_code', 'comment'])


def char_index_to_line_mapping(text: str):
    lines = text.splitlines(keepends=True)  # Retain line endings for accurate indexing
    cumulative_length = 0  # Tracks the cumulative character position in the content
    # Create a mapping of cumulative character position to line number
    mapping = []
    for line_no, line in enumerate(lines, start=1):
        cumulative_length += len(line)
        mapping.append((cumulative_length, line_no))
    return mapping


def count_unescaped_dollar_signs(txt: str):
    return len(re.findall(r'(?<!\\)\$', txt))


def gather_from_latex(latex_files_dict, queries, search_comments=True, clean_equations=False, verbose=False):
    r"""
    Returns a dictionary of lists of dictionaries
    containing the regular expression matches of each of the files.
    Format: { file_name: [{'e': str, 'l': int, 't': str}] }
    where 'e' contains a match, 'l' is the line number of the match,
    and 't' is the type of the part of content ('b' - latex body or 'c' - latex comment)
    in which the equation was found.
    """
    temp_dict = {file_name: [] for file_name in latex_files_dict}
    for file_name, content in latex_files_dict.items():
        text, comments = split_latex(content)
        text_line_mapping = char_index_to_line_mapping(text)

        for query in queries:
            # matches in text
            for match in re.finditer(query, text):
                equation = match.group()  # Extract the full equation
                start_index = match.start()  # Start position of the match
                # Find the line number corresponding to the start index
                line_number = next(line_no for cum_len, line_no in text_line_mapping if start_index < cum_len)

                if clean_equations:
                    equation = clean_equation(equation)
                temp_dict[file_name].append({
                    'e': equation,
                    'l': line_number,
                    't': 'b'
                })
            
            # matches in comments
            # each comment block is checked separately because they may not compile,
            # e.g. regular expression for equation search may result in strings that are not equations
            if search_comments:
                comment_line_mapping = char_index_to_line_mapping(comments)
                
                for i, comment_block in enumerate(re.finditer(commented_block_patterns(), comments), start=1):
                    comment_block_start_index = comment_block.start()                        
                    comment_block_line_number = next(line_no for cum_len, line_no in comment_line_mapping if comment_block_start_index < cum_len)
                    if verbose:
                        print(f'Comment block {i}: start index: {comment_block_start_index}, line number: {comment_block_line_number}')
                    if count_unescaped_dollar_signs(comment_block.group()) % 2 != 0:
                        if verbose:
                            print(f'Skipping this comment block: Uneven number of unescaped dollar signs ($) in comment block {i}: {comment_block.group()}')
                        continue

                    comment_block_line_mapping = char_index_to_line_mapping(comment_block.group())

                    for match in re.finditer(query, comment_block.group()):
                        equation = match.group()
                        start_index = match.start()
                        line_number = comment_block_line_number - 1 + next(line_no for cum_len, line_no in comment_block_line_mapping if start_index < cum_len)

                        if clean_equations:
                            equation = clean_equation(equation)
                        temp_dict[file_name].append({
                            'e': equation,
                            'l': line_number,
                            't': 'c'
                        })
    return temp_dict


# Manipulating gathers


def compare_gather(gather, gather_func: Callable):
    r"""
    Compares the equations in a gather with the equations in a new gather
    obtained by applying a function to the original gather.
    """
    new_gather = gather_func(deepcopy(gather))
    return pd.concat([gather_to_df(gather).rename(columns={'equation': 'original_equation'}),
                      gather_to_df(new_gather)['equation'].rename("new_equation")], axis=1)


def compare_equation_cleaning(arxiv_id, queries=[], verbose=False):
    r"""
    Compares the original equations with equations after clean_equation
    function is applied for the arXiv ID supplied.
    """
    cleandic = gather_latex([arxiv_id], queries=queries, clean_equations=True, search_comments=True, verbose=verbose)[0]
    cleandf = gather_to_df(cleandic)
    dirtydic = gather_latex([arxiv_id], queries=queries, clean_equations=False, search_comments=True, verbose=verbose)[0]
    dirtydf = gather_to_df(dirtydic)
    return pd.concat([dirtydf.rename(columns={'equation': 'original_equation'}), cleandf['equation'].rename("cleaned_equation")], axis=1)


def apply_to_gather(equation_func: Callable, gather=None, return_func=False):
    r"""
    Applies a function to each equation dictionary in a gather.
    Args:
        * equation_func: function to apply to each equation dictionary
        * gather: gather to apply the function to
        * return_func: if True, returns the function instead of applying it
    Returns:
        * A new gather with the same keys as the input gather, or
        * If return_func is True, returns a function that applies the equation_func to a gather.
    Either gather or return_func must be set.
    """
    def func(g):
        new_gather = {
        id:
            {
            file:
                [equation_func(eq) for eq in ls]  # {**eq, 'e': equation_func(eq['e'])}
            for file, ls in id_dict.items()
            }
        for id, id_dict in deepcopy(g).items()
        }
        return new_gather

    if return_func:
        return func
    elif gather is not None:
        return func(gather)
    else:
        raise ValueError('Either gather or return_func must be set')


def clean_gather(gather):
    r"""
    Cleans all the equations in a gather and returns a gather with the same keys.
    """
    def clean_equation_dict(eq_dict):
        return {**eq_dict, 'e': clean_equation(eq_dict['e'])}
    return apply_to_gather(clean_equation_dict, gather=gather, return_func=False)


def remove_equation_wrappers_gather(gather): # TODO: split relevant equation arrays into separate equations &&, &
    r"""
    Removes wrappers from all equations in a gather and returns a gather with the same keys.
    """
    return apply_to_gather(remove_equation_wrapper, gather=gather, return_func=False)


def split_equations_gather(gather):
    r"""
    Splits all equations in a gather and returns a gather with the same keys.
    """
    def split_equation_dict(eq_dict):
        return {**eq_dict, 'e': split_equation(eq_dict['e'])}
    return apply_to_gather(split_equation_dict, gather=gather, return_func=False)


def sat_filter_gather(sat_strings: List[List[str]], gather: Optional[Dict[str, Dict[str, List[Dict[str, str]]]]],
                      forbidden_strings=['FORBIDDEN'], return_func=False):
    """
    Args:
        gather: dictionary (key is paper id) of dictionaries (key is file name) of lists (formulas)
        sat_strings: list of lists (referred to as tup), all the strings in at least one list must be present in a string
        for it to be admitted to the filtered gather. Regex (re) supported.
        forbidden_strings: if one of these is present in a string, it is not admitted to the filtered gather.
        return_func: if True, returns a function that filters a gather.
    Returns:
        A filtered gather with the same keys as the input gather, or
        If return_func is True, returns a function that filters a gather.
    """

    def sat_filter_equation_dict(eq_dict):
        return eq_dict if any([all([re.findall(s, eq_dict['e']) for s in tup]) for tup in sat_strings]) \
                and not any([re.findall(s, eq_dict['e']) for s in forbidden_strings]) else None
    
    def sat_filter(g):
            filtered = apply_to_gather(sat_filter_equation_dict, gather=g)
            return {id: {file: [eq for eq in eq_list if eq is not None]
                         for file, eq_list in file_dict.items()}
                         for id, file_dict in filtered.items()}
    if return_func:
        return sat_filter
    else:
        return sat_filter(gather)


# Interpreting gathers


def gather_equations(gather):
    return [eq['e'] for id_dict in gather.values() for eq_list in id_dict.values() for eq in eq_list]


def gather_files(gather):
    return [file for id_dict in gather.values() for file in id_dict.keys()]


def equations_per_file(gather):
    return [len(eq_list) for file_dict in gather.values() for eq_list in file_dict.values()]


def equations_per_file_hist(gather, resolution=100):
    fig, ax = plt.subplots()
    ax.hist(equations_per_file(gather), bins=range(0, max(equations_per_file(gather)) + 1, resolution))
    ax.set_xlabel('Number of equations')
    ax.set_ylabel('Number of files')
    ax.set_title('Number of equations per file')
    return fig


def equations_per_id(gather):
    return [sum([len(eq_list) for eq_list in file_dict.values()]) for file_dict in gather.values()]


def equations_per_id_hist(gather, resolution=100):
    fig, ax = plt.subplots()
    ax.hist(equations_per_id(gather), bins=range(0, max(equations_per_id(gather)) + 1, resolution))
    ax.set_xlabel('Number of equations')
    ax.set_ylabel('Number of papers')
    ax.set_title('Number of equations per paper')
    return fig


def average_equations_per_file(gather):
    return len(gather_equations(gather)) / len(gather_files(gather))


def gather_to_df(gather: Dict[str, Dict[str, List[Dict[str, str]]]]) -> pd.DataFrame:
    """
    Args:
        gather: dictionary (key is paper id) of dictionaries (key is file name)
        of lists of dictionaries (equations and their line numbers)
    Returns:
        pandas DataFrame with columns: 'paper_id', 'file_name', 'line_number', 'source', 'equation'
        where 'source' is 'body' if the equation is in the body of the latex
        and 'comment' if it is in a latex comment
    """
    data = []
    for paper_id, file_dict in gather.items():
        for file_name, eq_list in file_dict.items():
            for eq_dict in eq_list:
                data.append([paper_id, file_name, eq_dict['l'], 'body' if eq_dict['t'] == 'b' else 'comment', eq_dict['e']])
    df = pd.DataFrame(data, columns=['paper_id', 'file_name', 'line_number', 'source', 'equation'])
    return df.sort_values(['paper_id', 'file_name', 'line_number']).reset_index(drop=True)


def gather_latex_df(arxiv_ids, queries=[], all_latex=False, remove_version=False, verbose=False, sleep=1, sleep_burst=10):

    gather, fails = gather_latex(arxiv_ids, queries=queries, all_latex=all_latex, remove_version=remove_version,
                                      verbose=verbose, sleep=sleep, sleep_burst=sleep_burst)
    df = gather_to_df(gather)
    return df, fails


def display_df(df: pd.DataFrame, max_rows: int = 10, **kwargs):
    display(HTML(df.to_html(max_rows=max_rows, **kwargs)))
