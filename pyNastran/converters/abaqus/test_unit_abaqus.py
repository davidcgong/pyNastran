from __future__ import print_function
import os
import unittest

from pyNastran.converters.abaqus.abaqus import read_abaqus
from pyNastran.utils.log import get_logger
PWD = os.path.dirname(__file__)

class TestAbaqus(unittest.TestCase):
    def test_abaqus_1(self):
        """simple test"""
        lines = make_model()
        log = get_logger(level='warning', encoding='utf-8')
        read_abaqus(lines, log=log, debug=False)

        abaqus_filename = os.path.join(PWD, 'abaqus.inp')
        with open(abaqus_filename, 'w') as abaqus_file:
            abaqus_file.writelines('\n'.join(lines))

def make_model():
    """makes a test model"""
    dummy_part1 = _make_part('dummy1')
    dummy_part2 = _make_part('dummy2')
    assembly_name = 'combo'
    lines = dummy_part1 + dummy_part2 + [
        '*material,elastic,name=steel',
        #'*elastic',
        #'*plastic',
        '*user material,constants=3',
        '1,2',
        '*assembly, name=%s' % assembly_name,
        '*instance',
        '1',
        '*end instance',
        '*node',
        '1,0.,0.,0.',
        '2,1.,0.,0.',
        '3,1.,1.,0.',
        '4,0.,1.,0.',
        #'*element, type=cpe3',
        #'1,1,2,3',
        '*nset,instance=dummy1',
        '1,2,3,4,5',
        '*elset,instance=dummy1',
        '1',
        '*elset,instance=dummy2,generate',
        '1,10,3',
        '*end assembly',

        '*step',
        '*static',
        '1,3,4,2.0',
        '*end step',
    ]
    return lines

def _make_part(part_name):
    """makes a test part"""
    part = [
        '*part, name=%s' % part_name,
        '*node',
        '1,0.,0.,0.',
        '2,1.,0.,0.',
        '3,1.,1.,0.',
        '4,0.,1.,0.',
        '*element, type=cpe3',
        '1,1,2,3',
        '*element, type=cpe4',
        '2,1,2,3,4',
        '*element, type=r2d2',
        '3,1,2',
        '*element, type=cax3',
        '4,1,2,3',
        '*element, type=cpe4r',
        '5,1,2,3,4',
        '*element, type=cax4r',
        '6,1,2,3,4',
        '*element, type=cohax4',
        '7,1,2,3,4',
        '*element, type=coh2d4',
        '8,1,2,3,4',
        '*mass',
        'mass_str',
        '*rotary inertia',
        'rotary_inertia_str',
        '*elset',
        '1',
        '*mass',
        'mass_str',
        '*solid section,material=steel',
        '42',
        #''
        '*end part',
        #'*material, name=steel',
        #'42',
    ]
    return part

if __name__ == '__main__':  #  pragma: no cover
    unittest.main()
