import io
import tarfile
import gzip
import urllib.request
import re
import time
from typing import Dict, List
import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display
from IPython.core.display import HTML
from copy import deepcopy


def get_gzip_name(data):
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
            return None


def decode_gz(data, verbose=False):
    """
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
                if member.isfile() and member.name.split('.')[-1] in ['tex', 'TeX', 'TEX']:
                    file_data = tar.extractfile(member).read()
                    # Decode using utf-8 for all files
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
    for the given arxiv ID.
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

    return latex_files_content


def equation_patterns(inner_string=''):
    # make . include newlines: ?s:.
    equation_pattern =  r'\\begin{equation}(?s:.)*?\\end{equation}|' + \
                        r'\\begin{align}(?s:.)*?\\end{align}|' + \
                        r'\\begin{gather}(?s:.)*?\\end{gather}|' + \
                        r'\\begin{multline}(?s:.)*?\\end{multline}|' + \
                        r'\\begin{split}(?s:.)*?\\end{split}|' + \
                        r'\\begin{alignat}(?s:.)*?\\end{alignat}|' + \
                        r'\\begin{cases}(?s:.)*?\\end{cases}|' + \
                        r'\\begin{eqnarray}(?s:.)*?\\end{eqnarray}'
    equation_pattern_unnumbered =   r'\\begin{equation\*}(?s:.)*?\\end{equation\*}|' + \
                                    r'\\begin{align\*}(?s:.)*?\\end{align\*}|' + \
                                    r'\\begin{gather\*}(?s:.)*?\\end{gather\*}' + \
                                    r'\\begin{multline\*}(?s:.)*?\\end{multline\*}|' + \
                                    r'\\begin{split\*}(?s:.)*?\\end{split\*}|' + \
                                    r'\\begin{alignat\*}(?s:.)*?\\end{alignat\*}|' + \
                                    r'\\begin{cases\*}(?s:.)*?\\end{cases\*}|' + \
                                    r'\\begin{eqnarray\*}(?s:.)*?\\end{eqnarray\*}'
    inline_pattern =    r'\$\$(?s:.)*?\$\$|' + \
                        r'(?<!\\)\$(?:(?!\\\$)(?s:.))*?\$' + \
                        r'|\\\[(?s:.)*?\\\]|' + \
                        r'\\\((?s:.)*?\\\)|' + \
                        r'\\begin{math}(?s:.)*?\\end{math}'
    # (?<!\\)\$((?:[^$]|(?<!\\)\$)+?)\$
    # r'(?<!\\)\$(?:(?!\\\$).)*?\$' 
    return_string = '(' + equation_pattern + '|' + equation_pattern_unnumbered + '|' + inline_pattern + ')'
    if inner_string:
        return_string = return_string.replace('(?s:.)*?', inner_string)
    return return_string


def cf_patterns():
  return r'\\cfrac\s*{\s*[^{}]*\s*}\s*{\s*[^{}]*?(?:\\cfrac\s*{\s*[^{}]*\s*}\s*{\s*[^{}]*})+\s*}|' + \
         r'\\frac\s*{\s*[^{}]*\s*}\s*{\s*[^{}]*?(?:\\frac\s*{\s*[^{}]*\s*}\s*{\s*[^{}]*})+\s*}'


def constant_computing_patterns(const: str):
    const = re.escape(const)
    return (r'place_holder\s*?=|\\=\s*?place_holder' + \
    r'\\frac\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*{\s*[^{}]*}\s*=|=\s*\\frac\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*{\s*[^{}]*}' + \
    r'\\frac\s*{\s*[^{}]*}\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*=|=\s*\\frac\s*{\s*[^{}]*}\s*{\s*[^{}]*place_holder[^{}]*\s*}' + \
    r'\\cfrac\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*{\s*[^{}]*}\s*=|=\s*\\cfrac\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*{\s*[^{}]*}' + \
    r'\\cfrac\s*{\s*[^{}]*}\s*{\s*[^{}]*place_holder[^{}]*\s*}\s*=|=\s*\\cfrac\s*{\s*[^{}]*}\s*{\s*[^{}]*place_holder[^{}]*\s*}').replace('place_holder', const)


def commented_block_patterns():
    return r'(?m)^(?:[ \t]*%.*\n)+'


def split_latex(txt: str):
    r"""
    Splits latex text into actual latex code and comments.
    Keeps the original line breaks.
    """
    pattern = r'([^%\n]*)(%.*)?(\n?)'
    onlytxt = re.sub(pattern, lambda m: m.group(3) if m.group(2) and not m.group(1) else m.group(1) + m.group(3), txt)
    onlycomments = re.sub(pattern, lambda m: m.group(3) if not m.group(2) else m.group(2) + m.group(3), txt)
    return onlytxt, onlycomments


def gather_latex(arxiv_ids, queries=[], all_latex=False, remove_version=False,
                 clean_equations=True, verbose=False, sleep=1, sleep_burst=10):
    """
    Args:
        arxiv_ids: list of arXiv IDs
        queries: regular expression to search for in each latex file
        all_latex: if True, returns all the latex content of the .gz / tar.gz files
        remove_version: if True, remove the version number from the arXiv ID
        sleep: time to wait between API requests
        sleep_burst: number of requests to make before waiting
    Returns: 
        if all_latex=True, returns a dictionary of dictionaries:
        { id: { file_name: content } }
        if all_latex=False, returns a dictionary of dictionaries of lists of dictionaries:
        { id: { file_name: [{'e': str, 'l': int}] } }
        containing the regular expression matches in the latex content and the corresponding line numbers
    """

    if not queries and not all_latex:
        queries = [equation_patterns()]

    contents = {}
    fails = 0

    for i, paper_id in enumerate(arxiv_ids):
        if i % sleep_burst == 0 and i != 0:
            time.sleep(sleep)
        try:
            if paper_id[-2] == 'v' and remove_version:
                paper_id = paper_id[:-2]
                if verbose:
                    print(f'{i + 1} Removed version to get {paper_id}')
            if all_latex:
                contents[paper_id] = fetch_arxiv_latex(paper_id, verbose=verbose)
            else:
                latex_dict = fetch_arxiv_latex(paper_id, verbose=verbose)
                temp_dict = {file_name: [] for file_name in latex_dict}
                for file_name, content in latex_dict.items():

                    comments = re.sub(r'([^%\n]*)(%.*\n?)?\n?',  lambda m: '\n' if m.group(1) and not m.group(2) else m.group(2), content)
                    # TODO: iterate over these too and extract equations if number of $ is even etc. 
                    
                    # Change content: remove commented out lines by substituting them with newlines
                    content = re.sub(r'%.*\n', '\n', content)

                    lines = content.splitlines(keepends=True)  # Retain line endings for accurate indexing
                    cumulative_length = 0  # Tracks the cumulative character position in the content
                    # Create a mapping of cumulative character position to line number
                    line_mapping = []
                    for line_no, line in enumerate(lines, start=1):
                        cumulative_length += len(line)
                        line_mapping.append((cumulative_length, line_no))

                    for query in queries:
                        temp_line_mapping = deepcopy(line_mapping)
                        for match in re.finditer(query, content):
                            equation = match.group()  # Extract the full equation
                            start_index = match.start()  # Start position of the match

                            # Find the line number corresponding to the start index
                            line_number = next(line_no for cum_len, line_no in temp_line_mapping if start_index < cum_len)
                            if clean_equations:
                                equation = clean_equation(equation)
                            temp_dict[file_name].append({
                                'e': equation,
                                'l': line_number
                            })
                contents[paper_id] = temp_dict
        except Exception as x:
            if verbose:
                print(i + 1, ':', paper_id, ':', x)
            fails += 1

    return contents, fails


def sat_filter_gather(gather: Dict[str, Dict[str, list]], sat_strings: List[List[str]], forbidden_strings=['FORBIDDEN']):
    """
    Args:
        gather: dictionary (key is paper id) of dictionaries (key is file name) of lists (formulas)
        sat_strings: list of lists (referred to as tup), all the strings in at least one list must be present in a string
        for it to be admitted to the filtered gather
        forbidden_strings: if one of these is present in a string, it is not admitted to the filtered gather
    """
    filtered = {
        id:
            {
            file:
                [eq for eq in ls if any([all([s in eq['e'] for s in tup]) for tup in sat_strings]) and all([s not in eq['e'] for s in forbidden_strings])]
            for file, ls in id_dict.items()
            }
        for id, id_dict in gather.items()
    }

    return filtered


def re_filter_gather(gather: Dict[str, Dict[str, list]], regexs=[], forbidden_strings=['FORBIDDEN']):
    if not regexs:
        regexs = [cf_patterns(), r'\\pi.*?=.*?\\sum|\\sum.*?=.*?\\pi']

    filtered = {
        id:
            {
            file:
                [eq for eq in ls if any([re.findall(reg, eq['e']) for reg in regexs]) and not any([re.findall(reg, eq['e']) for reg in forbidden_strings])]
            for file, ls in id_dict.items()
            }
        for id, id_dict in gather.items()
    }

    return filtered


def clean_equation1(equation: str):
    equation = re.sub(r'\\left(?!\w)|\\right(?!\w)', r' ', equation)
    equation = re.sub(r'\\lparen|\\lbrack', '(', equation)
    equation = re.sub(r'\\rparen|\\rbrack', ')', equation)
    equation = re.sub(r'=', r' = ', equation)
    equation = re.sub(r'(\\n\b|\\r\b|\\t\b)+', r' ', equation)
    equation = re.sub(r'\\label\{(?s:.)*?\}', r' ', equation)
    equation = re.sub(r'\s+', r' ', equation)
    return equation.strip()


def clean_equation(equation: str):
    equation = re.sub(r'\\left(?!\w)|\\right(?!\w)', r' ', equation)
    equation = re.sub(r'\\lparen|\\lbrack', '(', equation)
    equation = re.sub(r'\\rparen|\\rbrack', ')', equation)

    equation = re.sub(r'=', r' = ', equation)
    equation = re.sub(r'&', r' & ', equation)
    equation = re.sub(r', \\quad|, \\qquad', r' & ', equation)

    equation = re.sub(r'(\\n\b|\\r\b|\\t\b|\\quad|\\qquad|%)+', r' ', equation)
    equation = re.sub(r'\\label\{(?s:.)*?\}', r' ', equation)
    equation = re.sub(r'\s+', r' ', equation)
    return equation.strip()


def clean_gather(gather: Dict[str, Dict[str, list]]):
    r"""def clean_equation(match):
    content = match.group(0)
    # Remove \begin{...}...\end{...} wrappers
    content = re.sub(r'\\begin{.*?}|\\end{.*?}', '', content, flags=re.DOTALL)
    # Remove $$ or $ or \[...\] or \(...\)
    content = re.sub(r'^\$\$|^\$|^\[|^\(|\$\$$|\$$|\]$|\)$', '', content, flags=re.DOTALL)
    return content.strip()"""
    pass


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
        pandas DataFrame with columns: 'paper_id', 'file_name', 'line_number', 'equation'
    """
    data = []
    for paper_id, file_dict in gather.items():
        for file_name, eq_list in file_dict.items():
            for eq_dict in eq_list:
                data.append([paper_id, file_name, eq_dict['l'], eq_dict['e']])
    df = pd.DataFrame(data, columns=['paper_id', 'file_name', 'line_number', 'equation'])
    return df.sort_values(['paper_id', 'file_name', 'line_number']).reset_index(drop=True)


def gather_latex_df(arxiv_ids, queries=[], all_latex=False, remove_version=False, verbose=False, sleep=1, sleep_burst=10):

    gather, fails = gather_latex(arxiv_ids, queries=queries, all_latex=all_latex, remove_version=remove_version,
                                      verbose=verbose, sleep=sleep, sleep_burst=sleep_burst)
    df = gather_to_df(gather)
    return df, fails


def display_df(df: pd.DataFrame, max_rows: int = 10, **kwargs):
    display(HTML(df.to_html(max_rows=max_rows, **kwargs)))