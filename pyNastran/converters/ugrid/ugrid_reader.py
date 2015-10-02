from __future__ import print_function
import os
import struct
from copy import deepcopy
from struct import Struct

from numpy import zeros, unique, where, argsort, searchsorted, allclose, array
from collections import defaultdict

from pyNastran.bdf.field_writer_double import print_card_double
from pyNastran.utils.log import get_logger

from pyNastran.converters.ugrid.surf_reader import TagReader
from pyNastran.converters.tecplot.tecplot import Tecplot


class UGRID(object):
    def __init__(self, log=None, debug=False):
        #FortranFormat.__init__(self)
        self.log = get_logger(log, 'debug' if debug else 'info')
        self.debug = debug
        self.n = 0

        self.nodes = None
        self.tris = None
        self.quads = None
        self.pids = None

        self.tets = None
        self.penta5s = None
        self.penta6s = None
        self.hexas = None

        self.isort = None

    def read_ugrid(self, ugrid_filename):
        """
        $
        $       NASTRAN INPUT DECK GENERATED BY UG_IO
        $
        BEGIN BULK
        $UG_IO_ Data
        $Number_of_BL_Vol_Tets 2426
        $UG_IO_ Data
        $Number_of_Bnd_Nodes 34350
        $UG_IO_ Data
        $Number_of_Nodes 399036
        $UG_IO_ Data
        $Number_of_Surf_Quads 20665
        $UG_IO_ Data
        $Number_of_Surf_Trias 27870
        $UG_IO_ Data
        $Number_of_Vol_Hexs 163670
        $UG_IO_ Data
        $Number_of_Vol_Pents_5 27875
        $UG_IO_ Data
        $Number_of_Vol_Pents_6 67892
        $UG_IO_ Data
        $Number_of_Vol_Tets 1036480
        """
        out = determine_dytpe_nfloat_endian_from_ugrid_filename(ugrid_filename)
        ndarray_float, float_fmt, nfloat, endian = out

        # more for documentation than anything else
        assert ndarray_float in ['float32', 'float64'], ndarray_float
        assert float_fmt in ['f', 'd'], float_fmt
        assert nfloat in [4, 8], nfloat
        assert endian in ['<', '>'], ndarray_float


        ugrid_file = open(ugrid_filename, 'rb')
        data = ugrid_file.read(7 * 4)
        self.n += 7 * 4

        nnodes, ntris, nquads, ntets, npenta5s, npenta6s, nhexas = struct.unpack(endian + '7i', data)
        npids = nquads + ntris
        nvol_elements = ntets + npenta5s + npenta6s + nhexas
        self.log.info('nnodes=%s ntris=%s nquads=%s ntets=%s npenta5s=%s npenta6s=%s nhexas=%s' % (
            nnodes, ntris, nquads, ntets, npenta5s, npenta6s, nhexas))

        nvolume_elements = ntets + npenta5s + npenta6s + nhexas
        self.log.info('nsurface_elements=%s nvolume_elements=%.3f Million' % (npids, nvolume_elements / 1e6))

        # we know the shapes of nodes (e.g. Nx3), but we want to directly
        # unpack the data into the array, so we shape it as N*3, load the
        # data and and then do a reshape
        self.log.debug('ndarray_float=%s' % (ndarray_float))
        nodes = zeros(nnodes * 3, dtype=ndarray_float)
        tris = zeros(ntris * 3, dtype='int32')
        quads = zeros(nquads * 4, dtype='int32')
        pids = zeros(npids, dtype='int32')

        tets = zeros(ntets * 4, dtype='int32')
        penta5s = zeros(npenta5s * 5, dtype='int32')
        penta6s = zeros(npenta6s * 6, dtype='int32')
        hexas = zeros(nhexas * 8, dtype='int32')


        ## NODES
        data = ugrid_file.read(nnodes * 3 * nfloat)
        self.n += nnodes * 3 * nfloat
        fmt = '%s%i%s' % (endian, nnodes * 3, float_fmt)  # >9f
        nodes[:] = struct.unpack(fmt, data)
        nodes = nodes.reshape((nnodes, 3))
        #print('min xyz value = ' , nodes.min())
        #print('max xyz value = ' , nodes.max())

        ## CTRIA3
        data = ugrid_file.read(ntris * 3 * 4)
        self.n += ntris * 3 * 4
        fmt = '%s%ii' % (endian, ntris * 3)  # >9i
        tris[:] = struct.unpack(fmt, data)
        tris = tris.reshape((ntris, 3))
        #print('min tris value = ' , tris.min())
        #print('max tris value = ' , tris.max())

        ## CQUAD4
        data = ugrid_file.read(nquads * 4 * 4)
        self.n += nquads * 4 * 4
        fmt = '%s%ii' % (endian, nquads * 4)  # >12i
        quads[:] = struct.unpack(fmt, data)
        quads = quads.reshape((nquads, 4))
        #print('min quads value = ' , quads.min())
        #print('max quads value = ' , quads.max())

        data = ugrid_file.read(npids * 4)
        self.n += npids * 4
        fmt = '%s%ii' % (endian, npids)  # >12i
        pids[:] = struct.unpack(fmt, data)
        #print('min pids value = ' , pids.min())
        #print('max pids value = ' , pids.max())

        #==========================================
        # solids

        ## CTETRA
        data = ugrid_file.read(ntets * 4 * 4)
        self.n += ntets * 4 * 4
        fmt = '%s%ii' % (endian, ntets * 4)  # >12i
        try:
            tets[:] = struct.unpack(fmt, data)
        except:
            self.log.error('fmt=%s len(data)=%s len(data)/4=%s' % (fmt, len(data), len(data)//4))
            raise
        tets = tets.reshape((ntets, 4))
        #print('min tets value = ' , tets.min())
        #print('max tets value = ' , tets.max())

        ## CPYRAM
        data = ugrid_file.read(npenta5s * 5 * 4)
        self.n += npenta5s * 5 * 4
        fmt = '%s%ii' % (endian, npenta5s * 5)
        penta5s[:] = struct.unpack(fmt, data)
        penta5s = penta5s.reshape((npenta5s, 5))
        #print('min penta5s value = ' , penta5s.min())
        #print('max penta5s value = ' , penta5s.max())

        ## cPENTA
        data = ugrid_file.read(npenta6s * 6 * 4)
        self.n += npenta6s * 6 * 4
        fmt = '%s%ii' % (endian, npenta6s * 6)
        penta6s[:] = struct.unpack(fmt, data)
        penta6s = penta6s.reshape((npenta6s, 6))
        #print('min penta6s value = ' , penta6s.min())
        #print('max penta6s value = ' , penta6s.max())

        ## CHEXA
        data = ugrid_file.read(nhexas * 8 * 4)
        self.n += nhexas * 8 * 4
        fmt = '%s%ii' % (endian, nhexas * 8)
        hexas[:] = struct.unpack(fmt, data)
        hexas = hexas.reshape((nhexas, 8))
        #print('min hexas value = ' , hexas.min())
        #print('max hexas value = ' , hexas.max())

        self.nodes = nodes
        self.tris = tris
        self.quads = quads
        self.pids = pids

        self.tets = tets
        self.penta5s = penta5s
        self.penta6s = penta6s
        self.hexas = hexas

        if 0:
            #self.show(100, types='i', big_endian=True)
            if nvol_elements == 0:
                raise RuntimeError('not a volume grid')

            data = ugrid_file.read(4)
            nBL_tets = struct.unpack(endian + 'i', data)
            self.n += 4
            print('nBL_tets=%s' % (nBL_tets)) # trash


            data = ugrid_file.read(nvol_elements * 4)
            self.n += nvol_elements * 4
            print('len(data)=%s len/4=%s nvol_elements=%s' % (len(data), len(data) / 4., nvol_elements))
            assert len(data) == (nvol_elements * 4)

            fmt = endian + '%ii' % (nvol_elements * 4)
            volume_ids = zeros(nvol_elements, dtype='int32')
            volume_ids[:] = struct.unpack(fmt, data)

            # some more data we're not reading for now...

            #self.show(100, types='i', big_endian=True)
        assert self.n == ugrid_file.tell()
        ugrid_file.close()

    def write_bdf(self, bdf_filename, include_shells=True, include_solids=True, convert_pyram_to_penta=True):
        bdf_file = open(bdf_filename, 'wb')
        #bdf_file.write('CEND\n')
        #bdf_file.write('BEGIN BULK\n')
        bdf_file.write('$ pyNastran: punch=True\n')
        mid = 1
        bdf_file.write('MAT1, %i, 1.0e7,, 0.3\n' % mid)

        pids = self.pids
        if 1:
            print('writing GRID')
            for nid, node in enumerate(self.nodes):
                card = ['GRID', nid + 1, None] + list(node)
                bdf_file.write(print_card_double(card))
        else:
            print('skipping GRID')

        eid = 1
        if include_shells:
            upids = unique(pids)
            upids.sort()
            for pid in upids:
                bdf_file.write('PSHELL,%i,%i, 0.1\n' % (pid, mid))
            print('writing CTRIA3')
            for element in self.tris:
                bdf_file.write('CTRIA3  %-8i%-8i%-8i%-8i%-8i\n' % (eid, pids[eid-1], element[0], element[1], element[2]))
                eid += 1

            print('writing CQUAD4')
            for element in self.quads:
                bdf_file.write('CQUAD4  %-8i%-8i%-8i%-8i%-8i%-8i\n' % (eid, pids[eid-1], element[0], element[1], element[2], element[3]))
                eid += 1
        else:
            ntris = self.tris.shape[0]
            nquads = self.quads.shape[0]
            eid += ntris + nquads


        max_pid = pids.max()
        #==========================================
        # solids
        if include_solids:
            pid = max_pid + 1
            eid, pid = self._write_bdf_solids(bdf_file, eid, pid, convert_pyram_to_penta=convert_pyram_to_penta)
        bdf_file.write('ENDDATA\n')
        bdf_file.close()

    def write_tecplot(self, tecplot_filename):
        tecplot = ugrid_to_tecplot(self)
        tecplot.write_tecplot(tecplot_filename, adjust_nids=True)  # is adjust correct???
        tecplot.results = array([], dtype='float32')

    def write_ugrid(self, ugrid_filename_out):
        outi = determine_dytpe_nfloat_endian_from_ugrid_filename(ugrid_filename_out)
        ndarray_float, float_fmt, nfloat, endian = outi

        nodes = self.nodes
        nnodes = nodes.shape[0]

        tris = self.tris
        quads = self.quads
        pids = self.pids
        tets = self.tets
        pyrams = self.penta5s
        pentas = self.penta6s
        hexas = self.hexas

        ntris = tris.shape[0]
        nquads = quads.shape[0]
        ntets = tets.shape[0]
        npyramids = pyrams.shape[0]
        npentas = pentas.shape[0]
        nhexas = hexas.shape[0]

        nshells = ntris + nquads
        assert nshells > 0

        with open(ugrid_filename_out, 'wb') as f_ugrid:
            s = Struct(endian + '7i')
            f_ugrid.write(s.pack(nnodes, ntris, nquads, ntets, npyramids, npentas, nhexas))

            # %3f or %3d
            fmt = endian + '%i%s' % (nnodes * 3, float_fmt) # len(x,y,z) = 3
            s = Struct(fmt)
            f_ugrid.write(s.pack(*nodes.ravel()))

            # CTRIA3
            fmt = endian + '%ii' % (ntris * 3)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*tris.ravel()))

            # QUAD4
            fmt = endian + '%ii' % (nquads * 4)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*quads.ravel()))

            # PSHELL
            fmt = endian + '%ii' % (nshells)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*pids.ravel()))

            # CTETRA
            fmt = endian + '%ii' % (ntets * 4)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*tets.ravel()))

            # CPYRAM
            fmt = endian + '%ii' % (npyramids * 5)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*pyrams.ravel()))

            # CPENTA
            fmt = endian + '%ii' % (npentas * 6)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*pentas.ravel()))

            # CHEXA
            fmt = endian + '%ii' % (nhexas * 8)
            s = Struct(fmt)
            f_ugrid.write(s.pack(*hexas.ravel()))

    def _write_bdf_solids(self, f, eid, pid, convert_pyram_to_penta=True):
        #pid = 0
        f.write('PSOLID,%i,1\n' % pid)
        print('writing CTETRA')
        f.write('$ CTETRA\n')
        for element in self.tets:
            #card = ['CTETRA', eid, pid] + list(element)
            #f.write(print_int_card(card))
            f.write('CTETRA  %-8i%-8i%-8i%-8i%-8i%-8i\n' % (
                eid, pid, element[0], element[1], element[2], element[3]))
            eid += 1

        if convert_pyram_to_penta:
            # skipping the penta5s
            print('writing CPYRAM as CPENTA with node6=node5')
            f.write('$ CPYRAM - CPENTA5\n')
            for element in self.penta5s:
                f.write('CPENTA  %-8i%-8i%-8i%-8i%-8i%-8i%-8i%-8i\n' % (
                    eid, pid, element[0], element[1], element[2], element[3], element[4], element[4]))
                eid += 1
        else:
            print('writing CPYRAM')
            f.write('$ CPYRAM - CPENTA5\n')
            for element in self.penta5s:
                f.write('CPENTA  %-8i%-8i%-8i%-8i%-8i%-8i%-8i\n' % (
                    eid, pid, element[0], element[1], element[2], element[3], element[4]))
                eid += 1

        print('writing CPENTA')
        f.write('$ CPENTA6\n')
        for element in self.penta6s:
            #card = ['CPENTA', eid, pid] + list(element)
            #f.write(print_int_card(card))
            f.write('CPENTA  %-8i%-8i%-8i%-8i%-8i%-8i%-8i%-8i\n' % (
                eid, pid, element[0], element[1], element[2], element[3], element[4], element[5]))
            eid += 1

        print('writing CHEXA')
        f.write('$ CHEXA\n')
        for element in self.hexas:
            #card = ['CHEXA', eid, pid] + list(element)
            f.write('CHEXA   %-8i%-8i%-8i%-8i%-8i%-8i%-8i%-8i\n        %-8i%-8i\n' % (
                eid, pid, element[0], element[1], element[2], element[3], element[4], element[5], element[6], element[7]))
            #f.write(print_int_card(card))
            eid += 1
        return eid, pid

    def write_foam(self, foam_filename, tag_filename):
        dirname = os.path.dirname(foam_filename)
        base = os.path.splitext(foam_filename)[0]

        points_filename = os.path.join(dirname, 'points')
        boundary_filename = os.path.join(dirname, 'boundary')
        faces_filename = os.path.join(dirname, 'faces')
        #neighbor_filename = os.path.join(dirname, 'neighbor')
        #owner_filename = os.path.join(dirname, 'owner')

        # boundary
        # 1. get array of unique properties
        # 2. loop over in sorted order
        # 3.   find where values are equal to the property id in ctrias and cquads (surface elements)
        # 4.   find the min/max

        # points
        # 1. loop over points and write

        # faces
        # 1. loop over tets/penta5s/penta/chexas   ):  DO CPENTA5s last!
        # 2.    element.faces
        # 3.    only write it once!  (Sort the data for checking, but write out with proper connectivity)

        #f.write('CEND\n')
        #f.write('BEGIN BULK\n')
        #f.write('PSHELL,1,1, 0.1\n')
        #f.write('MAT1, 1, 1.0e7,, 0.3\n')

        #pids = self.pids
        #mid = 1
        points_filename = foam_filename  # remove...
        #self._write_points(points_filename)
        self._write_boundary(boundary_filename + '2', tag_filename)
        self._write_faces(faces_filename + '2')

    def _write_points(self, points_filename):
        points_file = open(points_filename, 'wb')
        nnodes = self.nodes.shape[0]

        points_file.write('/*--------------------------------*- C++ -*----------------------------------*\\\n')
        points_file.write('| =========                 |                                                 |\n')
        points_file.write('| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n')
        points_file.write('|  \\\\    /   O peration     | Version:  1.7.1                                 |\n')
        points_file.write('|   \\\\  /    A nd           | Web:      www.OpenFOAM.com                      |\n')
        points_file.write('|    \\\\/     M anipulation  |                                                 |\n')
        points_file.write('\\*---------------------------------------------------------------------------*/\n')
        points_file.write('FoamFile\n')
        points_file.write('{\n')
        points_file.write('    version     2.0;\n')
        points_file.write('    format      ascii;\n')
        points_file.write('    class       vectorField;\n')
        points_file.write('    location    "constant/polyMesh";\n')
        points_file.write('    object      points;\n')
        points_file.write('}\n')
        points_file.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * /\n')


        points_file.write('\n\n')
        points_file.write('%i\n' % (nnodes))
        points_file.write('(\n')
        for nid, node in enumerate(self.nodes):
            points_file.write(('    (%-12s %-12s %-12s)\n') % (node[0], node[1], node[2]))
        points_file.write(')\n')
        points_file.close()

    def _write_boundary(self, boundary_filename, tag_filename):
        boundary_file = open(boundary_filename, 'wb')
        boundary_file.write('\n\n')
        #f.write('%i\n' % (nnodes))
        boundary_file.write('(\n')

        uboundaries = unique(self.pids)
        nboundaries = len(uboundaries)
        boundary_file.write('%i\n' % nboundaries)
        boundary_file.write('(\n')

        tagger = TagReader()
        tag_data = tagger.read_tag_filename(tag_filename)


        isort = argsort(self.pids)
        self.pids.sort()
        #print(isort)
        pids = self.pids
        for iboundary in uboundaries:
            data = tag_data[iboundary]
            #name, is_visc, is_recon, is_rebuild, is_fixed, is_source,
            #is_trans, is_delete, bl_spacing, bl_thickness, nlayers = data
            name = data[0]

            i = where(iboundary == pids)[0]
            nfaces = i.max() - i.min() + 1
            startface = i.min()

            assert len(i) == nfaces, 'The data is unsorted...len(i)=%s nfaces=%s' % (len(i), nfaces)
            boundary_file.write('    %s\n' % name)
            boundary_file.write('    {\n')
            boundary_file.write('        type patch;\n')
            #f.write('        type 1(wall);\n')  # create a new group
            boundary_file.write('        nFaces %i;\n' % nfaces)
            boundary_file.write('        startFace %i;\n' % startface)
            boundary_file.write('    }\n')
        boundary_file.write(')\n')
        boundary_file.close()

        self.isort = isort

    def _write_faces(self, faces_filename):
        nhexas = self.hexas.shape[0]
        npenta6s = self.penta6s.shape[0]
        npenta5s = self.penta5s.shape[0]
        ntets = self.tets.shape[0]

        nquad_faces = nhexas * 6 + npenta5s + npenta6s * 3
        ntri_faces = ntets * 4 + npenta5s * 4 + npenta6s * 2
        nfaces = ntri_faces + nquad_faces

        #tri_face_to_eids = ones((nt, 2), dtype='int32')
        tri_face_to_eids = defaultdict(list)

        #quad_face_to_eids = ones((nq, 2), dtype='int32')
        quad_face_to_eids = defaultdict(list)

        tri_faces = zeros((ntri_faces, 3), dtype='int32')
        quad_faces = zeros((nquad_faces, 4), dtype='int32')

        faces_file = open(faces_filename, 'wb')
        faces_file.write('\n\n')
        #faces_file.write('%i\n' % (nnodes))
        faces_file.write('(\n')

        it_start = {}
        iq_start = {}
        min_eids = {}
        it = 0
        iq = 0
        eid = 1
        it_start[1] = it
        iq_start[1] = iq
        min_eids[eid] = self.tets
        for element in self.tets - 1:
            (n1, n2, n3, n4) = element
            face1 = [n3, n2, n1]
            face2 = [n1, n2, n4]
            face3 = [n4, n3, n1]
            face4 = [n2, n3, n4]

            tri_faces[it, :] = face1
            tri_faces[it+1, :] = face2
            tri_faces[it+2, :] = face3
            tri_faces[it+3, :] = face4

            face1.sort()
            face2.sort()
            face3.sort()
            face4.sort()
            tri_face_to_eids[tuple(face1)].append(eid)
            tri_face_to_eids[tuple(face2)].append(eid)
            tri_face_to_eids[tuple(face3)].append(eid)
            tri_face_to_eids[tuple(face4)].append(eid)
            it += 4
            eid += 1

        it_start[2] = it
        iq_start[2] = iq
        min_eids[eid] = self.hexas
        print('HEXA it=%s iq=%s' % (it, iq))
        for element in self.hexas-1:
            (n1, n2, n3, n4, n5, n6, n7, n8) = element

            face1 = [n1, n2, n3, n4]
            face2 = [n2, n6, n7, n3]
            face3 = [n6, n5, n8, n7]
            face4 = [n5, n1, n4, n8]
            face5 = [n4, n3, n7, n8]
            face6 = [n5, n6, n2, n1]

            quad_faces[iq, :] = face1
            quad_faces[iq+1, :] = face2
            quad_faces[iq+2, :] = face3
            quad_faces[iq+3, :] = face4
            quad_faces[iq+4, :] = face5
            quad_faces[iq+5, :] = face6

            face1.sort()
            face2.sort()
            face3.sort()
            face4.sort()
            face5.sort()
            face6.sort()

            quad_face_to_eids[tuple(face1)].append(eid)
            quad_face_to_eids[tuple(face2)].append(eid)
            quad_face_to_eids[tuple(face3)].append(eid)
            quad_face_to_eids[tuple(face4)].append(eid)
            quad_face_to_eids[tuple(face5)].append(eid)
            quad_face_to_eids[tuple(face6)].append(eid)
            iq += 6
            eid += 1

        it_start[3] = it
        iq_start[3] = iq
        min_eids[eid] = self.penta5s
        print('PENTA5 it=%s iq=%s' % (it, iq))
        for element in self.penta5s-1:
            (n1, n2, n3, n4, n5) = element

            face1 = [n2, n3, n5]
            face2 = [n1, n2, n5]
            face3 = [n4, n1, n5]
            face4 = [n5, n3, n4]
            face5 = [n4, n3, n2, n1]

            tri_faces[it, :] = face1
            tri_faces[it+1, :] = face2
            tri_faces[it+2, :] = face3
            tri_faces[it+3, :] = face4
            quad_faces[iq, :] = face5

            face1.sort()
            face2.sort()
            face3.sort()
            face4.sort()
            face5.sort()

            tri_face_to_eids[tuple(face1)].append(eid)
            tri_face_to_eids[tuple(face2)].append(eid)
            tri_face_to_eids[tuple(face3)].append(eid)
            tri_face_to_eids[tuple(face4)].append(eid)
            quad_face_to_eids[tuple(face5)].append(eid)

            it += 4
            iq += 1
            eid += 1

        it_start[4] = it
        iq_start[4] = iq
        min_eids[eid] = self.penta6s
        print('PENTA6 it=%s iq=%s' % (it, iq))
        for element in self.penta6s-1:
            (n1, n2, n3, n4, n5, n6) = element

            face1 = [n1, n2, n3]
            face2 = [n5, n4, n6]
            face3 = [n2, n5, n6, n3]
            face4 = [n4, n1, n3, n6]
            face5 = [n4, n5, n2, n1]

            tri_faces[it, :] = face1
            tri_faces[it+1, :] = face2
            quad_faces[iq, :] = face3
            quad_faces[iq+1, :] = face4
            quad_faces[iq+2, :] = face5

            face1.sort()
            face2.sort()
            face3.sort()
            face4.sort()
            face5.sort()

            tri_face_to_eids[tuple(face1)].append(eid)
            tri_face_to_eids[tuple(face2)].append(eid)
            quad_face_to_eids[tuple(face3)].append(eid)
            quad_face_to_eids[tuple(face4)].append(eid)
            quad_face_to_eids[tuple(face5)].append(eid)
            it += 2
            iq += 3
            eid += 1

        # find the unique faces
        tri_faces_sort = deepcopy(tri_faces)
        quad_faces_sort = deepcopy(quad_faces)
        #print('t0', tri_faces_sort[0, :])
        #print('t1', tri_faces_sort[1, :])

        print('nt=%s nq=%s' % (ntri_faces, nquad_faces))
        tri_faces_sort.sort(axis=1)
        #for i, tri in enumerate(tri_faces):
            #assert tri[2] > tri[0], 'i=%s tri=%s' % (i, tri)
        #print('*t0', tri_faces_sort[0, :])
        #print('*t1', tri_faces_sort[1, :])

        quad_faces_sort.sort(axis=1)
        #for i, quad in enumerate(quad_faces):
            #assert quad[3] > quad[0], 'i=%s quad=%s' % (i, quad)


        #iq_start_keys = iq_start.keys()
        #it_start_keys = it_start.keys()
        #iq_start_keys.sort()
        #it_start_keys.sort()

        face_to_eid = []

        eid_keys = min_eids.keys()
        eid_keys.sort()

        type_mapper = {
            1 : 'tets',
            2 : 'hexas',
            3 : 'penta5s',
            4 : 'penta6s',
        }
        print("eid_keys =", eid_keys)
        for face, eids in tri_face_to_eids.iteritems():
            if len(eids) == 1:
                #if it's a boundary face, wer're fine, otherwise, error...
                #print('*face=%s eids=%s' % (face, eids))
                #pid = lookup from quads/tris
                eid = eids[0]
                owner = eid
                neighbor = -1
                continue
                #raise RuntimeError()

            e1, e2 = eids
            i1 = searchsorted(eid_keys, e1)
            i2 = searchsorted(eid_keys, e2)

            if i1 == 1: # tet
                it1 = (e1-1) * 4
                it2 = (e1-1) * 4 + 4
                faces1_sort = tri_faces_sort[it1:it2, :]
                faces1_unsorted = tri_faces[it1:it2, :]

                #print "faces1 = \n", faces1_sort, '\n'

                # figure out irow; 3 for the test case
                face = array(face, dtype='int32')

                #print('face  = %s' % face)
                #print('face3 = %s' % faces1_sort[3, :])

                if allclose(face, faces1_sort[0, :]):
                    n1 = 0
                elif allclose(face, faces1_sort[1, :]):
                    n1 = 1
                elif allclose(face, faces1_sort[2, :]):
                    n1 = 2
                elif allclose(face, faces1_sort[3, :]):
                    n1 = 3
                else:
                    raise RuntimeError('cant find face=%s in faces for eid1=%s' % (face, e1))

                if allclose(face, faces1_unsorted[n1, :]):
                    owner = e1
                    neighbor = e2
                else:
                    owner = e2
                    neighbor = e1
                face_new = faces1_unsorted[n1, :]

            elif i1 == 2:  # CHEXA
                iq1 = iq_start[2]
                iq2 = iq1 + 6

            elif i1 == 3:  # CPENTA5
                #e1_new = e1 - eid_keys[2]
                iq1 = iq_start[3]
                iq2 = iq1 + 1
                it1 = it_start[3]
                it2 = it1 + 4
            elif i1 == 4:  # CPENTA6
                iq1 = iq_start[4]
                iq2 = iq1 + 3
                it1 = it_start[4]
                it2 = it1 + 2
            else:
                raise NotImplementedError('This is a %s and is not supported' % type_mapper[i1])

            # do we need to check this???
            if 0:
                if i2 == 1: # tet

                    it1 = it_start_keys[i1]
                    it2 = it1 + 4
                    faces2 = tri_faces_sort[it1:it2, :]
                    #print('face=%s eids=%s' % (face, eids))
                    #print "faces2 = \n", faces2
                    # spits out 3
                else:
                    asdf
            #type1 = type_mapper[i1]
            #type2 = type_mapper[i2]
            #if type1:
            #asdf
        faces_file.write(')\n')
        faces_file.close()


def determine_dytpe_nfloat_endian_from_ugrid_filename(ugrid_filename):
    base, file_format, ext = os.path.basename(ugrid_filename).split('.')
    assert ext == 'ugrid', 'extension=%r' % ext

    if '8' in file_format:
        ndarray_float = 'float64'
        float_fmt = 'd'
        nfloat = 8
    elif '4' in file_format:
        ndarray_float = 'float32'
        float_fmt = 'f'
        nfloat = 4
    else:  # ???
        msg = 'file_format=%r ugrid_filename=%s' % (file_format, ugrid_filename)
        raise NotImplementedError(msg)

    if 'lb' in file_format:  # C binary, little endian
        endian = '<'
    elif 'b' in file_format: # C binary, big endian
        endian = '>'
    #elif 'lr' in file_format: # Fortran unformatted binary, little endian
        #endian = '>'
    #elif 'r' in file_format:  # Fortran unformatted binary, big endian
        #endian = '>'
    else:  # fortran unformatted
        msg = 'file_format=%r ugrid_filename=%s' % (file_format, ugrid_filename)
        raise NotImplementedError(msg)
    return ndarray_float, float_fmt, nfloat, endian


def ugrid_to_tecplot(ugrid_model):
    nnodes = len(ugrid_model.nodes)
    nodes = zeros((nnodes, 3), dtype='float64')
    elements = []

    ntets = len(ugrid_model.tets)
    non_tets = len(ugrid_model.penta5s) + len(ugrid_model.penta6s) + len(ugrid_model.hexas)

    tecplot = Tecplot()
    tecplot.xyz = ugrid_model.nodes

    if ntets and non_tets == 0:
        elements = ugrid_model.tets
        tecplot.tet_elements = elements - 1
    elif non_tets:
        for element in ugrid_model.tets:
            n1, n2, n3, n4 = element
            elements.append([n1, n2, n3, n4,
                             n4, n4, n4, n4])
        for element in ugrid_model.penta5s:
            n1, n2, n3, n4, n5 = element
            elements.append([n1, n2, n3, n4,
                             n5, n5, n5, n5])
        for element in ugrid_model.penta6s:
            n1, n2, n3, n4, n5, n6 = element
            elements.append([n1, n2, n3, n4,
                             n5, n6, n6, n6])
        for element in ugrid_model.hexas:
            n1, n2, n3, n4, n5, n6, n7, n8 = element
            elements.append([n1, n2, n3, n4,
                             n5, n6, n7, n8])
        elements = array(elements, dtype='int32') - 1
        tecplot.hexa_elements = elements
    else:
        raise RuntimeError()
    return tecplot

def main():
    ugrid_filename = 'bay_steve_recon1_fixed0.b8.ugrid'
    #bdf_filename = 'bay_steve_recon1_fixed0.b8.bdf'
    foam_filename = 'bay_steve_recon1_fixed0.b8.foam'
    tag_filename = 'bay_steve.tags'
    assert os.path.exists(tag_filename)
    ugrid_model = UGRID()
    ugrid_model.read_ugrid(ugrid_filename)
    #ugrid_model.write_bdf(bdf_filename)
    ugrid_model.write_foam(foam_filename, tag_filename)





if __name__ == '__main__':
    main()