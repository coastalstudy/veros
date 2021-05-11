from veros import logger

from veros.variables import Variable
from veros.core.operators import numpy as np
from veros.diagnostics.base import VerosDiagnostic
from veros.distributed import global_sum


class TracerMonitor(VerosDiagnostic):
    """Diagnostic monitoring global tracer contents / fluxes.

    Writes output to stdout (no binary output).
    """
    name = 'tracer_monitor'
    output_frequency = None

    def __init__(self, state):
        self.var_meta = {
            "tempm1": Variable("tempm1", None, write_to_restart=True),
            "vtemp1": Variable("vtemp1", None, write_to_restart=True),
            "saltm1": Variable("saltm1", None, write_to_restart=True),
            "vsalt1": Variable("vsalt1", None, write_to_restart=True),
        }

    def initialize(self, state):
        self.initialize_variables(state)

    def diagnose(self, state):
        pass

    def output(self, state):
        """
        Diagnose tracer content
        """
        vs = state.variables
        tracer_vs = self.variables

        cell_volume = vs.area_t[2:-2, 2:-2, np.newaxis] * vs.dzt[np.newaxis, np.newaxis, :] \
            * vs.maskT[2:-2, 2:-2, :]
        volm = global_sum(np.sum(cell_volume))
        tempm = global_sum(np.sum(cell_volume * vs.temp[2:-2, 2:-2, :, vs.tau]))
        saltm = global_sum(np.sum(cell_volume * vs.salt[2:-2, 2:-2, :, vs.tau]))
        vtemp = global_sum(np.sum(cell_volume * vs.temp[2:-2, 2:-2, :, vs.tau]**2))
        vsalt = global_sum(np.sum(cell_volume * vs.salt[2:-2, 2:-2, :, vs.tau]**2))

        logger.diagnostic(f' Mean temperature {tempm / volm:.2e} change to last {(tempm - tracer_vs.tempm1) / volm:.2e}')
        logger.diagnostic(' Mean salinity    {:.2e} change to last {:.2e}'
                          .format(float(saltm / volm), float((saltm - tracer_vs.saltm1) / volm)))
        logger.diagnostic(' Temperature var. {:.2e} change to last {:.2e}'
                          .format(float(vtemp / volm), float((vtemp - tracer_vs.vtemp1) / volm)))
        logger.diagnostic(' Salinity var.    {:.2e} change to last {:.2e}'
                          .format(float(vsalt / volm), float((vsalt - tracer_vs.vsalt1) / volm)))

        tracer_vs.tempm1 = tempm
        tracer_vs.vtemp1 = vtemp
        tracer_vs.saltm1 = saltm
        tracer_vs.vsalt1 = vsalt
