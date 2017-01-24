import imp
import os
import numpy as np

from climate.pyom import PyOMLegacy, cyclic

MAIN_OPTIONS = dict(
    nx = 360,
    ny = 160,
    nz = 115,
    dt_mom = 3600.0 / 2.0,
    dt_tracer = 3600.0 / 2.0,

    coord_degree = True,
    enable_cyclic_x = True,

    runlen = 365. * 86400 * 2,

    enable_diag_ts_monitor = True,
    ts_monint = 86400.0,
    enable_diag_snapshots = True,
    snapint = 365 * 86400.0 / 12.,

    enable_diag_overturning = True,
    overint = 365 * 86400,
    overfreq = 365 * 86400 / 24.,
    enable_diag_energy = True,
    energint = 365 * 86400,
    energfreq = 365 * 86400 / 24.,
    enable_diag_averages = True,
    aveint = 365 * 86400,
    avefreq = 365 * 86400 / 24.,

    congr_epsilon = 1e-6,
    congr_max_iterations = 10000,
    enable_streamfunction = True,
    #enable_congrad_verbose = True

    enable_hor_friction = True,
    A_h = 5e4,
    enable_hor_friction_cos_scaling = True,
    hor_friction_cosPower = 1,
    enable_tempsalt_sources = True,

    eq_of_state_type = 5
)

ISONEUTRAL_OPTIONS = dict(
    enable_neutral_diffusion = True,
    K_iso_0 = 1000.0,
    K_iso_steep = 50.0,
    iso_dslope = 0.005,
    iso_slopec = 0.005,
    enable_skew_diffusion = True
)

TKE_OPTIONS = dict(
    enable_implicit_vert_friction = True,
    enable_tke = True,
    c_k = 0.1,
    c_eps = 0.7,
    alpha_tke = 30.0,
    mxl_min = 1e-8,
    tke_mxl_choice = 2,
    enable_tke_superbee_advection = True
)

EKE_OPTIONS = dict(
    enable_eke = True,
    eke_k_max = 1e4,
    eke_c_k = 0.4,
    eke_c_eps = 0.5,
    eke_cross = 2.,
    eke_crhin = 1.0,
    eke_lmin = 100.0,
    enable_eke_superbee_advection = True,
    enable_eke_isopycnal_diffusion = True,
)

IDEMIX_OPTIONS = dict(
    enable_idemix = True,
    enable_eke_diss_surfbot = True,
    eke_diss_surfbot_frac = 0.2, # fraction which goes into bottom
    enable_idemix_superbee_advection = True,

    enable_idemix_hor_diffusion = True
    #np = 17+2
    #enable_idemix_M2 = True
    #enable_idemix_niw = True
    #omega_M2 = 2*pi/( 12*60*60 +  25.2 *60 )   ! M2 frequency in 1/s
)

DATA_FILES = dict(
    dz = "dz.bin",
    temperature = "lev_clim_temp.bin",
    salt = "lev_clim_salt.bin",
    sss = "lev_sss.bin",
    tau_x = "ECMWFBB_taux.bin",
    tau_y = "ECMWFBB_tauy.bin",
    q_net = "ECMWFBB_qnet.bin",
    dqdt = "ECMWFBB_dqdt.bin",
    swf = "ECMWFBB_swf.bin",
    sst = "ECMWFBB_target_sst.bin",
    bathymetry = "bathymetry.bin",
    tidal_energy = "tidal_energy.bin",
    wind_energy = "wind_energy_ncep.bin"
)


class GlobalOneDegree(PyOMLegacy):
    """
    Global 1 degree model with 115 vertical levels, translated from setup1.f90.

    https://wiki.zmaw.de/ifm/TO/pyOM2/1x1%20global%20model
    """
    def __init__(self):
        for name, filepath in DATA_FILES.items():
            if not os.path.isfile(filepath):
                raise RuntimeError("{} data file {} not found".format(name,filepath))
        super(GlobalOneDegree,self).__init__()

    def allocate(self):
        super(GlobalOneDegree,self).allocate()

        m = self.fortran.main_module
        self.t_star = np.zeros((m.nx+4, m.ny+4, 12))
        self.s_star = np.zeros((m.nx+4, m.ny+4, 12))
        self.qnec = np.zeros((m.nx+4, m.ny+4, 12))
        self.qnet = np.zeros((m.nx+4, m.ny+4, 12))
        self.qsol = np.zeros((m.nx+4, m.ny+4, 12))
        self.divpen_shortwave = np.zeros(m.nz)
        self.taux = np.zeros((m.nx+4, m.ny+4, 12))
        self.tauy = np.zeros((m.nx+4, m.ny+4, 12))


    def set_parameter(self):
        """
        set main parameters
        """
        self._set_parameters(self.fortran.main_module, MAIN_OPTIONS)
        self._set_parameters(self.fortran.isoneutral_module, ISONEUTRAL_OPTIONS)
        self._set_parameters(self.fortran.tke_module, TKE_OPTIONS)
        self._set_parameters(self.fortran.eke_module, EKE_OPTIONS)
        self._set_parameters(self.fortran.idemix_module, IDEMIX_OPTIONS)


    def _set_parameters(self,module,parameters):
        for key, attribute in parameters.items():
            setattr(module,key,attribute)

    def _read_binary(self, var, shape=(-1,), dtype=">f"):
        return np.array(np.fromfile(DATA_FILES[var], dtype=dtype).reshape(shape, order="F"), dtype=np.float)

    def set_grid(self):
        dz_data = self._read_binary("dz")
        m = self.fortran.main_module
        m.dzt[...] = dz_data[::-1]
        m.dxt[...] = 1.0
        m.dyt[...] = 1.0
        m.y_origin = -79.
        m.x_origin = 91.


    def set_coriolis(self):
        m = self.fortran.main_module
        m.coriolis_t = 2 * m.omega * np.sin(m.yt[None,:] / 180. * m.pi)


    def set_initial_conditions(self):
        m = self.fortran.main_module

        rpart_shortwave = 0.58
        efold1_shortwave = 0.35
        efold2_shortwave = 23.0

        # initial conditions
        temp_data = self._read_binary("temperature", (m.nx, m.ny, m.nz))
        m.temp[2:-2, 2:-2, :, 0] = temp_data[..., ::-1] * m.maskT[2:-2, 2:-2, :]
        m.temp[2:-2, 2:-2, :, 1] = temp_data[..., ::-1] * m.maskT[2:-2, 2:-2, :]

        salt_data = self._read_binary("salt", (m.nx, m.ny, m.nz))
        m.salt[2:-2, 2:-2, :, 0] = salt_data[..., ::-1] * m.maskT[2:-2, 2:-2, :]
        m.salt[2:-2, 2:-2, :, 1] = salt_data[..., ::-1] * m.maskT[2:-2, 2:-2, :]

        # wind stress on MIT grid
        taux_data = self._read_binary("tau_x", (m.nx, m.ny, 12))
        self.taux[2:-2, 2:-2, :] = taux_data / m.rho_0
        self.taux[self.taux < -99.9] = 0.

        tauy_data = self._read_binary("tau_y", (m.nx, m.ny, 12))
        self.tauy[2:-2, 2:-2, :] = tauy_data / m.rho_0
        self.tauy[self.tauy < -99.9] = 0.

        if self.legacy_mode:
            self.fortran.setcyclic_xyz(is_=-1, ie_=m.nx+2, js_=-1, je_=m.ny+2, p1=self.taux)
            self.fortran.setcyclic_xyz(is_=-1, ie_=m.nx+2, js_=-1, je_=m.ny+2, p1=self.tauy)
        else:
            cyclic.setcyclic_xyz(self.taux, self.enable_cyclic_x, self.nx, 12)
            cyclic.setcyclic_xyz(self.tauy, self.enable_cyclic_x, self.nx, 12)

        # Qnet and dQ/dT and Qsol
        qnet_data = self._read_binary("q_net", (m.nx, m.ny, 12))
        self.qnet[2:-2, 2:-2, :] = -qnet_data * m.maskT[2:-2, 2:-2, :12]

        qnec_data = self._read_binary("dqdt", (m.nx, m.ny, 12))
        self.qnec[2:-2, 2:-2, :] = qnec_data * m.maskT[2:-2, 2:-2, :12]

        qsol_data = self._read_binary("swf", (m.nx, m.ny, 12))
        self.qsol[2:-2, 2:-2, :] = -qsol_data * m.maskT[2:-2, 2:-2, :12]

        # SST and SSS
        sst_data = self._read_binary("sst", (m.nx, m.ny, 12))
        self.t_star[2:-2, 2:-2, :] = sst_data * m.maskT[2:-2, 2:-2, :12]

        sss_data = self._read_binary("sss", (m.nx, m.ny, 12))
        self.s_star[2:-2, 2:-2, :] = sss_data * m.maskT[2:-2, 2:-2, :12]

        if m.enable_idemix:
            idm = self.fortran.idemix_module

            tidal_energy_data = self._read_binary("tidal_energy", (m.nx, m.ny))
            mask_x, mask_y = (i+2 for i in np.indices((m.nx, m.ny)))
            mask_z = np.maximum(0, m.kbot[2:-2, 2:-2]-1)
            tidal_energy_data[:, :] *= m.maskW[mask_x, mask_y, mask_z] / m.rho_0

            if m.enable_idemix_M2:
                idm.forc_M2[2:-2, 2:-2, 1:m.np-1] = 0.5 * tidal_energy_data[..., None] / (2*m.pi)
            else:
                m.forc_iw_bottom[2:-2, 2:-2] = 0.5 * tidal_energy_data
        else:
             m.forc_iw_bottom[2:-2, 2:-2] = tidal_energy_data

        wind_energy_data = self._read_binary("wind_energy", (m.nx, m.ny))
        wind_energy_data[...] *= m.maskW[2:-2, 2:-2, -1] / m.rho_0 * 0.2

        if m.enable_idemix_niw:
            idm.forc_niw[2:-2, 2:-2, :m.np-1] = 1.0 * wind_energy_data[..., None] / (2*m.pi)
            m.forc_iw_surface[2:-2, 2:-2] = 0.
        else:
            m.forc_iw_surface[2:-2, 2:-2] = wind_energy_data

        if m.enable_idemix_niw:
            idm.omega_niw[2:-2] = np.maximum(1e-8, np.abs(1.05 * m.coriolis_t))

        if m.enable_idemix_niw or m.enable_idemix_M2:
            """
             if enable_idemix_niw .or. enable_idemix_M2:
              iret = nf_open("hrms_1deg.nc",NF_nowrite,ncid)
              iret = nf_inq_varid(ncid,"HRMS",id)
              iret = nf_get_vara_double(ncid,id,(/is_pe,js_pe/),(/ie_pe-is_pe+1,je_pe-js_pe+1/),topo_hrms(is_pe:ie_pe,js_pe:je_pe))
              iret = nf_inq_varid(ncid,"LAM",id)
              iret = nf_get_vara_double(ncid,id,(/is_pe,js_pe/),(/ie_pe-is_pe+1,je_pe-js_pe+1/),topo_lam(is_pe:ie_pe,js_pe:je_pe))
              ncclos (ncid, iret)

              border_exchg_xy(is_pe-onx,ie_pe+onx,js_pe-onx,je_pe+onx,topo_hrms)
              setcyclic_xy   (is_pe-onx,ie_pe+onx,js_pe-onx,je_pe+onx,topo_hrms)
              border_exchg_xy(is_pe-onx,ie_pe+onx,js_pe-onx,je_pe+onx,topo_lam)
              setcyclic_xy   (is_pe-onx,ie_pe+onx,js_pe-onx,je_pe+onx,topo_lam)
             endif
             """
            # NOTE: file hrms_1deg.nc needed
            raise NotImplementedError

        """
        Initialize penetration profile for solar radiation
        and store divergence in divpen
        note that pen(nz) is set 0.0 instead of 1.0 to compensate for the
        shortwave part of the total surface flux
        """
        swarg1 = m.zw / efold1_shortwave
        swarg2 = m.zw / efold2_shortwave
        pen = rpart_shortwave * np.exp(swarg1) + (1.0 - rpart_shortwave) * np.exp(swarg2)
        self.divpen_shortwave = np.zeros(m.nz)
        self.divpen_shortwave[1:] = (pen[1:] - pen[:-1]) / m.dzt[1:]
        self.divpen_shortwave[0] = 0


    def _get_periodic_interval(self, currentTime, cycleLength, recSpacing, nbrec):
        # interpolation routine taken from mitgcm
        locTime = currentTime - recSpacing * 0.5 + cycleLength * (2 - round(currentTime / cycleLength))
        tmpTime = locTime % cycleLength
        tRec1 = int(tmpTime / recSpacing)
        tRec2 = int(tmpTime % nbrec)
        wght2 = (tmpTime - recSpacing * tRec1) / recSpacing
        wght1 = 1. - wght2
        return (tRec1, wght1), (tRec2, wght2)

    def set_forcing(self):
        t_rest = 30 * 86400
        cp_0 = 3991.86795711963 # J/kg /K
        fxa = 365 * 86400.

        m = self.fortran.main_module
        (n1, f1), (n2, f2) = self._get_periodic_interval((m.itt-1) * m.dt_tracer, fxa, fxa / 12., 12)

        # linearly interpolate wind stress and shift from MITgcm U/V grid to this grid
        m.surface_taux[:-1, :-1] = f1 * self.taux[1:, :-1, n1] + f2 * self.taux[1:, :-1, n2]
        m.surface_tauy[:-1, :-1] = f1 * self.tauy[:-1, 1:, n1] + f2 * self.tauy[:-1, 1:, n2]

        if m.enable_tke:
            tkm = self.fortran.tke_module
            tkm.forc_tke_surface[1:, 1:] = np.sqrt((0.5 * (m.surface_taux[1:, 1:] + m.surface_taux[:-1, 1:]) ** 2 \
                                                  + 0.5 * (m.surface_tauy[1:, 1:] + m.surface_tauy[1:, :-1]) ** 2) ** (3./2.))

        # W/m^2 K kg/J m^3/kg = K m/s
        fxa = f1 * self.t_star[2:-2, 2:-2, n1] + f2 * self.t_star[2:-2, 2:-2, n2]
        self.qqnec = f1 * m.qnec[2:-2, 2:-2, n1] + f2 * self.qnec[2:-2, 2:-2, n2]
        self.qqnet = f1 * m.qnet[2:-2, 2:-2, n1] + f2 * self.qnet[2:-2, 2:-2, n2]
        m.forc_temp_surface[2:-2, 2:-2] = (self.qqnet + self.qqnec * (fxa - m.temp[2:-2, 2:-2, -1, 1])) \
                                            * m.maskT[2:-2, 2:-2, -1] / cp_0 / m.rho_0
        fxa = f1 * self.s_star[2:-2, 2:-2, n1] + f2 * self.s_star[2:-2, 2:-2, n2]
        m.forc_salt_surface[2:-2, 2:-2] = m.dzt[-1] / t_rest * (fxa - m.salt[2:-2, 2:-2, -1, 1]) * m.maskT[2:-2, 2:-2, -1]

        # apply simple ice mask
        ice = np.ones((m.nx+4, m.ny+4))
        mask1 = m.temp[:, :, -1, 1] * m.maskT[:, :, -1] <= -1.8
        mask2 = m.forc_temp_surface <= 0
        mask = mask1 & mask2
        m.forc_temp_surface[mask] = 0.0
        m.forc_salt_surface[mask] = 0.0
        ice[mask] = 0.0

        # solar radiation
        m.temp_source[2:-2, 2:-2, :] = (f1 * self.qsol[2:-2, 2:-2, n1, None] + f2 * self.qsol[2:-2, 2:-2, n2, None]) \
                                        * self.divpen_shortwave[None, None, :] * ice[2:-2, 2:-2, None] \
                                        * m.maskT[2:-2, 2:-2, :] / cp_0 / m.rho_0

    def set_topography(self):
        m = self.fortran.main_module

        bathymetry_data = self._read_binary("bathymetry", (m.nx, m.ny))
        salt_data = self._read_binary("salt", (m.nx, m.ny, m.nz))

        for k in xrange(m.nz-1, -1, -1):
            mask_salt = salt_data[:,:,k] != 0.
            m.kbot[2:-2, 2:-2][mask_salt] = k+1

        mask_bathy = bathymetry_data == 0
        m.kbot[2:-2, 2:-2][mask_bathy] = 0

        m.kbot = np.minimum(m.kbot,m.nz)

        # close some channels
        i, j = np.indices((m.nx,m.ny))

        mask_channel = (i >= 207) & (i < 214) & (j < 5) # i = 208,214; j = 1,5
        m.kbot[2:-2, 2:-2][mask_channel] = 0

        # Aleuten island
        mask_channel = (i == 104) & (j == 134) # i = 105; j = 135
        m.kbot[2:-2, 2:-2][mask_channel] = 0

        # Engl channel
        mask_channel = (i >= 269) & (i < 271) & (j == 130) # i = 270,271; j = 131
        m.kbot[2:-2, 2:-2][mask_channel] = 0


    def set_diagnostics(self):
        m = self.fortran.main_module

        self.register_average("taux","Zonal wind stress","m^2/s","UT",m.surface_taux,0.0,False)
        self.register_average("tauy","Meridional wind stress","m^2/s","TU",m.surface_tauy,0.0,False)
        self.register_average("forc_temp_surface","Surface temperature flux","m K/s","TT",m.forc_temp_surface,0.0,False)
        self.register_average("forc_salt_surface","Surface salinity flux","m g/s kg","TT",m.forc_salt_surface,0.0,False)
        if m.enable_streamfunction:
            self.register_average("psi","Barotropic streamfunction","m^2/s","UU",m.psi[:,:,1],0.0,False)
        else:
            self.register_average("psi","Surface pressure","m^2/s","TT",m.psi[:,:,1],0.0,False)
        self.register_average("temp","Temperature","deg C","TTT",0.0,m.temp[:,:,:,1],True)
        self.register_average("salt","Salinity","g/kg","TTT",0.0,m.salt[:,:,:,1],True)
        self.register_average("u","Zonal velocity","m/s","UTT",0.0,m.u[:,:,:,1],True)
        self.register_average("v","Meridional velocity","m/s","TUT",0.0,m.v[:,:,:,1],True)
        self.register_average("w","Vertical velocity","m/s","TTU",0.0,m.w[:,:,:,1],True)
        self.register_average("Nsqr","Square of stability frequency","1/s^2","TTU",0.0,m.Nsqr[:,:,:,1],True)
        self.register_average("Hd","Dynamic enthalpy","m^2/s^2","TTT",0.0,m.Hd[:,:,:,1],True)
        self.register_average("rho","Density","kg/m^3","TTT",0.0,m.rho[:,:,:,1],True)
        self.register_average("K_diss_v","Dissipation by vertical friction","m^2/s^3","TTU",0.0,m.K_diss_v,True)
        self.register_average("P_diss_v","Dissipation by vertical mixing","m^2/s^3","TTU",0.0,m.P_diss_v,True)
        self.register_average("P_diss_nonlin","Dissipation by nonlinear vert. mix.","m^2/s^3","TTU",0.0,m.P_diss_nonlin,True)
        self.register_average("P_diss_iso","Dissipation by Redi mixing tensor","m^2/s^3","TTU",0.0,m.P_diss_iso,True)
        self.register_average("kappaH","Vertical diffusivity","m^2/s","TTU",0.0,m.kappaH,True)
        if m.enable_skew_diffusion:
            self.register_average("B1_gm","Zonal component of GM streamfct.","m^2/s","TUT",0.0,m.B1_gm,True)
            self.register_average("B2_gm","Meridional component of GM streamfct.","m^2/s","UTT",0.0,m.B2_gm,True)
        if m.enable_TEM_friction:
            self.register_average("kappa_gm","Vertical GM viscosity","m^2/s","TTU",0.0,m.kappa_gm,True)
            self.register_average("K_diss_gm","Dissipation by GM friction","m^2/s^3","TTU",0.0,m.K_diss_gm,True)
        if m.enable_tke:
            self.register_average("TKE","Turbulent kinetic energy","m^2/s^2","TTU",0.0,m.tke[:,:,:,1],True)
            self.register_average("Prandtl","Prandtl number"," ","TTU",0.0,m.Prandtlnumber,True)
            self.register_average("mxl","Mixing length"," ","TTU",0.0,m.mxl,True)
            self.register_average("tke_diss","Dissipation of TKE","m^2/s^3","TTU",0.0,m.tke_diss,True)
            self.register_average("forc_tke_surface","TKE surface forcing","m^3/s^2","TT",m.forc_tke_surface,0.0,False)
            self.register_average("tke_surface_corr","TKE surface flux correction","m^3/s^2","TT",m.tke_surf_corr,0.0,False)
        if m.enable_idemix:
            self.register_average("E_iw","Internal wave energy","m^2/s^2","TTU",0.0,m.e_iw[:,:,:,1],True)
            self.register_average("forc_iw_surface","IW surface forcing","m^3/s^2","TT",m.forc_iw_surface,0.0,False)
            self.register_average("forc_iw_bottom","IW bottom forcing","m^3/s^2","TT",m.forc_iw_bottom,0.0,False)
            self.register_average("iw_diss","Dissipation of E_iw","m^2/s^3","TTU",0.0,m.iw_diss,True)
            self.register_average("c0","Vertical IW group velocity","m/s","TTU",0.0,m.c0,True)
            self.register_average("v0","Horizontal IW group velocity","m/s","TTU",0.0,m.v0,True)
        if m.enable_eke:
            self.register_average("EKE","Eddy energy","m^2/s^2","TTU",0.0,m.eke[:,:,:,1],True)
            self.register_average("K_gm","Lateral diffusivity","m^2/s","TTU",0.0,m.K_gm,True)
            self.register_average("eke_diss","Eddy energy dissipation","m^2/s^3","TTU",0.0,m.eke_diss,True)
            self.register_average("L_Rossby","Rossby radius","m","TT",m.L_rossby,0.0,False)
            self.register_average("L_Rhines","Rhines scale","m","TTU",0.0,m.L_Rhines,True)
        if m.enable_idemix_M2:
            self.register_average("E_M2","M2 tidal energy","m^2/s^2","TT",m.E_M2_int,0.0,False)
            self.register_average("cg_M2","M2 group velocity","m/s","TT",m.cg_M2,0.0,False)
            self.register_average("tau_M2","Decay scale","1/s","TT",m.tau_M2,0.0,False)
            self.register_average("alpha_M2_cont","Interaction coeff.","s/m^3","TT",m.alpha_M2_cont,0.0,False)
        if m.enable_idemix_niw:
            self.register_average("E_niw","NIW energy","m^2/s^2","TT",m.E_niw_int,0.0,False)
            self.register_average("cg_niw","NIW group velocity","m/s","TT",m.cg_niw,0.0,False)
            self.register_average("tau_niw","Decay scale","1/s","TT",m.tau_niw,0.0,False)


if __name__ == "__main__":
    simulation = GlobalOneDegree()
    simulation.setup()
    simulation.run()
