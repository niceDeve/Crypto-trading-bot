# pragma pylint: disable=missing-docstring
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from jsonschema import validate
from telegram import Message, Chat, Update

from freqtrade.misc import CONF_SCHEMA


@pytest.fixture(scope="module")
def default_conf():
    """ Returns validated configuration suitable for most tests """
    configuration = {
        "max_open_trades": 3,
        "stake_currency": "BTC",
        "stake_amount": 0.05,
        "dry_run": True,
        "minimal_roi": {
            "40":  0.0,
            "30":  0.01,
            "20":  0.02,
            "0":  0.04
        },
        "stoploss": -0.05,
        "bid_strategy": {
            "ask_last_balance": 0.0
        },
        "exchange": {
            "name": "bittrex",
            "enabled": True,
            "key": "key",
            "secret": "secret",
            "pair_whitelist": [
                "BTC_ETH",
                "BTC_TKN",
                "BTC_TRST",
                "BTC_SWT"
            ]
        },
        "telegram": {
            "enabled": True,
            "token": "token",
            "chat_id": "0"
        },
        "initial_state": "running"
    }
    validate(configuration, CONF_SCHEMA)
    return configuration


@pytest.fixture(scope="module")
def backtest_conf():
    return {
        "minimal_roi": {
            "40":  0.0,
            "30":  0.01,
            "20":  0.02,
            "0":  0.04
        },
        "stoploss": -0.05
    }


@pytest.fixture(scope="module")
def backdata():
    result = {}
    for pair in ['btc-neo', 'btc-eth', 'btc-omg', 'btc-edg', 'btc-pay',
                 'btc-pivx', 'btc-qtum', 'btc-mtl', 'btc-etc', 'btc-ltc']:
        with open('freqtrade/tests/testdata/' + pair + '.json') as data_file:
            result[pair] = json.load(data_file)
    return result


@pytest.fixture
def update():
    _update = Update(0)
    _update.message = Message(0, 0, datetime.utcnow(), Chat(0, 0))
    return _update


@pytest.fixture
def ticker():
    return MagicMock(return_value={
        'bid': 0.07256061,
        'ask': 0.072661,
        'last': 0.07256061,
    })


@pytest.fixture
def limit_buy_order():
    return {
        'id': 'mocked_limit_buy',
        'type': 'LIMIT_BUY',
        'pair': 'mocked',
        'opened': datetime.utcnow(),
        'rate': 0.07256061,
        'amount': 206.43811673387373,
        'remaining': 0.0,
        'closed': datetime.utcnow(),
    }


@pytest.fixture
def limit_sell_order():
    return {
        'id': 'mocked_limit_sell',
        'type': 'LIMIT_SELL',
        'pair': 'mocked',
        'opened': datetime.utcnow(),
        'rate': 0.0802134,
        'amount': 206.43811673387373,
        'remaining': 0.0,
        'closed': datetime.utcnow(),
    }
