""" Binance exchange subclass """
import logging
from datetime import datetime
from typing import Dict, List, Optional

import ccxt

from freqtrade.exceptions import (DDosProtection, InsufficientFundsError, InvalidOrderException,
                                  OperationalException, TemporaryError)
from freqtrade.exchange import Exchange
from freqtrade.exchange.common import retrier


logger = logging.getLogger(__name__)


class Binance(Exchange):

    _ft_has: Dict = {
        "stoploss_on_exchange": True,
        "order_time_in_force": ['gtc', 'fok', 'ioc'],
        "ohlcv_candle_limit": 1000,
        "trades_pagination": "id",
        "trades_pagination_arg": "fromId",
        "l2_limit_range": [5, 10, 20, 50, 100, 500, 1000],
    }
    funding_fee_times: List[int] = [0, 8, 16]  # hours of the day

    def stoploss_adjust(self, stop_loss: float, order: Dict) -> bool:
        """
        Verify stop_loss against stoploss-order value (limit or price)
        Returns True if adjustment is necessary.
        """
        return order['type'] == 'stop_loss_limit' and stop_loss > float(order['info']['stopPrice'])

    @retrier(retries=0)
    def stoploss(self, pair: str, amount: float, stop_price: float, order_types: Dict) -> Dict:
        """
        creates a stoploss limit order.
        this stoploss-limit is binance-specific.
        It may work with a limited number of other exchanges, but this has not been tested yet.
        """
        # Limit price threshold: As limit price should always be below stop-price
        limit_price_pct = order_types.get('stoploss_on_exchange_limit_ratio', 0.99)
        rate = stop_price * limit_price_pct

        ordertype = "stop_loss_limit"

        stop_price = self.price_to_precision(pair, stop_price)

        # Ensure rate is less than stop price
        if stop_price <= rate:
            raise OperationalException(
                'In stoploss limit order, stop price should be more than limit price')

        if self._config['dry_run']:
            dry_order = self.create_dry_run_order(
                pair, ordertype, "sell", amount, stop_price)
            return dry_order

        try:
            params = self._params.copy()
            params.update({'stopPrice': stop_price})

            amount = self.amount_to_precision(pair, amount)

            rate = self.price_to_precision(pair, rate)

            order = self._api.create_order(symbol=pair, type=ordertype, side='sell',
                                           amount=amount, price=rate, params=params)
            logger.info('stoploss limit order added for %s. '
                        'stop price: %s. limit: %s', pair, stop_price, rate)
            self._log_exchange_response('create_stoploss_order', order)
            return order
        except ccxt.InsufficientFunds as e:
            raise InsufficientFundsError(
                f'Insufficient funds to create {ordertype} sell order on market {pair}. '
                f'Tried to sell amount {amount} at rate {rate}. '
                f'Message: {e}') from e
        except ccxt.InvalidOrder as e:
            # Errors:
            # `binance Order would trigger immediately.`
            raise InvalidOrderException(
                f'Could not create {ordertype} sell order on market {pair}. '
                f'Tried to sell amount {amount} at rate {rate}. '
                f'Message: {e}') from e
        except ccxt.DDoSProtection as e:
            raise DDosProtection(e) from e
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            raise TemporaryError(
                f'Could not place sell order due to {e.__class__.__name__}. Message: {e}') from e
        except ccxt.BaseError as e:
            raise OperationalException(e) from e

    def _get_funding_rate(self, pair: str, when: datetime) -> Optional[float]:
        """
            Get's the funding_rate for a pair at a specific date and time in the past
        """
        # TODO-lev: implement
        raise OperationalException("_get_funding_rate has not been implement on binance")

    def _get_funding_fee(
        self,
        contract_size: float,
        mark_price: float,
        funding_rate: Optional[float],
    ) -> float:
        """
            Calculates a single funding fee
            :param contract_size: The amount/quanity
            :param mark_price: The price of the asset that the contract is based off of
            :param funding_rate: the interest rate and the premium
                - interest rate: 0.03% daily, BNBUSDT, LINKUSDT, and LTCUSDT are 0%
                - premium: varies by price difference between the perpetual contract and mark price
        """
        if funding_rate is None:
            raise OperationalException("Funding rate cannot be None for Binance._get_funding_fee")
        nominal_value = mark_price * contract_size
        adjustment = nominal_value * funding_rate
        return adjustment
