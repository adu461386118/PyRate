#   This Python module is part of the PyRate software package.
#
#   Copyright 2020 Geoscience Australia
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""
This Python module implements residual orbital corrections for interferograms.
"""
# pylint: disable=invalid-name
import tempfile
from typing import Optional, List, Dict, Iterable
from collections import OrderedDict
from pathlib import Path
from numpy import empty, isnan, reshape, float32, squeeze
from numpy import dot, vstack, zeros, meshgrid
import numpy as np
from numpy.linalg import pinv, cond

import pyrate.constants as C
from pyrate.core.algorithm import first_second_ids, get_all_epochs
from pyrate.core import shared, ifgconstants as ifc, prepifg_helper, mst, mpiops
from pyrate.core.shared import nanmedian, Ifg, InputTypes, iterable_split
from pyrate.core.logger import pyratelogger as log
from pyrate.prepifg import find_header
from pyrate.configuration import MultiplePaths
# Orbital correction tasks
#
# TODO: options for multilooking
# 1) do the 2nd stage mlook at prepifg.py/generate up front, then delete in
#    workflow afterward
# 2) refactor prep_ifgs() call to take input filenames and params & generate
#    mlooked versions from that
#    this needs to be more generic to call at any point in the runtime.


# Design notes:
# The orbital correction code includes several enhancements. PyRate creates
# sparse arrays for the linear inversion, which contain many empty cells.
# This is unnecessary for the independent method, and temporarily wastes
# potentially a lot of memory.
#
# For the independent method, PyRate makes individual small design matrices and
# corrects the Ifgs one by one. If required in the correction, the offsets
# option adds an extra column of ones to include in the inversion.
#
# Network method design matrices are mostly empty, and offsets are handled
# differently. Individual design matrices (== independent method DMs) are
# placed in the sparse network design matrix. Offsets are not included in the
# smaller DMs to prevent unwanted cols being inserted. This is why some funcs
# appear to ignore the offset parameter in the networked method. Network DM
# offsets are cols of 1s in a diagonal line on the LHS of the sparse array.

MAIN_PROCESS = 0

# ORBITAL ERROR correction constants
INDEPENDENT_METHOD = C.INDEPENDENT_METHOD
NETWORK_METHOD = C.NETWORK_METHOD

PLANAR = C.PLANAR
QUADRATIC = C.QUADRATIC
PART_CUBIC = C.PART_CUBIC


def remove_orbital_error(ifgs: List, params: dict) -> None:
    """
    Wrapper function for PyRate orbital error removal functionality.

    NB: the ifg data is modified in situ, rather than create intermediate
    files. The network method assumes the given ifgs have already been reduced
    to a minimum spanning tree network.
    """
    ifg_paths = [i.data_path for i in ifgs] if isinstance(ifgs[0], Ifg) else ifgs
    degree = params[C.ORBITAL_FIT_DEGREE]
    method = params[C.ORBITAL_FIT_METHOD]
    orbfitlksx = params[C.ORBITAL_FIT_LOOKS_X]
    orbfitlksy = params[C.ORBITAL_FIT_LOOKS_Y]

    # Sanity check of the orbital params
    if type(orbfitlksx) != int or type(orbfitlksy) != int:
        msg = f"Multi-look factors for orbital correction should be of type: int"
        raise OrbitalError(msg)
    if degree not in [PLANAR, QUADRATIC, PART_CUBIC]:
        msg = "Invalid degree of %s for orbital correction" % C.ORB_DEGREE_NAMES.get(degree)
        raise OrbitalError(msg)
    if method not in [NETWORK_METHOD, INDEPENDENT_METHOD]:
        msg = "Invalid method of %s for orbital correction" % C.ORB_METHOD_NAMES.get(method)
        raise OrbitalError(msg)

    # Give informative log messages based on selected options
    log.info(f'Calculating {__degrees_as_string(degree)} orbital correction using '
             f'{__methods_as_string(method)} method')
    if orbfitlksx > 1 or orbfitlksy > 1:
        log.info(f'Multi-looking interferograms for orbital correction with '
                 f'factors of X = {orbfitlksx} and Y = {orbfitlksy}')

    if method == INDEPENDENT_METHOD:
        iterable_split(independent_orbital_correction, ifg_paths, params)

    elif method == NETWORK_METHOD:
        # Here we do all the multilooking in one process, but in memory
        # could use multiple processes if we write data to disc during
        # remove_orbital_error step
        # TODO: performance comparison of saving multilooked files on
        # disc vs in-memory single-process multilooking
        #
        # The gdal swig bindings prevent us from doing multi-looking in parallel
        # when using multiprocessing because the multilooked ifgs are held in
        # memory using in-memory tifs. Parallelism using MPI is possible.
        # TODO: Use a flag to select mpi parallel vs multiprocessing in the
        # iterable_split function, which will use mpi but can fall back on
        # single process based on the flag for the multiprocessing side.
        if mpiops.rank == MAIN_PROCESS:
            mlooked = __create_multilooked_datasets(params)
            _validate_mlooked(mlooked, ifg_paths)
            network_orbital_correction(ifg_paths, params, mlooked)
    else:
        raise OrbitalError("Unrecognised orbital correction method")


def __create_multilooked_datasets(params):
    exts, ifg_paths, multi_paths = __extents_from_params(params)
    mlooked_datasets = [_create_mlooked_dataset(m, i, exts, params) for m, i in zip(multi_paths, ifg_paths)]

    mlooked = [Ifg(m) for m in mlooked_datasets]
    for m in mlooked:
        m.initialize()
        shared.nan_and_mm_convert(m, params)
    return mlooked


def __extents_from_params(params):
    multi_paths = params[C.INTERFEROGRAM_FILES]
    ifg_paths = [p.tmp_sampled_path for p in multi_paths]
    rasters = [shared.dem_or_ifg(r) for r in ifg_paths]
    crop_opt = prepifg_helper.ALREADY_SAME_SIZE
    xlooks = params[C.ORBITAL_FIT_LOOKS_X]
    ylooks = params[C.ORBITAL_FIT_LOOKS_Y]
    exts = prepifg_helper.get_analysis_extent(crop_opt, rasters, xlooks, ylooks, None)
    return exts, ifg_paths, multi_paths


def _create_mlooked_dataset(multi_path, ifg_path, exts, params):
    '''
    Wrapper to generate a multi-looked dataset for a single ifg
    '''
    header = find_header(multi_path, params)
    thresh = params[C.NO_DATA_AVERAGING_THRESHOLD]
    crop_opt = prepifg_helper.ALREADY_SAME_SIZE
    xlooks = params[C.ORBITAL_FIT_LOOKS_X]
    ylooks = params[C.ORBITAL_FIT_LOOKS_Y]
    out_path = tempfile.mktemp()
    log.debug(f'Multi-looking {ifg_path} with factors X = {xlooks} and Y = {ylooks} for orbital correction')
    resampled_data, out_ds = prepifg_helper.prepare_ifg(ifg_path, xlooks, ylooks, exts, thresh, crop_opt, header, False, out_path)
    return out_ds


def _validate_mlooked(mlooked, ifgs):
    '''
    Basic sanity checking of the multilooked ifgs.
    '''

    if len(mlooked) != len(ifgs):
        msg = "Mismatching # ifgs and # multilooked ifgs"
        raise OrbitalError(msg)

    if not all([hasattr(i, 'phase_data') for i in mlooked]):
        msg = "Mismatching types in multilooked ifgs arg:\n%s" % mlooked
        raise OrbitalError(msg)


def _get_num_params(degree, offset=None):
    '''
    Returns number of model parameters from string parameter
    '''

    if degree == PLANAR:
        nparams = 2
    elif degree == QUADRATIC:
        nparams = 5
    elif degree == PART_CUBIC:
        nparams = 6
    else:
        msg = "Invalid orbital model degree: %s" \
              % C.ORB_DEGREE_NAMES.get(degree)
        raise OrbitalError(msg)

    # NB: independent method only, network method handles offsets separately
    if offset:
        nparams += 1  # eg. y = mx + offset
    return nparams


def independent_orbital_correction(ifg_path,  params):
    """
    Calculates and removes an orbital error surface from a single independent
    interferogram.

    Warning: This will write orbital error corrected phase_data to the ifg.

    :param Ifg class instance ifg: the interferogram to be corrected
    :param str degree: model to fit (PLANAR / QUADRATIC / PART_CUBIC)
    :param bool offset: True to calculate the model using an offset
    :param dict params: dictionary of configuration parameters

    :return: None - interferogram phase data is updated and saved to disk
    """
    log.debug(f"Orbital correction of {ifg_path}")
    degree = params[C.ORBITAL_FIT_DEGREE]
    offset = params[C.ORBFIT_OFFSET]
    xlooks = params[C.ORBITAL_FIT_LOOKS_X]
    ylooks = params[C.ORBITAL_FIT_LOOKS_Y]
    scale = params[C.ORBFIT_SCALE]

    ifg0 = shared.Ifg(ifg_path) if isinstance(ifg_path, str) else ifg_path
    design_matrix = get_design_matrix(ifg0, degree, offset, scale=scale)

    ifg = shared.dem_or_ifg(ifg_path) if isinstance(ifg_path, str) else ifg_path
    ifg_path = ifg.data_path

    multi_path = MultiplePaths(ifg_path, params)
    original_ifg = ifg  # keep a backup
    orb_on_disc = MultiplePaths.orb_error_path(ifg_path, params)
    if not ifg.is_open:
        ifg.open()

    shared.nan_and_mm_convert(ifg, params)

    if orb_on_disc.exists():
        log.info(f'Reusing already computed orbital fit correction: {orb_on_disc}')
        orbital_correction = np.load(file=orb_on_disc)
    else:
        # Multi-look the ifg data if either X or Y is greater than 1
        if (xlooks > 1) or (ylooks > 1):
            exts, _, _ = __extents_from_params(params)
            mlooked = _create_mlooked_dataset(multi_path, ifg.data_path, exts, params)
            ifg = Ifg(mlooked)

        # vectorise, keeping NODATA
        vphase = reshape(ifg.phase_data, ifg.num_cells)
        dm = get_design_matrix(ifg, degree, offset, scale=scale)

        # filter NaNs out before inverting to get the model
        B = dm[~isnan(vphase)]
        data = vphase[~isnan(vphase)]
        model = dot(pinv(B, 1e-6), data)

        if offset:
            fullorb = np.reshape(np.dot(design_matrix[:, :-1], model[:-1]), original_ifg.phase_data.shape)
        else:
            fullorb = np.reshape(np.dot(design_matrix, model), original_ifg.phase_data.shape)

        if not orb_on_disc.parent.exists():
            shared.mkdir_p(orb_on_disc.parent)
        offset_removal = nanmedian(np.ravel(original_ifg.phase_data - fullorb))
        orbital_correction = fullorb - offset_removal
        # dump to disc
        np.save(file=orb_on_disc, arr=orbital_correction)

    # subtract orbital error from the ifg
    original_ifg.phase_data -= orbital_correction
    # set orbfit meta tag and save phase to file
    _save_orbital_error_corrected_phase(original_ifg, params)
    original_ifg.close()


def network_orbital_correction(ifg_paths, params, m_ifgs: Optional[List] = None):
    """
    This algorithm implements a network inversion to determine orbital
    corrections for a set of interferograms forming a connected network.

    Warning: This will write orbital error corrected phase_data to the ifgs.

    :param list ifg_paths: List of Ifg class objects reduced to a minimum spanning
        tree network
    :param str degree: model to fit (PLANAR / QUADRATIC / PART_CUBIC)
    :param bool offset: True to calculate the model using offsets
    :param dict params: dictionary of configuration parameters
    :param list m_ifgs: list of multilooked Ifg class objects
        (sequence must be multilooked versions of 'ifgs' arg)
    :param dict preread_ifgs: Dictionary containing information specifically
        for MPI jobs (optional)

    :return: None - interferogram phase data is updated and saved to disk
    """
    # pylint: disable=too-many-locals, too-many-arguments
    offset = params[C.ORBFIT_OFFSET]
    degree = params[C.ORBITAL_FIT_DEGREE]
    preread_ifgs = params[C.PREREAD_IFGS]
    # all orbit corrections available?
    if isinstance(ifg_paths[0], str):
        if __check_and_apply_orberrors_found_on_disc(ifg_paths, params):
            log.warning("Reusing orbfit errors from previous run!!!")
            return
        # all corrections are available in numpy files already saved - return
        ifgs = [shared.Ifg(i) for i in ifg_paths]
    else:  # alternate test paths # TODO: improve
        ifgs = ifg_paths

    src_ifgs = ifgs if m_ifgs is None else m_ifgs
    src_ifgs = mst.mst_from_ifgs(src_ifgs)[3]  # use networkx mst

    vphase = vstack([i.phase_data.reshape((i.num_cells, 1)) for i in src_ifgs])
    vphase = squeeze(vphase)

    B = get_network_design_matrix(src_ifgs, degree, offset)

    # filter NaNs out before getting model
    B = B[~isnan(vphase)]
    orbparams = dot(pinv(B, 1e-6), vphase[~isnan(vphase)])

    ncoef = _get_num_params(degree)
    if preread_ifgs:
        temp_ifgs = OrderedDict(sorted(preread_ifgs.items())).values()
        ids = first_second_ids(get_all_epochs(temp_ifgs))
    else:
        ids = first_second_ids(get_all_epochs(ifgs))
    coefs = [orbparams[i:i+ncoef] for i in range(0, len(set(ids)) * ncoef, ncoef)]

    # create full res DM to expand determined coefficients into full res
    # orbital correction (eg. expand coarser model to full size)

    if preread_ifgs:
        temp_ifg = Ifg(ifg_paths[0])  # ifgs here are paths
        temp_ifg.open()
        dm = get_design_matrix(temp_ifg, degree, offset=False)
        temp_ifg.close()
    else:
        ifg = ifgs[0]
        dm = get_design_matrix(ifg, degree, offset=False)

    for i in ifg_paths:
        # open if not Ifg instance
        if isinstance(i, str):  # pragma: no cover
            # are paths
            i = Ifg(i)
            i.open(readonly=False)
            shared.nan_and_mm_convert(i, params)
        _remove_network_orb_error(coefs, dm, i, ids, offset, params)


def __check_and_apply_orberrors_found_on_disc(ifg_paths, params):
    saved_orb_err_paths = [MultiplePaths.orb_error_path(ifg_path, params) for ifg_path in ifg_paths]
    for p, i in zip(saved_orb_err_paths, ifg_paths):
        if p.exists():
            orb = np.load(p)
            if isinstance(i, str):
                # are paths
                ifg = Ifg(i)
                ifg.open(readonly=False)
                shared.nan_and_mm_convert(ifg, params)
            else:
                ifg = i
            ifg.phase_data -= orb
            # set orbfit meta tag and save phase to file
            _save_orbital_error_corrected_phase(ifg, params)
    return all(p.exists() for p in saved_orb_err_paths)


def _remove_network_orb_error(coefs, dm, ifg, ids, offset, params):
    """
    remove network orbital error from input interferograms
    """
    saved_orb_err_path = MultiplePaths.orb_error_path(ifg.data_path, params)
    orb = dm.dot(coefs[ids[ifg.second]] - coefs[ids[ifg.first]])
    orb = orb.reshape(ifg.shape)
    # offset estimation
    if offset:
        # bring all ifgs to same base level
        orb -= nanmedian(np.ravel(ifg.phase_data - orb))
    # subtract orbital error from the ifg
    ifg.phase_data -= orb

    # save orb error on disc
    np.save(file=saved_orb_err_path, arr=orb)
    # set orbfit meta tag and save phase to file
    _save_orbital_error_corrected_phase(ifg, params)


def _save_orbital_error_corrected_phase(ifg, params):
    """
    Convenience function to update metadata and save latest phase after
    orbital fit correction
    """
    # set orbfit tags after orbital error correction
    ifg.dataset.SetMetadataItem(ifc.PYRATE_ORB_METHOD, __methods_as_string(params[C.ORBITAL_FIT_METHOD]))
    ifg.dataset.SetMetadataItem(ifc.PYRATE_ORB_DEG, __degrees_as_string(params[C.ORBITAL_FIT_DEGREE]))
    ifg.dataset.SetMetadataItem(ifc.PYRATE_ORB_XLOOKS, str(params[C.ORBITAL_FIT_LOOKS_X]))
    ifg.dataset.SetMetadataItem(ifc.PYRATE_ORB_YLOOKS, str(params[C.ORBITAL_FIT_LOOKS_Y]))
    ifg.dataset.SetMetadataItem(ifc.PYRATE_ORBITAL_ERROR, ifc.ORB_REMOVED)
    ifg.write_modified_phase()
    ifg.close()


def __methods_as_string(method):
    """Look up table to get orbital method string names"""
    meth = {1:ifc.PYRATE_ORB_INDEPENDENT, 2:ifc.PYRATE_ORB_NETWORK}
    return str(meth[method])


def __degrees_as_string(degree):
    """Look up table to get orbital degree string names"""
    deg = {1: ifc.PYRATE_ORB_PLANAR, 2: ifc.PYRATE_ORB_QUADRATIC, 3: ifc.PYRATE_ORB_PART_CUBIC}
    return str(deg[degree])


# TODO: subtract reference pixel coordinate from x and y
def get_design_matrix(ifg, degree, offset, scale: Optional[float] = 100.0):
    """
    Returns orbital error design matrix with columns for model parameters.

    :param Ifg class instance ifg: interferogram to get design matrix for
    :param str degree: model to fit (PLANAR / QUADRATIC / PART_CUBIC)
    :param bool offset: True to include offset column, otherwise False.
    :param float scale: Scale factor to divide cell size by in order to
        improve inversion robustness

    :return: dm: design matrix
    :rtype: ndarray
    """
    if not ifg.is_open:
        ifg.open()

    if degree not in [PLANAR, QUADRATIC, PART_CUBIC]:
        raise OrbitalError("Invalid degree argument")

    # scaling required with higher degree models to help with param estimation
    xsize = ifg.x_size / scale if scale else ifg.x_size
    ysize = ifg.y_size / scale if scale else ifg.y_size

    # mesh needs to start at 1, otherwise first cell resolves to 0 and ignored
    xg, yg = [g+1 for g in meshgrid(range(ifg.ncols), range(ifg.nrows))]
    x = xg.reshape(ifg.num_cells) * xsize
    y = yg.reshape(ifg.num_cells) * ysize

    # TODO: performance test this vs np.concatenate (n by 1 cols)??
    dm = empty((ifg.num_cells, _get_num_params(degree, offset)), dtype=float32)

    # apply positional parameter values, multiply pixel coordinate by cell size
    # to get distance (a coord by itself doesn't tell us distance from origin)
    if degree == PLANAR:
        dm[:, 0] = x
        dm[:, 1] = y
    elif degree == QUADRATIC:
        dm[:, 0] = x**2
        dm[:, 1] = y**2
        dm[:, 2] = x * y
        dm[:, 3] = x
        dm[:, 4] = y
    elif degree == PART_CUBIC:
        dm[:, 0] = x * (y**2)
        dm[:, 1] = x**2
        dm[:, 2] = y**2
        dm[:, 3] = x * y
        dm[:, 4] = x
        dm[:, 5] = y
    if offset:
        dm[:, -1] = np.ones(ifg.num_cells)

    # report condition number of the design matrix - L2-norm computed using SVD
    log.debug(f'The condition number of the design matrix is {cond(dm)}')

    return dm


def get_network_design_matrix(ifgs, degree, offset):
    # pylint: disable=too-many-locals
    """
    Returns larger-format design matrix for network error correction. The
    network design matrix includes rows which relate to those of NaN cells.

    :param list ifgs: List of Ifg class objects
    :param str degree: model to fit (PLANAR / QUADRATIC / PART_CUBIC)
    :param bool offset: True to include offset cols, otherwise False.

    :return: netdm: network design matrix
    :rtype: ndarray
    """

    if degree not in [PLANAR, QUADRATIC, PART_CUBIC]:
        raise OrbitalError("Invalid degree argument")

    nifgs = len(ifgs)
    if nifgs < 1:
        # can feasibly do correction on a single Ifg/2 epochs
        raise OrbitalError("Invalid number of Ifgs: %s" % nifgs)

    # init sparse network design matrix
    nepochs = len(set(get_all_epochs(ifgs)))

    # no offsets: they are made separately below
    ncoef = _get_num_params(degree)
    shape = [ifgs[0].num_cells * nifgs, ncoef * nepochs]

    if offset:
        shape[1] += nifgs  # add extra block for offset cols

    netdm = zeros(shape, dtype=float32)

    # calc location for individual design matrices
    dates = [ifg.first for ifg in ifgs] + [ifg.second for ifg in ifgs]
    ids = first_second_ids(dates)
    offset_col = nepochs * ncoef  # base offset for the offset cols
    tmpdm = get_design_matrix(ifgs[0], degree, offset=False)

    # iteratively build up sparse matrix
    for i, ifg in enumerate(ifgs):
        rs = i * ifg.num_cells  # starting row
        m = ids[ifg.first] * ncoef  # start col for first
        s = ids[ifg.second] * ncoef  # start col for second
        netdm[rs:rs + ifg.num_cells, m:m + ncoef] = -tmpdm
        netdm[rs:rs + ifg.num_cells, s:s + ncoef] = tmpdm

        # offsets are diagonal cols across the extra array block created above
        if offset:
            netdm[rs:rs + ifg.num_cells, offset_col + i] = 1  # init offset cols

    return netdm


class OrbitalError(Exception):
    """
    Generic class for errors in orbital correction.
    """


def orb_fit_calc_wrapper(params: dict) -> None:
    """
    MPI wrapper for orbital fit correction
    """
    multi_paths = params[C.INTERFEROGRAM_FILES]
    if not params[C.ORBITAL_FIT]:
        log.info('Orbital correction not required!')
        return
    ifg_paths = [p.tmp_sampled_path for p in multi_paths]
    remove_orbital_error(ifg_paths, params)
    mpiops.comm.barrier()
    shared.save_numpy_phase(ifg_paths, params)
    log.debug('Finished Orbital error correction')
