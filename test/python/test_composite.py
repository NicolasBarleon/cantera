import sys

import numpy as np
from collections import OrderedDict
import pickle

import pytest
from .utilities import allow_deprecated

import cantera as ct

try:
    ct.composite._import_pandas()
except ImportError:
    pass

try:
    ct.composite._import_h5py()
except ImportError:
    pass

from cantera.composite import _pandas, _h5py
from . import utilities


class TestModels(utilities.CanteraTest):

    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.yml_file = cls.test_data_path / "thermo-models.yaml"
        cls.yml = utilities.load_yaml(cls.yml_file)

    def test_load_thermo_models(self):
        for ph in self.yml['phases']:
            ph_name = ph['name']
            try:
                sol = ct.Solution(self.yml_file, ph_name)

                T0, p0 = sol.TP
                TD = sol.TD
                z = sol.state # calls Phase::saveState
                sol.TP = 300, 2*ct.one_atm
                sol.state = z # calls Phase::restoreState
                self.assertEqual(sol.T, T0)
                self.assertEqual(sol.P, p0)

                if sol.thermo_model in ('pure-fluid',):
                    self.assertTrue(sol.has_phase_transition)
                else:
                    self.assertFalse(sol.has_phase_transition)

                if not sol.is_compressible:
                    with self.assertRaisesRegex(ct.CanteraError,
                                                'Density is not an independent'):
                        sol.TD = TD

                self.assertEqual(len(z), sol.state_size)
                if sol.is_pure:
                    # stoich phase (fixed composition)
                    self.assertEqual(sol.n_species, 1)
                    self.assertEqual(len(z), 2)
                else:
                    self.assertEqual(len(z), 2 + sol.n_species)

            except Exception as inst:

                # raise meaningful error message without breaking test suite
                # ignore deprecation warnings originating in C++ layer
                # (converted to errors in test suite)
                if 'Deprecated' not in str(inst):

                    msg = ("Error in processing of phase '{}' with type '{}'\n"
                           "TPX = {}")
                    msg = msg.format(ph['name'], ph['thermo'], sol.TPX)
                    raise TypeError(msg) from inst

    def test_restore_thermo_models(self):

        def check(a, b):
            self.assertArrayNear(a.T, b.T)
            self.assertArrayNear(a.P, b.P)
            self.assertArrayNear(a.X, b.X)

        for ph in self.yml['phases']:

            skipped = ['pure-fluid']
            if ph['thermo'] in skipped:
                continue

            ph_name = ph['name']

            try:
                sol = ct.Solution(self.yml_file, ph_name)
                a = ct.SolutionArray(sol, 10)
                if ph['thermo'] == 'liquid-water-IAPWS95':
                    # ensure that phase remains liquid
                    a.TP = sol.T, sol.critical_pressure

                # assign some state
                T = 373.15 + 100*np.random.rand(10)
                P = a.P * (1 + np.random.rand(10))
                if sol.is_pure:
                    a.TP = T, P
                else:
                    X = a.X
                    xmin = np.min(X[X>0])
                    ix = np.where(xmin)
                    X[ix] = .5 * X[ix]
                    X = np.diag(X.sum(axis=1)).dot(X)
                    self.assertFalse(sol.is_pure)
                    self.assertIn('TPX', sol._full_states.values())
                    a.TPX = T, P, X

                # default columns
                data = a.collect_data()
                b = ct.SolutionArray(sol)
                b.restore_data(data)
                check(a, b)

            except Exception as inst:

                # raise meaningful error message without breaking test suite
                # ignore deprecation warnings originating in C++ layer
                # (converted to errors in test suite)
                if 'Deprecated' not in str(inst):

                    msg = ("Error in processing of phase '{}' with type '{}'\n"
                           "TPX = {}")
                    msg = msg.format(ph['name'], ph['thermo'], sol.TPX)
                    raise TypeError(msg) from inst


class TestPickle(utilities.CanteraTest):

    def test_pickle_gas(self):
        gas = ct.Solution("h2o2.yaml", transport_model=None)
        gas.TPX = 500, 500000, "H2:.75,O2:.25"
        with open(self.test_work_path / "gas.pkl", "wb") as pkl:
            pickle.dump(gas, pkl)

        with open(self.test_work_path / "gas.pkl", "rb") as pkl:
            gas2 = pickle.load(pkl)
        self.assertNear(gas.T, gas2.T)
        self.assertNear(gas.P, gas2.P)
        self.assertArrayNear(gas.X, gas2.X)

        self.assertEqual(gas2.transport_model, "none")

    def test_pickle_gas_with_transport(self):
        gas = ct.Solution("h2o2.yaml")
        gas.TPX = 500, 500000, "H2:.75,O2:.25"
        gas.transport_model = "multicomponent"
        with open(self.test_work_path / "gas.pkl", "wb") as pkl:
            pickle.dump(gas, pkl)

        with open(self.test_work_path / "gas.pkl", "rb") as pkl:
            gas2 = pickle.load(pkl)
        self.assertNear(gas.T, gas2.T)
        self.assertNear(gas.P, gas2.P)
        self.assertArrayNear(gas.X, gas2.X)

        self.assertEqual(gas2.transport_model, "multicomponent")

    def test_pickle_interface(self):
        gas = ct.Solution("diamond.yaml", "gas")
        solid = ct.Solution("diamond.yaml", "diamond")
        interface = ct.Interface("diamond.yaml", "diamond_100", (gas, solid))

        with self.assertRaises(NotImplementedError):
            with open(self.test_work_path / "interface.pkl", "wb") as pkl:
                pickle.dump(interface, pkl)


class TestEmptyThermoPhase(utilities.CanteraTest):
    """ Test empty Solution object """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.gas = ct.ThermoPhase()

    def test_empty_report(self):
        with self.assertRaisesRegex(ct.CanteraError, "NotImplementedError"):
            self.gas()

    def test_empty_TP(self):
        with self.assertRaisesRegex(ct.CanteraError, "NotImplementedError"):
            self.gas.TP = 300, ct.one_atm

    def test_empty_equilibrate(self):
        with self.assertRaisesRegex(ct.CanteraError, "NotImplementedError"):
            self.gas.equilibrate("TP")


class TestEmptySolution(TestEmptyThermoPhase):
    """ Test empty Solution object """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.gas = ct.Solution()

    def test_empty_composite(self):
        self.assertEqual(self.gas.thermo_model, "none")
        self.assertEqual(self.gas.composite, ("none", "none", "none"))


class TestEmptyEdgeCases(utilities.CanteraTest):
    """ Test for edge cases where constructors are not allowed """
    def test_empty_phase(self):
        with self.assertRaisesRegex(ValueError, "Arguments are insufficient to define a phase"):
            ct.ThermoPhase(thermo="ideal-gas")

    def test_empty_kinetics(self):
        with self.assertRaisesRegex(ValueError, "Cannot instantiate"):
            ct.Kinetics()

    def test_empty_transport(self):
        with self.assertRaisesRegex(ValueError, "Cannot instantiate"):
            ct.Transport()


class TestSolutionArray(utilities.CanteraTest):
    """ Test SolutionArray file basics """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.gas = ct.Solution('h2o2.yaml', transport_model=None)

    def test_from_state_scalar(self):
        state = list(self.gas.state)
        arr = ct.SolutionArray(self.gas, states=[state])
        assert arr.shape == (1,)

    def test_from_state_list(self):
        states = [list(self.gas.state)] * 5
        arr = ct.SolutionArray(self.gas, states=states)
        assert arr.shape == (5,)

    def test_from_state_array(self):
        states = [[list(self.gas.state)] * 5] * 3
        arr = ct.SolutionArray(self.gas, states=states)
        assert arr.shape == (3, 5) # shape is based on numpy conversion

    def test_from_state_numpy(self):
        states = np.array([[list(self.gas.state)] * 5] * 3)
        arr = ct.SolutionArray(self.gas, states=states)
        assert arr.shape == (3, 5)

    def test_missing_attribute(self):
        arr = ct.SolutionArray(self.gas, 5, extra={"spam": 0})
        assert len(arr.spam) == 5
        with pytest.raises(AttributeError, match="no attribute"):
            arr.eggs

    def test_auxiliary(self):
        arr = ct.SolutionArray(self.gas, 5, extra={"spam": 0})
        arr.spam = np.arange(5)
        assert len(arr.spam) == 5
        assert arr.get_auxiliary(4) == {"spam": 4}
        arr.set_auxiliary(0, {"spam": 42})
        assert arr.spam[0] == 42


class TestSolutionArrayIO(utilities.CanteraTest):
    """ Test SolutionArray file IO """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.gas = ct.Solution('h2o2.yaml', transport_model=None)

    def test_collect_data(self):
        states = ct.SolutionArray(self.gas)
        collected = states.collect_data(tabular=True)
        self.assertIsInstance(collected, dict)
        self.assertIn('Y_H2', collected)
        self.assertEqual(len(collected['Y_H2']), 0)

        states = ct.SolutionArray(self.gas)
        collected = states.collect_data(tabular=False, species='X')
        self.assertIn('X', collected)
        self.assertEqual(collected['X'].shape, (0, self.gas.n_species))

    def test_getitem(self):
        states = ct.SolutionArray(self.gas, 10, extra={"index": range(10)})
        for ix, state in enumerate(states):
            assert state.index == ix

        assert list(states[:2].index) == [0, 1]
        assert list(states[100:102].index) == [] # outside of range

    def test_append_state(self):
        gas = ct.Solution("h2o2.yaml")
        gas.TPX = 300, ct.one_atm, 'H2:0.5, O2:0.4'
        states = ct.SolutionArray(gas)
        states.append(gas.state)
        self.assertEqual(states[0].T, gas.T)
        self.assertEqual(states[0].P, gas.P)
        self.assertArrayNear(states[0].X, gas.X)
        self.assertEqual(len(states), 1)
        self.assertEqual(states.shape, (1,))
        self.assertEqual(states.ndim, 1)
        self.assertEqual(states.size, 1)

    def test_append_no_norm_data(self):
        gas = ct.Solution("h2o2.yaml")
        gas.TP = 300, ct.one_atm
        gas.set_unnormalized_mass_fractions(np.full(gas.n_species, 0.3))
        states = ct.SolutionArray(gas)
        states.append(T=gas.T, P=gas.P, Y=gas.Y, normalize=False)
        self.assertEqual(states[0].T, gas.T)
        self.assertEqual(states[0].P, gas.P)
        self.assertArrayNear(states[0].Y, gas.Y)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_import_no_norm_data(self):
        outfile = self.test_work_path / "solutionarray_no_norm.h5"
        outfile.unlink(missing_ok=True)

        gas = ct.Solution("h2o2.yaml")
        gas.set_unnormalized_mole_fractions(np.full(gas.n_species, 0.3))
        states = ct.SolutionArray(gas, 5)
        states.save(outfile, "group0")

        gas_new = ct.Solution("h2o2.yaml")
        b = ct.SolutionArray(gas_new)
        b.restore(outfile, "group0") #, normalize=False)
        self.assertArrayNear(states.T, b.T)
        self.assertArrayNear(states.P, b.P)
        self.assertArrayNear(states.X, b.X)

    def test_write_csv(self):
        states = ct.SolutionArray(self.gas, 7)
        states.TPX = np.linspace(300, 1000, 7), 2e5, 'H2:0.5, O2:0.4'
        states.equilibrate('HP')

        outfile = self.test_work_path / "solutionarray.csv"
        states.write_csv(outfile)

        data = np.genfromtxt(outfile, names=True, delimiter=',')
        self.assertEqual(len(data), 7)
        self.assertEqual(len(data.dtype), self.gas.n_species + 2)
        self.assertIn('Y_H2', data.dtype.fields)

        b = ct.SolutionArray(self.gas)
        b.read_csv(outfile)
        self.assertArrayNear(states.T, b.T)
        self.assertArrayNear(states.P, b.P)
        self.assertArrayNear(states.X, b.X)

    def test_write_csv_single_row(self):
        gas = ct.Solution("gri30.yaml")
        states = ct.SolutionArray(gas)
        states.append(T=300., P=ct.one_atm, X="CH4:0.5, O2:0.4")
        states.equilibrate("HP")

        outfile = self.test_work_path / "solutionarray.csv"
        states.write_csv(outfile)

        b = ct.SolutionArray(gas)
        b.read_csv(outfile)
        self.assertArrayNear(states.T, b.T)
        self.assertArrayNear(states.P, b.P)
        self.assertArrayNear(states.X, b.X)

    def test_write_csv_str_column(self):
        states = ct.SolutionArray(self.gas, 3, extra={'spam': 'eggs'})

        outfile = self.test_work_path / "solutionarray.csv"
        states.write_csv(outfile)

        b = ct.SolutionArray(self.gas, extra={'spam'})
        b.read_csv(outfile)
        self.assertEqual(list(states.spam), list(b.spam))

    def test_write_csv_multidim_column(self):
        states = ct.SolutionArray(self.gas, 3, extra={'spam': np.zeros((3, 5,))})

        outfile = self.test_work_path / "solutionarray.csv"
        with self.assertRaisesRegex(NotImplementedError, 'not supported'):
            states.write_csv(outfile)

    @utilities.unittest.skipIf(_pandas is None, "pandas is not installed")
    def test_to_pandas(self):
        states = ct.SolutionArray(self.gas, 7, extra={"props": range(7)})
        states.TPX = np.linspace(300, 1000, 7), 2e5, 'H2:0.5, O2:0.4'
        df = states.to_pandas()
        self.assertEqual(df.shape[0], 7)
        states.props = np.zeros((7,2,))
        with self.assertRaisesRegex(NotImplementedError, 'not supported'):
            states.to_pandas()

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    @utilities.unittest.skipIf(_h5py is None, "h5py is not installed")
    def test_write_hdf(self):
        outfile = self.test_work_path / "solutionarray_fancy.h5"
        outfile.unlink(missing_ok=True)

        extra = {'foo': range(7), 'bar': range(7)}
        meta = {'spam': 'eggs', 'hello': 'world'}
        states = ct.SolutionArray(self.gas, 7, extra=extra, meta=meta)
        states.TPX = np.linspace(300, 1000, 7), 2e5, 'H2:0.5, O2:0.4'
        states.equilibrate('HP')

        states.save(outfile, "group0")

        b = ct.SolutionArray(self.gas)
        attr = b.restore(outfile, "group0")
        self.assertArrayNear(states.T, b.T)
        self.assertArrayNear(states.P, b.P)
        self.assertArrayNear(states.X, b.X)
        self.assertArrayNear(states.foo, b.foo)
        self.assertArrayNear(states.bar, b.bar)
        self.assertEqual(b.meta['spam'], 'eggs')
        self.assertEqual(b.meta['hello'], 'world')

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_write_hdf_str_column(self):
        self.run_write_str_column("h5")

    def test_write_yaml_str_column(self):
        self.run_write_str_column("yaml")

    def run_write_str_column(self, mode):
        outfile = self.test_work_path / f"solutionarray_str.{mode}"
        outfile.unlink(missing_ok=True)

        states = ct.SolutionArray(self.gas, 3, extra={'spam': 'eggs'})
        states.save(outfile, "arr")

        b = ct.SolutionArray(self.gas, extra={'spam'})
        b.restore(outfile, "arr")
        self.assertEqual(list(states.spam), list(b.spam))

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_write_hdf_multidim_column(self):
        self.run_write_multidim_column("h5")

    def test_write_yaml_multidim_column(self):
        self.run_write_multidim_column("yaml")

    def run_write_multidim_column(self, mode):
        outfile = self.test_work_path / f"solutionarray_multi.{mode}"
        outfile.unlink(missing_ok=True)

        states = ct.SolutionArray(self.gas, 3, extra={'spam': [[1, 2], [3, 4], [5, 6]]})
        states.save(outfile, "arr")

        b = ct.SolutionArray(self.gas, extra={'spam'})
        b.restore(outfile, "arr")
        self.assertArrayNear(states.spam, b.spam)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_write_hdf_2d(self):
        self.run_write_2d("h5")

    def test_write_yaml_2d(self):
        self.run_write_2d("yaml")

    def run_write_2d(self, mode):
        outfile = self.test_work_path / f"solutionarray_2d.{mode}"
        outfile.unlink(missing_ok=True)

        states = ct.SolutionArray(self.gas, (2, 5))
        states.save(outfile, "arr")

        b = ct.SolutionArray(self.gas)
        b.restore(outfile, "arr")
        assert b.shape == states.shape

class TestLegacyHDF(utilities.CanteraTest):
    # Test SolutionArray legacy HDF file input
    #
    # All input files were created using the Cantera 2.6 Python test suite:
    # - solutionarray_fancy_legacy.h5
    #   -> test_composite.py::TestSolutionArrayIO::test_write_hdf
    # - solutionarray_str_legacy.h5
    #   -> test_composite.py::TestSolutionArrayIO::test_write_hdf_str_column
    # - solutionarray_multi_legacy.h5
    #   -> test_composite.py::TestSolutionArrayIO::test_write_hdf_multi_column
    # - solutionarray_no_norm_legacy.h5
    #   -> test_composite.py::TestSolutionArrayIO::test_import_no_norm_data
    # - solutionarray_water_legacy.h5
    #   -> test_composite.py::TestRestorePureFluid::test_import_no_norm_water

    def setUp(self):
        self.gas = ct.Solution('h2o2.yaml', transport_model=None)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif("h5py" not in ct.hdf_support(), reason="h5py is not installed")
    def test_legacy_hdf_str_column_h5py(self):
        self.run_read_legacy_hdf_str_column(legacy=True)

    @pytest.mark.xfail(reason="Unable to read fixed length strings from HDF")
    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_legacy_hdf_str_column(self):
        # h5py writes strings with fixed length, which require a priori knowledge of
        # length in order to be read with HighFive (which currently only supports
        # fixed string lengths based on compile-time templates)
        self.run_read_legacy_hdf_str_column()

    def run_read_legacy_hdf_str_column(self, legacy=False):
        # recreate states used to create legacy HDF file
        arr = ct.SolutionArray(self.gas, 3, extra={'spam': 'eggs'})

        b = ct.SolutionArray(self.gas, extra={'spam'})
        infile = self.test_data_path / f"solutionarray_str_legacy.h5"

        if legacy:
            b.read_hdf(infile)
        else:
            b.restore(infile, "group0")
        assert all(arr.spam == b.spam)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif("h5py" not in ct.hdf_support(), reason="h5py is not installed")
    def test_legacy_hdf_multidim_h5py(self):
        self.run_read_legacy_hdf_multidim(legacy=True)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_legacy_hdf_multidim(self):
        self.run_read_legacy_hdf_multidim()

    def run_read_legacy_hdf_multidim(self, legacy=False):
        # recreate states used to create legacy HDF file
        arr = ct.SolutionArray(self.gas, 3, extra={'spam': [[1, 2], [3, 4], [5, 6]]})
        b = ct.SolutionArray(self.gas, extra={'spam'})
        infile = self.test_data_path / f"solutionarray_multi_legacy.h5"

        if legacy:
            b.read_hdf(infile)
        else:
            b.restore(infile, "group0")
        self.assertArrayNear(arr.spam, b.spam)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif(ct.hdf_support() != {"native", "h5py"},
                        reason="Both HDF support modes needed")
    def test_deprecated_write_read_hdf(self):
        # recreate states used to create legacy HDF file
        arr = ct.SolutionArray(self.gas, 3, extra={'spam': [[1, 2], [3, 4], [5, 6]]})
        outfile = self.test_work_path / "solutionarray_deprecated.h5"
        outfile.unlink(missing_ok=True)

        with pytest.raises(KeyError, match="Missing required parameter 'group'"):
            arr.write_hdf(outfile, "group0")

        with pytest.warns(DeprecationWarning, match="use 'save' instead"):
            # New HDF format is written regardless via 'save'
            arr.write_hdf(outfile, group="group0")

        b = ct.SolutionArray(self.gas)
        with pytest.raises(IOError, match="use 'restore' instead"):
            # New HDF format should not be read with 'read_hdf'
            with pytest.warns(DeprecationWarning, match="use 'restore' instead"):
                # DeprecationWarning is triggered before IOError is raised
                b.read_hdf(outfile, group="group0")

        meta = b.restore(outfile, "group0")
        assert meta["generator"] == "Cantera SolutionArray"
        self.assertArrayNear(arr.spam, b.spam)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif("h5py" not in ct.hdf_support(), reason="h5py is not installed")
    def test_legacy_hdf_h5py(self):
        self.run_legacy_hdf(legacy=True)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_legacy_hdf(self):
        self.run_legacy_hdf()

    def run_legacy_hdf(self, legacy=False):
        # recreate states used to create legacy HDF file (valid portion)
        extra = {'foo': range(7), 'bar': range(7)}
        meta = {'spam': 'eggs', 'hello': 'world'}
        states = ct.SolutionArray(self.gas, 7, extra=extra, meta=meta)
        states.TPX = np.linspace(300, 1000, 7), 2e5, 'H2:0.5, O2:0.4'
        states.equilibrate('HP')

        infile = self.test_data_path / f"solutionarray_fancy_legacy.h5"
        b = ct.SolutionArray(self.gas)
        if legacy:
            attr = b.read_hdf(infile)
        else:
            attr = b.restore(infile, "group0")
        self.assertArrayNear(states.T, b.T)
        self.assertArrayNear(states.P, b.P)
        self.assertArrayNear(states.X, b.X)
        self.assertArrayNear(states.foo, b.foo)
        self.assertArrayNear(states.bar, b.bar)
        self.assertEqual(b.meta['spam'], 'eggs')
        self.assertEqual(b.meta['hello'], 'world')
        self.assertEqual(attr['foobar'], 'spam and eggs')

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif("h5py" not in ct.hdf_support(), reason="h5py is not installed")
    def test_read_legacy_hdf_no_norm_h5py(self):
        self.run_read_legacy_hdf_no_norm(legacy=True)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_read_legacy_hdf_no_norm(self):
        self.run_read_legacy_hdf_no_norm()

    def run_read_legacy_hdf_no_norm(self, legacy=False):
        # recreate states used to create legacy HDF file
        self.gas.set_unnormalized_mole_fractions(np.full(self.gas.n_species, 0.3))
        states = ct.SolutionArray(self.gas, 5)

        infile = self.test_data_path / "solutionarray_no_norm_legacy.h5"

        b = ct.SolutionArray(self.gas)
        if legacy:
            b.read_hdf(infile, normalize=False)
        else:
            b.restore(infile, "group0")
        self.assertArrayNear(states.T, b.T, rtol=1e-7)
        self.assertArrayNear(states.P, b.P, rtol=1e-7)
        self.assertArrayNear(states.X, b.X, rtol=1e-7)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif("h5py" not in ct.hdf_support(), reason="h5py is not installed")
    def test_import_no_norm_water_h5py(self):
        self.run_import_no_norm_water(legacy=True)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_import_no_norm_water(self):
        self.run_import_no_norm_water()

    def run_import_no_norm_water(self, legacy=False):
        # recreate states used to create legacy HDF file
        w = ct.Water()
        w.TQ = 300, 0.5
        states = ct.SolutionArray(w, 5)

        w_new = ct.Water()
        infile = self.test_data_path / "solutionarray_water_legacy.h5"
        c = ct.SolutionArray(w_new)
        if legacy:
            c.read_hdf(infile, normalize=False)
        else:
            c.restore(infile, "group0")
        self.assertArrayNear(states.T, c.T, rtol=1e-7)
        self.assertArrayNear(states.P, c.P, rtol=1e-7)
        self.assertArrayNear(states.Q, c.Q, rtol=1e-7)

    @pytest.mark.usefixtures("allow_deprecated")
    @pytest.mark.skipif(ct.hdf_support() != {"native", "h5py"},
                        reason="Both HDF support modes needed")
    def test_new_hdf_h5py_exception(self):
        outfile = self.test_work_path / f"solutionarray_new.h5"
        outfile.unlink(missing_ok=True)

        states = ct.SolutionArray(self.gas, 3, extra={'spam': [[1, 2], [3, 4], [5, 6]]})
        states.save(outfile, "arr")

        b = ct.SolutionArray(self.gas, extra={'spam'})
        with pytest.raises(IOError, match="Cantera 3.0 HDF format"):
            b.read_hdf(outfile, "arr") # h5py file should not read new format


class TestRestoreIdealGas(utilities.CanteraTest):
    """ Test restoring of the IdealGas class """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.gas = ct.Solution('h2o2.yaml', transport_model=None)

    def test_restore_gas(self):

        def check(a, b, atol=None):
            if atol is None:
                self.assertArrayNear(a.T, b.T)
                self.assertArrayNear(a.P, b.P)
                self.assertArrayNear(a.X, b.X)
            else:
                self.assertArrayNear(a.T, b.T, atol=atol)
                self.assertArrayNear(a.P, b.P, atol=atol)
                self.assertArrayNear(a.X, b.X, atol=atol)

        # test ThermoPhase
        a = ct.SolutionArray(self.gas)
        for i in range(10):
            T = 300 + 1800*np.random.random()
            P = ct.one_atm*(1 + 10*np.random.random())
            X = np.random.random(self.gas.n_species)
            X[-1] = 0.
            X /= X.sum()
            a.append(T=T, P=P, X=X)

        data = a.collect_data()

        # basic restore
        b = ct.SolutionArray(self.gas)
        b.restore_data(data, normalize=True)
        check(a, b)

        # skip concentrations
        b = ct.SolutionArray(self.gas)
        b.restore_data({'T': data['T'], 'density': data['density']})
        self.assertArrayNear(a.T, b.T)
        self.assertArrayNear(a.density, b.density)
        self.assertFalse(np.allclose(a.X, b.X))

        # wrong data shape
        b = ct.SolutionArray(self.gas)
        with self.assertRaises(ValueError):
            b.restore_data(OrderedDict([(k, v[np.newaxis, :])
                                        for k, v in data.items()]))

        # inconsistent shape of receiving SolutionArray
        b = ct.SolutionArray(self.gas, 9)
        with self.assertRaises(ValueError):
            b.restore_data(data)

        # incomplete state
        b = ct.SolutionArray(self.gas)
        with self.assertRaises(ValueError):
            b.restore_data(OrderedDict([tup for i, tup in enumerate(data.items())
                                        if i]))

        # add extra column
        t = np.arange(10, dtype=float)

        # auto-detection of extra
        b = ct.SolutionArray(self.gas)
        data_mod = OrderedDict(data)
        data_mod['time'] = t
        b.restore_data(data_mod)
        check(a, b)

        # explicit extra
        b = ct.SolutionArray(self.gas, extra=('time',))
        b.restore_data(data_mod)
        check(a, b)
        self.assertArrayNear(b.time, t)

        # wrong extra
        b = ct.SolutionArray(self.gas, extra=('xyz',))
        with self.assertRaises(KeyError):
            b.restore_data(data_mod)

        # missing extra
        b = ct.SolutionArray(self.gas, extra=('time'))
        with self.assertRaises(KeyError):
            b.restore_data(data)

        # inconsistent species
        data_mod = a.collect_data(tabular=True)
        val = data_mod.pop('Y_AR')
        data_mod['Y_invalid'] = val
        b = ct.SolutionArray(self.gas)
        with self.assertRaises(ValueError):
            b.restore_data(data_mod)

        # incomplete species info (using threshold)
        data = a.collect_data(threshold=1e-6)

        # basic restore
        b = ct.SolutionArray(self.gas)
        b.restore_data(data)
        check(a, b, atol=1e-6)

        # skip calculated properties
        cols = ('T', 'P', 'X', 'gibbs_mass', 'forward_rates_of_progress')
        data = a.collect_data(cols=cols, threshold=1e-6)

        b = ct.SolutionArray(self.gas)
        b.restore_data(data)
        check(a, b)
        self.assertEqual(len(b.extra), 0)


class TestRestorePureFluid(utilities.CanteraTest):
    """ Test restoring of the PureFluid class """
    @classmethod
    def setUpClass(cls):
        utilities.CanteraTest.setUpClass()
        cls.water = ct.Water()

    def test_restore_water(self):

        def check(a, b):
            self.assertArrayNear(a.T, b.T)
            self.assertArrayNear(a.P, b.P)
            self.assertArrayNear(a.Q, b.Q)

        self.assertTrue(self.water.has_phase_transition)

        # benchmark
        a = ct.SolutionArray(self.water, 10)
        a.TQ = 373.15, np.linspace(0., 1., 10)

        # complete data
        cols = ('T', 'P', 'Q')
        data = a.collect_data(cols=cols)
        b = ct.SolutionArray(self.water)
        b.restore_data(data)
        check(a, b)

        # partial data
        cols = ('T', 'Q')
        data = a.collect_data(cols=cols)
        b = ct.SolutionArray(self.water)
        b.restore_data(data)
        check(a, b)

        # default columns
        data = a.collect_data()
        self.assertEqual(list(data.keys()), ['T', 'density'])
        b = ct.SolutionArray(self.water)
        b.restore_data(data)
        check(a, b)

        # default state plus Y
        cols = ('T', 'D', 'Y')
        data = a.collect_data(cols=cols)
        b = ct.SolutionArray(self.water)
        b.restore_data(data)
        check(a, b)

    @pytest.mark.skipif("native" not in ct.hdf_support(),
                        reason="Cantera compiled without HDF support")
    def test_import_no_norm_water(self):
        outfile = self.test_work_path / "solutionarray_water.h5"
        outfile.unlink(missing_ok=True)

        w = ct.Water()
        w.TQ = 300, 0.5
        states = ct.SolutionArray(w, 5)
        states.save(outfile, "group0")

        w_new = ct.Water()
        c = ct.SolutionArray(w_new)
        c.restore(outfile, "group0") # normalize=False)
        self.assertArrayNear(states.T, c.T)
        self.assertArrayNear(states.P, c.P)
        self.assertArrayNear(states.Q, c.Q)

    def test_append_no_norm_water(self):
        w = ct.Water()
        states = ct.SolutionArray(w)
        w.TQ = 300, 0.5
        states.append(w.state)
        self.assertEqual(states[0].T, w.T)
        self.assertEqual(states[0].P, w.P)
        self.assertEqual(states[0].Q, w.Q)

    def test_phase_of_matter(self):
        # based on test_thermo.py::TestSolutionArray::test_phase_of_matter
        outfile = self.test_work_path / "solutionarray_pom.yaml"
        outfile.unlink(missing_ok=True)

        water = ct.Water()
        states = ct.SolutionArray(water, 5)
        T = [300, 500, water.critical_temperature * 2, 300]
        P = [101325, 101325, 101325, water.critical_pressure*2]
        states[:4].TP = T, P
        states[4].TQ = 300, .4
        pom = ['liquid', 'gas', 'supercritical', 'supercritical', 'liquid-gas-mix']
        self.assertEqual(list(states.phase_of_matter), pom)
        states.save(outfile, "group0")

        saved = ct.SolutionArray(water)
        saved.restore(outfile, "group0") # normalize=False)
        self.assertArrayNear(states.T, saved.T)
        self.assertArrayNear(states.P, saved.P)
        self.assertArrayNear(states.Q, saved.Q)
        self.assertEqual(list(saved.phase_of_matter), pom)


class TestSolutionSerialization(utilities.CanteraTest):
    def test_input_data_simple(self):
        gas = ct.Solution('h2o2.yaml')
        data = gas.input_data
        self.assertEqual(data['name'], 'ohmech')
        self.assertEqual(data['thermo'], 'ideal-gas')
        self.assertEqual(data['kinetics'], 'gas')
        self.assertEqual(data['transport'], 'mixture-averaged')

    def test_input_data_user_modifications(self):
        gas = ct.Solution("h2o2.yaml")
        data1 = gas.input_data
        gas.update_user_data({"foo": True})  # should get overwritten
        extra = {"foo": [1.2, 3.4], "bar": [[1, 2], [3, 4]]}
        gas.update_user_data(extra)
        data2 = gas.input_data
        self.assertEqual(extra["foo"], data2["foo"])
        self.assertEqual(extra["bar"], data2["bar"])
        gas.clear_user_data()
        data3 = gas.input_data
        self.assertEqual(data1, data3)

    def test_input_data_state(self):
        gas = ct.Solution('h2o2.yaml', transport_model=None)
        data = gas.input_data
        self.assertEqual(gas.T, data['state']['T'])
        self.assertEqual(gas.density, data['state']['density'])

        gas.TP = 500, 3.14e5
        data = gas.input_data
        self.assertEqual(gas.T, data['state']['T'])
        self.assertEqual(gas.density, data['state']['density'])

    def test_input_data_custom(self):
        gas = ct.Solution('ideal-gas.yaml')
        data = gas.input_data
        self.assertEqual(data['custom-field']['first'], True)
        self.assertEqual(data['custom-field']['last'], [100, 200, 300])

        if sys.version_info >= (3,7):
            # Check that items are ordered as expected
            self.assertEqual(
                list(data),
                ["name", "thermo", "elements", "species", "state",
                 "custom-field", "literal-string"]
            )
            self.assertEqual(list(data["custom-field"]), ["first", "second", "last"])
            self.assertEqual(data["literal-string"], "spam\nand\neggs\n")

    def test_input_data_debye_huckel(self):
        soln = ct.Solution('thermo-models.yaml', 'debye-huckel-B-dot-ak')
        data = soln.input_data
        self.assertEqual(data['thermo'], 'Debye-Huckel')
        act_data = data['activity-data']
        self.assertEqual(act_data['model'], 'B-dot-with-variable-a')
        self.assertEqual(act_data['default-ionic-radius'], 4e-10)
        self.assertNotIn('kinetics', data)
        self.assertNotIn('transport', data)

    def test_yaml_simple(self):
        gas = ct.Solution('h2o2.yaml')
        gas.TPX = 500, ct.one_atm, 'H2: 1.0, O2: 1.0'
        gas.equilibrate('HP')
        gas.TP = 1500, ct.one_atm
        gas.write_yaml(self.test_work_path / "h2o2-generated.yaml")
        generated = utilities.load_yaml(self.test_work_path / "h2o2-generated.yaml")
        for key in ('generator', 'date', 'phases', 'species', 'reactions'):
            self.assertIn(key, generated)
        self.assertEqual(generated['phases'][0]['transport'], 'mixture-averaged')
        for i, species in enumerate(generated['species']):
            self.assertEqual(species['composition'], gas.species(i).composition)
        for blessed, generated in zip(gas.reactions(), generated["reactions"]):
            assert blessed.equation == generated["equation"]

        gas2 = ct.Solution(self.test_work_path / "h2o2-generated.yaml")
        self.assertArrayNear(gas.concentrations, gas2.concentrations)
        self.assertArrayNear(gas.partial_molar_enthalpies,
                             gas2.partial_molar_enthalpies)
        self.assertArrayNear(gas.forward_rate_constants,
                             gas2.forward_rate_constants)
        self.assertArrayNear(gas.mix_diff_coeffs, gas2.mix_diff_coeffs)

    def test_yaml_outunits1(self):
        gas = ct.Solution('h2o2.yaml')
        gas.TPX = 500, ct.one_atm, 'H2: 1.0, O2: 1.0'
        gas.equilibrate('HP')
        gas.TP = 1500, ct.one_atm
        units = {'length': 'cm', 'quantity': 'mol', 'energy': 'cal'}
        gas.write_yaml(self.test_work_path / "h2o2-generated.yaml", units=units)
        generated = utilities.load_yaml(self.test_work_path / "h2o2-generated.yaml")
        original = utilities.load_yaml(self.cantera_data_path / "h2o2.yaml")
        self.assertEqual(generated['units'], units)

        for r1, r2 in zip(original['reactions'], generated['reactions']):
            if 'rate-constant' in r1:
                self.assertNear(r1['rate-constant']['A'], r2['rate-constant']['A'])
                self.assertNear(r1['rate-constant']['Ea'], r2['rate-constant']['Ea'])

        gas2 = ct.Solution(self.test_work_path / "h2o2-generated.yaml")
        self.assertArrayNear(gas.concentrations, gas2.concentrations)
        self.assertArrayNear(gas.partial_molar_enthalpies,
                             gas2.partial_molar_enthalpies)
        self.assertArrayNear(gas.forward_rate_constants,
                             gas2.forward_rate_constants)
        self.assertArrayNear(gas.mix_diff_coeffs, gas2.mix_diff_coeffs)

    def test_yaml_outunits2(self):
        gas = ct.Solution('h2o2.yaml')
        gas.TPX = 500, ct.one_atm, 'H2: 1.0, O2: 1.0'
        gas.equilibrate('HP')
        gas.TP = 1500, ct.one_atm
        units = {'length': 'cm', 'quantity': 'mol', 'energy': 'cal'}
        system = ct.UnitSystem(units)
        gas.write_yaml(self.test_work_path / "h2o2-generated.yaml", units=system)
        generated = utilities.load_yaml(self.test_work_path / "h2o2-generated.yaml")
        original = utilities.load_yaml(self.cantera_data_path / "h2o2.yaml")

        for r1, r2 in zip(original['reactions'], generated['reactions']):
            if 'rate-constant' in r1:
                self.assertNear(r1['rate-constant']['A'], r2['rate-constant']['A'])
                self.assertNear(r1['rate-constant']['Ea'], r2['rate-constant']['Ea'])

        gas2 = ct.Solution(self.test_work_path / "h2o2-generated.yaml")
        self.assertArrayNear(gas.concentrations, gas2.concentrations)
        self.assertArrayNear(gas.partial_molar_enthalpies,
                             gas2.partial_molar_enthalpies)
        self.assertArrayNear(gas.forward_rate_constants,
                             gas2.forward_rate_constants)
        self.assertArrayNear(gas.mix_diff_coeffs, gas2.mix_diff_coeffs)

    def check_ptcombust(self, gas, surf):
        generated = utilities.load_yaml(self.test_work_path / "ptcombust-generated.yaml")
        for key in ("phases", "species", "gas-reactions", "Pt_surf-reactions"):
            self.assertIn(key, generated)
        self.assertEqual(len(generated["gas-reactions"]), gas.n_reactions)
        self.assertEqual(len(generated["Pt_surf-reactions"]), surf.n_reactions)
        self.assertEqual(len(generated["species"]), surf.n_total_species)

        surf2 = ct.Solution(self.test_work_path / "ptcombust-generated.yaml", "Pt_surf")
        self.assertArrayNear(surf.concentrations, surf2.concentrations)
        self.assertArrayNear(surf.partial_molar_enthalpies,
                             surf2.partial_molar_enthalpies)
        self.assertArrayNear(surf.forward_rate_constants,
                             surf2.forward_rate_constants)

    def test_yaml_surface_explicit(self):
        gas = ct.Solution("ptcombust.yaml", "gas")
        surf = ct.Interface("ptcombust.yaml", "Pt_surf", [gas])
        gas.TPY = 900, ct.one_atm, np.ones(gas.n_species)
        surf.coverages = np.ones(surf.n_species)
        surf.write_yaml(self.test_work_path / "ptcombust-generated.yaml")
        self.check_ptcombust(gas, surf)

    def test_yaml_surface_adjacent(self):
        surf = ct.Interface("ptcombust.yaml", "Pt_surf")
        gas = surf.adjacent["gas"]
        gas.TPY = 900, ct.one_atm, np.ones(gas.n_species)
        surf.coverages = np.ones(surf.n_species)
        surf.write_yaml(self.test_work_path / "ptcombust-generated.yaml")
        self.check_ptcombust(gas, surf)

    def test_yaml_eos(self):
        ice = ct.Solution('water.yaml', 'ice')
        ice.TP = 270, 2 * ct.one_atm
        ice.write_yaml(self.test_work_path / "ice-generated.yaml", units={'length': 'mm', 'mass': 'g'})

        ice2 = ct.Solution(self.test_work_path / "ice-generated.yaml")
        self.assertNear(ice.density, ice2.density)
        self.assertNear(ice.entropy_mole, ice2.entropy_mole)

    def test_yaml_inconsistent_species(self):
        gas = ct.Solution('h2o2.yaml', transport_model=None)
        gas2 = ct.Solution('h2o2.yaml', transport_model=None)
        gas2.name = 'modified'
        # modify the NASA coefficients for one species
        h2 = gas2.species('H2')
        nasa_coeffs = h2.thermo.coeffs
        nasa_coeffs[1] += 0.1
        nasa_coeffs[8] += 0.1
        h2.thermo = ct.NasaPoly2(h2.thermo.min_temp, h2.thermo.max_temp,
                                 h2.thermo.reference_pressure, nasa_coeffs)
        gas2.modify_species(gas2.species_index('H2'), h2)
        with self.assertRaisesRegex(ct.CanteraError, "different definitions"):
            gas.write_yaml(self.test_work_path / "h2o2-error.yaml", phases=gas2)

    def test_yaml_user_data(self):
        gas = ct.Solution("h2o2.yaml")
        extra = {"spam": {"A": 1, "B": 2}, "eggs": [1, 2.3, 4.5]}
        gas.update_user_data(extra)
        S = gas.species(2)
        S.update_user_data({"foo": "bar"})
        S.transport.update_user_data({"baz": 1234.5})
        S.thermo.update_user_data({"something": (False, True)})
        gas.reaction(5).update_user_data({"baked-beans": True})

        gas.write_yaml(self.test_work_path / "h2o2-generated-user-data.yaml")
        gas2 = ct.Solution(self.test_work_path / "h2o2-generated-user-data.yaml")
        data2 = gas2.species(2).input_data

        self.assertEqual(gas2.input_data["spam"], extra["spam"])
        self.assertEqual(gas2.input_data["eggs"], extra["eggs"])
        self.assertEqual(data2["foo"], "bar")
        self.assertEqual(data2["transport"]["baz"], 1234.5)
        self.assertEqual(data2["thermo"]["something"], [False, True])
        self.assertTrue(gas2.reaction(5).input_data["baked-beans"])


class TestSpeciesSerialization(utilities.CanteraTest):
    def test_species_simple(self):
        gas = ct.Solution('h2o2.yaml', transport_model=None)
        data = gas.species('H2O').input_data
        self.assertEqual(data['name'], 'H2O')
        self.assertEqual(data['composition'], {'H': 2, 'O': 1})

    def test_species_thermo(self):
        gas = ct.Solution('h2o2.yaml', transport_model=None)
        data = gas.species('H2O').input_data['thermo']
        self.assertEqual(data['model'], 'NASA7')
        self.assertEqual(data['temperature-ranges'], [200, 1000, 3500])
        self.assertEqual(data['note'], 'L8/89')

    def test_species_transport(self):
        gas = ct.Solution('h2o2.yaml')
        data = gas.species('H2O').input_data['transport']
        self.assertEqual(data['model'], 'gas')
        self.assertEqual(data['geometry'], 'nonlinear')
        self.assertNear(data['dipole'], 1.844)


class TestInterfaceAdjacent(utilities.CanteraTest):
    def test_surface(self):
        surf = ct.Interface("ptcombust.yaml", "Pt_surf")
        self.assertEqual(list(surf.adjacent), ["gas"])
        self.assertEqual(surf.phase_index(surf), 0)
        self.assertEqual(surf.phase_index("gas"), 1)
        self.assertEqual(surf.phase_index(surf.adjacent["gas"]), 1)

    def test_named_adjacent(self):
        # override the adjacent-phases to change the order
        surf = ct.Interface("surface-phases.yaml", "anode-surface",
                            adjacent=["electrolyte", "graphite"])
        self.assertEqual(list(surf.adjacent), ["electrolyte", "graphite"])

    def test_edge(self):
        tpb = ct.Interface("sofc.yaml", "tpb")
        self.assertEqual(set(tpb.adjacent), {"metal_surface", "oxide_surface", "metal"})
        self.assertIsInstance(tpb.adjacent["metal_surface"], ct.Interface)
        self.assertNotIsInstance(tpb.adjacent["metal"], ct.Interface)
        gas1 = tpb.adjacent["metal_surface"].adjacent["gas"]
        gas2 = tpb.adjacent["oxide_surface"].adjacent["gas"]
        gas1.X = [0.1, 0.4, 0.3, 0.2]
        self.assertArrayNear(gas1.X, gas2.X)

    def test_invalid(self):
        with self.assertRaisesRegex(ct.CanteraError, "does not contain"):
            surf = ct.Interface("ptcombust.yaml", "Pt_surf", ["foo"])

        with self.assertRaises(TypeError):
            surf = ct.Interface("ptcombust.yaml", "Pt_surf", [2])

    def test_remote_file(self):
        yaml = """
        phases:
        - name: Pt_surf
          thermo: ideal-surface
          adjacent-phases: [{ptcombust.yaml/phases: [gas]}]
          species: [{ptcombust.yaml/species: all}]
          kinetics: surface
          reactions: [{ptcombust.yaml/reactions: all}]
          site-density: 2.7063e-09
        """

        surf = ct.Interface(yaml=yaml)
        self.assertEqual(surf.adjacent["gas"].n_species, 32)
        self.assertEqual(surf.n_reactions, 24)
