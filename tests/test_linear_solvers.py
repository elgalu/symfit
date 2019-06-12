from __future__ import division, print_function
import unittest
import warnings

import numpy as np

from symfit import (
    MatrixSymbol, Fit, CallableModel, Parameter, Ge
)
from symfit.core.linear_solvers import LstSq, LstSqBounds
from symfit.core.objectives import LeastSquares
from symfit.core.minimizers import BFGS
from symfit.core.models import ModelError
from symfit.core.support import key2str


class TestLinearSolvers(unittest.TestCase):
    def setUp(self):
        np.random.seed(0)
        A_mat = np.array([[3, 1], [1, 2]])
        y_mat = np.array([[9], [8]])

        L = M = 2
        N = 1

        x = MatrixSymbol(Parameter('x'), M, N)
        A = MatrixSymbol('A', L, M)
        y = MatrixSymbol('y', L, N)

        self.simple_model = CallableModel({y: A * x})
        self.data = {A: A_mat, y: y_mat}

        x = MatrixSymbol(Parameter('x_bounded', min=np.array([[2.1], [2.5]])), M, N)
        A = MatrixSymbol('A', L, M)
        y = MatrixSymbol('y', L, N)

        self.bounded_model = CallableModel({y: A * x})

    def test_unbounded(self):
        for Solver in [LstSq, LstSqBounds]:
            solver = Solver(self.simple_model, data=self.data)
            ans = solver.execute()
            np.testing.assert_almost_equal(ans.params['x'], np.array([[2.], [3.]]))

    def test_fit(self):
        """
        Fit should be able to decide between the minimizers on the fly.
        :return:
        """
        results = {}
        for model, Solver in [(self.simple_model, LstSq),
                              (self.bounded_model, LstSqBounds)]:
            fit = Fit(model, **key2str(self.data))
            self.assertIsInstance(fit.linear_solver, Solver)
            fit_result = fit.execute()
            results[Solver] = fit_result

        np.testing.assert_almost_equal(results[LstSq].params['x'],
                                       np.array([[2.], [3.]]))
        np.testing.assert_almost_equal(results[LstSqBounds].params['x_bounded'],
                                       np.array([[2.1], [2.85]]))

    def test_numpy_lsqtsqbounds(self):
        solver = LstSqBounds(self.bounded_model, data=self.data)
        ans = solver.execute()
        lb, ub = self.bounded_model.bounds[0]
        self.assertTrue(np.all(ans.params['x_bounded'] >= lb))
        self.assertTrue(np.all(ans.params['x_bounded'] < ub))


    def test_nodata(self):
        solver = LstSq(self.simple_model, data={})
        with self.assertRaises(TypeError):
            solver.execute()

    def test_nonlinear_problems(self):
        L = M = 2
        x = MatrixSymbol(Parameter('x'), M, M)
        A = MatrixSymbol('A', L, M)
        y = MatrixSymbol('y', L, M)

        model = CallableModel({y: A * x**2})
        solver = LstSq(model, data={})
        with self.assertRaises(ModelError):
            solver.execute()

    @unittest.skip
    def test_linear_programming(self):
        """
        Do a simple linear programming problem taken from
        https://www.math.ucla.edu/~tom/LP.pdf

        TODO: Make this actually work
        """
        A_mat = [[1, 2], [4, 2], [-1, 1]]
        y_mat = [[4], [12], [1]]
        c_mat = np.ones((2, 1))

        x = MatrixSymbol(Parameter('x', min=0), 2, 1)
        A = MatrixSymbol('A', 3, 2)
        y = MatrixSymbol('y', 3, 1)
        c = MatrixSymbol('c', 2, 1)  # Coefficient matrix
        f = MatrixSymbol('f', 1, 1)

        # Minus sign for maximization
        model = CallableModel({f: - c.T * x})
        constraint = CallableModel.as_constraint(
            {y: A * x}, constraint_type=Ge, model=model
        )

        fit = Fit(model, A=A_mat, y=y_mat, c=c_mat, f=None,
                  constraints=[constraint])
        fit_result = fit.execute()

    def test_linear_subproblem(self):
        """
        Test a model with a Matrix parameter in it. The invariant of a model
        should always be::

            model(**independent_data, **fit_result.params)

        """
        N = 20
        I_mat = np.eye(N)
        s = np.linspace(1, 10, N)
        F_mat = (s + 1) ** (-2)
        M_mat = 1 / (s[None, :] + s[:, None])

        # Build the model
        a = Parameter('a', value=100)
        z = Parameter('z', value=1, fixed=True)
        c = MatrixSymbol(Parameter('c'), N, 1)
        F = MatrixSymbol('F', N, 1)
        I = MatrixSymbol('I', N, N)
        M = MatrixSymbol('M', N, N)
        d = MatrixSymbol('d', 1, 1)

        model_dict = {
            F: z * (I + M / a**2) * c,
            d: c.T * c
        }
        model = CallableModel(model_dict)
        fit = Fit(model, I=I_mat, M=M_mat, d=np.atleast_2d(0.0), F=F_mat)

        # subproblems_data contains the data needed to solve the subproblem
        A_data, y_data = fit.linear_solver.subproblems_data[c]
        np.testing.assert_almost_equal(A_data, z.value * (I_mat + M_mat / a.value**2))
        np.testing.assert_almost_equal(y_data, F_mat)
        fit_result = fit.execute()

        self.assertIsInstance(fit_result.objective, LeastSquares)
        self.assertIsInstance(fit_result.linear_solver, LstSq)
        self.assertIsInstance(fit_result.minimizer, BFGS)
        all_params = fit_result.scalar_params.copy()
        all_params.update(fit_result.tensor_params)
        self.assertEqual(fit_result.params, all_params)
        # Tikhonov parameter should be small
        self.assertLess(fit_result.value(a), 1e-1)

        ans = model(I=I_mat, M=M_mat, **fit_result.params)
        np.testing.assert_almost_equal(ans.F, F_mat, decimal=5)
        np.testing.assert_almost_equal(ans.d, 0.0, decimal=5)


if __name__ == '__main__':
    try:
        unittest.main(warnings='ignore')
        # Note that unittest will catch and handle exceptions raised by tests.
        # So this line will *only* deal with exceptions raised by the line
        # above.
    except TypeError:
        # In Py2, unittest.main doesn't take a warnings argument
        warnings.simplefilter('ignore')
        unittest.main()