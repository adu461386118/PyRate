import os
import re
from pathlib import Path
import numpy as np

PYRATEPATH = Path(__file__).parent.parent


__version__ = "0.5.0"
CLI_DESCRIPTION = """
PyRate workflow: 

    Step 1: conv2tif
    Step 2: prepifg
    Step 3: correct
    Step 4: timeseries
    Step 5: stack
    Step 6: merge

Refer to https://geoscienceaustralia.github.io/PyRate/usage.html for 
more details.
"""

from pyrate.core.mpiops import comm

NO_OF_PARALLEL_PROCESSES = comm.Get_size()

CONV2TIF = 'conv2tif'
PREPIFG = 'prepifg'
CORRECT = 'correct'
TIMESERIES = 'timeseries'
STACK = 'stack'
MERGE = 'merge'

# distance division factor of 1000 converts to km and is needed to match legacy output
DISTFACT = 1000
# mappings for metadata in header for interferogram
GAMMA_DATE = 'date'
GAMMA_TIME = 'center_time'
GAMMA_WIDTH = 'width'
GAMMA_NROWS = 'nlines'
GAMMA_CORNER_LAT = 'corner_lat'
GAMMA_CORNER_LONG = 'corner_lon'
GAMMA_Y_STEP = 'post_lat'
GAMMA_X_STEP = 'post_lon'
GAMMA_DATUM = 'ellipsoid_name'
GAMMA_FREQUENCY = 'radar_frequency'
GAMMA_INCIDENCE = 'incidence_angle'
GAMMA_HEADING = 'heading'
GAMMA_AZIMUTH = 'azimuth_angle'
GAMMA_RANGE_PIX = 'range_pixel_spacing'
GAMMA_RANGE_N = 'range_samples'
GAMMA_AZIMUTH_PIX = 'azimuth_pixel_spacing'
GAMMA_AZIMUTH_N = 'azimuth_lines'
GAMMA_AZIMUTH_LOOKS = 'azimuth_looks'
GAMMA_PRF = 'prf'
GAMMA_NEAR_RANGE = 'near_range_slc'
GAMMA_SAR_EARTH = 'sar_to_earth_center'
GAMMA_SEMI_MAJOR_AXIS = 'earth_semi_major_axis'
GAMMA_SEMI_MINOR_AXIS = 'earth_semi_minor_axis'
GAMMA_PRECISION_BASELINE = 'precision_baseline(TCN)'
GAMMA_PRECISION_BASELINE_RATE = 'precision_baseline_rate'
# RADIANS = 'RADIANS'
# GAMMA = 'GAMMA'
# value assigned to no-data-value
LOW_FLOAT32 = np.finfo(np.float32).min*1e-10

SIXTEEN_DIGIT_EPOCH_PAIR = r'\d{8}-\d{8}'
sixteen_digits_pattern = re.compile(SIXTEEN_DIGIT_EPOCH_PAIR)
TWELVE_DIGIT_EPOCH_PAIR = r'\d{6}-\d{6}'
twelve_digits_pattern = re.compile(TWELVE_DIGIT_EPOCH_PAIR)

# general constants

NO_MULTILOOKING = 1
ROIPAC = 0
GAMMA = 1
LOG_LEVEL = 'INFO'

# constants for lookups
#: STR; Name of input interferogram list file
IFG_FILE_LIST = 'ifgfilelist'
#: (0/1/2); The interferogram processor used (0==ROIPAC, 1==GAMMA, 2: GEOTIF)
PROCESSOR = 'processor'
#: STR; Name of directory containing input interferograms.
OBS_DIR = 'obsdir'
#: STR; Name of directory for saving output products
OUT_DIR = 'outdir'
#: STR; Name of Digital Elevation Model file
DEM_FILE = 'demfile'
#: STR; Name of the DEM header file
DEM_HEADER_FILE = 'demHeaderFile'
#: STR; Name of directory containing GAMMA SLC header files
SLC_DIR = 'slcFileDir'
#: STR; Name of the file list containing the pool of available header files
HDR_FILE_LIST = 'hdrfilelist'

INTERFEROGRAM_FILES = 'interferogram_files'
HEADER_FILE_PATHS = 'header_file_paths'
COHERENCE_FILE_PATHS = 'coherence_file_paths'
BASELINE_FILE_PATHS = 'baseline_file_paths'
DEM_FILE_PATH = 'dem_file'


# STR; The projection of the input interferograms.
# TODO: only used in tests; deprecate?
INPUT_IFG_PROJECTION = 'projection'
#: FLOAT; The no data value in the interferogram files.
NO_DATA_VALUE = 'noDataValue'
#: FLOAT; No data averaging threshold for prepifg
NO_DATA_AVERAGING_THRESHOLD = 'noDataAveragingThreshold'
# BOOL (1/2/3); Re-project data from Line of sight, 1 = vertical, 2 = horizontal, 3 = no conversion
# REPROJECTION = 'prjflag' # NOT CURRENTLY USED
#: BOOL (0/1): Convert no data values to Nan
NAN_CONVERSION = 'nan_conversion'

# Prepifg parameters
#: BOOL (1/2/3/4); Method for cropping interferograms, 1 = minimum overlapping area (intersection), 2 = maximum area (union), 3 = customised area, 4 = all ifgs already same size
IFG_CROP_OPT = 'ifgcropopt'
#: INT; Multi look factor for interferogram preparation in x dimension
IFG_LKSX = 'ifglksx'
#: INT; Multi look factor for interferogram preparation in y dimension
IFG_LKSY = 'ifglksy'
#: FLOAT; Minimum longitude for cropping with method 3
IFG_XFIRST = 'ifgxfirst'
#: FLOAT; Maximum longitude for cropping with method 3
IFG_XLAST = 'ifgxlast'
#: FLOAT; Minimum latitude for cropping with method 3
IFG_YFIRST = 'ifgyfirst'
#: FLOAT; Maximum latitude for cropping with method 3
IFG_YLAST = 'ifgylast'

# reference pixel parameters
#: INT; Longitude (decimal degrees) of reference pixel, or if left blank a search will be performed
REFX = 'refx'
REFX_FOUND = 'refxfound'
#: INT; Latitude (decimal degrees) of reference pixel, or if left blank a search will be performed
REFY = 'refy'
REFY_FOUND = 'refyfound'
#: INT; Number of reference pixel grid search nodes in x dimension
REFNX = "refnx"
#: INT; Number of reference pixel grid search nodes in y dimension
REFNY = "refny"
#: INT; Dimension of reference pixel search window (in number of pixels)
REF_CHIP_SIZE = 'refchipsize'
#: FLOAT; Minimum fraction of observations required in search window for pixel to be a viable reference pixel
REF_MIN_FRAC = 'refminfrac'
#: BOOL (1/2); Reference phase estimation method (1: median of the whole interferogram, 2: median within the window surrounding the reference pixel)
REF_EST_METHOD = 'refest'

MAXVAR = 'maxvar'
VCMT = 'vcmt'
PREREAD_IFGS = 'preread_ifgs'
TILES = 'tiles'

# coherence masking parameters
#: BOOL (0/1); Perform coherence masking (1: yes, 0: no)
COH_MASK = 'cohmask'
#: FLOAT; Coherence threshold for masking
COH_THRESH = 'cohthresh'
#: STR; Directory containing coherence files; defaults to OBS_DIR if not provided
COH_FILE_DIR = 'cohfiledir'
#: STR; Name of the file list containing the pool of available coherence files
COH_FILE_LIST = 'cohfilelist'

# baseline parameters
#: STR; Directory containing baseline files; defaults to OBS_DIR if not provided
BASE_FILE_DIR = 'basefiledir'
#: STR; Name of the file list containing the pool of available baseline files
BASE_FILE_LIST = 'basefilelist'

#: STR; Name of the file containing the GAMMA lookup table between lat/lon and radar coordinates (row/col)
LT_FILE = 'ltfile'

# atmospheric error correction parameters NOT CURRENTLY USED
APS_CORRECTION = 'apscorrect'
APS_METHOD = 'apsmethod'
APS_INCIDENCE_MAP = 'incidencemap'
APS_INCIDENCE_EXT = 'APS_INCIDENCE_EXT'
APS_ELEVATION_MAP = 'elevationmap'
APS_ELEVATION_EXT = 'APS_ELEVATION_EXT'


# phase closure
PHASE_CLOSURE = 'phase_closure'
LARGE_DEV_THR = 'large_dev_thr'
AVG_IFG_ERR_THR = 'avg_ifg_err_thr'
LOOPS_THR_IFG = 'loops_thr_ifg'
PHS_UNW_ERR_THR = 'phs_unw_err_thr'
MAX_LOOP_LENGTH = 'max_loop_length'
SUBTRACT_MEDIAN = 'subtract_median'
MAX_LOOPS_IN_IFG = 'max_loops_in_ifg'

# orbital error correction/parameters
#: BOOL (1/0); Perform orbital error correction (1: yes, 0: no)
ORBITAL_FIT = 'orbfit'
#: BOOL (1/2); Method for orbital error correction (1: independent, 2: network)
ORBITAL_FIT_METHOD = 'orbfitmethod'
#: BOOL (1/2/3) Polynomial order of orbital error model (1: planar in x and y - 2 parameter model, 2: quadratic in x and y - 5 parameter model, 3: quadratic in x and cubic in y - part-cubic 6 parameter model)
ORBITAL_FIT_DEGREE = 'orbfitdegrees'
#: INT; Multi look factor for orbital error calculation in x dimension
ORBITAL_FIT_LOOKS_X = 'orbfitlksx'
#: INT; Multi look factor for orbital error calculation in y dimension
ORBITAL_FIT_LOOKS_Y = 'orbfitlksy'
#: BOOL (1/0); Add column of offset params to orbit correction design matrix (1: yes, 0: no)
ORBFIT_OFFSET = 'orbfitoffset'

# Stacking parameters
#: FLOAT; Threshold ratio between 'model minus observation' residuals and a-priori observation standard deviations for stacking estimate acceptance (otherwise remove furthest outlier and re-iterate)
LR_NSIG = 'nsig'
#: INT; Number of required observations per pixel for stacking to occur
LR_PTHRESH = 'pthr'
#: FLOAT; Maximum allowable standard error for pixels in stacking
LR_MAXSIG = 'maxsig'

# atmospheric delay errors fitting parameters NOT CURRENTLY USED
# atmfitmethod = 1: interferogram by interferogram; atmfitmethod = 2, epoch by epoch
# ATM_FIT = 'atmfit'
# ATM_FIT_METHOD = 'atmfitmethod'

# APS correction parameters
#: BOOL (0/1) Perform APS correction (1: yes, 0: no)
APSEST = 'apsest'
# temporal low-pass filter parameters
#: FLOAT; Cutoff time for gaussian filter in days;
TLPF_CUTOFF = 'tlpfcutoff'
#: INT; Number of required input observations per pixel for temporal filtering
TLPF_PTHR = 'tlpfpthr'
# spatially correlated noise low-pass filter parameters
#: FLOAT; Cutoff  value for both butterworth and gaussian filters in km
SLPF_CUTOFF = 'slpfcutoff'
#: INT (1/0); Do spatial interpolation at NaN locations (1 for interpolation, 0 for zero fill)
SLPF_NANFILL = 'slpnanfill'
#: #: STR; Method for spatial interpolation (one of: linear, nearest, cubic), only used when slpnanfill=1
SLPF_NANFILL_METHOD = 'slpnanfill_method'

# DEM error correction parameters
#: BOOL (0/1) Perform DEM error correction (1: yes, 0: no)
DEMERROR = 'demerror'
#: INT; Number of required input observations per pixel for DEM error estimation
DE_PTHR = 'de_pthr'

# Time series parameters
#: INT (1/2); Method for time series inversion (1: Laplacian Smoothing; 2: SVD)
TIME_SERIES_METHOD = 'tsmethod'
#: INT; Number of required input observations per pixel for time series inversion
TIME_SERIES_PTHRESH = 'ts_pthr'
#: INT (1/2); Order of Laplacian smoothing operator, first or second order
TIME_SERIES_SM_ORDER = 'smorder'
#: FLOAT; Laplacian smoothing factor (values used is 10**smfactor)
TIME_SERIES_SM_FACTOR = 'smfactor'
# tsinterp is automatically assigned in the code; not needed in conf file
# TIME_SERIES_INTERP = 'tsinterp'

#: BOOL (0/1/2); Use parallelisation/Multi-threading (0: in serial, 1: in parallel by rows, 2: in parallel by pixel)
PARALLEL = 'parallel'
#: INT; Number of processes for multi-threading
PROCESSES = 'processes'
LARGE_TIFS = 'largetifs'
# Orbital error correction constants for conversion to readable strings
INDEPENDENT_METHOD = 1
NETWORK_METHOD = 2
PLANAR = 1
QUADRATIC = 2
PART_CUBIC = 3

# Orbital error name look up for logging
ORB_METHOD_NAMES = {INDEPENDENT_METHOD: 'INDEPENDENT',
                    NETWORK_METHOD: 'NETWORK'}
ORB_DEGREE_NAMES = {PLANAR: 'PLANAR',
                    QUADRATIC: 'QUADRATIC',
                    PART_CUBIC: 'PART CUBIC'}


# geometry outputs
GEOMETRY_OUTPUT_TYPES = ['rdc_azimuth', 'rdc_range', 'look_angle', 'incidence_angle', 'azimuth_angle', 'range_dist']


# LOS projection
LOS_PROJECTION = 'los_projection'

# dir for temp files
TMPDIR = 'tmpdir'

# Lookup to help convert args to correct type/defaults
# format is	key : (conversion, default value)
# None = no conversion

# filenames reused in  many parts of the program
REF_PIXEL_FILE = 'ref_pixel_file'
ORB_ERROR_DIR = 'orb_error'
DEM_ERROR_DIR = 'dem_error'
APS_ERROR_DIR = 'aps_error'
PHASE_CLOSURE_DIR = 'phase_closure_dir'
MST_DIR = 'mst_dir'
TEMP_MLOOKED_DIR = 'temp_mlooked_dir'
COHERENCE_DIR = 'coherence_dir'
GEOMETRY_DIR = 'geometry_dir'


# temp constants
DISABLE_PHASE_CLOSURE = True
