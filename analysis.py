import os
import re
import sys
import shutil
import subprocess
from glob import glob

import configinterface as cfg
import treeutils as tree
import exceptions as ex
import utils

import numpy as np
import scipy.stats as stats
import nibabel as nib
import nipype.interfaces.freesurfer as fs
from nipype.interfaces.base import Bunch

__all__ = ["Analysis", "FirstLevelStats", 
           "BetaImage", "ContrastImage", "TStatImage", "SigImage",
           "init_stat_object"]

__module__ = "analysis"

class Analysis(Bunch):
    """Analysis object."""
    def __init__(self, analysis):
        
        if not cfg.is_setup:
            raise ex.ex.SetupError
        
        tree.make_analysis_tree(analysis)
        self.dict = analysis
        self.paradigm = analysis["par"]
        self.extract = analysis["extract"]
        self.name = utils.get_analysis_name(analysis)
        if "maskpar" in analysis.keys() and \
           analysis["maskpar"] != "nomask":
            self.mask = True
            self.maskpar = analysis["maskpar"]
            self.maskcon = analysis["maskcon"]
            self.maskthresh = analysis["maskthresh"]
            if "masksign" in analysis.keys():
                self.masksign = analysis["masksign"]
            else:
                self.masksign = "abs"
        else:
            self.mask = False

class FirstLevelStats(Bunch):
    """Base First Level Stats class"""
    def __init__(self, analysis, **kwargs):
        
        if not cfg.is_setup:
            raise ex.SetupError
        
        tree.make_levelone_tree()
        self.analysis = analysis
        
        self.roidir = os.path.join(cfg.setup.basepath, "roi")
        
        self._init_subject = False

        self.__dict__.update(**kwargs)

        if "debug" not in self.__dict__:
            self.debug = False

    # Operation methods
    def _nipype_run(self, interface):
        """Run a program using its nipype interface"""
        if self.debug:
            return interface.cmdline, None
        else:
            res = interface.run()
            return interface.cmdline, res
    
    def _manual_run(self, cmd):
        """Run a freesurfer program that lacks a nipype interface"""
        cmdline = cmd[0]
        for i, component in enumerate(cmd):
            if i != 0:
                cmdline = "%s %s" % (cmdline, component)
        if self.debug:
            return cmdline, None
        else:
            res = subprocess.call(cmd)
            return cmdline, res

    # Processing methods
    def concatenate(self):
        """Concatenate the first level statistic images."""
        if not self._init_subject:
            raise ex.InitError("Subject")
        
        concat = fs.Concatenate()

        concat.inputs.invol = self.extractlist
        concat.inputs.outvol = self.extractvol

        cmdline, res = self._nipype_run(concat)
        return cmdline, res

    def sample_to_surface(self):
        """Sample an extraction volume to the surface."""
        if not self._init_subject:
            raise ex.InitError("Subject")

        surfs = {"lh": self.extractlhsurf,
                 "rh": self.extractrhsurf}

        cmdlines = []
        results = []

        for hemi in ["lh","rh"]:
            cmd = ["mri_vol2surf"]    
            cmd.append("--mov %s" % self.extractvol)
            cmd.append("--o %s" % surfs[hemi])
            cmd.append("--reg %s" % self.regmat)
            cmd.append("--hemi %s" % hemi)
            cmd.append("--noreshape")

            cmdline, res = self._manual_run(cmd)
            cmdlines.append(cmdline)
            results.append(res)

        return cmdlines, results

    def group_concatenate(self, subjects=None):
        """Concatenate stat images for a group of subjects."""
        if subjects is None:
            subjects = cfg.subjects()
        for subj in subjects:
            self.init_subject(subj)
            cmdline, res = self.concatenate()
            if self.debug:
                print "\n%s\n\n" % cmdline
            else:
                print "\n%s\n\n%s\n%s" % (cmdline, 
                                          res.runtime.stdout,
                                          res.runtime.stdout)

    def group_sample_to_surface(self, subjects=None):
        """Sample stat volumes to the surface for a group."""
        if subjects is None:
            subjects = cfg.subjects()
        for subj in subjects:
            self.init_subject(subj)
            cmdlines, results = self.sample_to_surface()
            for i in range(1):
                if self.debug:
                    print "\n%s\n\n" % cmdlines[i]
                else:
                    print "\n%s\n\n%s\n%s" % (cmdlines[i], 
                                          results[i].runtime.stdout,
                                          results[i].runtime.stdout)

class BetaImage(FirstLevelStats):
    """Docstring goes here"""
    def __init__(self, analysis, **kwargs):

        FirstLevelStats.__init__(self, analysis, **kwargs)
        self.betalist = cfg.betas(analysis.paradigm, "images")
        self.statsdir = os.path.join(self.roidir, "levelone", "beta")

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the object for a subject"""
        self.subject = subject
        self.betapath = cfg.pathspec("beta", self.analysis.paradigm,
                                        self.subject)
        self.extractlist = []
        for img in self.betalist:
            self.extractlist.append(os.path.join(self.betapath, img))

        self.roistatdir = os.path.join(self.roidir, "levelone", "beta",
                                       self.analysis.paradigm, subject)
        self.extractvol = os.path.join(self.roistatdir, "task_betas.mgz")
        self.extractsurf = os.path.join(self.roistatdir, "%s.task_betas.mgz")
        self.regmat = os.path.join(self.roidir, "reg", self.analysis.paradigm,
                                   subject, "func2orig.dat")
        
        self._init_subject = True


class ContrastImage(FirstLevelStats):
    """Contrast Image class."""
    def __init__(self, analysis, **kwargs):

        FirstLevelStats.__init__(self, analysis, **kwargs)
        self.imgdict = cfg.contrasts(analysis.maskpar, "con-img", ".img")
        self.statsdir = os.path.join(self.roidir, "levelone", "contrast")

    # Initialization methods
    def init_subject(self, subject):
        """Initialize the object for a subject"""
        self.subject = subject
        self.extractlist = []
        for name, image in self.imgdict.items():
            self.conpath = cfg.pathspec("contrast", self.analysis.paradigm,
                                        self.subject, name)
            self.extractlist.append(os.path.join(self.conpath, image))

        self.roistatdir = os.path.join(self.roidir, "levelone", "contrast",
                                       self.analysis.paradigm, subject)
        self.extractvol = os.path.join(self.roistatdir, "all_contrasts.mgz") 
        self.extractsurf = os.path.join(self.roistatdir, "%s.all_contrasts.mgz")
        self.regmat = os.path.join(self.roidir, "reg", self.analysis.paradigm,
                                   subject, "func2orig.dat")
        
        self._init_subject = True


class TStatImage(FirstLevelStats):
    """T Statistic class"""
    def __init__(self, analysis, **kwargs):
        
        FirstLevelStats.__init__(self, analysis, **kwargs)
        self.imgdict = cfg.contrasts(analysis.maskpar, "T-map", ".img")
        self.statsdir = os.path.join(self.roidir, "levelone", "contrast")

    # Operation methods
    def get_dof(self, timg):
        """Get the degrees of freedom from a NiBabel T image"""
        theader = timg.get_header()
        desc = str(theader["descrip"])
        m = re.search("(\[)([\d\.]+)(\])", desc)
        dof = float(m.groups()[1])

        return dof
    
    # Initialization methods
    def init_subject(self, subject):
        """Initialize the object for a subject"""
        self.subject = subject
        conpath = cfg.pathspec("contrast", self.analysis.maskpar,
                                       subject, self.analysis.maskcon)
        self.timg = os.path.join(conpath, 
                                 self.imgdict[self.analysis.maskcon])
        self.sigpath = os.path.join(self.statsdir, self.analysis.maskpar,
                                   subject)
        imagefname = cfg.contrasts(self.analysis.maskpar,
                                        "sig", ".nii")[analysis.maskcon]
        self.sigimg = os.path.join(self.sigpath, imagefname)

        self.regmat = os.path.join(self.roidir, "reg", self.analysis.maskpar,
                                   subject, "func2orig.dat")
        self.sigsurf = os.path.join(self.roistatdir, "%s." + imagefname)

        self._init_subject = True                                               

    # Processing methods
    def convert_to_sig(self):
        """Read a T stat image in and write it to -log10(P)"""
        if not self._init_subject:
            raise ex.InitError("Subject")
        
        timg = nib.load(self.timg)
        dof = self.get_dof(timg)
        origvol = timg.get_data()
        signvol = np.sign(origvol)
        pvol = stats.t.sf(origvol, dof)
        unsignedsigvol = -np.log10(pvol)
        sigvol = signvol * unsignedsigvol
        
        sigaffine = timg.get_affine()
        sigimg = nib.Nifti1Image(sigvol, sigaffine)

        nib.save(sigimg, self.sigimg)

    def group_convert_to_sig(self, subjects=None):
        """Convert a t statistic image to a sig image for a group of subjects"""  
        if subjects is None:
            subjects = cfg.subjects()
        for subj in subjects:
            self.init_subject(subj)
            self.convert_to_sig()
            print "Converting %s to %s" % (self.timg, self.sigimg)

class SigImage(FirstLevelStats):
    """Sig image class"""
    def __init__(self, analysis, **kwargs):
        
        FirstLevelStats.__init__(self, analysis, **kwargs)
        self.imgdict = cfg.contrasts(analysis.maskpar, "sig", ".nii")
        self.statsdir = os.path.join(self.roidir, "levelone", "contrast")

    def init_subject(self, subject):
        """Initialize the object for a subject"""
        self.subject = subject
        self.sigpath = os.path.join(self.statsdir, self.analysis.maskpar,
                                   subject)
        imagefname = cfg.contrasts(self.analysis.maskpar,
                                        "sig", ".nii")[self.analysis.maskcon]
        self.sigvol = os.path.join(self.sigpath, imagefname)
        self.sigsurf = os.path.join(self.sigpath, "%s." + imagefname)
        self.regmat = os.path.join(self.roidir, "reg", self.analysis.maskpar,
                                   subject, "func2orig.dat")
        self.roistatdir = os.path.join(self.roidir, "levelone", "contrast",
                                       self.analysis.paradigm, subject)

        self._init_subject = True                                               

def init_stat_object(analysis):
    """Initalize the proper first level statistic class with an analysis object.
    
    Parameters
    ----------
    analysis : Analysis object
    
    Returns
    -------
    FirstLevelStats object
    
    """
    if analysis.extract == "beta":
        return BetaImage(analysis)
    elif analysis.extract == "contrast":
        return ContrastImage(analysis)