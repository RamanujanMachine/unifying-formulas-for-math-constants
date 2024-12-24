from pcf_validation import pcf_compute_to
from ramanujantools import Matrix, Limit
from ramanujantools.pcf.pcf import PCF
# from LIReC.db.access import db
import sympy as sp
from typing import Union

from sympy import symbols
n = symbols('n')


def test_pcf_compute_to():
    pcf = PCF(2*n + 1, n**2)
    assert pcf_compute_to(pcf, 1) == pcf.limit(1+1)
    # note the shift due to definition of depth in pcf.limit
    # pcf.limit(1) = Limit([A, I])
    
    assert pcf_compute_to(pcf, 2) == pcf.limit(2+1)
    assert pcf_compute_to(pcf, 3) == pcf.limit(3+1)
    assert pcf_compute_to(pcf, 2000) == pcf.limit(2000+1)

    limit10 = Limit(Matrix([[3958113600, 100370793600], [3108695040,  78831037440]]),
                    Matrix([[172504080, 3958113600], [135484416, 3108695040]]))
    
    # mat1 = pcf.limit(1+1).current
    mat1 = Matrix([[1, 4], [1, 3]]) # first convergent matrix
    assert pcf_compute_to(pcf, 10, 1, mat1) == limit10
    
    # mat2 = pcf.limit(2+1).current
    mat2 = Matrix([[4, 24], [3, 19]]) # second convergent matrix
    assert pcf_compute_to(pcf, 10, 2, mat2) == limit10
    
    # mat3 = pcf.limit(2+1).current
    mat3 = Matrix([[24, 204], [19, 160]]) # third convergent matrix
    assert pcf_compute_to(pcf, 10, 3, mat3) == limit10

    mat1000 = pcf.limit(1000+1).current # 1000th convergent matrix
    assert pcf_compute_to(pcf, 2000, 1000, mat1000) == pcf.limit(2000+1)

    convergent = pcf_compute_to(pcf, 1000)
    assert pcf_compute_to(pcf, 3500, 1000, convergent.current) == pcf.limit(3500+1)
