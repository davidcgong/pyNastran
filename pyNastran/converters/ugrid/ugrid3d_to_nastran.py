from __future__ import print_function
import os

from pyNastran.converters.ugrid.ugrid_reader import UGRID


def ugrid3d_to_nastran(ugrid_filename, bdf_filename, include_shells=True, include_solids=True):
    """
    Converts a UGRID to a BDF.

    Parameters
    ----------
    ugrid_filename : str
        the input UGRID filename
    bdf_filename : str
        the output BDF filename
    """
    model = UGRID(log=None, debug=False)
    assert os.path.exists(ugrid_filename), '%r doesnt exist' % ugrid_filename
    model.read_ugrid(ugrid_filename)
    model.export_bdf(bdf_filename, include_shells=include_shells, include_solids=include_solids)


def main():
    import sys
    assert len(sys.argv) == 3, 'number of arguments must be 2; ugrid_filename, bdf_filename; nargs=%s; args=%s' % (len(sys.argv[1:]), sys.argv[1:])
    ugrid_filename = sys.argv[1]
    bdf_filename = sys.argv[2]
    ugrid3d_to_nastran(ugrid_filename, bdf_filename)


if __name__ == '__main__':
    main()