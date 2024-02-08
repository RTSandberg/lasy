import numpy as np
from numba import jit

c = 2.998e8  # m/s

from .profile import Profile


class SpeckleProfile(Profile):
    r"""
    Derived class for the profile of a speckled laser pulse.



    The speckles are created using with random (RPP) or continuous phase plates (CPP)
    then either the Smoothing by spectral dispersion (SSD)
    or Induced spatial incoherence methods.
    More precisely, the electric field corresponds to:

    .. math::

        E_u(\boldsymbol{x}_\perp,t) &= Re\left[ E_0\,
        \sum_{j=1}^{N_{bx}\times N_{by}} A_j
        {\rm sinc}\left(\frac{\pi D_xx}{\lambda_0 f}\right)
        {\rm sinc}\left(\frac{\pi D_yy}{\lambda_0 f}\right)\\\\
        \exp\left(i\boldsymbol{k}_{\perp,j}\cdot\boldsymbol{x}_\perp
        + i\phi_{{\rm RPP/CPP},j}+i\psi_{{\rm SSD/ISI},j}\right) \times p_u \right]

    where :math:`u` is either :math:`x` or :math:`y`, :math:`p_u` is
    the polarization vector, :math:`Re` represent the real part, and
    :math:`\boldsymbol{x}_\perp=(x,y)` is the transverse coordinate (orthogonal
    to the propagation direction).
    Several quantities are computed internally to the code depending on the
    method of smoothing chosen, including the beamlet amplitude :math:`A_j`,
    the beamlet wavenumber at focus :math:`k_{\perp,j}`,
    the phase contribution :math:`\phi_{{\rm RPP/CPP},j}` from the phase plate,
    and the phase contribution :math:`\psi_{{\rm SSD/ISI},j}` from the smoothing.
    The other parameters in this formula are defined below.

    Notes
    -----
    This assumes a rectangular laser and so a rectangular grid of beamlets.

    Parameters
    ----------
    wavelength : float (in meter)
        The main laser wavelength :math:`\lambda_0` of the laser, which
        defines :math:`\omega_0` in the above formula, according to
        :math:`\omega_0 = 2\pi c/\lambda_0`.

    pol : list of 2 complex numbers (dimensionless)
        Polarization vector. It corresponds to :math:`p_u` in the above
        formula ; :math:`p_x` is the first element of the list and
        :math:`p_y` is the second element of the list. Using complex
        numbers enables elliptical polarizations.

    w0 : float (in meter)
        The waist of the laser pulse, i.e. :math:`w_0` in the above formula.

    tau : float (in second)
        The duration of the laser pulse, i.e. :math:`\tau` in the above
        formula. Note that :math:`\tau = \tau_{FWHM}/\sqrt{2\log(2)}`,
        where :math:`\tau_{FWHM}` is the Full-Width-Half-Maximum duration
        of the intensity distribution of the pulse.

    t_peak : float (in second)
        The time at which the laser envelope reaches its maximum amplitude,
        i.e. :math:`t_{peak}` in the above formula.

    focal_length : float (in meter)
        Focal length of lens :math:`f` just after the RPP/CPP.

    beam_aperture : list of 2 floats (in meters)
        Beam width :math:`D_x,D_y` at the lens / size of the illuminated region of the RPP/CPP.

    n_beamlets : list of integers
        Number of RPP/CPP elements :math:`N_{bx},N_{by}` in each direction.

    lsType : string
        Which method for beamlet production and evolution is used.
        Can be 'FM SSD', 'GS RPM SSD', or 'GS ISI'

        - 'FM SSD': frequency modulated (FM) Smoothing by Spectral Dispersion (SSD)
        - 'GP RPM SSD': Gaussian process (GP) Random Phase Modulated (RPM) SSD

        An idealized form of SSD where each beamlet has random phase
        determined by sampling from a Gaussian stochastic process.

        - 'GP ISI': GP Induced spatial incoherence (ISI)
        An idealized form of ISI where each beamlet has random phase and amplitude
        sampled from a Gaussian stochastic process.

    relative_laser_bandwidth : float (optional, default 0.005)
        Bandwidth of laser pulse, relative to central frequency.

    phase_mod_amp : 2-tuple of floats, (optional, default (4.1,4.1))
        Amplitude of phase modulation in each transverse direction.
        Only used if `lsType` is `FM SSD`.

    ncc : list of 2 floats, (optional, default [1.4, 1.0])
        Number of color cycles of SSD spectrum to include in modulation
        Only used if `lsType` is `FM SSD`.

    ssd_distr: list of 2 floats, (optional, default [1.2, 1.])
        Determines how much SSD is distributed in the `x` and `y` directions.
        if `ssd_distr=[a,b]`, then the SSD frequency modulation is `a/sqrt(a^2+b^2)` in `x` and `b/sqrt(a^2+b^2)` in `y`.
        Only used if `lsType` is `FM SSD`.

    do_include_transverse_decay : boolean, (optional, default False)
        Whether to include the transverse sinc envelope or not.
        I.e. whether it is assumed to be close enough to the laser axis to neglect the transverse field decay.

    z_foc : float (in meter), optional
        Position of the focal plane. (The laser pulse is initialized at `z=0`.)
    """

    def __init__(
        self,
        wavelength,
        pol,
        w0,
        tau,
        t_peak,
        focal_length,
        beam_aperture,
        n_beamlets,
        lsType="FM SSD",
        relative_laser_bandwidth=0.005,
        phase_mod_amp=(4.1, 4.1),
        ncc=[1.4, 1.0],
        ssd_distr=[1.2, 1.0],
        do_include_transverse_decay=False,
        z_foc=0,
    ):
        super().__init__(wavelength, pol)
        self.wavelength = wavelength
        self.w0 = w0
        self.tau = tau
        self.t_peak = t_peak
        self.z_foc = z_foc
        self.cep_phase = 0
        self.focal_length = focal_length
        self.beam_aperture = np.array(beam_aperture, dtype="float")
        self.n_beamlets = np.array(n_beamlets, dtype="int")
        self.lsType = lsType
        self.laser_bandwidth = relative_laser_bandwidth

        # ======================== SSD parameters ========================= #
        # Only support single FM for now
        # the amplitude of phase along each direction
        self.phase_mod_amp = phase_mod_amp
        # number of color cycles
        self.ncc = ncc
        # bandwidth distributed with respect to the two transverse direction
        self.ssd_distr = ssd_distr
        #                                                                               #
        # \                                                                           / #
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ USER INPUT ENDS ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ #
        # time interval to update the speckle pattern, roughly update 50 time every bandwidth cycle
        self.tu = 1 / self.laser_bandwidth / 50
        self.do_include_transverse_decay = do_include_transverse_decay

        # ================== Sanity checks on user inputs ===================== #
        assert relative_laser_bandwidth > 0, "laser_bandwidth must be greater than 0"
        for q in (n_beamlets, phase_mod_amp, ncc, ssd_distr):
            assert np.size(q) == 2, "has to be a size 2 array"
        for q in (ncc, ssd_distr, phase_mod_amp):
            assert q[0] > 0 or q[1] > 0, "cannot be all zeros"
        supported_bandwidth = "FM SSD", "GP RPM SSD", "GP ISI"
        assert (
            lsType.upper() in supported_bandwidth
        ), "Only support one of the following: " + ", ".join(supported_bandwidth)

    def evaluate(self, x, y, t):
        """
        Return the envelope field of the laser.

        Parameters
        ----------
        x, y, t: ndarrays of floats
            Define points on which to evaluate the envelope
            These arrays need to all have the same shape.

        Returns
        -------
        envelope: ndarray of complex numbers
            Contains the value of the envelope at the specified points
            This array has the same shape as the arrays x, y, t
        """

        # ======================== General parameters ==================== #
        t_norm = t[0, 0, :] * c / self.wavelength
        tmax = t_norm[-1]

        # # ================== Calculate auxiliary variables ================== #
        if "SSD" in self.lsType.upper():
            phase_plate = np.random.uniform(
                -np.pi, np.pi, size=self.n_beamlets[0] * self.n_beamlets[1]
            ).reshape(self.n_beamlets)
        elif "ISI" in self.lsType.upper():
            phase_plate = np.zeros(self.n_beamlets)  # ISI does not require phase plates
        else:
            raise NotImplementedError

        ssd_frac = np.sqrt(self.ssd_distr[0] ** 2 + self.ssd_distr[1] ** 2)
        ssd_frac = self.ssd_distr[0] / ssd_frac, self.ssd_distr[1] / ssd_frac
        phase_mod_freq = [
            self.laser_bandwidth * sf * 0.5 / pma
            for sf, pma in zip(ssd_frac, self.phase_mod_amp)
        ]
        x_lens_list = np.linspace(
            -0.5 * (self.n_beamlets[0] - 1),
            0.5 * (self.n_beamlets[0] - 1),
            num=self.n_beamlets[0],
        )
        y_lens_list = np.linspace(
            -0.5 * (self.n_beamlets[1] - 1),
            0.5 * (self.n_beamlets[1] - 1),
            num=self.n_beamlets[1],
        )
        Y_lens_matrix, X_lens_matrix = np.meshgrid(y_lens_list, x_lens_list)
        Y_lens_index_matrix, X_lens_index_matrix = np.meshgrid(
            np.arange(self.n_beamlets[1], dtype=float),
            np.arange(self.n_beamlets[0], dtype=float),
        )
        phase_mod_phase = np.random.standard_normal(2) * np.pi
        td = (
            self.ncc[0] / phase_mod_freq[0] if phase_mod_freq[0] > 0 else 0,
            self.ncc[1] / phase_mod_freq[1] if phase_mod_freq[1] > 0 else 0,
        )
        stochastic_process_time = np.arange(0, tmax + self.tu, self.tu)

        # ======================= Initialization ========================= #
        def gen_gaussian_time_series(t_num, fwhm, rms_mean):
            """generate a discrete time series that has gaussian power spectrum

            :param t_num: number of grid points in time
            :param fwhm: full width half maximum of the power spectrum
            :param rms_mean: root-mean-square average of the spectrum
            :return: a time series array of complex numbers with shape [t_num]
            """
            if fwhm == 0.0:
                return np.zeros((2, t_num))
            omega = np.fft.fftshift(np.fft.fftfreq(t_num, d=self.tu))
            # rand_ph = np.random.normal(scale=np.pi, size=t_num)
            psd = np.exp(-np.log(2) * 0.5 * np.square(omega / fwhm * 2 * np.pi))
            psd *= np.sqrt(t_num) / np.sqrt(np.mean(np.square(psd))) * rms_mean
            pm_phase = np.array(psd) * (
                np.random.normal(size=t_num) + 1j * np.random.normal(size=t_num)
            )
            pm_phase = np.fft.ifftshift(np.fft.fft(np.fft.fftshift(pm_phase)))
            pm_phase *= rms_mean / np.sqrt(np.mean(np.square(np.abs(pm_phase))))
            return pm_phase

        def init_GS_timeseries():
            if "SSD" in self.lsType.upper():
                pm_phase0 = gen_gaussian_time_series(
                    stochastic_process_time.size + int(np.sum(td) / self.tu) + 2,
                    2 * np.pi * phase_mod_freq[0],
                    self.phase_mod_amp[0],
                )
                pm_phase1 = gen_gaussian_time_series(
                    stochastic_process_time.size + int(np.sum(td) / self.tu) + 2,
                    2 * np.pi * phase_mod_freq[1],
                    self.phase_mod_amp[1],
                )
                time_interp = np.arange(
                    start=0,
                    stop=stochastic_process_time[-1] + np.sum(td) + 3 * self.tu,
                    step=self.tu,
                )[: pm_phase0.size]
                return (
                    time_interp,
                    [
                        (np.real(pm_phase0) + np.imag(pm_phase0)) / np.sqrt(2),
                        (np.real(pm_phase1) + np.imag(pm_phase1)) / np.sqrt(2),
                    ],
                )
            elif "ISI" in self.lsType.upper():
                complex_amp = np.stack(
                    [
                        np.stack(
                            [
                                gen_gaussian_time_series(
                                    stochastic_process_time.size,
                                    2 * self.laser_bandwidth,
                                    1,
                                )
                                for _i in range(self.n_beamlets[1])
                            ]
                        )
                        for _j in range(self.n_beamlets[0])
                    ]
                )
                return stochastic_process_time, complex_amp

        if "GP" in self.lsType.upper():
            time_ext, timeSeries = init_GS_timeseries()
        else:
            time_ext, timeSeries = stochastic_process_time, None

        def beamlets_complex_amplitude(t_now, lsType="FM SSD"):
            if lsType.upper() == "FM SSD":
                phase_t = self.phase_mod_amp[0] * np.sin(
                    phase_mod_phase[0]
                    + 2
                    * np.pi
                    * phase_mod_freq[0]
                    * (t_now - X_lens_matrix * td[0] / self.n_beamlets[0])
                ) + self.phase_mod_amp[1] * np.sin(
                    phase_mod_phase[1]
                    + 2
                    * np.pi
                    * phase_mod_freq[1]
                    * (t_now - Y_lens_matrix * td[1] / self.n_beamlets[1])
                )
                return np.exp(1j * phase_t)
            elif lsType.upper() == "GP RPM SSD":
                phase_t = np.interp(
                    t_now + X_lens_index_matrix * td[0] / self.n_beamlets[0],
                    time_ext,
                    timeSeries[0],
                ) + np.interp(
                    t_now + Y_lens_index_matrix * td[1] / self.n_beamlets[1],
                    time_ext,
                    timeSeries[1],
                )
                return np.exp(1j * phase_t)
            elif lsType.upper() == "GP ISI":
                return timeSeries[:, :, int(round(t_now / self.tu))]
            else:
                raise NotImplementedError

        exp_phase_plate = np.exp(1j * phase_plate)
        lambda_fnum = self.wavelength * self.focal_length / self.beam_aperture
        X_focus_matrix = x[:, :, 0] / lambda_fnum[0]
        Y_focus_matrix = y[:, :, 0] / lambda_fnum[1]
        x_focus_list = X_focus_matrix[:, 0]
        y_focus_list = Y_focus_matrix[0, :]
        x_phase_matrix = np.exp(
            -2
            * np.pi
            * 1j
            / self.n_beamlets[0]
            * np.einsum("i,j", x_lens_list, x_focus_list)
        )
        y_phase_matrix = np.exp(
            -2
            * np.pi
            * 1j
            / self.n_beamlets[1]
            * np.einsum("i,j", y_lens_list, y_focus_list)
        )

        def generate_speckle_pattern(tnow):
            bca = beamlets_complex_amplitude(tnow, lsType=self.lsType)
            speckle_amp = np.einsum(
                "jk,jl->kl",
                np.einsum("ij,ik->jk", bca * exp_phase_plate, x_phase_matrix),
                y_phase_matrix,
            )
            if self.do_include_transverse_decay:
                speckle_amp = (
                    np.sinc(X_focus_matrix / self.n_beamlets[0])
                    * np.sinc(Y_focus_matrix / self.n_beamlets[1])
                    * speckle_amp
                )
            return speckle_amp

        envelope = np.zeros(x.shape, dtype=complex)
        for i, t_i in enumerate(t_norm):
            envelope[:, :, i] = generate_speckle_pattern(t_i)
        return envelope