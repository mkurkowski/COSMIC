# -*- coding: utf-8 -*-
# Copyright (C) Scott Coughlin (2017)
#
# This file is part of cosmic.
#
# cosmic is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cosmic is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cosmic.  If not, see <http://www.gnu.org/licenses/>.

"""`independent`
"""

import numpy as np
import multiprocessing as mp
import math
import random
import scipy.integrate

from cosmic.utils import mass_min_max_select

from .sampler import register_sampler
from .. import InitialBinaryTable

from cosmic.utils import idl_tabulate, rndm

__author__ = 'Katelyn Breivik <katie.breivik@gmail.com>'
__credits__ = 'Scott Coughlin <scott.coughlin@ligo.org>'
__all__ = ['get_independent_sampler', 'Sample']


def get_independent_sampler(final_kstar1, final_kstar2, primary_model, ecc_model, SFH_model, component_age, met, size, **kwargs):
    """Something

    Parameters
    ----------
    final_kstar1 : `int`
        name of the format to be registered

    final_kstar2 : `int`
        the class that the sampler returns
    """
    if type(final_kstar1) in [int, float]:
        final_kstar1 = [final_kstar1]
    if type(final_kstar2) in [int, float]:
        final_kstar2 = [final_kstar2]
    sampled_mass = 0.0
    primary_min, primary_max, secondary_min, secondary_max = mass_min_max_select(final_kstar1, final_kstar2)
    initconditions = Sample()
    mass1, total_mass1 = initconditions.sample_primary(primary_min, primary_max, primary_model, size=size)
    # add in the total sampled primary mass
    sampled_mass += total_mass1
    mass1_binary, mass_singles = initconditions.binary_select(mass1, model='half')
    mass2_binary = initconditions.sample_secondary(mass1_binary)
    # add in the sampled secondary mass
    sampled_mass += np.sum(mass2_binary)
    ecc =  initconditions.sample_ecc(ecc_model, size = mass1_binary.size)
    porb =  initconditions.sample_porb(mass1_binary, mass2_binary, ecc, size=mass1_binary.size)
    tphysf, metallicity = initconditions.sample_SFH(SFH_model, component_age=component_age, met=met, size = mass1_binary.size)
    metallicity[metallicity < 1e-4] = 1e-4
    metallicity[metallicity > 0.03] = 0.03
    kstar1 = initconditions.set_kstar(mass1_binary)
    kstar2 = initconditions.set_kstar(mass2_binary)

    return InitialBinaryTable.MultipleBinary(mass1_binary, mass2_binary, porb, ecc, tphysf, kstar1, kstar2, metallicity), sampled_mass, size



register_sampler('independent', InitialBinaryTable, get_independent_sampler,
                 usage="final_kstar1, final_kstar2, primary_model, ecc_model, SFH_model, component_age, metallicity, size")


class Sample(object):

    # sample primary masses
    def sample_primary(self, primary_min, primary_max, primary_model='kroupa93', size=None):
        """Sample the primary mass (always the most massive star) from a user-selected model

        kroupa93 follows Kroupa (1993), normalization comes from
        `Hurley 2002 <https://arxiv.org/abs/astro-ph/0201220>`_
        between 0.1 and 150 Msun
        salpter55 follows
        `Salpeter (1955) <http://adsabs.harvard.edu/abs/1955ApJ...121..161S>`_
        between 0.1 and 150 Msun

        Parameters
        ----------
        primary_min : float
            minimum initial primary mass [Msun]

        primary_max : float
            maximum initial primary mass [Msun]

        primary_model : str, optional
            model for mass distribution; choose from:

            kroupa93 follows Kroupa (1993), normalization comes from
            `Hurley 2002 <https://arxiv.org/abs/astro-ph/0201220>`_
            valid for masses between 0.1 and 100 Msun

            salpter55 follows
            `Salpeter (1955) <http://adsabs.harvard.edu/abs/1955ApJ...121..161S>`_
            valid for masses between 0.1 and 100 Msun

            Default kroupa93
        size : int, optional
            number of initial primary masses to sample
            NOTE: this is set in runFixedPop call as Nstep

        Returns
        -------
        a_0 : array
            Sampled primary masses
        total_sampled_mass : float
            Total amount of mass sampled
        """

        if primary_model=='kroupa93':
            # If the final binary contains a compact object (BH or NS),
            # we want to evolve 'size' binaries that could form a compact
            # object so we over sample the initial population
            a_0_all = np.array([])
            total_sampled_mass = 0
            multiplier = 1
            while a_0_all.size < size:
                # scale the size way up in order to hopefully get enough
                # samples in the requested region,
                # if we get more than we will scale down
                a_0 = np.random.uniform(0.0, 1, size*multiplier)

                low_cutoff = 0.925
                high_cutoff = 0.986

                lowIdx, = np.where(a_0 <= low_cutoff)
                midIdx, = np.where((a_0 > low_cutoff) & (a_0 < high_cutoff))
                highIdx, = np.where(a_0 >= high_cutoff)

                a_0[lowIdx] = rndm(a=0.1, b=0.5, g=-1.3, size=len(lowIdx))
                a_0[midIdx] = rndm(a=0.50, b=1.0, g=-2.2, size=len(midIdx))
                a_0[highIdx] = rndm(a=1.0, b=150.0, g=-2.7, size=len(highIdx))

                total_sampled_mass += np.sum(a_0)

                a_0 = a_0[(a_0 >= primary_min) & (a_0 <= primary_max)]
                if not a_0.size:
                    # well this size clearly is not working time to increase
                    # the multiplier by an order of magintiude
                    multiplier *= 10
                a_0_all = np.append(a_0_all,a_0)

            return a_0_all, total_sampled_mass

        elif primary_model=='salpeter55':
            # If the final binary contains a compact object (BH or NS),
            # we want to evolve 'size' binaries that could form a compact
            # object so we over sample the initial population
            a_0_all = np.array([])
            total_sampled_mass = 0
            multiplier = 1
            while a_0_all.size < size:
                a_0 = rndm(a=0.08, b=150, g=-2.35, size=size*multiplier)

                total_sampled_mass += np.sum(a_0)

                a_0 = a_0[(a_0 >= primary_min) & (a_0 <= primary_max)]
                if not a_0.size:
                    # well this size clearly is not working time to increase
                    # the multiplier by an order of magintiude
                    multiplier *= 10
                a_0_all = np.append(a_0_all,a_0)

            return a_0_all, total_sampled_mass

    # sample secondary mass
    def sample_secondary(self, primary_mass):
        """Sample a secondary mass using draws from a uniform mass ratio distribution motivated by
        `Mazeh et al. (1992) <http://adsabs.harvard.edu/abs/1992ApJ...401..265M>`_
        and `Goldberg & Mazeh (1994) <http://adsabs.harvard.edu/abs/1994ApJ...429..362G>`_

        Parameters
        ----------
        primary_mass : array
            sets the maximum secondary mass (for a maximum mass ratio of 1)

        Returns
        -------
        secondary_mass : array
            sampled secondary masses with array size matching size of
            primary_mass
        """

        a_0 = np.random.uniform(0.001, 1, primary_mass.size)
        secondary_mass = primary_mass*a_0

        return secondary_mass


    def binary_select(self, primary_mass, model='half'):
        """Select the which primary masses will have a companion using 
        either a binary fraction of fifty percent or a
        primary-mass dependent binary fraction following
        `van Haaften et al.(2009) <http://adsabs.harvard.edu/abs/2013A%26A...552A..69V>`_ in appdx

        Parameters
        ----------
        primary_mass : array
            Mass that determines the binary fraction
        model : string
            half - every two stars selected are in a binary
            vanHaaften - primary mass dependent and ONLY VALID 
                         up to 100 Msun

        Returns
        -------
        primary_mass[binaryIdx] : array
            primary masses that will have a binary companion
        primary_mass[singleIdx] : array
            primary masses that will be single stars
        """

        if model == 'half':
            binary_choose = np.random.uniform(0, 1.0, primary_mass.size)
            binaryIdx, = np.where(binary_choose >= 0.5)
            singleIdx, = np.where(binary_choose < 0.5)

        elif model == 'vanHaaften':
            binary_fraction = 1/2.0 + 1/4.0 * np.log10(primary_mass)
            binary_choose =  np.random.uniform(0, 1.0, primary_mass.size)

            binaryIdx, = np.where(binary_fraction > binary_choose)
            singleIdx, = np.where(binary_fraction < binary_choose)

        return primary_mass[binaryIdx], primary_mass[singleIdx]


    def sample_porb(self, mass1, mass2, ecc, size=None):
        """Sample the semi-major axis flat in log space from RROL < 0.5 up
        to 1e5 Rsun according to
        `Abt (1983) <http://adsabs.harvard.edu/abs/1983ARA%26A..21..343A>`_
        and consistent with Dominik+2012,2013
        and then converted to orbital period in days using Kepler III

        Parameters
        ----------
        mass1 : array
            primary masses
        mass2 : array
            secondary masses
        ecc : array
            eccentricities

        Returns
        -------
        porb_sec/sec_in_day : array
            orbital period with array size equalling array size
            of mass1 and mass2
        """
        q = mass2/mass1
        RL_fac = (0.49*q**(2./3.)) / (0.6*q**(2./3.) + np.log(1+q**1./3.))

        q2 = mass1/mass2
        RL_fac2 = (0.49*q2**(2./3.)) / (0.6*q2**(2./3.) + np.log(1+q2**1./3.))
        try:
            ind_lo, = np.where(mass1 < 1.66)
            ind_hi, = np.where(mass1 >= 1.66)

            rad1 = np.zeros(len(mass1))
            rad1[ind_lo] = 1.06*mass1[ind_lo]**0.945
            rad1[ind_hi] = 1.33*mass1[ind_hi]**0.555
        except:
            if mass1 < 1.66:
                rad1 = 1.06*mass1**0.945
            else:
                rad1 = 1.33*mass1**0.555

        try:
            ind_lo, = np.where(mass2 < 1.66)
            ind_hi, = np.where(mass2 >= 1.66)

            rad2 = np.zeros(len(mass2))
            rad2[ind_lo] = 1.06*mass2[ind_lo]**0.945
            rad2[ind_hi] = 1.33*mass2[ind_hi]**0.555
        except:
            if mass2 < 1.66:
                rad2 = 1.06*mass1**0.945
            else:
                rad2 = 1.33*mass1**0.555

        # include the factor for the eccentricity
        RL_max = 2*rad1/RL_fac
        ind_switch, = np.where(RL_max < 2*rad2/RL_fac2)
        if len(ind_switch) >= 1:
            RL_max[ind_switch] = 2*rad2/RL_fac2[ind_switch]
        a_min = RL_max*(1+ecc)
        a_0 = np.random.uniform(np.log(a_min), np.log(1e5), size)

        # convert out of log space
        a_0 = np.exp(a_0)
        # convert to au
        rsun_au = 0.00465047
        a_0 = a_0*rsun_au

        # convert to orbital period in years
        yr_day = 365.24
        porb_yr = ((a_0**3.0)/(mass1+mass2))**0.5
        return porb_yr*yr_day


    def sample_ecc(self, ecc_model='thermal', size=None):
        """Sample the eccentricity according to a user specified model

        Parameters
        ----------
        ecc_model : string
            'thermal' samples from a  thermal eccentricity distribution following
            `Heggie (1975) <http://adsabs.harvard.edu/abs/1975MNRAS.173..729H>`_
            'uniform' samples from a uniform eccentricity distribution
            DEFAULT = 'thermal'

        size : int, optional
            number of eccentricities to sample
            NOTE: this is set in runFixedPop call as Nstep

        Returns
        -------
        ecc : array
            array of sampled eccentricities with size=size
        """

        if ecc_model=='thermal':
            a_0 = np.random.uniform(0.0, 1.0, size)
            ecc = a_0**0.5

            return ecc

        if ecc_model=='uniform':
            ecc = np.random.uniform(0.0, 1.0, size)

            return ecc


    def sample_SFH(self, SFH_model='const', component_age=10000.0, met=0.02, size=None):
        """Sample an evolution time for each binary based on a user-specified
        star formation history (SFH) and Galactic component age.
        The default is a MW thin disk constant evolution over 10000 Myr

        Parameters
        ----------
        SFH_model : str
            'const' assigns an evolution time assuming a constant star
            formation rate over the age of the MW disk: component_age [Myr]
            'burst' assigns an evolution time assuming a burst of constant
            star formation for 1Gyr starting at component_age [Myr] in the past
            'delta_burst' assignes a t=0 evolution time until component age
            DEFAULT: 'const'
        component_age: float
            age of the Galactic component [Myr]; DEFAULT: 10000.0
        met : float
            metallicity of the population [Z_sun = 0.02]
            Default: 0.02
        size : int, optional
            number of evolution times to sample
            NOTE: this is set in runFixedPop call as Nstep

        Returns
        -------
        tphys : array
            array of evolution times of size=size
        metallicity : array
            array of metallicities
        """

        if SFH_model=='const':

            tphys = np.random.uniform(0, component_age, size)
            metallicity = np.ones(size)*met
            return tphys, metallicity

        elif SFH_model=='burst':
            tphys = component_age - np.random.uniform(0, 1000, size)
            metallicity = np.ones(size)*met
            return tphys, metallicity

        elif SFH_model=='delta_burst':
            tphys = component_age*np.ones(size)
            metallicity = np.ones(size)*met
            return tphys, metallicity

    def set_kstar(self, mass):
        """Initialize stellar types according to BSE classification
        kstar=1 if M>=0.7 Msun; kstar=0 if M<0.7 Msun

        Parameters
        ----------
        mass : array
            array of masses

        Returns
        -------
        kstar : array
            array of initial stellar types
        """

        kstar = np.zeros(mass.size)
        low_cutoff = 0.7
        lowIdx = np.where(mass < low_cutoff)[0]
        hiIdx = np.where(mass >= low_cutoff)[0]

        kstar[lowIdx] = 0
        kstar[hiIdx] = 1

        return kstar

