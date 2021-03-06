"""
This module contains classes with methods that relate to atlas manipulation.

Classes
-------
Atlas              :  Base class with most processing methods

FreesurferAtlas    :  Methods for extraction from Freesurfer volume and surface 
                      atlases in native space

HarvardOxfordAtlas :  Methods for extraction from the Harvard-Oxford probabilistic
                      atlas in standard space

SigSurfAtlas       :  Methods for turning the blobs on a second-level Freesurfer
                      significance map into an atlas

LabelAtlas         :  Methods for the creation of user-defined atlases from
                      Freesurfer surface labels

MaskAtlas          :  Methods for the creation of user-defined atlases from
                      binary mask images in standard space

SphereAtlas        :  Methods for the creation of user-defined atlases from
                      spherical ROIs

Functions
---------
init_atlas         :  Common interface to instantiation of atlas classes

See the docstrings for different classes for more information and usage examples

"""
import os
import re
import sys
import shutil
import subprocess
from glob import glob
from tempfile import mkdtemp

import numpy as np
import scipy.stats as stats
import nibabel as nib

import configinterface as cfg
import source
import treeutils as tree
from exceptions import *
from database import build_database
import core
from core import RoiBase, RoiResult

__all__ = ["Atlas", "FreesurferAtlas", "FSRegister", "LabelAtlas", "SigSurfAtlas",
           "MaskAtlas", "HarvardOxfordAtlas", "SphereAtlas", "init_atlas"]

__module__ = "atlases"

class Atlas(RoiBase):
    """Base atlas class.
    
    See the docstrings of atlas subclasses for usage and examples.
    Subclasses currently offered:

    - FreesurferAtlas
    
    - HarvardOxfordAtlas

    - SigSurfAtlas
    
    - LabelAtlas
    
    - MaskAtlas

    - SphereAtlas [Not quite ready yet]

    """    
    def __init__(self, atlasdict, **kwargs):

        if not cfg.is_setup:
            raise SetupError

        self.roidir = os.path.join(cfg.setup.basepath,"roi")
        self.subjdir = cfg.fssubjdir()

        self.atlasdict = atlasdict
        self.atlasname = atlasdict["atlasname"]
        self.source = atlasdict["source"]
        self.manifold = atlasdict["manifold"]

        if "sourcefiles" in atlasdict:
            self.sourcefiles = atlasdict["sourcefiles"]
            self.sourcenames = atlasdict["sourcenames"]
            self._sourcenames_to_lutdict()

        self._init_paradigm = False
        self._init_subject = False
        self._init_analysis = False
        
        if len(cfg.paradigms()) == 1:
            self.init_paradigm(cfg.paradigms()[0])

        self.__dict__.update(**kwargs)
        if "debug" not in self.__dict__:
            self.debug = False

    def __call__(self, analysis):
        """Calling the atlas object on an analysis will initialize it.

        Parameters
        ----------
        analysis : int, dict, or analysis object

        """
        self.init_analysis(analysis)

    def __str__(self):
        """Provides an easily readable summary of inforamtion about the atlas."""
        repr = ""
        repr = "\n".join((repr, "Name -- %s" % self.atlasname))
        sourcedict = dict(freesurfer="Freesurfer",
                          fsl="Harvard Oxford Atlas",
                          sigsurf="SigSurf",
                          label="Label",
                          mask="Mask",
                          sphere="Sphere")
        repr = "\n".join((repr, "Source -- %s" % sourcedict[self.source]))
        if hasattr(self, "regionnames"):
            names = "Region Names -- %s" % self.regionnames[0]
            for i, name in enumerate(self.regionnames):
                if i: names = "\n".join((names, "                %s" % name))
            repr = "\n".join((repr, names))
        if self._init_subject:
            repr = "\n".join((repr, ""))
            repr = "\n".join((repr, "Subject -- %s" % self.subject))
            if self.manifold == "surface":
                if len(self.iterhemi) == 2:
                    s1 = "s"; s2 = ""
                else:
                    s1 = ""; s2 = "s"
            else:
                s1 = ""; s2 = "s"
            if self._atlas_exists():
                exists = "Yes"
            else:
                exists = "No"
            repr = "\n".join((repr, "Atlas Image%s Exist%s -- %s"%(s1,s2,exists)))
            if self._atlas_exists():
                atlas = ("...%s"
                         % self.atlas.replace(cfg.setup.basepath, "").strip("/"))
                if self.manifold == "surface":
                    repr = "\n".join((repr, "Atlas Image%s:"%s1,
                                      "\t%s"%atlas%self.iterhemi[0]))
                    if len(self.iterhemi) == 2:
                        repr = "\n".join((repr,"\t%s" 
                                          % atlas
                                          % self.iterhemi[1]))
                else:
                    repr = "\n".join((repr, "Atlas Image:","    %s" % atlas))
            if self._init_analysis:
                repr = "\n".join((repr, ""))
                repr = "\n".join((repr, "Analysis -- %s" % self.analysis.name))
                if self._source_exists():
                    exists = "Yes"
                else:
                    exists = "No"
                repr = "\n".join((repr, 
                    "Source Image%s Exist%s -- %s"%(s1,s2,exists)))
                if self._source_exists():
                    source = ("...%s"
                              % self.analysis.source.replace(
                                 cfg.setup.basepath, "").strip())
                    if self.manifold == "surface":
                        source = ("...%s"
                                  % self.analysis.source.replace(
                                     cfg.setup.basepath, "").strip("/"))
                        repr = "\n".join((repr, "Source Image%s:"%s1,
                                          "\t%s"%source%self.iterhemi[0]))
                        if len(self.iterhemi) == 2:
                            repr = "\n".join((repr,"\t%s" 
                                              % source
                                              % self.iterhemi[1]))
                    else:
                        repr = "\n".join((repr, "Source Image:", "    %s" 
                                                 % source))

                if self._extract_exists():
                    exists = "Yes"
                else:
                    exists = "No"
                repr = "\n".join((repr, 
                    "\nExtraction File%s Exist%s -- %s"%(s1,s2,exists)))
                if self._extract_exists():
                    text = ("...%s"
                             % self.functxt.replace(
                               cfg.setup.basepath, "").strip("/"))
                    if self.manifold == "surface":
                        repr = "\n".join((repr, "Extraction Table%s:"%s1,
                                          "\t%s"%text%self.iterhemi[0]))
                        if len(self.iterhemi) == 2:
                            repr = "\n".join((repr,"\t%s" 
                                              % source
                                              % self.iterhemi[1]))
                    else:
                        repr = "\n".join((repr, "Extraction Table:","    %s" 
                                                 % text))
        return repr

    def _atlas_exists(self):
        """Return whether the atlas file exists."""
        if self.manifold == "volume":
            return os.path.isfile(self.atlas)
        else:
            exists = []
            for hemi in self.iterhemi:
                if os.path.isfile(self.atlas % hemi):
                    exists.append(True)
                else:  
                    exists.append(False)
            return all(exists)

    def _source_exists(self):
        """Return whether the atlas file exists."""
        if self.manifold == "volume":
            return os.path.isfile(self.analysis.source)
        else:
            exists = []
            for hemi in self.iterhemi:
                if os.path.isfile(self.analysis.source % hemi):
                    exists.append(True)
                else:  
                    exists.append(False)
            return all(exists)
    def _extract_exists(self):
        """Return whether an extraction text file exists."""
        if self.manifold == "volume":
            return os.path.isfile(self.functxt)
        else:
            exists = []
            for hemi in self.iterhemi:
                if os.path.isfile(self.functxt % hemi):
                    exists.append(True)
                else:  
                    exists.append(False)
            return all(exists)


    # Initialization methods
    def init_paradigm(self, paradigm):
        """Initialize the atlas with a paradigm.
        
        Parameters
        ----------
        paradigm : str
            Full paradigm name
        
        """
        self.paradigm = paradigm
        self._init_paradigm = True


    def init_analysis(self, analysis):
        """Initialize the atlas with an analysis.
        
        Parameters
        ----------
        analysis : int, dict, or Analysis object
        
        """
        if not self._init_subject:
            raise InitError("Subject")

        if isinstance(analysis, dict) or isinstance(analysis, int):
            analysis = source.Analysis(analysis)

        self.analysis = analysis
        if analysis.mask:
            self.mask = True
            mask = source.SigImage(analysis)
            mask.init_subject(self.subject)
            if self.manifold == "surface":
                mask.sigimg = mask.sigsurf
            else:
                mask.sigimg = mask.sigvol
            self.analysis.maskimg = mask.sigimg
            self.analysis.maskthresh = analysis.maskthresh
            self.analysis.masksign = analysis.masksign
        else:
            self.mask = False
        sourceimg = source.init_stat_object(analysis, debug=self.debug)
        sourceimg.init_subject(self.subject)
        if self.manifold == "surface":
            self.analysis.source = sourceimg.extractsurf
        else:
            self.analysis.source = sourceimg.extractvol


        analysisdir = os.path.join(self.roidir, "analysis", 
                                   cfg.projectname(), 
                                   core.get_analysis_name(analysis.dict))
        if self.manifold == "surface":
            self.analysis.dir = os.path.join(analysisdir, self.atlasname, "%s")
        else:
            self.analysis.dir = os.path.join(analysisdir, self.atlasname)

        self.funcstats = os.path.join(self.analysis.dir, "stats", 
                                      "%s.stats" % self.subject)
        self.functxt = os.path.join(self.analysis.dir, "extracttxt",
                                    "%s.txt" % self.subject)
        self.funcvol = os.path.join(self.analysis.dir, "extractvol",
                                    "%s.nii" % self.subject)
        self._init_analysis = True         

    # Operation methods
    def _copy_atlas(self):
        """Copy original atlas file to pyroi atlas tree."""
        result = RoiResult()
        if self.manifold == "volume":
            if not self.debug:
                shutil.copyfile(self.origatlas, self.atlas)  
            return result("cp %s %s" % (self.origatlas, self.atlas))
        else:
            for hemi in self.iterhemi:
                if not self.debug:
                    shutil.copyfile(self.origatlas % hemi,
                                self.atlas % hemi)
                result("cp %s %s" % (self.origatlas % hemi,
                                     self.atlas % hemi))
            return result

    def _inv_copy_annot(self):
        """Copy an annotation from the roi atlas tree to the subjects directory."""
        result = RoiResult()
        for hemi in self.iterhemi:
            target = os.path.join(self.subjdir, self.subject, "label", 
                                  "%s.%s.annot" % (hemi, self.atlasname))
            if not self.debug:
                shutil.copyfile(self.atlas % hemi, target)
            result("cp %s %s" % (self.atlas % hemi, target))
        return result
                                    

    def _sourcenames_to_lutdict(self):                        
        """Turn the list of sourcenames into a lookup dict."""
        self.lutdict = {}
        for i, name in enumerate(self.sourcenames):
            self.lutdict[i+1] = name

    # Display methods
    def display(self, mask=False):
        """Display the atlas.
        
        This method will launch a viewing program that will display
        the atlas.  For native-space atlases, the atlas must be
        initialized with a subject.  Volume atlases are displayed
        with Freeview, while surface atlases are displayed on the
        inflated surface with tksurfer.

        Examples
        --------
        >>> atlas = roi.init_atlas("atlasname", "subj_id")
        >>> atlas.make_atlas()
        >>> atlas.display()

        """
        if not self._init_subject and self.source in ["freesurfer", "label"]:
            raise InitError("Subject")

        if self.manifold == "surface":
            self._surf_display(mask)
        else:
            self._vol_display(mask)
    
    def _surf_display(self, mask=False):
        """Display a surface atlas using tksurfer."""
        if "hemi" not in self.__dict__:
            hemi = "lh"
        else:
            hemi = self.hemi

        cmd = ["tksurfer"]

        cmd.append(self.subject)
        cmd.append(hemi)
        cmd.append("inflated")
        cmd.append("-gray")
        cmd.append("-annot %s" % self.atlas % hemi)
        if mask and self._init_analysis:
            cmd.append("-overlay %s" % self.analysis.maskimg % hemi)
            cmd.append("-fthresh %.1f" % self.analysis.maskthresh)
            cmd.append("-%s" % self.analysis.masksign)
            cmd.append("-fmax %.1f" % (0.1 + self.analysis.maskthresh))

        if self.debug:
            print " ".join(cmd)
        else:
            subprocess.call(cmd) 

    def _vol_display(self, mask=False):
        """Display a volume atlas using Freeview."""
        cmd = ["freeview"]
        cmd.append("-v")
        if self.atlasdict["source"] == "freesurfer":
            anat = os.path.join(self.subjdir, self.subject, "mri", "orig.mgz")
        else:
            anat = os.path.join(os.getenv("FSLDIR"), "data", "standard",
                                "avg152T1.nii.gz")
        cmd.append("%s:%s" % (anat, "colormap=grayscale"))
        cmd.append("%s:colormap=lut:lut=%s:opacity=.5" % (self.atlas, self.lutfile))
        if mask and self._init_analysis:
            thresh = [i + self.analysis.maskthresh for i in [0., 0.001, 0.002]]
            cmd.append("%s:colormap=heat:heatscale=%.3f,%.3f,%.3f"
                       %tuple([self.analysis.maskimg] + thresh))

        if self.debug:
            print " ".join(cmd)
        else:
            subprocess.call(cmd)

    def check_registration(self):
        """Open a tkregister2 session to check registration"""
        if not self._init_subject:
            raise InitError("Subject")
        
        cmd = ["tkregister2"]

        cmd.append("--mov %s" % cfg.pathspec("meanfunc", 
                                             self.analysis.paradigm, 
                                             self.subject, self.subjgroup))
        cmd.append("--reg %s" % self.regmat)
        cmd.append("--surf")

        if self.debug:
            print " ".join(cmd)
        else:
            subprocess.call(cmd)
        
    
    def group_make_atlas(self, subjects=None, reg=1, gen_new_atlas=False):
        """Run atlas preprocessing steps for a list of subjects.
        
        Prerequisite
        ------------
        For native space atlases, the paradigm has to be initialized.  
        This is uneccesary for standard space atlases.

        Parameters
        ----------
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the full subject list from config if ommitted.
        reg : int, optional
            See make_atlas() docstring for more info
            0 : do not create registration matrices
            1 : create registration matrices if they do not exist -- default
            2 : create or overwrite registration matricies
        gen_new_atlas : bool, optional
            An average surface significance map only needs to be analyzed 
            for clusters once.  By default, if the surfcluster summary file
            is found, this method will skip that step.  To force  a new
            cluster summary table to be made, set to true.  
        
        Returns
        -------
        result : RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        if self.source == "standard":
            result(self.make_atlas(reg))
        else:
            for i, subject in enumerate(subjects):
                self.init_subject(subject)
                if self.source != "sigsurf":
                    res = self.make_atlas(reg)
                else:
                    if not i:
                        gen_new_atlas = gen_new_atlas
                    else:
                        gen_new_atlas = False
                    res = self.make_atlas(reg, gen_new_atlas=gen_new_atlas)
                print res
                result(res)
        return result


    def _adj_binary_segvol(self, segnum):
        """Adjust the segmentation value of a binary mask image."""
        cmd = ["mri_concat"]

        cmd.append("--i %s"%self.sourcefiles[segnum-1])
        output = os.path.join(
            self.tempdir, "adj-%s"%os.path.split(self.sourcefiles[segnum-1])[1])
        self.tempvols.append(output)
        cmd.append("--o %s"%output)
        cmd.append("--mul %d"%segnum)

        return self._run(cmd)

    def _combine_segvols(self):
        """Combine adjusted segvols into one atlas."""
        cmd = ["mri_concat"]

        for vol in self.tempvols:
            cmd.append("--i %s"%vol)
        cmd.append("--o %s"%self.atlas)
        cmd.append("--combine")

        return self._run(cmd)

    def _surfcluster(self):
        """Run mri_surfcluster to get a list of significant labels."""

        cmd = ["mri_surfcluster"]

        cmd.append("--subject fsaverage")
        cmd.append("--hemi %s" % self.hemi)
        cmd.append("--in %s" % self.sourcefile)
        cmd.append("--cortex")
        cmd.append("--annot aparc")
        cmd.append("--olab %s" % self.surfclusterlab) 
        cmd.append("--sum %s" % self.surfclustersum)
        if self.threshtype == "fdr":
            cmd.append("--fdr %.3f" % self.threshold)
        else:
            cmd.append("--thmin %.3f" % self.threshold)

        return self._run(cmd)
    
    def _get_atlas_info_from_sum(self):
        """Parse a surfcluster summary file and get label names/files."""
        if not os.path.isfile(self.surfclustersum):
            return "%s does not exist" % self.surfclustersum
        sumtable = np.genfromtxt(self.surfclustersum, str)
        roihash = {}
        self.sourcenames = []
        self.sourcefiles = []
        for row in sumtable:
            if int(row[7]) >= self.minsize:
                roiname = row[8]
                if roiname in roihash:
                    roihash[roiname] += 1
                    roiname = "%s-%d" % (roiname, roihash[roiname])
                else:
                    roihash[roiname] = 1
                self.sourcenames.append("%s_%s" % (self.hemi, roiname))
                self.sourcefiles.append(
                    os.path.join(self.sourcedir, "%s_%s-%.4d.label" 
                                 % (self.hemi, self.atlasname, int(row[0]))))
        self._sourcenames_to_lutdict()
        self.regions = {}
        self.regions[self.hemi] = self.lutdict.keys()
        self.all_regions = {}
        self.all_regions[self.hemi] = self.lutdict.keys()
            
    def _copy_labels(self):
        """Copy labels from the sourcedir to the roi atlas hierarchy."""
        result = RoiResult()
        for i, labelfile in enumerate(self.sourcefiles):
            shutil.copyfile(labelfile.replace("$subject", self.subject),
                            os.path.join(self.basedir, self.subject, self.atlasname,
                                         self.sourcenames[i] + ".label"))
            result("cp %s %s" % (labelfile.replace("$subject", self.subject),
                                 os.path.join(self.basedir, self.subject,
                                              self.atlasname,
                                              self.sourcenames[i] + ".label")))
        return result

    def _resample_labels(self):
        """Resample label files from fsaverage surface to native surfaces."""
        res = RoiResult()
        subjlevel = bool(self.sourcelevel == "subject")
        for i, label in enumerate(self.sourcefiles):
            if subjlevel:
                label = label.replace("$subject", self.subject)

            cmd = ["mri_label2label"]

            cmd.append("--srcsubject fsaverage")
            cmd.append("--srclabel %s"  % label)
            cmd.append("--trgsubject %s" % self.subject)
            cmd.append("--hemi %s" % self.hemi)
            cmd.append("--regmethod surface")
            cmd.append("--trglabel %s" 
                       % os.path.join(self.atlasdir,
                       "%s.label" % self.sourcenames[i]))

            result = self._run(cmd)
            res(result)      

        return res

    def _gen_annotation(self):
        """Create an annotation from a list of labels."""
        if os.path.isfile(self.origatlas % self.hemi) and not self.debug:
            os.remove(self.origatlas % self.hemi) 
        cmd = ["mris_label2annot"]

        cmd.append("--s %s" % self.subject)
        cmd.append("--hemi %s" % self.hemi)
        cmd.append("--ctab %s" % self.lutfile)
        cmd.append("--a %s" % self.atlasname)
        for label in self.sourcenames:
            cmd.append("--l %s" % os.path.join(self.atlasdir, "%s.label" % label))

        res = self._run(cmd)

        try:
            res(self._copy_atlas())
        except IOError:
            res("IOError: Atlas copy failed")

        return res
    
    def _write_lut(self):
        """Write a look up table to the roi atlas directory."""
        if self.debug:
            return ""
        lutfile = open(self.lutfile, "w")
        for id, name in self.lutdict.items():
            lutfile.write("%d\t%s\t\t\t" % (id, name))
            for color in np.random.randint(0, 256, 3):
                lutfile.write("%d\t" % color)
            lutfile.write("0\n")

        lutfile.close()
        return RoiResult("Writing %s" % self.lutfile)

    def _resample(self):
        """Resample a freesurfer volume atlas into functional space."""
        cmd = ["mri_vol2vol"]
        
        cmd.append("--mov %s"%self.meanfuncimg)
        cmd.append("--targ %s"%self.origatlas)
        cmd.append("--reg %s"%self.regmat)
        cmd.append("--inv")
        cmd.append("--interp nearest")
        cmd.append("--o %s"%self.atlas)

        return self._run(cmd)

    def _write_mask(self):
        """Turn an atlas into a binary mask volume."""
        cmd = ["mri_binarize"]

        cmd.extend(["--i %s" % self.atlas,
                    "--o %s" % self.mask_image])
        for id in self.regions:
            cmd.append("--match %d" % id)

        return(self._run(cmd))
                    
    def _stats(self):
        """Generate a summary of voxel/vertex counts for all regions in an atlas."""
        if self.manifold == "volume":
            return self._vol_stats()
        else:
            results = RoiResult()
            for hemi in self.iterhemi:
                res = self._surf_stats(hemi)
                results(res) 
            return results

    def _surf_stats(self, hemi):
        """Generate stats for a surface atlas."""
        cmd = ["mri_segstats"]

        cmd.append("--annot %s %s %s" % (self.subject, hemi, self.atlasname))
        cmd.append("--sum %s" % self.statsfile % hemi)
        cmd.append("--ctab %s" % self.lutfile)
        ids = self.all_regions[hemi]
        ids.sort()
        for id in ids:
            cmd.append("--id %d" % id)

        return self._run(cmd)

    def _vol_stats(self):
        """Generate stats for a volume atlas."""
        cmd = ["mri_segstats"]

        cmd.append("--seg %s"%self.atlas)
        cmd.append("--i %s"%self.atlas)
        ids = self.all_regions
        ids.sort()
        for id in ids:
            cmd.append("--id %d"%id)
        cmd.append("--ctab %s"%self.lutfile)
        cmd.append("--sum %s"%self.statsfile)

        return self._run(cmd)

    def prepare_source_images(self, analysis=None, reg=1):
        """Prepare the functional and statistical images for extraction.
        
        An analysis must be initialized in the atlas

        Parameters
        ----------
        analysis : int, dict, or Analysis object, optional
            Analysis to extract from.  Runs init_analysis() internally.
        reg : int, optional
            This option controls whether Freesurfer's bbregister program will 
            be run to register the mean functional volume to the anatomical so
            statistical images can be sampled to the surface.  This is only
            relevant for surface atlases.  The option has three settings:
            0 : do not create registration matrix
            1 : create registration matrix if it does not exist -- default
            2 : create or overwrite registration matrix

        Returns
        -------
        RoiResult object

        """
        if analysis is not None:
            self.init_analysis(analysis)
        if not self._init_analysis:
            raise InitError("Analysis")
        if not reg:
            if self.manifold == "surface" :
                if not os.path.isfile(self.regmat) and not reg:
                    print ("\nRegistration matrix not found for %s %s to orig."
                           "\nCall method with a different `reg` setting to create."
                           % (self.subject, self.analysis.paradigm))
                    return
                elif self.mask:
                    mask = source.SigImage(self.analysis)
                    mask.init_subject(self.subject)
                    if not os.path.isfile(mask.regmat) and not reg:
                        print ("\nRegistration matrix not found for %s %s to orig."
                               "\nCall method with a different `reg` setting to create."
                               % (self.subject, mask.analysis.maskpar))
                        return
                        

        res = RoiResult()
        if self.manifold == "surface":
            sourcereg = FSRegister(self.analysis.paradigm, self.subject, debug=self.debug)
            if reg==2 or (reg==1 and not os.path.isfile(sourcereg.regmat)):
                res(sourcereg.register())
                if self.mask and self.analysis.maskpar != self.analysis.paradigm:
                    maskreg = FSRegister(self.analysis.maskpar, self.subject, debug=self.debug)
                    if reg==2 or (reg==1 and not os.path.isfile(maskreg.regmat)):
                        res(maskreg.register())
        extractvols = source.init_stat_object(self.analysis, debug=self.debug)
        extractvols.init_subject(self.subject)
        if not self.analysis.extract == "timecourse":
            res(extractvols.concatenate())
        if self.manifold == "surface":
            res(extractvols.sample_to_surface())
        if self.mask:
            tstat = source.TStatImage(self.analysis, debug=self.debug)
            tstat.init_subject(self.subject)
            res(tstat.convert_to_sig())
            if self.manifold == "surface":
                sig = source.SigImage(self.analysis, debug=self.debug)
                sig.init_subject(self.subject)
                res(sig.sample_to_surface())

        return res

    def group_prepare_source_images(self, analysis, subjects=None, reg=1):
        """Prepare the source images for a group.

        Parameters
        ----------
        analysis : analysis number, dict or Analysis object
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the full subject list from config if ommitted.
        reg : int, optional
            See prepare_source_images() docstring for more info.
            0 : do not create registration matrices
            1 : create registration matrices if they do not exist -- default
            2 : create or overwrite registration matricies

        Returns
        -------
        RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        for subject in subjects:
            self.init_subject(subject)
            res = self.prepare_source_images(analysis, reg=reg)
            print res
            result(res)

        return result

    def extract(self, analysis=None):
        """Extract average functional data from select regions in an atlas.
        
        This prints a text file with the average statistic for each region
        to the $main_dir/roi/analysis/ directory structure.  It also saves
        a binary "volume" where each voxel represents a region in the atlas.
        See the database functions to collect this data for statistical 
        analysis.

        Parameters
        ----------
        analysis : int, dict, or Analysis object, optional
            Analysis to extract from.  Runs init_analysis() internally.

        Returns
        -------
        RoiResult object.
        
        Note
        ----
        Currently, this just averages the voxelwise statistics over all voxels
        considered to be in each region, after applying a functional mask (if
        included in the analysis parameters).  If a mask is applied, it will
        also generate a count of how many voxels/vertices were included in the
        final ROI.

        """
        if not self._init_analysis:
            raise InitError("Analysis")
        elif not self._atlas_exists() and not self.debug:
            raise PreprocessError("The atlas")
        elif not self._source_exists() and not self.debug:
            raise PreprocessError("The source")

        if self.manifold == "volume":
            return self._vol_extract()
        else:
            results = RoiResult()
            for hemi in self.iterhemi:
                res = self._surf_extract(hemi)
                results(res)
            return results

    def _surf_extract(self, hemi):
        """Internal function to extract from a surface."""
        cmd = ["mri_segstats"]

        cmd.append("--annot %s %s %s"%(self.subject, hemi, self.fname[:-6]))
        cmd.append("--i %s"%self.analysis.source%hemi)
        ids = self.regions[hemi]
        ids.sort()
        for id in ids:
            cmd.append("--id %d"%id)
        if self.mask:
            cmd.append("--mask %s"%self.analysis.maskimg%hemi)
            cmd.append("--maskthresh %.1d"%self.analysis.maskthresh)
            cmd.append("--masksign %s"%self.analysis.masksign)
        cmd.append("--avgwf %s"%self.functxt%hemi)
        cmd.append("--avgwfvol %s"%self.funcvol%hemi)
        cmd.append("--sum %s"%self.funcstats%hemi)

        return self._run(cmd)

    def _vol_extract(self):
        """Internal function to extract from a volume."""
        cmd = ["mri_segstats"]

        cmd.append("--seg %s"%self.atlas)
        cmd.append("--i %s"%self.analysis.source)
        ids = self.regions
        ids.sort()
        for id in ids:
            cmd.append("--id %d"%id)
        if self.mask:
            cmd.append("--mask %s"%self.analysis.maskimg)
            cmd.append("--maskthresh %s"%self.analysis.maskthresh)
            cmd.append("--masksign %s"%self.analysis.masksign)
        cmd.append("--avgwf %s"%self.functxt)
        cmd.append("--avgwfvol %s"%self.funcvol)
        cmd.append("--sum %s"%self.funcstats)

        return self._run(cmd)

    def group_extract(self, analysis, subjects=None):
        """Extract functional data for a group of subjects.
        
        See the docstring for the extract() method for more information.
        The database function build_database() is automatically run after
        all data is extracted.
        
        Parameters
        ----------
        analysis : Analysis object or dict
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the config setup module.
           
        Returns
        -------
        RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        if isinstance(analysis, dict) or isinstance(analysis, int):
            analysis = source.Analysis(analysis)
        result = RoiResult()
        for subj in subjects:
            self.init_paradigm(analysis.paradigm)
            self.init_subject(subj)
            self.init_analysis(analysis)
            res = self.extract()
            print res
            result(res)
        if not self.debug:
            res=build_database(self.atlasname, self.analysis.dict, subjects)
            print res
            result(res)
        return result

    def process(self, subject, analysis, force=False):
        """Process a subject up through extraction.
        
        Parameters
        ----------
        subject : str
            Subject ID
        analysis : int
            Analysis index
        force : bool, optional
            Force overwriting of the files the processing methods create 
            if they are found to exist.  False by default.

        Returns
        -------
        RoiResult object

        """
        if isinstance(analysis, dict) or isinstance(analysis, int):
            analysis = source.Analysis(analysis)
        self.init_paradigm(analysis.paradigm)
        self.init_subject(subject)
        result = RoiResult()
        if force or not self._atlas_exists():
            result(self.make_atlas())
        self.init_analysis(analysis)
        if force or not self._source_exists():
            result(self.prepare_source_images())
        if force or not self._extract_exists():
            result(self.extract())
        return result

    def group_process(self, analysis, subjects=None, force=False):
        """Process a group up through extraction.
        
        Parameters
        ----------
        analysis : int
            Analysis index
        subjects : None, string or list
            If None, runs all subjects defined in the config file.  If a
            string, runs the group defined by that name.  If a list, runs
            the each subject defined in that list.  None by default.
        force : bool, optional
            Force overwriting of the files the processing methods create 
            if they are found to exist.  False by default.

        Returns
        -------
        RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        if isinstance(analysis, dict) or isinstance(analysis, int):
            analysis = source.Analysis(analysis)
        result = RoiResult()
        for subj in subjects:
            res = self.process(subj, analysis, force)
            print res
            result(res)
        if not self.debug:
            res=build_database(self.atlasname, self.analysis.dict, subjects)
            print res
            result(res)
        return result
            
class FreesurferAtlas(Atlas):
    """Class for Freesurfer atlases.

    Examples
    --------
    
    Single Subject:
    
    >>> aseg = roi.FreesurferAtlas("aseg", "par_name", "subj_id")
    >>> res = aseg.make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> aseg(analysis)
    >>> aseg.prepare_source_images()
    >>> res = aseg.extract()

    Group:

    >>> aseg = roi.FreesurferAtlas("aseg", "par_name")
    >>> res = aseg.group_make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> res = aseg.group_prepare_source_images(analysis)
    >>> res = aseg.group_extract(analysis)

    Atlas Information
    -----------------
    The FreesurferAtlas class can be used for the Freesurfer aseg (automatic
    subcortical segmentation) or either flavour of aparc (automatic cortical
    parcellation).  In theory, any "Freesurfer style" atlas should work with
    this class.  Custom atlases are not yet officially implemented in the setup
    module, but it should be possible to hack together a working atlas object.

    If you want to extract from ROIs defined by Freesurfer labels (e.g, ROIs
    drawn around activation blobs), see the LabelAtlas class.
    
    Anatomical data must have been preprocessed in Freesurfer (with recon-all)
    to use this class.  When using cortical atlases, functional/statistical 
    volumes are automatically sampled onto the reconstructed cortical surface.

    References
    ----------
    Fischl, B., D.H. Salat, E. Busa, M. Albert, M. Dieterich, C. Haselgrove,
        A. van der Kouwe, R. Killiany, D. Kennedy, S. Klaveness, A. Montillo,
        N. Makris, B. Rosen, and A.M. Dale, (2002).  Whole Brain Segmentation:
        Automated Labeling of Neuroanatomical Structures in the Human Brain,  
        Neuron, 33:341-355.     
    Desikan, R.S., F. Segonne, B. Fischl, B.T. Quinn, B.C. Dickerson, D. 
        Blacker, R.L. Buckner, A.M. Dale, R.P. Maguire, B.T. Hyman, M.S. 
        Albert, and R.J. Killiany, (2006).  An automated labeling system 
        for subdividing the human cerebral cortex on MRI scans into gyral 
        based regions of interest,  NeuroImage, 31(3):968-80.  
    Destrieux C., B. Fischl, A. Dale, E. Halgren, (2010).  Automatic parcel-
        lation of human cortical gyri and sulci using standard anatomical 
        nomenclature. Neuroimage, 2010 [Epub ahead of print] 
        
    """
    def __init__(self, atlas, paradigm=None, subject=None, **kwargs):
        """
        Parameters
        ----------
        atlas : str or dict
            The name of an atlas defined in your setup module, or a dictionary
            of atlas parameters.
        paradigm : str, optional
            The name of a paradigm to initialize the atlas for. 
        subject : str, optional
            The name of a subject to initialize the atlas for.  
        """
        if isinstance(atlas, str):
            atlasdict = cfg.atlases(atlas)
        else:
            atlasdict = atlas

        Atlas.__init__(self, atlasdict, **kwargs)

        if self.manifold == "surface":
            self.iterhemi = ["lh","rh"]
        self.fname = atlasdict["fname"]
        self.space = "native"
        self.lutfile = os.path.join(os.getenv("FREESURFER_HOME"), 
                                    "FreeSurferColorLUT.txt")

        dictdict = {"aseg.mgz": "aseg-lut.txt",
                    "aparc.annot": "aparc-lut.txt",
                    "aparc.a2009s.annot": "aparc.a2009s-lut.txt"}
        datadir = os.path.join(os.path.split(__file__)[0], 
                               os.path.pardir, "data", "Freesurfer")
        dictfile = os.path.join(datadir, dictdict[self.fname])
        lutarray = np.genfromtxt(dictfile, str)
        self.lutdict = {}
        for row in lutarray:
            self.lutdict[int(row[0])] = row[1]
        
        convtable = {1:(10,49), 2:(11,50), 3:(12,51), 4:(13,52), 
                     5:(17,53), 6:(18,54), 7:(26,58), 8:(28,60)}
        if self.fname == "aseg.mgz":
            self.regions = ([convtable[id][0] for id in self.atlasdict["regions"]] + 
                            [convtable[id][1] for id in self.atlasdict["regions"]])
            self.all_regions = self.lutdict.keys()
            self.regionnames = [self.lutdict[id] for id in self.regions]
        else:
            self.regions = {}
            self.all_regions = {}
            if self.fname == "aparc.annot":
                self.regions["lh"] = [1000 + id for id in self.atlasdict["regions"]]
                self.regions["rh"] = [2000 + id for id in self.atlasdict["regions"]]
                self.all_regions["lh"] = \
                    [id for id in self.lutdict.keys() if id < 2000]
                self.all_regions["rh"] = \
                    [id for id in self.lutdict.keys() if id >= 2000]
                self.regionnames = ([self.lutdict[id] for id in self.regions['lh']] + 
                                    [self.lutdict[id] for id in self.regions['rh']]) 
            else:
                self.regions["lh"] = self.atlasdict["regions"]
                self.regions["rh"] = self.atlasdict["regions"]
                self.all_regions["lh"] = self.lutdict.keys()
                self.all_regions["rh"] = self.lutdict.keys()
                self.regionnames = \
                    (["lh-" + self.lutdict[id] for id in self.atlasdict["regions"]] +
                     ["rh-" + self.lutdict[id] for id in self.atlasdict["regions"]])
        self.regionnames.sort()                                


        self.basedir = os.path.join(self.roidir, "atlases", "freesurfer")

        if paradigm is not None: self.init_paradigm(paradigm)
        if subject is not None: self.init_subject(subject)

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the atlas for a subject"""
        if not self._init_paradigm:
            raise InitError("Paradigm")

        if self.atlasname == "register":
            tree.make_reg_tree()
        else:
            tree.make_fs_atlas_tree(self.atlasname, subject)
        
        self.subject = subject
        self.subjgroup = cfg.subjects(subject=subject)
        if self.manifold == "surface":
            pardir = ""
            fname = "%s." + self.fname
            atlasname = "%s." + self.atlasname
            origdir = "label"
            ext = "annot"
        else:
            pardir = self.paradigm
            fname = self.fname
            atlasname = self.atlasname
            origdir = "mri"
            ext = "mgz"

        self._regtreepath = os.path.join(self.roidir, "reg", self.paradigm,
                                        subject, "func2orig.dat")
        self.meanfuncimg = cfg.pathspec("meanfunc", self.paradigm,
                                        self.subject, self.subjgroup)
        cfgreg = cfg.pathspec("regmat", self.paradigm, self.subject, self.subjgroup)
        if cfgreg:
            self.regmat = cfgreg
        else: 
            self.regmat = self._regtreepath

        if self.manifold != "reg":
            self.origatlas = os.path.join(self.subjdir, subject, origdir, fname)
            self.atlas = os.path.join(self.basedir, self.manifold, pardir, subject,
                                      self.atlasname, "%s.%s" % (atlasname, ext))
            self.statsfile = os.path.join(self.basedir, self.manifold, pardir,
                                          subject, self.atlasname,
                                          "%s.stats" % atlasname)
            self.mask_image = os.path.join(self.basedir, self.manifold, pardir, subject,
                                           self.atlasname, "%s_mask.%s" % (atlasname, ext))

            self._init_subject = True

    def make_atlas(self, reg=1):
        """Run the neccessary preprocessing steps to make a create the atlas image.
        
        Parameters
        ----------
        reg : int, optional
            This option controls whether Freesurfer's bbregister program will 
            be run to register the mean functional volume to the anatomical.  
            This is only relevant for Freesurfer atlases.  It has three settings:
            0 : do not create registration matrix
            1 : create registration matrix if it does not exist -- default
            2 : create or overwrite registration matrix

        Notes
        -----
        For volume atlases, the original image, which is in Freesurfer anatomical
        space (1mm isotropic voxels) is resampled into native functional space
        by inverting the transformation matrix used to map functional images to
        the anatomical models.  A mask volume is also created by binarizing the
        atlas image so that all voxels within regions specified in the region list
        of the config dictionary have a value of 1 and other voxels have a value of
        0.  This mask image can be used for small-volume correction, MVPA analysis,
        or any other situation that requires such a mask.

        Surface atlases do not have to undergo any processing steps to be used to
        define ROIs for extraction, but the .annot file is copied over to the roi
        directory tree.  

        Returns
        -------
        result : RoiResult object
            
        """
        result = RoiResult()
        if self.space == "native" and not self._init_subject:
            raise InitError("Subject")
        if not os.path.isfile(self.regmat) and not reg:
            print ("\nRegistration matrix not found for %s."
                   "\nCall method with a different setting for the `reg` argument "
                   "to create."
                   % self.subject)
            return
        result = RoiResult()
        if self.manifold == "volume":
            if reg==2 or (reg==1 and not os.path.isfile(self.regmat)):
                reg = FSRegister(debug=self.debug)
                reg.init_paradigm(self.paradigm)
                reg.init_subject(self.subject)
                result(reg.register())
            result(self._resample())
        else:
            result(self._copy_atlas())
            result(self._inv_copy_annot())
        if self._atlas_exists:
            result(self._stats())
            if self.manifold == "volume":
                result(self._write_mask())
        return result

    def group_make_atlas(self, subjects=None, reg=1):
        """Run atlas preprocessing steps for a list of subjects.
        
        Parameters
        ----------
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the full subject list from config if ommitted.
        reg : int, optional
            See make_atlas() docstring for more info
            0 : do not create registration matrices
            1 : create registration matrices if they do not exist -- default
            2 : create or overwrite registration matricies
        
        Returns
        -------
        result : RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        for i, subject in enumerate(subjects):
            self.init_subject(subject)
            res = self.make_atlas(reg)
            print res
            result(res)
        return result

class FSRegister(FreesurferAtlas):
    """Extension of FreesurferAtlas for intramodal registration.
    
    This class is used internally by the make_atlas() and prepare_source_image()
    methods, so it is usually not neccesary for a user to interface with it.
    The register() method runs the Freesurfer program bbregister, which can
    internally find a linear transform matrix with either FSL FLIRT, the SPM
    coregister routine, or from header geometry.  It uses FLIRT by default.

    Examples
    --------
    >>> reg = roi.FSRegister("par_name", "subj_id")
    >>> reg.register()

    """
    def __init__(self, paradigm=None, subject=None, **kwargs):

        tree.make_reg_tree()
        self.roidir = os.path.join(cfg.setup.basepath, "roi")
        subjdir = cfg.fssubjdir()
        
        self.manifold = "reg"
        self.fname = "orig.mgz"
        self.atlasname = "register"

        self.basedir = os.path.join(self.roidir, "atlases", "reg")
        self.subjdir = subjdir
        
        self.__dict__.update(**kwargs)
        if "debug" not in self.__dict__:
            self.debug = False
        
        if paradigm is not None: self.init_paradigm(paradigm)
        if subject is not None: self.init_subject(subject)

    # Processing methods
    def register(self, method="fsl"):
        """Register functional space to Freesurfer original atlas space.
        
        Parameters
        ----------
        method : str, optional
            Specifiy the initial registration method.  Options are 'fsl',
            'spm', or 'header'.  Defaults to 'fsl'.

        Returns
        -------
        RoiResult object

        """
        cmd = ["bbregister"]

        cmd.append("--s %s"%self.subject)
        cmd.append("--mov %s"%self.meanfuncimg)
        cmd.append("--bold")
        cmd.append("--reg %s"%self._regtreepath)
        cmd.append("--init-%s"%method)

        return self._run(cmd)

    def group_register(self, subjects=None, method="fsl"):
        """Register functional space to Freesurfer original atlas space for a group.
        
        Parameters
        ----------
        subjects : str or list, optional
            If None: runs the full subject list from the config file -- default
            If str: runs analysis for that group as defined in config file
            If list: runs analysis on the subjects in the list
        method : str, optional
            Specifiy the initial registration method.  Options are 'fsl',
            'spm', or 'header'.  Defaults to 'fsl'.

        Returns
        -------
        RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        for subj in subjects:
            self.init_subject(subjects)
            res = self.register(method)
            result(res)

        return result


class HarvardOxfordAtlas(Atlas):
    """Class for the HarvardOxford atlas included with FSL.   

    Examples
    --------

    Single Subject:
    
    >>> fslatlas = roi.init_atlas("fsl_atlas")
    >>> res = fslatlas.prepare_source_images(1)
    >>> res = fslatlas.extract(1)
    
    Group:
    
    >>> fslatlas = roi.HarvardOxfordAtlas("fsl")
    >>> res = fslatlas.group_prepare_source_images(1)
    >>> res = fslatlas.group_extract(1)

    Atlas Information
    -----------------
    The HarvardOxford Atlas is a probabilistic standard-space atlas 
    drawn from data collected at the Harvard Center for Morphometric
    Analysis and Oxford's FMRIB.  Two versions are provided with PyROI,
    corresponding to thresholding the probabilistic atlas at 25% or 50%.
    See http://www.fmrib.ox.ac.uk/fsl/fslview/atlas-descriptions.html
    for more information.  The FSL volumes were modified slightly using
    scripts written by Russ Poldrack to give different segmentation 
    values for left and right hemisphere structures.

    """
    def __init__(self, atlas, subject=None, **kwargs):
        """
        Parameters
        ----------
        atlas : str or dict
            The name of an atlas defined in your setup module, or a 
            dictionary of atlas parameters.
        subject : str, optional
            The name of a subject to initialize the atlas for. 

        """
        if isinstance(atlas, str):
            atlasdict = cfg.atlases(atlas)
        else:
            atlasdict = atlas

        Atlas.__init__(self, atlasdict, **kwargs)
     
        self.space = "standard"
        self.thresh = atlasdict["probthresh"]
        datadir = os.path.abspath(os.path.join(os.path.split(__file__)[0], 
                                               os.path.pardir, "data", "HarvardOxford"))
        filestem = "HarvardOxford-%d" % self.thresh
        self.atlas = os.path.join(datadir, "%s.nii" % filestem)
        self.lutfile = os.path.join(datadir, "HarvardOxford-LUT.txt")
        lutarray = np.genfromtxt(self.lutfile, str)
        self.lutdict = {}
        for row in lutarray:
            self.lutdict[int(row[0])] = row[1]
        self.statsfile = os.path.join(datadir, "%s.stats" % filestem) 
        self.regions = atlasdict["regions"] + [id + 55 for id in atlasdict["regions"]]
        self.regions.sort()

        self.regionnames = [self.lutdict[id] for id in self.regions]
        self.regionnames.sort()                                

        if subject is not None: self.init_subject(subject)

    def init_subject(self, subject):
       """Initialize the atlas for a subject"""
       self.subject = subject
   
       self._init_subject = True

    def make_atlas(self):
        """Simply returns an empty RoiResult object.
        
        No processing is needed for the Harvard Oxford atlas.
        
        """
        return RoiResult(None)


class SigSurfAtlas(Atlas):
    """Atlas made from a second level sig map on the average surface.
    
    Examples
    --------

    Single Subject:
    
    >>> surfatlas = roi.init_atlas("surfatlas", "subj_id")
    >>> res = surfatlas.make_atlas()
    >>> res = fslatlas.prepare_source_images(1)
    >>> res = fslatlas.extract(1)
    
    Group:
    
    >>> surfatlas = roi.init_atlas("surfatlas", "subj_id")
    >>> res = surfatlas.group_prepare_source_images(1)
    >>> res = surfatlas.group_extract(1)

    Atlas Information
    -----------------
    A SigSurf atlas is created by taking a surface significance map 
    in fsaverage space, thresholding it (possibly with FDR correction),
    and turning the contiguous blobs that remain above threshold into
    regions of interest.  This obviates manually creating labels to
    extract from ROIs defined by second-level analyses.
    
    """
    def __init__(self, atlas, subject=None, **kwargs):
        """
        Parameters
        ----------
        atlas : str or dict
            The name of an atlas defined in your setup module, or a 
            dictionary of atlas parameters.
        subject : str, optional
            The name of a subject to initialize the atlas for. 

        """
        if isinstance(atlas, str):
            atlasdict = cfg.atlases(atlas)
        else:
            atlasdict = atlas
        
        Atlas.__init__(self, atlasdict, **kwargs)
        
        tree.make_sigsurf_atlas_tree()

        self.space = "native"
        self.hemi = self.atlasdict["hemi"]
        self.iterhemi = [self.hemi]
        self.fname = "%s.annot" % self.atlasname
        self.sourcefile = self.atlasdict["file"]
        self.threshtype = self.atlasdict["thresh"][0]
        self.threshold = self.atlasdict["thresh"][1]
        self.minsize = self.atlasdict["minsize"]
        self.sourcelevel = "group"

        self.basedir = os.path.join(self.roidir, "atlases", "sigsurf", 
                                    cfg.projectname())
        self.lutfile = os.path.join(
            self.basedir, "lookup_tables", "%s.lut" % self.atlasname)
        self.sourcedir = os.path.join(self.basedir, "source", self.atlasname)
        self.surfclustersum = os.path.join(self.sourcedir, 
                                           "%s.sum" % self.atlasname)
        self.surfclusterlab = os.path.join(self.sourcedir,
                                           "%s_%s" % (self.hemi, self.atlasname))

        if os.path.isfile(self.surfclustersum):
            self._get_atlas_info_from_sum()

        if subject is not None: self.init_subject(subject)

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the atlas for a subject"""
        self.subject = subject
        self.atlasdir = os.path.join(self.basedir, subject, self.atlasname)
        self.statsfile = os.path.join(self.atlasdir,
                                      "%s." + self.atlasname + ".stats")
        self.atlas = os.path.join(self.atlasdir, "%s." + self.fname)
        self.origatlas = os.path.join(self.subjdir, subject, 
                                      "label", "%s." + self.fname)
        
        self._init_subject = True

    def make_atlas(self, gen_new_atlas=False):
        """Turn a second level sig image into an atlas image.

        Parameters
        ----------
        gen_new_atlas : bool, optional
            An average surface significance map only needs to be analyzed 
            for clusters once.  By default, if the surfcluster summary file
            is found, this method will skip that step.  To force  a new
            cluster summary table to be made, set to true.  
        
        Returns
        -------
        result : RoiResult object

        """
        result = RoiResult()
        if not os.path.isfile(self.surfclustersum) or gen_new_atlas:
            result(self._surfcluster())
            self._get_atlas_info_from_sum()
            result(self._write_lut())
        else:
            self._get_atlas_info_from_sum()
        result(self._resample_labels())
        result(self._gen_annotation())
        if self._atlas_exists():
            result(self._stats())
        return result

    def group_make_atlas(self, subjects=None, gen_new_atlas=False):
        """Run atlas preprocessing steps for a list of subjects.
        
        Prerequisite
        ------------
        For native space atlases, the paradigm has to be initialized.  
        This is uneccesary for standard space atlases.

        Parameters
        ----------
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the full subject list from config if ommitted.
        gen_new_atlas : bool, optional
            An average surface significance map only needs to be analyzed 
            for clusters once.  By default, if the surfcluster summary file
            is found, this method will skip that step.  To force  a new
            cluster summary table to be made, set to true.  
        
        Returns
        -------
        result : RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        for i, subject in enumerate(subjects):
            self.init_subject(subject)
            if not i:
                gen_new_atlas = gen_new_atlas
            else:
                gen_new_atlas = False
            res = self.make_atlas(gen_new_atlas=gen_new_atlas)
            print res
            result(res)
        return result


class LabelAtlas(Atlas):
    """Atlas class for an atlas construced from surface labels.

    Examples
    --------

    Single subject:
    
    >>> labls = roi.LabelAtlas("social_labels", "subj_id")
    >>> labls.make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> labls.init_analysis(analysis)
    >>> labls.extract()

    Group:
    
    >>> labls = roi.LabelAtlas("social_labels")
    >>> labls.group_make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> labls.group_extract(analysis)

    Atlas Information
    -----------------
    The LabelAtlas class can construct and extract from an atlas 
    composed of any number of non-overlapping Freesurfer surface 
    label files defined on the fsaverage standard-space subject.  
    These labels will be resampled back to each subject's native
    surface space via a spherical transform.  This class should 
    not be used for labels derived from Freesurfer's automatic
    parcellations that are produced during the reconstruction
    process.  See the FreesurferAtlas class to extract data
    from those regions.

    """
    def __init__(self, atlas, subject=None, **kwargs):
        """
        Parameters
        ----------
        atlas : str or dict
            The name of an atlas defined in your setup module, or a dictionary
            of atlas parameters.
        subject : str, optional
            The name of a subject to initialize the atlas for.

        """
        if isinstance(atlas, str):
            atlasdict = cfg.atlases(atlas)
        else:
            atlasdict = atlas
        
        Atlas.__init__(self, atlasdict, **kwargs)
        
        tree.make_label_atlas_tree()

        self.space = "native"
        self.hemi = self.atlasdict["hemi"]
        self.iterhemi = [self.hemi]
        self.fname = "%s.annot" % self.atlasname

        self.basedir = os.path.join(self.roidir, "atlases", "label", 
                                    cfg.projectname())
        
        self.sourcelevel = atlasdict["sourcelevel"]
        self.lutfile = os.path.join(self.basedir,"%s.lut" % self.atlasname)
        self.regions = {}
        self.regions[self.hemi] = self.lutdict.keys()
        self.all_regions = {}
        self.all_regions[self.hemi] = self.regions[self.hemi]
        self.regionnames = [self.lutdict[id] for id in self.regions[self.hemi]]
        self.regionnames.sort()                                

        if subject is not None: self.init_subject(subject)

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the atlas for a subject"""
        self.subject = subject
        self.atlasdir = os.path.join(self.basedir, subject, self.atlasname)
        self.statsfile = os.path.join(self.atlasdir,
                                      "%s." + self.atlasname + ".stats")
        self.atlas = os.path.join(self.atlasdir, "%s." + self.fname)
        self.origatlas = os.path.join(self.subjdir, subject, 
                                      "label", "%s." + self.fname)
        self._init_subject = True

    def make_atlas(self):
        """Run the neccessary steps required to make the atlas annotation.
        
        Notes
        -----
        If the atlas is defined in average space, the first step is to resample
        each label back to individual subject space via the spherical transformation.
        Once all labels are in native space, a color look-up-table is generated, and
        then the labels are combined into a single annotation that is used to 
        define regions for extraction.  Finally, a summary file is generated that
        reports the size of each region in both number of vertices and mm^3.

        Returns
        --------
        RoiResult object
        
        """
        result = RoiResult(self._write_lut())
        if self.sourcelevel == "group":
            result(self._resample_labels())
        else:
            result(self._copy_labels())
        result(self._gen_annotation())
        if self._atlas_exists():
            result(self._stats())
        return result

    def group_make_atlas(self, subjects=None):
        """Run atlas preprocessing steps for a list of subjects.
        
        Parameters
        ----------
        subjects : list, or str, optional
            List of subjects to preprocess. If a string, it runs the
            group defined by that name in the config file. Will run
            the full subject list from config if ommitted.
        
        Returns
        -------
        result : RoiResult object

        """
        if subjects is None:
            subjects = cfg.subjects()
        elif isinstance(subjects, str):
            subjects = cfg.subjects(subjects)
        result = RoiResult()
        for i, subject in enumerate(subjects):
            self.init_subject(subject)
            res = self.make_atlas()
            print res
            result(res)
        return result

class MaskAtlas(Atlas):
    """Class for atlases constructed from binary volume masks.

    Examples
    --------

    Single subject:
    
    >>> masks = roi.MaskAtlas("social_masks", "subj_id")
    >>> masks.make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> masks.init_analysis(analysis)
    >>> masks.extract()

    Group:
    
    >>> masks = roi.LabelAtlas("social_masks")
    >>> masks.group_make_atlas()
    >>> analysis = roi.cfg.analysis(1)
    >>> masks.group_extract(analysis)

    Atlas Information
    -----------------
    The MaskAtlas class can construct and extract from an atlas 
    defined by any number of non-overlapping binary mask images
    in standard volume space.  
    
    Note
    ----
    This has not yet been tested for masks in Analyze format, and
    it is quite likely that using Analyze masks will cause orienta-
    tion problems. If at all possible, use Nifti (both .nii single
    volumes and .img/.hdr pairs should work).

    """
    def __init__(self, atlasdict, subject=None, **kwargs):
        """
        Parameters
        ----------
        atlas : str or dict
            The name of an atlas defined in your setup module, or a dictionary
            of atlas parameters.
        subject : str, optional
            The name of a subject to initialize the atlas for.
        """

        if isinstance(atlasdict, str):
            atlasdict = cfg.atlases(atlasdict)
        
        Atlas.__init__(self, atlasdict, **kwargs)

        tree.make_mask_atlas_tree()
       
        self.space = "standard"
        self.fname = "%s.mgz" % self.atlasname

        self.basedir = os.path.join(self.roidir, "atlases",
                                    "mask", cfg.projectname())
        
        self.lutfile = os.path.join(self.basedir, "%s.lut" % self.atlasname)
        self.statsfile = os.path.join(self.basedir, "%s.stats" % self.atlasname)
        self.regions = self.lutdict.keys()
        self.all_regions = self.regions
        self.regionnames = [self.lutdict[id] for id in self.regions]
        self.regionnames.sort()                                
        
        self.atlas = os.path.join(self.basedir, self.fname)


        if subject is not None: self.init_subject(subject)

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the atlas for a subject"""
        self.subject = subject
        
        self._init_subject = True

    def make_atlas(self):
        """Make the single atlas image and look-up-table from a group of masks."""
        self.tempdir = mkdtemp()
        self.tempvols = []
        result = RoiResult(self._write_lut())
        for segnum in range(1, len(self.sourcefiles) + 1):
            res = self._adj_binary_segvol(segnum)
            result(res)

        res = self._combine_segvols()
        result(res)
        shutil.rmtree(self.tempdir)
        if self._atlas_exists():
            result(self._stats())
        return result


class SphereAtlas(Atlas):
    """Not yet implemented."""
    def __init__(self, atlasdict, subject=None, **kwargs):

        if isinstance(atlasdict, str):
            atlasdict = cfg.atlases(atlasdict)
        
        Atlas.__init__(self, atlasdict, **kwargs)

        if not self.debug:
            raise NotImplementedError(
                "Sphere atlases are not yet implemented (sorry!)")

        tree.make_sphere_atlas_tree()
        
        self.space = "standard"
        self.fname = "%s.mgz" % self.atlasname

        self.basedir = os.path.join(self.roidir, "atlases",
                                    "sphere", cfg.projectname())
        
        self.radius = atlasdict["radius"]
        self.coordsys = atlasdict["coordsys"]
        self.lutfile = os.path.join(self.basedir, "%s.lut" % self.atlasname)
        self.lutdict = {}
        self.centers = {}
        self.regionnames = []
        for i, name in enumerate(atlasdict["centers"]):
            self.lutdict[i+1] = name
            self.centers[i+1] = atlasdict["centers"][name]
            self.regionnames.append(name)
        self.regions = self.lutdict.keys()
        self.all_regions = self.regions
        self.regionnames.sort()                                
        
        self.atlas = os.path.join(self.basedir, self.fname)

        if subject is not None: self.init_subject(subject)

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the atlas for a subject"""
        self.subject = subject
        
        self._init_subject = True

    def make_atlas(self):
        raise NotImplementedError

def init_atlas(atlas, *args, **kwargs):
    """Initialize the proper atlas class with an atlas dictionary.
    
    Parameters
    ----------
    atlas : str or dict
        Atlas name or a dictionary of atlas parameters
    subject : str, optional
        If included, the atlas will be initialized for this subject
    paradigm : str, optional
        If included, the atlas will be initialized for this paradigm.
        Note that this is only relevant for Freesurfer atlases.

    Returns
    -------
    Atlas object

    """
    par = None
    sub = None
    for arg in args:
        if arg in cfg.paradigms():
            par = arg
        elif arg in cfg.subjects():
            sub = arg

    if isinstance(atlas, str):
        atlas = cfg.atlases(atlas)

    switch = dict(freesurfer = FreesurferAtlas,
                  fsl        = HarvardOxfordAtlas,
                  sigsurf    = SigSurfAtlas,
                  label      = LabelAtlas,
                  mask       = MaskAtlas,
                  sphere     = SphereAtlas)
    source = atlas["source"]                  
    return switch[source](atlas, subject=sub, paradigm=par, **kwargs)
