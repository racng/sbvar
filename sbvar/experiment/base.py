import numpy as np
import pandas as pd
import warnings

from sbvar.utils import *
from sbvar.plotting import *

doc_simulation = """
    rr : `RoadRunner` object
        RoadRunner object for simulating SBML model.
    start: float (default:0)
        Starting time for simulations
    end: float (default:5)
        Ending time for simulations
    points: int (default: 51)
        Number of time points to return for each simulation.
    steps: int (optional, default: None)
        Number of steps at which output is sampled, 
        where the samples are evenly spaced.
        Steps = points - 1. Steps and points may not both be specified. 
    selections: list of str (optional, default: None)
        A list of variables to be recorded in simulation output. 
        Time will be added to selections if not specified. If None, 
        keeps track of time and all floating species'amounts and derivatives 
        and reaction rates.
"""

class Experiment(object):
    """
    Generic Experiment class for specifying model and simulation parameters.

    Parameters
    ----------
    {simulation_params}

    Attributes
    ----------
    conditions: list of tuples
        List of levels 
    simulations: numpy.ndarray
        Three-dimensional stacked arrays of simulation outputs across all conditions.
        (Number of timepoints x Number of Selections x Number of conditions)
    var: pd.DataFrame
        Dataframe storing annotation of selections
    obs: pd.DataFrame
        Dataframe storing annotations of conditions
    """
    def __init__(self, rr, start=0, end=5, points=51, 
        selections=None, steps=None, steady_state_selections=None):
        self.rr = rr
        self.start = start
        self.end = end
        self.points = points
        self.steps = steps
        self.species_ids = rr.getFloatingSpeciesIds()
        self.boundary_ids = rr.getBoundarySpeciesIds()
        self.reaction_ids = rr.getReactionIds()
        self.flux_ids = [x + "'" for x in self.species_ids]
        self.set_selections(selections)
        self.set_steady_state_selections(steady_state_selections)
        
        self.dim = 0
        self.conditions = None
        self.simulations = None
        self.steady_states = None

    # def check_in_model(self, x):
    #     """"""
    #     in_model = (x in self.species_ids) or (x in self.boundary_ids) \
    #         or (x in self.reaction_ids) or (x in self.flux_ids)
    #     return in_model
    def check_in_rr(self, selection):
        """Check if selection is specified in the roadrunner object.
        Parameters
        ----------
        selection: str
            Selection variable to look for in the roadrunner object. 
        Return
        ------
        Returns nothing, but raises error if selection is not found.
        """
        # TO-DO: compare with self.rr.model.keys()?
        if selection not in self.rr.keys():
            raise ValueError(f"{selection} not in roadrunner object.")

    def set_selections(self, selections):
        """
        Set the selections attribute. Use user provided selections if 
        valide. Otherwise, set selection values to all floating species' 
        amounts and derivatives and reaction rates.
        Time added to selections if it was omitted by user.
        Parameters
        ----------
        selections: list of str
            List of variables to be recorded in simulation output.
        Returns
        -------
        Updates `selections` attribute. 
        """
        # Default behavior uses all floating species' amounts and derivatives
        # and reaction rates.
        if selections == None:
            self.selections = ['time'] + self.species_ids + self.flux_ids \
                + self.reaction_ids
        else:
            self.selections = selections.copy()
            # Add time selection if omitted
            if 'time' not in self.selections:
                self.selections.insert(0, 'time')
                warnings.warn('Added time to list of selections.', UserWarning)
            # Check if selection is in model
            for x in self.selections:
                if x != 'time':
                    self.check_in_rr(x)
            # If selections list was empty, call default behavior
            if len(self.selections)<2:
                self.set_selections(None)

    def set_steady_state_selections(self, steady_state_selections):
        """
        Set the steady state selections attribute. 
        Use user provided selections if valid. Otherwise, set steady 
        state selection values to all floating species' amounts and 
        reaction rates.
        Parameters
        ----------
        steady_state_selections: list of str
            List of variables to be included in steady state calculations.
        
        Returns
        -------
        Updates `steady_state_selections` attribute. 
        """
        # Default behavior uses all floating species' amounts and reaction rates.
        if steady_state_selections == None:
            self.steady_state_selections = [x for x in self.selections \
                if (x not in self.flux_ids) and (x != 'time')]
        else:
            self.steady_state_selections = steady_state_selections.copy()
            for x in self.steady_state_selections:
                if x != 'time':
                    self.check_in_rr(x)
        return 

    def iter_conditions(self, func, **kwargs):
        """
        Wrapper function for resetting model and calling `func`.
        Parent Experiment class does not have multiple conditions,
        so function is applied once to initial conditions.

        Parameters
        ----------
        func: callable
            Function to be called for each condition.

        Returns
        -------
        output: 
            Output is from calling `func` once.
        """
        # Reset model
        self.rr.reset()
        output = func(**kwargs)
        return output
    
    def _simulate(self):
        output = self.rr.simulate(
                        start=self.start, end=self.end, 
                        points=self.points, steps=self.steps, 
                        selections=self.selections)
        return output

    def simulate(self):
        """Run and store simulations for each condition."""
        self.simulations = np.dstack(self.iter_conditions(self._simulate))
        return

    def _steady_state(self):
        self.rr.steadyStateSelections = self.steady_state_selections
        try:
            self.rr.steadyState()
        except:
            self.rr.conservedMoietyAnalysis = True 
            # Changing conservedMoietyAnalysis resets steadyStateSelections
            self.rr.steadyStateSelections = self.steady_state_selections
            self.rr.steadyState()
        output = self.rr.getSteadyStateValues()
        self.rr.conservedMoietyAnalysis = False # reset to default
        return output

    def calc_steady_state(self):
        """
        Run and store steady state values of floating species amount
        and reaction rates for each condition.
        """
        self.steady_states = np.vstack(self.iter_conditions(self._steady_state))
        return

    def get_selection_index(self, variable):
        """Get index of variable in selections."""
        if variable not in self.selections:
            raise ValueError(f"{variable} not in steady state selections.")
        return self.selections.index(variable)

    def get_steady_state(self, variable):
        """Get steady state values."""
        if variable not in self.steady_state_selections:
            raise ValueError(f"{variable} not in steady state selections.")
        if self.steady_states is None:
            warnings.warn("Calculating steady state.", UserWarning)
            self.calc_steady_state()
        i = self.steady_state_selections.index(variable)
        vector = self.steady_states[:, i]
        return vector

    def get_step_values(self, variable, step):
        """Get values of variable from time step."""
        i = self.get_selection_index(variable)
        if self.simulations is None:
            warnings.warn("Running simulations.")
            self.simulate()
        vector = self.simulations[step, i, :]
        return vector

    def get_timepoints(self):
        """Get array of all timepoints."""
        return self.simulations[:, 0, 0]

    def get_closest_timepoint(self, time):
        """Get index of timepoint closest to t."""
        return np.argmin(np.abs(self.get_timepoints()-time))

    def get_time_values(self, variable, time):
        """Get values of variable from timepoint closest to time."""
        i = self.get_selection_index(variable)
        if self.simulations is None:
            warnings.warn("Running simulations.")
            self.simulate()
        step = self.get_closest_timepoint(time)
        vector = self.get_step_values(variable, step)
        return vector

    def get_values(self, variable, steady_state=True, step=None, time=None):
        """Get meshgrid of simulation results for a variable. 
        If steady_state is True, returns steady state value. Otherwise,
        return variable value at a specific time or step. If time is provided,
        the nearest time point is returned.
        Parameters
        ----------
        steady_state: boolean
            If True, returns steady state values. Overrides step and time.
        step: int
            Index of time point to get values for.
        time: float
            Timepoint value to get values for. Values for the nearest
            timepoint is returned. 
        Return
        ------
        mesh: np.array
            2D Meshgrid of values. 
        """
        if steady_state:
            return self.get_steady_state(variable)
        elif step is not None:
            return self.get_step_values(variable, step)
        elif time is not None:
            return self.get_timepoint_values(variable, time)