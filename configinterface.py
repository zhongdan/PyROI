"""
The config interface module provides an interface to custom config modules.

If a file called ``.roisetupfile`` exists in the working directory when
PyROI is imported, it will attempt to import the file named within as the
config setup module.  If successful, that module will be imported as 
``setup`` within this module.  If not, it will have to be manually 
imported through the ``import_setup()`` fucntion.

See the docstrings for individual functions in this module for 
information on how to use them.
"""

import os
import re
import imp
from warnings import warn
from copy import deepcopy
from glob import glob
import nipype.interfaces.freesurfer as fs
from exceptions import *

__module__ = "configinterface"

# Look for a file indicating the setup module and import that module if found
if os.path.isfile(".roiconfigfile"):
    
    module = open(".roiconfigfile","r").read()
    
    # Get rid of any extraneous whitespace
    m = re.search("\w+", module)
    if m:
        module = m.group()

    # Trim the file extension if it exists
    if module.endswith(".py"):
        module = pmodule[:-3]
    
    # Import the module
    try:
        if not module: raise ImportError
        f, name, desc = imp.find_module(module)
        setup = imp.load_module("setup", f, name, desc)
        is_setup = True
        f.close()
        del f, name, desc
    except ImportError:
        print ("\nFound .roiconfigfile, but config module import failed."
               "\nYou will need to use the `import_setup()' function.")
        is_setup = False
    
    # Clean up
    del m, module
else:
    is_setup = False


def projectname():
    """Return the project name string.

    Returns
    -------
    str
    """
 
    return setup.projname


def analysis(dictnumber=None):
    """Return the analysis list or an analysis dict.  
    
    Parameter
    ---------
    dictnumber : int, optional
        If included, the function returns the dictionary at this index.
        Otherwise, it returns the full list.  Note that indexing for this
        function is 1-based, unlike most python sequences.        

    Returns
    -------
    list of dicts or dict

    """

    analyses = setup.analysis

    if isinstance(analyses, dict):
        analyses = [analyses]

    if dictnumber is None:
        return analyses
    else:
        if dictnumber not in range(1, len(analyses) + 1):
            print ("\nAnalysis %d is out of range." 
                   "\nRemember that the analysis list index is 1-based."
                   % dictnumber)
            return
        else:
            return analyses[dictnumber - 1]


def atlases(atlasname=None):
    """Return the atlas specifications.
    
    This function performs a fair amount of checking and addition of obvious but 
    neccessary fields (via calls to private subfunctions), so always get atlas 
    dictionaries from this function, not directly from the setup module.

    Parameters
    ----------
    atlasname : str, optional
        The atlas name, or None to return the full dictionary, which is default.

    Returns
    -------
    dict

    """
    atlasdicts = deepcopy(setup.atlases)

    for name, dictionary in atlasdicts.items():
        dictionary["atlasname"] = name
        for k, v in dictionary.items():
            if not k.islower():
                dictionary[k.lower()] = v
                del dictionary[k]
        if "source" not in dictionary:
            raise SetupError("Source missing from %s atlas dictionary" % name)
        dictionary["source"] = dictionary["source"].lower()
        if dictionary["source"] == "freesurfer":
            dictionary = _prep_freesurfer_atlas(dictionary)
        elif dictionary["source"] == "fsl":
            dictionary = _prep_fsl_atlas(dictionary)
        elif dictionary["source"] == "label":
            dictionary = _prep_label_atlas(dictionary)
        elif dictionary["source"] == "sigsurf":
            dictionary = _prep_sigsurf_atlas(dictionary)
        elif dictionary["source"] == "mask":
            dictionary = _prep_mask_atlas(dictionary)
        elif dictionary["source"] == "sphere":
            dictionary = _prep_sphere_atlas(dictionary)
        else:
            raise SetupError("Source setting '%s' for %s atlas not understood"
                                % (dictionary["source"], name))

    if atlasname is None:
        return atlasdicts
    else:
        return atlasdicts[atlasname]

def _check_fields(atlasfields, atlasdict):
    """Check whether any fields are missing or unexpected in an atlas dictionary."""
    extra = [k for k in atlasdict if k not in atlasfields]
    missing = [f for f in atlasfields if f not in atlasdict]
    atlasname = atlasdict["atlasname"]
    if extra:
        raise SetupError("Unexpected field(s) %s found in %s dictionary"
                            % (extra, atlasname))
    if missing:
        raise SetupError("Field(s) %s missing from %s dictionary"
                            % (missing, atlasname))

def _prep_freesurfer_atlas(atlasdict):
    """Prepare a Freesurfer atlas dictionary."""
    atlasfields = ["atlasname", "source", "fname", "manifold", "regions"]
    _check_fields(atlasfields, atlasdict)

    atlasdict["manifold"] = atlasdict["manifold"].lower()
    if atlasdict["manifold"] not in ["surface", "volume"]:
        raise SetupError("Manifold setting '%s' for %s atlas not understood"
                            % (atlasdict["manifold"], atlasdict["atlasname"]))

    if atlasdict["manifold"] == "surface" and not atlasdict["fname"].endswith(".annot"):
        atlasdict["fname"] = "%s.annot" % atlasdict["fname"]

    if not os.path.isdir(fssubjdir()):
        raise SetupError("Using Freesurfer atlas with illegitimite "
                            "subjects directory path")

    if not isinstance(atlasdict["regions"], list):
        atlasdict["regions"] = [atlasdict["regions"]]

    return atlasdict                                

def _prep_fsl_atlas(atlasdict):
    """Prepare a HarvardOxford atlas dictionary."""
    atlasfields = ["atlasname", "source", "probthresh", "regions"]
    _check_fields(atlasfields, atlasdict)

    atlasdict["manifold"] = "volume"

    if atlasdict["probthresh"] not in [25, 50]:
        raise SetupError("HarvardOxford atlas probthresh setting must be either 25 or 50.")

    if not isinstance(atlasdict["regions"], list):
        atlasdict["regions"] = [atlasdict["regions"]]

    return atlasdict                                

def _prep_sigsurf_atlas(atlasdict):
    """Prepare a sigsurf atlas dictionary."""
    atlasfields = ["atlasname", "source", "hemi", "file", "fdr", "minsize"]
    _check_fields(atlasfields, atlasdict)

    atlasdict["manifold"] = "surface"

    if not os.path.isdir(fssubjdir()):
        raise SetupError("Using sigsurf atlas with illegitimite "
                            "Freesurfer Subjects Directory path")

    if isinstance(atlasdict["fdr"], str):
        try:
            atlasdict["fdr"] = float(atlasdict["fdr"])
        except ValueError:
            raise SetupError("FDR thresh setting for %s atlas does not appear "
                             "to be a number" % atlasdict["atlasname"])
    if isinstance(atlasdict["minsize"], str):
        try:
            atlasdict["fdr"] = int(atlasdict["fdr"])
        except ValueError:
            raise SetupError("Minsize setting for %s atlas does not appear "
                             "to be a number" % atlasdict["atlasname"])

    if not os.path.isabs(atlasdict["file"]):
        atlasdict["file"] = os.path.join(setup.basedir, atlasdict["file"])
    if not os.path.isfile(atlasdict["file"]):
        raise SetupError("%s source image %s does not exist" 
                         % (atlasdict["atlasname"], atlasdict["file"]))

    return atlasdict                         

def _prep_label_atlas(atlasdict):
    """Prepare a label atlas dictionary"""
    atlasfields = ["atlasname", "source", "hemi", "sourcedir", "sourcefiles"]
    _check_fields(atlasfields, atlasdict)
    
    if not os.path.isdir(fssubjdir()):
        raise SetupError("Using label atlas with illegitimite "
                            "Freesurfer Subjects Directory path")

    if not os.path.isabs(atlasdict["sourcedir"]):
        atlasdict["sourcedir"] = os.path.join(setup.basepath, atlasdict["sourcedir"])

    atlasdict["manifold"] = "surface"

    if atlasdict["sourcefiles"] == "all" or ["all"]:
        atlasdict["sourcefiles"] = glob(os.path.join(atlasdict["sourcedir"], "*.label"))
        if not atlasdict["sourcefiles"]:
            raise SetupError("Using 'all' for %s atlas found no label images"
                                % atlasdict["atlasname"])

    lfiles = atlasdict["sourcefiles"]
    if not isinstance(lfiles, list):
        lfiles = [lfiles]
    lnames = []
    for i, lfile in enumerate(lfiles):
        path, lfile = os.path.split(lfile)
        if lfile.endswith(".label"):
            lfile, ext = os.path.splitext(lfile)
        lfiles[i] = os.path.join(atlasdict["sourcedir"], lfile + ".label")
        lnames.append(lfile)
        if not os.path.isfile(lfiles[i]):
            warn("%s does not exist." % lfiles[i])
    atlasdict["sourcefiles"] = lfiles
    atlasdict["sourcenames"] = lnames
    return atlasdict

def _prep_mask_atlas(atlasdict):
    """Prepare a mask atlas dictionary"""
    atlasfields = ["atlasname", "source", "sourcedir", "sourcefiles"]
    _check_fields(atlasfields, atlasdict)

    if not os.path.isabs(atlasdict["sourcedir"]):
        atlasdict["sourcedir"] = os.path.join(setup.basepath, atlasdict["sourcedir"])

    atlasdict["manifold"] = "volume"
    
    imgregexp = re.compile("[\w\.-]+\.(img)|(nii)|(nii\.gz)|(mgh)|(mgz)$")

    if atlasdict["sourcefiles"] == "all" or ["all"]:
        refiles = []
        gfiles = glob(os.path.join(atlasdict["sourcedir"],"*"))
        for gfile in gfiles:
            m = imgregexp.search(gfile)
            if m:
                refiles.append(m.group())
        if refiles:
            atlasdict["sourcefiles"] = refiles
        else:
            raise SetupError("Using 'all' for %s atlas found no mask images" 
                                % atlasdict["atlasname"])

    lfiles = atlasdict["sourcefiles"]
    if not isinstance(lfiles, list):
        lfiles = [lfiles]

    notimgs = [f for f in lfiles if not imgregexp.search(f)]
    if notimgs:
        spl = lambda fpath: os.path.splitext(os.path.split(fpath)[1])[0]
        repimgs = []
        for img in notimgs:
            imglob = glob(os.path.join(atlasdict["sourcedir"], img + "*"))
            imreg = [f for f in imglob if imgregexp.search(f)]
            if len(imreg) == 1:
                lfiles[lfiles.index(img)] = imreg[0]
                repimgs.append(spl(imreg[0]))
        if not len(notimgs) == len(repimgs):
            raise SetupError(
                "File type of mask(s) %s could not be determined or is not supported"
                 % [f for f in notimgs if f not in repimgs])

    lnames = []
    for i, lfile in enumerate(lfiles):
        path, lfile = os.path.split(lfile)
        lfiles[i] = os.path.join(atlasdict["sourcedir"], lfile)
        lfile, ext = os.path.splitext(lfile)
        lnames.append(lfile)
        if not os.path.isfile(lfiles[i]):
            warn("%s does not exist." % lfiles[i])
    atlasdict["sourcefiles"] = lfiles
    atlasdict["sourcenames"] = lnames
    return atlasdict

def _prep_sphere_atlas(atlasdict):
    """Prepare the atlas dictionary for a sphere atlas."""
    atlasdict["manifold"] = "volume"

def fssubjdir():
    """Set and return the path to the Freesurfer Subjects directory.

    Returns
    -------
    str
    
    """
   
    """
    dirpath = setup.subjdir
    print dirpath
    if not os.path.isabs:
        dirpath = os.path.join(setup.basepath, dirpath)

    subjdir = fs.FSInfo.subjectsdir(dirpath)
    """

    return fs.FSInfo.subjectsdir(os.getenv("SUBJECTS_DIR"))


def paradigms(parname=None, case="upper"):
    """Return paradigm information.
    
    This function has two uses. If called with an empty scope, it will
    return a list of the paradigms inolved in the project. If called with 
    the full name of a paradigm as the first argument, it will return the 
    two-letter code for that paradigm. You may specify whether the paradigm
    code should be returned in upper or lower case using the second argument
    (upper case is default).

    Parameters
    ----------
    parname : string, optional
        full paradigm name (if None, returns the full list of paradigms)
    case : string
        "upper" or "lower" -- Def: upper

    Returns
    -------
    list of full paradigm names or string 
    
    """

    pardict = setup.paradigms

 
    if parname is None:
        return pardict.keys()
    else:
        if case == "lower":
            return pardict[parname].lower()
        elif case == "upper":
            return pardict[parname].upper()
        else:
            raise Exception("Case argument '%s' to "
                            "config.Paradigms not understood." % case) 


def betas(par=None, retval=None):
    """Return information about task regressors.
    
    This function deals with both condition and file names for the 
    first-level regressors.  It takes the name of a paradigm and the 
    type of list to return as parameters.  If asked for "names," it 
    will return the list of condition names.  If asked for "images," 
    it will return the list of image file names associated with task
    betas for that paradigm. If par is None, it will return the full
    conditions dictionary.

    If the hrfconditions variable is set higher than 1, it will add
    n names to the condition list in the format cond-n.  You can also
    control which of the multiple components will be returned (and thus
    involved in the analysis) with the betastoextract variable. Note 
    that this functionality is included for forward compatability, but 
    that it has not yet actually been tested.

    Parameters
    ----------
    par : str
        paradigm
    retval : str
        "images" or "names"

    Returns
    -------
    list or dict
    
    """    

    # Get the elements from the setup function 
    hrfcomponents = setup.hrfcomponents
    betastoextract = setup.betastoextract
    conditions = setup.conditions

    # Return the conditions dictionary and hrfcomponents if scope is empty
    if par is None:
        return conditions, hrfcomponents

    # Check that the paradigm is in the conditions dictionary
    # Exit with a more informative error if it is not
    try:
        dump = conditions[par]
    except KeyError:
        raise Exception("Paradigm '%s' not found in conditions dictionary"
                        % par)

    # Wrap betastoextract in a list if it"s just an int
    if isinstance(betastoextract, int):
        betastoextract = [betastoextract]

    # Initialize filename and multi-component condition name lists
    condimages = []
    mcompnames = []

    # If extracting all beta components, make that list
    if betastoextract == "all" or betastoextract == ["all"]:
        betastoextract = range(1, hrfcomponents + 1)

    # Insert additional component image/names
    for i in range(1,len(conditions[par])+1):
        for j in range(0,hrfcomponents):
            if j+1 in betastoextract:
                # Add the component number to condition names
                mcompnames.append("%s-%02d" % (conditions[par][i-1], j+1))
                num = i + ((i-1)*(hrfcomponents-1)) + j
                # Add the image filename to the image list
                condimages.append("beta_%04d.img" % num)
    
    # Figure out what the function is being asked about and return it
    if retval == "images":
        return condimages
    elif retval == "names" and (hrfcomponents == 1 or betastoextract == [1]):
        return conditions[par]
    elif retval == "names" and hrfcomponents > 1:
        return mcompnames
    else:
        raise Exception("Beta return type \"%s\" not understood" % retval)


def contrasts(par=None, type="con-img", format=".nii"):
    """Return information about contrasts.
    
    This function controls the contrast images used in the analysis.
    It takes the paradigm, image type, and image format as parameters 
    and returns a dictionary mapping contrast shorthand names to image
    file names.

    Parameters
    ----------
    par : str
        Paradigm
    type : str
        "sig", "T-map", "con-img", or "names" -- default: con-img
    format : str
        File extension -- default: .nii

    Returns
    -------
    dictionary

    """

    # Get the specified dict from setup
    contrastdict = setup.contrasts

    # Return the full dict if called with an empty scope
    if par is None:
        return contrastdict

    # Get the dictionary for the paradigm we"re looking at
    contrasts = contrastdict[par]

    # Initialize the dictionaries for file names
    contrasts_sig = {}
    contrasts_tstat = {}
    contrasts_con = {}

    if not format.startswith("."): 
        format = "." + format

    # Iterate through the contrasts and populate the filename dictionaries
    for con in contrasts:
        contrasts_sig[con] = "spmSig_%04d%s" % (contrasts[con], format)
        contrasts_tstat[con] = "spmT_%04d%s" % (contrasts[con], format)
        contrasts_con[con] = "con_%04d%s" % (contrasts[con], format)

    # Get the list of names
    names = []
    connums = contrasts.values()
    connums.sort()
    for num in connums:
        names.append([k for k, v in contrasts.items() if v == num][0])

    # Figure out what type of image the function is being asked about and return
    if type == "sig":
        return contrasts_sig
    elif type == "T-map":
        return contrasts_tstat
    elif type == "con-img":
        return contrasts_con
    elif type == "names":
        return names
    else:
        raise Exception("Image type '%s' " % type +
                        "not understood: use 'T-map', 'sig', or 'con-img'")


def pathspec(imgtype, paradigm=None, subject=None, contrast=None):
    """Return the path to directories containing various first-level components.

    Parameters
    -----------
    imgtype : str
        "beta", "meanfunc", "timecourse," or "contrast"
    paradigm : str
        full paradigm name
    subject : str 
        subject name
    contrast: str
        contrast name

    Returns
    -------
    str : path to image directory or to image

    """
    basepath = setup.basepath
    betapath = setup.betapath
    meanfuncpath = setup.meanfuncpath
    contrastpath = setup.contrastpath
    timecoursepath = setup.timecoursepath
    
    vardict = {"$paradigm" : paradigm,
               "$contrast" : contrast,
               "$subject" : subject}

    imgdict = {"beta": betapath,
               "meanfunc": meanfuncpath,
               "contrast": contrastpath,
               "timecourse": timecoursepath}
    
    varpath = os.path.join(basepath, imgdict[imgtype])

    for var in vardict:
        if var in varpath:
            varpath = varpath.replace(var,vardict[var])

    if imgtype in ["beta", "contrast"]:
        return varpath
    else:
        imgs = glob(varpath)
        if len(imgs) > 1:
            raise SetupError("Found more than one %s image." % imgtype)
        else:
            try:
                return imgs[0]
            except IndexError:
                raise SetupError("Found no %s images." % imgtype)
                

def subjects(group = None, subject = None):
    """Return a list of subjects or subject group membership.
    
    This function controls the subjects and groups involved in the 
    analysis.  It takes either a group or a subject as a parameter.
    If called with an empty scope, it returns a list of all subjects.
    If called with the name of a group, it returns a list of the subjects
    in that group. If called with group = "groups", it returns a list of 
    the group names.  If called with the name of a subject, it will return
    the name of the group that subject is a member of.

    Parameters
    ----------
    group : group name or "groups"
    subject : subject name

    Returns
    -------
    list

    """

    subjects = setup.subjects

    for grp in subjects:
        subjects[grp].sort()
	
    if subject:
        for grp in subjects:
           if subject in subjects[grp]:
              return grp

    if group is None:
        all = []
        for grp in subjects:
	        all = all + subjects[grp]
        return all
    elif group in subjects:
        return subjects[group]
    elif group == "groups":
        return subjects.keys()
    else:
        raise Exception("Group '%s' not found." % group)


def overwrite(filetype=None):
    """Control file overwriting.
    
    Query whether a given filetype should be overwritten if it is found
    to exist at runtime.

    If this filetype is None, the function will return the dictionary

    Parameters
    ----------
    string specifying file type

    Returns
    -------
    boolean where True means "overwrite"
    
    """

    overwrite = setup.overwrite

    if filetype is None:
        return overwrite
    else:
        return overwrite[filetype]
