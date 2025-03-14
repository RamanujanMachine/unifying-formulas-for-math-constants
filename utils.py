# miscellaneous utility functions.
from arxiv_dataset_utils import build_formula # TODO: decide whether to move this here
from ramanujantools.pcf import PCF
from LIReC.db.access import db
from LIReC.lib.pslq_utils import PolyPSLQRelation, get_exponents, reduce
from operator import add, mul
from sympy import Symbol, sympify, Add, Mul, Rational, pi
import pandas as pd
import re
from typing import Collection, Optional, Union
from IPython.display import display
from IPython.core.display import HTML


def remove_keys_from_dict(d, keys):
    r"""
    Remove a key from a dictionary.
    
    Args:
        - d: dictionary
        - key: key to remove
    
    Returns:
        - dictionary with the key removed
    """
    d = d.copy()
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        if key in d:
            del d[key]
    return d


def float_to_string(f, n=4, return_float=False):
    result = str(round(f, n)).rstrip('0').rstrip('.')
    return float(result) if return_float else result


def check_lists_are_integer_multiples(list1, list2, order_matters=False, return_scale=False, verbose=False):
    r"""
    If order_matters is True, then list1[i] / list2[i] must be an integer for all i.
    If order_matters is False, then list1[i] / list2[i] or list2[i] / list1[i] must be an integer for all i.

    Args:
        list1: list of integers
        list2: list of integers
        order_matters: whether the order of the lists matters
        return_scale: whether to return the factor by which the lists are multiples of each other

    Returns:
        result: whether the lists are integer multiples of each other
        or if return_factor is True, returns
        factor: the factor by which the lists are multiples of each other,
        None if the lists are not integer multiples of each other
    """
    if len(list1) != len(list2):
        raise ValueError("The lists must have the same length.")
    if all([num == 0 for num in list1]) and all([num == 0 for num in list2]):
        return 1 if return_scale else True
    
    for num1, num2 in zip(list1, list2):
        if num1 == 0 and num2 == 0:
            continue
        if num1 == 0 or num2 == 0:
            return None if return_scale else False
        scale = Rational(num1, num2)
        break
    if scale % 1 != 0:
        if not order_matters:
            return check_lists_are_integer_multiples(list2, list1, order_matters=True, return_scale=return_scale, verbose=verbose)
        else:
            return None if return_scale else False
    
    result = True
    for num1, num2 in zip(list1, list2):
        num2 = num2 * scale
        if verbose:
            print(num1, num2)
        if num1 != num2:
            result = False
            break

    if return_scale:
        return scale if result else None
    return result


def display_df(df: pd.DataFrame, max_rows: int = 10, from_ind=0, to_ind=None, **kwargs):
    if to_ind is None:
        to_ind = len(df)
    display(HTML(df.iloc[from_ind:to_ind].to_html(max_rows=max_rows, **kwargs)))


# for final dataset
# TODO: decide whether to create a new file for functions like this one
def find_paper_id(pcfs, id, verbose=False):
    r"""
    Locates all pandas indices for which the PCF at the indices has a source with the given paper id.
    """
    rows_of_interest = []
    for i, row in pcfs.iterrows():
        for source in row['sources']:
            if isinstance(source['source'], dict) and 'paper_id' in source['source'].keys() and source['source']['paper_id'] == id:
                if verbose:
                    print(source['source'])
                    display(build_formula(source['origin_formula_type'], source['metadata']['info']))
                rows_of_interest.append(i)
    return list(set(rows_of_interest))


def lid(strings, constants=['pi'], min_roi=1.5, as_sympy=False) -> Collection[Optional[Union[Add, Mul, Symbol]]]:
    r"""
    Identify relation to pi using LIReC.
    
    Args:
        - strings: str, float, mpf or list of these
        - as_sympy: whether to return sympified results

    Returns: identification
        - list of objects if multiple or no identifications found
        - otherwise a single object
        (object is sympy if as_sympy otherwise a string)
    """
    if isinstance(strings, list):
        results = db.identify([*[str(string) for string in strings], *constants], min_roi=min_roi)
    else:
        results = db.identify([str(strings), *constants], min_roi=min_roi)
    if as_sympy:
        results = [lirec_identify_result_to_sympy(res) for res in results]
    else:
        results = [res.__str__() for res in results]
    return results[0] if len(results) == 1 else None if results == [] else results


# NOTE: only works for pi at the moment
# meaning other constants will not be returned as their sympy objects,
# but instead as sympy symbols.
# TODO: fix this
def lirec_identify_result_to_sympy(polypslq, verbose=False):
    r"""
    Taken from `LIReC.lib.pslq_utils.PolyPSLQRelation.__str__`.
    """
    exponents = get_exponents(polypslq.degree, polypslq.order, len(polypslq.constants))
    for i,c in enumerate(polypslq.constants): # verify symbols
        if not c.symbol:
            c.symbol = f'c{i}'
        if not isinstance(c.symbol, Symbol):
            c.symbol = Symbol(c.symbol)
    
    polypslq._PolyPSLQRelation__fix_isolate()
    polypslq._PolyPSLQRelation__fix_symbols()
    monoms = [reduce(mul, (c.symbol**exp[i] for i,c in enumerate(polypslq.constants)), polypslq.coeffs[j]) for j, exp in enumerate(exponents)]
    expr = sympify(reduce(add, monoms, 0))
    res = None
    if polypslq.isolate not in expr.free_symbols or not expr.is_Add: # checking is_Add just in case...
        # res = f'{expr} = 0 ({self.precision})'
        res = None
    else:
        # expect expr to be Add of Muls or Pows, so args will give the terms
        # so now the relation is (-num) + (denom) * isolate = 0, or isolate = num/denom!
        res = True
        num = reduce(add, [-t for t in expr.args if polypslq.isolate not in t.free_symbols], 0)
        denom = reduce(add, [t/polypslq.isolate for t in expr.args if polypslq.isolate in t.free_symbols], 0)
        if verbose:
            print(num, denom)
            print(type(num), type(denom))
        res = sympify((num / denom).expand())
        if verbose:
            print(res.free_symbols)
        res = res.subs({Symbol('pi'): pi}) # replace 'pi' with sympy's pi
        if verbose:
            print('Substituted sp.pi for `pi` symbol:', res)
            print(res.free_symbols)
        # this will not be perfect if isolate appears with an exponent! will also be weird if either num or denom is 0
    #     res = (fr'\frac{{{num}}}{{{denom}}}' if polypslq.latex_mode else f'{num/denom}') + f' ({polypslq.precision})' 
    #     res = (f'{polypslq.isolate} = ' if polypslq.include_isolated else '') + res
    # # finally perform latex_mode substitution for exponents if necessary
    # return re.subn('\*\*(\w+)', '**{\\1}', res)[0] if polypslq.latex_mode else res
    return res


def write_dicts_to_latex_table(dict_list, output_file, headers=None, sort=None):
    if not dict_list:
        raise ValueError("The list of dictionaries is empty.")
    
    if not headers:
        # Get the headers from the keys of the first dictionary
        header_list = [dic.keys() for dic in dict_list]
        headers_set = set()
        for h in header_list:
            headers_set.update(set(h))
        print(headers_set)
        headers = list(headers_set)
        assert set(headers) == headers_set, "The headers do not match the keys of the dictionaries."

    if sort:
        dict_list = sorted(dict_list, key=lambda x: x[sort])
    
    with open(output_file, 'w') as f:
        # Write the beginning of the LaTeX document
        f.write(r'\documentclass{article}' + '\n')
        f.write(r'\usepackage{booktabs}' + '\n')
        f.write(r'\begin{document}' + '\n')
        f.write(r'\begin{table}[h!]' + '\n')
        f.write(r'\centering' + '\n')
        f.write(r'\begin{tabular}{' + ' '.join(['l' for _ in headers]) + '}' + '\n')
        f.write(r'\toprule' + '\n')
        
        # Write the headers
        f.write(' & '.join(headers) + r' \\' + '\n')
        f.write(r'\midrule' + '\n')
        
        # Write the rows
        for dictionary in dict_list:
            dictionary = {header: dictionary.get(header, '') for header in headers} # Fill in missing values with empty strings
            row = ' & '.join(str(dictionary[header]) for header in headers)
            f.write(row + r' \\' + '\n')
        
        # Write the end of the table and document
        f.write(r'\bottomrule' + '\n')
        f.write(r'\end{tabular}' + '\n')
        f.write(r'\caption{Your Table Caption Here}' + '\n')
        f.write(r'\end{table}' + '\n')
        f.write(r'\end{document}' + '\n')


# as latex (PCFs)

def python_to_latex(python_str):
    # Convert '**' to '^'
    latex_str = re.sub(r'\*\*(\d+)', r'^{\1}', python_str) # python_str.replace('**', '^')
    
    # Convert '*' to '\cdot' (for multiplication)
    latex_str = latex_str.replace('*', '') # r'\cdot '
    
    # Convert '/' to '\frac{}{}' (for division)
    # Use regular expressions to find the division operation
    def convert_division(match):
        numerator = match.group(1)
        denominator = match.group(2)
        return r'\frac{' + numerator + '}{' + denominator + '}'
    latex_str = re.sub(r'(\w+)\s*/\s*(\w+)', convert_division, latex_str)
    return latex_str


def generic_recursive_fraction(level, depth):
    if level == depth:
        return r'\ddots + \cfrac{b_n}{a_n + \ddots}'
    else:
        a_i = f'a_{level}'
        b_i = f'b_{level + 1}'
        return rf'{a_i} + \cfrac{{{b_i}}}{{{generic_recursive_fraction(level + 1, depth)}}}'


def recursive_fraction(level, depth, a_n, b_n):
    n = Symbol('n')
    if level == depth:
        return rf'\ddots + \cfrac{{{b_n}}}{{{a_n} + \ddots}}'
    else:
        a_val = a_n.subs(n, level)
        b_val = b_n.subs(n, level + 1)
        return rf'{a_val} + \cfrac{{{b_val}}}{{{recursive_fraction(level + 1, depth, a_n, b_n)}}}'


def pcf_as_latex(pcf: PCF, depth: int = 3, start: int = 1) -> str:
        """
        Returns the continued fraction as a string in LaTeX format.
        Note: result should be printed to obtain actual LaTex string format.

        Args:
            depth: The index to display up to.
            start: The index from which to display.
        Returns:
            The LaTeX string for the continued fraction (python representation, i.e. '\' is '\\').
        """
        n = Symbol('n')
        if start != 1:
            result = rf'\cfrac{{{pcf.b_n.subs(n, start)}}}{{{recursive_fraction(start, depth, pcf.a_n, pcf.b_n)}}}'
        else:
            result = rf'{pcf.a_n.subs(n, 0)} + \cfrac{{{pcf.b_n.subs(n, 1)}}}{{{recursive_fraction(start, depth, pcf.a_n, pcf.b_n)}}}'
        return python_to_latex(result)


def generic_pcf_as_latex(depth: int = 3, start: int = 1) -> str:
        """
        Returns a generic continued fraction as a string in LaTeX format,
        with symbols $a_n$ and $b_n$ as the partial denominators and numerators, respectively.
        Args:
            depth: The index to display up to.
            start: The index from which to display.
        Returns:
            The LaTeX string for the continued fraction (python representation, i.e. '\' is '\\').
            e.g. 'a_0 + \\cfrac{b_1}{a_1 + \\cfrac{b_2}{a_2 + \\cfrac{b_3}{\\ddots + \\cfrac{b_n}{a_n + \\ddots}}}}'.
        """
        if start != 1:
            result = rf'\cfrac{{b_{start}}}{{{generic_recursive_fraction(start, depth)}}}'
        else:
            result = rf'a_0 + \cfrac{{b_1}}{{{generic_recursive_fraction(start, depth)}}}'
        return python_to_latex(result)
        