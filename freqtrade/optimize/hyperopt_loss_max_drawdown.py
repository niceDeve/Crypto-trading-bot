"""
MaxDrawDownHyperOptLoss

This module defines the alternative HyperOptLoss class which can be used for
Hyperoptimization.
"""
from datetime import datetime
from freqtrade.data.btanalysis import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss

from pandas import DataFrame


class MaxDrawDownHyperOptLoss(IHyperOptLoss):

    """
    Defines the loss function for hyperopt.

    This implementation optimizes for max draw down and profit
    Less max drawdown more profit -> Lower return value
    """

    @staticmethod
    def hyperopt_loss_function(results: DataFrame, trade_count: int,
                               min_date: datetime, max_date: datetime,
                               *args, **kwargs) -> float:

        """
        Objective function.

        Uses profit ratio weighted max_drawdown when drawdown is available.
        Otherwise directly optimizes profit ratio.
        """
        total_profit = results['profit_ratio'].sum()        
        try:
            max_drawdown = calculate_max_drawdown(results)
        except ValueError:
            # No losing trade, therefore no drawdown.
            return -total_profit
        max_drawdown_rev = 1 / max_drawdown[0]
        ret = max_drawdown_rev * total_profit
        return -ret