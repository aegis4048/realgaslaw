import numpy as np
from scipy import optimize
import matplotlib.pyplot as plt
import inspect

from gascompressibility.utilities.utilities import calc_Fahrenheit_to_Rankine
from gascompressibility.z_correlation.z_helper import get_z_model


class sutton:
    def __init__(self):
        self.mode = 'sutton'
        self._check_invalid_mode(self.mode)  # prevent user modification of self.mode

        self.sg = None
        self.T_f = None
        self.T = None
        self.P = None
        self.H2S = None
        self.CO2 = None

        self.Tpc = None
        self.Ppc = None
        self.A = None
        self.B = None
        self.e_correction = None
        self.Tpc_corrected = None
        self.Ppc_corrected = None
        self.Tr = None
        self.Pr = None

        self.Z = None

        self._first_caller_name = None
        self._first_caller_keys = {}
        self._first_caller_kwargs = {}
        self._first_caller_is_saved = False

    def __str__(self):
        return str(self.Z)

    def __repr__(self):
        return '<GasCompressibilityFactor object. Mixing Rule = %s>' % self.mode

    """sum of the mole fractions of CO2 and H2S in a gas mixture"""
    def _calc_A(self, H2S=None, CO2=None):
        self._initialize_H2S(H2S)
        self._initialize_CO2(CO2)
        self.A = self.H2S + self.CO2
        return self.A

    """mole fraction of H2S in a gas mixture"""
    def _calc_B(self, H2S=None):
        self._initialize_H2S(H2S)
        self.B = self.H2S
        return self.B

    """pseudo-critical temperature (°R)"""
    def calc_Tpc(self, sg=None):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_sg(sg)
        self.Tpc = 169.2 + 349.5 * self.sg - 74.0 * self.sg ** 2
        return self.Tpc

    """pseudo-critical pressure (psi)"""
    def calc_Ppc(self, sg=None):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_sg(sg)
        self.Ppc = 756.8 - 131.07 * self.sg - 3.6 * self.sg ** 2
        return self.Ppc

    """correction for CO2 and H2S (°R)"""
    def calc_e_correction(self, H2S=None, CO2=None):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_A(A=None, H2S=H2S, CO2=CO2)
        self._initialize_B(B=None, H2S=H2S)
        self.e_correction = 120 * (self.A ** 0.9 - self.A ** 1.6) + 15 * (self.B ** 0.5 - self.B ** 4)
        return self.e_correction

    def calc_Tpc_corrected(self, sg=None, Tpc=None, e_correction=None, H2S=None, CO2=None, ignore_conflict=False):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_Tpc(Tpc, sg=sg)

        # Correction is not needed if no sour gas is present
        if e_correction is None and H2S is None and CO2 is None:
            self.Tpc_corrected = self.Tpc
            return self.Tpc_corrected

        self._initialize_e_correction(e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        self.Tpc_corrected = self.Tpc - self.e_correction
        return self.Tpc_corrected

    """ corrected pseudo-critical pressure (psi)"""
    def calc_Ppc_corrected(self, sg=None, Tpc=None, Ppc=None, e_correction=None, Tpc_corrected=None, H2S=None, CO2=None, ignore_conflict=False):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_Ppc(Ppc, sg=sg)

        # Correction is not needed if no sour gas is present
        if e_correction is None and H2S is None and CO2 is None and Tpc is None and Tpc_corrected is None:
            self.Ppc_corrected = self.Ppc
            return self.Ppc_corrected

        self._initialize_Tpc(Tpc, sg=sg)
        self._initialize_B(B=None, H2S=H2S)
        self._initialize_e_correction(e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        self._initialize_Tpc_corrected(Tpc_corrected, sg=sg, Tpc=Tpc, e_correction=e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        self.Ppc_corrected = (self.Ppc * self.Tpc_corrected) / (self.Tpc - self.B * (1 - self.B) * self.e_correction)
        return self.Ppc_corrected

    """pseudo-reduced temperature (°R)"""
    def calc_Tr(self, T=None, Tpc_corrected=None, sg=None, Tpc=None, e_correction=None, H2S=None, CO2=None, ignore_conflict=False):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_T(T)
        self._initialize_Tpc_corrected(Tpc_corrected, sg=sg, Tpc=Tpc, e_correction=e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        self.Tr = self.T / self.Tpc_corrected
        return self.Tr

    """pseudo-reduced pressure (psi)"""
    def calc_Pr(self, P=None, Ppc_corrected=None, sg=None, Tpc=None, Ppc=None, e_correction=None, Tpc_corrected=None, H2S=None, CO2=None, ignore_conflict=False):
        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_P(P)
        self._initialize_Ppc_corrected(Ppc_corrected, sg=sg, Tpc=Tpc, Ppc=Ppc, e_correction=e_correction, Tpc_corrected=Tpc_corrected, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        self.Pr = self.P / self.Ppc_corrected
        return self.Pr

    """Newton-Raphson nonlinear solver"""
    def calc_Z(self, sg=None, P=None, T=None, Tpc=None, Ppc=None, Tpc_corrected=None, Ppc_corrected=None,
               H2S=None, CO2=None, Tr=None, Pr=None, e_correction=None, ignore_conflict=False,
               model='DAK', guess=0.9, newton_kwargs=None):

        self._set_first_caller_attributes(inspect.stack()[0][3], locals())
        self._initialize_Tr(Tr, T, Tpc_corrected=Tpc_corrected, sg=sg, Tpc=Tpc, e_correction=e_correction, H2S=H2S,
                            CO2=CO2, ignore_conflict=ignore_conflict)
        self._initialize_Pr(Pr, P=P, Ppc_corrected=Ppc_corrected, sg=sg, Tpc=Tpc, Ppc=Ppc, e_correction=e_correction,
                            Tpc_corrected=Tpc_corrected, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)

        z_model = get_z_model(model=model)

        if newton_kwargs is None:
            self.Z = optimize.newton(z_model, guess, args=(self.Pr, self.Tr))
        else:
            self.Z = optimize.newton(z_model, guess, args=(self.Pr, self.Tr), **newton_kwargs)

        return self.Z

    def _set_first_caller_attributes(self, func_name, func_kwargs):
        """
        Helper function to set properties related to the first function called (first in the call stack).
        This function doesn't do anything for 'calc_...()' functions called inside the first function.
        For exmaple, if `calc_Ppc_corrected()' is called, this function is skipped for 'calc_Ppc()' function which is
        triggered inside `calc_Ppc_corrected()`.
        :param func_name: string
            ex1) func_name= "calc_Tpc_corrected",
            ex2) func_name = "calc_Ppc_corrected",
        :param func_kwargs: kwarg parameters passed to 'func_name'
            ex1) func_kwargs = {'self': ...some_string, 'sg': None, 'Tpc': 377.59, 'e_correction': None, 'H2S': 0.07, 'CO2': 0.1}
            ex2) func_kwargs = {'self': ...some_string, 'sg': 0.6, 'Tpc': None, 'e_correction': None, 'H2S': 0.07, 'CO2': 0.1}
        """
        if not self._first_caller_is_saved:
            func_kwargs = {key: value for key, value in func_kwargs.items() if key != 'self'}
            if 'ignore_conflict' in func_kwargs:

                if func_kwargs['ignore_conflict'] is False:
                    """
                    This modification is needed for self._check_conflicting_arguments(). 
                    The exception in self._check_conflicting_arguments() compares if "kwarg is not None"
                    The default 'ignore_conflict' is a boolean object, so comparing if "ignore_conflict is not None"
                    will raise type error 
                    """
                    func_kwargs['ignore_conflict'] = None

            self._first_caller_name = func_name
            self._first_caller_kwargs = func_kwargs
            self._first_caller_is_saved = True
        else:
            pass

    def _check_conflicting_arguments(self, func, calculated_var):
        """
        :param func: string
            ex1) func_name = "calc_Tpc",
            ex2) func_name = "calc_J",
        :param calculated_var: string
            ex1) calculated_var = 'Tpc'
            ex1) calculated_var = 'J'
        """

        args = inspect.getfullargspec(func).args[1:]  # arg[0] = 'self', args = arguments defined in "func"
        for arg in args:
            if self._first_caller_kwargs[arg] is not None:
                raise TypeError('%s() has conflicting keyword arguments "%s" and "%s"' % (self._first_caller_name, calculated_var, arg))

    def _initialize_sg(self, sg):
        if sg is None:
            if self._first_caller_name == 'calc_Ppc' or self._first_caller_name == 'calc_Tpc':
                raise TypeError("Missing a required argument, sg (specific gravity, dimensionless)")
            else:
                raise TypeError("Missing a required arguments, sg (specific gravity, dimensionless), or Tpc "
                                "(pseudo-critical temperature, °R) or Ppc (pseudo-critical pressure, psia). "
                                "Either both Tpc and Ppc must be inputted, or only sg needs to be inputted. "
                                "Both Tpc and Ppc can be computed from sg")
        else:
            self.sg = sg

    def _initialize_P(self, P):
        if P is None:
            raise TypeError("Missing a required argument, P (gas pressure, psia)")
        else:
            self.P = P

    def _initialize_T(self, T):
        if T is None:
            raise TypeError("Missing a required argument, T (gas temperature, °F)")
        else:
            self.T_f = T
            self.T = calc_Fahrenheit_to_Rankine(T)

    def _initialize_H2S(self, H2S):
        if H2S is None:
            self.H2S = 0
        else:
            self.H2S = H2S

    def _initialize_CO2(self, CO2):
        if CO2 is None:
            self.CO2 = 0
        else:
            self.CO2 = CO2

    # The first argument A will always be None when called. However, still defining it for structural consistency
    def _initialize_A(self, A, H2S=None, CO2=None):
        if A is None:
            self._calc_A(H2S=H2S, CO2=CO2)
        else:
            self.A = A

    # The first argument B will always be None when called. However, still defining it for structural consistency
    def _initialize_B(self, B, H2S=None):
        if B is None:
            self._calc_B(H2S=H2S)
        else:
            self.B = B

    def _initialize_Tpc(self, Tpc, sg=None):
        if Tpc is None:
            self.calc_Tpc(sg=sg)
        else:
            self.Tpc = Tpc

    def _initialize_Ppc(self, Ppc, sg=None):
        if Ppc is None:
            self.calc_Ppc(sg=sg)
        else:
            self.Ppc = Ppc

    def _initialize_e_correction(self, e_correction, H2S=None, CO2=None, ignore_conflict=False):
        if e_correction is None:
            self.calc_e_correction(H2S=H2S, CO2=CO2)
        else:
            if ignore_conflict is False:
                self._check_conflicting_arguments(self.calc_e_correction, 'e_correction')
            self.e_correction = e_correction

    def _initialize_Tpc_corrected(self, Tpc_corrected, sg=None, Tpc=None, e_correction=None, H2S=None, CO2=None, ignore_conflict=False):
        if Tpc_corrected is None:
            self.calc_Tpc_corrected(sg=sg, Tpc=Tpc, e_correction=e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        else:
            if ignore_conflict is False:
                self._check_conflicting_arguments(self.calc_Tpc_corrected, 'Tpc_corrected')
            self.Tpc_corrected = Tpc_corrected

    def _initialize_Ppc_corrected(self, Ppc_corrected, sg=None, Tpc=None, Ppc=None, e_correction=None,
                                  Tpc_corrected=None, H2S=None, CO2=None, ignore_conflict=False):
        if Ppc_corrected is None:
            self.calc_Ppc_corrected(sg=sg, Tpc=Tpc, Ppc=Ppc, e_correction=e_correction, Tpc_corrected=Tpc_corrected, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        else:
            if ignore_conflict is False:
                self._check_conflicting_arguments(self.calc_Ppc_corrected, 'Ppc_corrected')
            self.Ppc_corrected = Ppc_corrected

    def _initialize_Pr(self, Pr, P=None, Ppc_corrected=None, sg=None, Tpc=None, Ppc=None, e_correction=None, Tpc_corrected=None, H2S=None, CO2=None, ignore_conflict=False):
        if Pr is None:
            self.calc_Pr(P=P, Ppc_corrected=Ppc_corrected, sg=sg, Tpc=Tpc, Ppc=Ppc, e_correction=e_correction, Tpc_corrected=Tpc_corrected, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        else:
            if ignore_conflict is False:
                self._check_conflicting_arguments(self.calc_Pr, 'Pr')
            self.Pr = Pr

    def _initialize_Tr(self, Tr, T, Tpc_corrected=None, sg=None, Tpc=None, e_correction=None, H2S=None, CO2=None, ignore_conflict=False):
        if Tr is None:
            self.calc_Tr(T=T, Tpc_corrected=Tpc_corrected, sg=sg, Tpc=Tpc, e_correction=e_correction, H2S=H2S, CO2=CO2, ignore_conflict=ignore_conflict)
        else:
            if ignore_conflict is False:
                self._check_conflicting_arguments(self.calc_Tr, 'Tr')
            self.Tr = Tr

    def _check_invalid_mode(self, mode):
        if mode != 'sutton' and mode != 'piper':
            raise TypeError("Invalid optional argument, mode (calculation method), input either 'sutton', 'piper', or None (default='sutton')")
        self.mode = mode

    def quickstart(self):

        xmax = 8
        Prs = np.linspace(0, xmax, xmax * 10 + 1)
        Prs = np.array([round(Pr, 1) for Pr in Prs])

        Trs = np.array([1.05, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0])

        results = {Tr: {
            'Pr': np.array([]),
            'Z': np.array([])
        } for Tr in Trs}

        for Tr in Trs:
            for Pr in Prs:
                z_obj = sutton()
                z = z_obj.calc_Z(Tr=Tr, Pr=Pr, **{'maxiter': 1000})
                results[Tr]['Z'] = np.append(results[Tr]['Z'], [z], axis=0)
                results[Tr]['Pr'] = np.append(results[Tr]['Pr'], [Pr], axis=0)

        label_fontsize = 12

        fig, ax = plt.subplots(figsize=(8, 5))
        for Tr in Trs:

            Zs = results[Tr]['Z']
            idx_min = np.where(Zs == min(Zs))

            p = ax.plot(Prs, Zs)
            if Tr == 1.05:
                t = ax.text(Prs[idx_min] - 0.5, min(Zs) - 0.005, '$T_{r}$ = 1.2', color=p[0].get_color())
                t.set_bbox(dict(facecolor='white', alpha=0.9, edgecolor='white', pad=1))
            else:
                t = ax.text(Prs[idx_min] - 0.2, min(Zs) - 0.005, Tr, color=p[0].get_color())
                t.set_bbox(dict(facecolor='white', alpha=0.9, edgecolor='white', pad=1))

        ax.set_xlim(0, xmax)
        ax.minorticks_on()
        ax.grid(alpha=0.5)
        ax.grid(b=True, which='minor', alpha=0.1)
        ax.spines.top.set_visible(False)
        ax.spines.right.set_visible(False)

        ax.set_ylabel('Compressibility Factor, $Z$', fontsize=label_fontsize)
        ax.set_xlabel('Pseudo-Reduced Pressure, $P_{r}$', fontsize=label_fontsize)
        ax.text(0.57, 0.08, '$T_{r}$ = Pseudo-Reduced Temperature', fontsize=11, transform=ax.transAxes,
                bbox=dict(facecolor='white'))

        def setbold(txt):
            return ' '.join([r"$\bf{" + item + "}$" for item in txt.split(' ')])

        ax.set_title(setbold('Real Gas Law Compressibility Factor - Z') + ", computed with GasCompressiblityFactor-py ",
                     fontsize=12, pad=10, x=0.445, y=1.06)
        ax.annotate('', xy=(-0.09, 1.05), xycoords='axes fraction', xytext=(1.05, 1.05),
                    arrowprops=dict(arrowstyle="-", color='k'))

        fig.tight_layout()

        return results, fig, ax


