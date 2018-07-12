# pragma pylint: disable=protected-access, unused-argument, invalid-name
# pragma pylint: disable=too-many-lines, too-many-arguments

"""
Unit test file for rpc/telegram.py
"""

import re
from copy import deepcopy
from datetime import datetime
from random import randint
from unittest.mock import MagicMock, ANY

import arrow
from telegram import Chat, Message, Update
from telegram.error import NetworkError

from freqtrade import __version__
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Trade
from freqtrade.rpc import RPCMessageType
from freqtrade.rpc.telegram import Telegram, authorized_only
from freqtrade.state import State
from freqtrade.tests.conftest import (get_patched_freqtradebot, log_has,
                                      patch_exchange)
from freqtrade.tests.test_freqtradebot import (patch_coinmarketcap,
                                               patch_get_signal)


class DummyCls(Telegram):
    """
    Dummy class for testing the Telegram @authorized_only decorator
    """
    def __init__(self, freqtrade) -> None:
        super().__init__(freqtrade)
        self.state = {'called': False}

    def _init(self):
        pass

    @authorized_only
    def dummy_handler(self, *args, **kwargs) -> None:
        """
        Fake method that only change the state of the object
        """
        self.state['called'] = True

    @authorized_only
    def dummy_exception(self, *args, **kwargs) -> None:
        """
        Fake method that throw an exception
        """
        raise Exception('test')


def test__init__(default_conf, mocker) -> None:
    """
    Test __init__() method
    """
    mocker.patch('freqtrade.rpc.telegram.Updater', MagicMock())
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())

    telegram = Telegram(get_patched_freqtradebot(mocker, default_conf))
    assert telegram._updater is None
    assert telegram._config == default_conf


def test_init(default_conf, mocker, caplog) -> None:
    """ Test _init() method """
    start_polling = MagicMock()
    mocker.patch('freqtrade.rpc.telegram.Updater', MagicMock(return_value=start_polling))

    Telegram(get_patched_freqtradebot(mocker, default_conf))
    assert start_polling.call_count == 0

    # number of handles registered
    assert start_polling.dispatcher.add_handler.call_count > 0
    assert start_polling.start_polling.call_count == 1

    message_str = "rpc.telegram is listening for following commands: [['status'], ['profit'], " \
                  "['balance'], ['start'], ['stop'], ['forcesell'], ['performance'], ['daily'], " \
                  "['count'], ['reload_conf'], ['help'], ['version']]"

    assert log_has(message_str, caplog.record_tuples)


def test_cleanup(default_conf, mocker) -> None:
    """
    Test cleanup() method
    """
    updater_mock = MagicMock()
    updater_mock.stop = MagicMock()
    mocker.patch('freqtrade.rpc.telegram.Updater', updater_mock)

    telegram = Telegram(get_patched_freqtradebot(mocker, default_conf))
    telegram.cleanup()
    assert telegram._updater.stop.call_count == 1


def test_authorized_only(default_conf, mocker, caplog) -> None:
    """
    Test authorized_only() method when we are authorized
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    patch_exchange(mocker, None)

    chat = Chat(0, 0)
    update = Update(randint(1, 100))
    update.message = Message(randint(1, 100), 0, datetime.utcnow(), chat)

    conf = deepcopy(default_conf)
    conf['telegram']['enabled'] = False
    dummy = DummyCls(FreqtradeBot(conf))
    dummy.dummy_handler(bot=MagicMock(), update=update)
    assert dummy.state['called'] is True
    assert log_has(
        'Executing handler: dummy_handler for chat_id: 0',
        caplog.record_tuples
    )
    assert not log_has(
        'Rejected unauthorized message from: 0',
        caplog.record_tuples
    )
    assert not log_has(
        'Exception occurred within Telegram module',
        caplog.record_tuples
    )


def test_authorized_only_unauthorized(default_conf, mocker, caplog) -> None:
    """
    Test authorized_only() method when we are unauthorized
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    patch_exchange(mocker, None)
    chat = Chat(0xdeadbeef, 0)
    update = Update(randint(1, 100))
    update.message = Message(randint(1, 100), 0, datetime.utcnow(), chat)

    conf = deepcopy(default_conf)
    conf['telegram']['enabled'] = False
    dummy = DummyCls(FreqtradeBot(conf))
    dummy.dummy_handler(bot=MagicMock(), update=update)
    assert dummy.state['called'] is False
    assert not log_has(
        'Executing handler: dummy_handler for chat_id: 3735928559',
        caplog.record_tuples
    )
    assert log_has(
        'Rejected unauthorized message from: 3735928559',
        caplog.record_tuples
    )
    assert not log_has(
        'Exception occurred within Telegram module',
        caplog.record_tuples
    )


def test_authorized_only_exception(default_conf, mocker, caplog) -> None:
    """
    Test authorized_only() method when an exception is thrown
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    patch_exchange(mocker)

    update = Update(randint(1, 100))
    update.message = Message(randint(1, 100), 0, datetime.utcnow(), Chat(0, 0))

    conf = deepcopy(default_conf)
    conf['telegram']['enabled'] = False
    dummy = DummyCls(FreqtradeBot(conf))
    dummy.dummy_exception(bot=MagicMock(), update=update)
    assert dummy.state['called'] is False
    assert not log_has(
        'Executing handler: dummy_handler for chat_id: 0',
        caplog.record_tuples
    )
    assert not log_has(
        'Rejected unauthorized message from: 0',
        caplog.record_tuples
    )
    assert log_has(
        'Exception occurred within Telegram module',
        caplog.record_tuples
    )


def test_status(default_conf, update, mocker, fee, ticker, markets) -> None:
    """
    Test _status() method
    """
    update.message.chat.id = 123
    conf = deepcopy(default_conf)
    conf['telegram']['enabled'] = False
    conf['telegram']['chat_id'] = 123

    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)

    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_pair_detail_url=MagicMock(),
        get_fee=fee,
        get_markets=markets
    )
    msg_mock = MagicMock()
    status_table = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _rpc_trade_status=MagicMock(return_value=[{
            'trade_id': 1,
            'pair': 'ETH/BTC',
            'market_url': 'https://bittrex.com/Market/Index?MarketName=BTC-ETH',
            'date': arrow.utcnow(),
            'open_rate': 1.099e-05,
            'close_rate': None,
            'current_rate': 1.098e-05,
            'amount': 90.99181074,
            'close_profit': None,
            'current_profit': -0.59,
            'open_order': '(limit buy rem=0.00000000)'
        }]),
        _status_table=status_table,
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    freqtradebot = FreqtradeBot(conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    for _ in range(3):
        freqtradebot.create_trade()

    telegram._status(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1

    update.message.text = MagicMock()
    update.message.text.replace = MagicMock(return_value='table 2 3')
    telegram._status(bot=MagicMock(), update=update)
    assert status_table.call_count == 1


def test_status_handle(default_conf, update, ticker, fee, markets, mocker) -> None:
    """
    Test _status() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )
    msg_mock = MagicMock()
    status_table = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _status_table=status_table,
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.STOPPED
    telegram._status(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'trader is not running' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()

    freqtradebot.state = State.RUNNING
    telegram._status(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'no active trade' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()

    # Create some test data
    freqtradebot.create_trade()
    # Trigger status while we have a fulfilled order for the open trade
    telegram._status(bot=MagicMock(), update=update)

    assert msg_mock.call_count == 1
    assert '[ETH/BTC]' in msg_mock.call_args_list[0][0][0]


def test_status_table_handle(default_conf, update, ticker, fee, markets, mocker) -> None:
    """
    Test _status_table() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        buy=MagicMock(return_value={'id': 'mocked_order_id'}),
        get_fee=fee,
        get_markets=markets
    )
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    conf = deepcopy(default_conf)
    conf['stake_amount'] = 15.0
    freqtradebot = FreqtradeBot(conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.STOPPED
    telegram._status_table(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'trader is not running' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()

    freqtradebot.state = State.RUNNING
    telegram._status_table(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'no active order' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()

    # Create some test data
    freqtradebot.create_trade()

    telegram._status_table(bot=MagicMock(), update=update)

    text = re.sub('</?pre>', '', msg_mock.call_args_list[-1][0][0])
    line = text.split("\n")
    fields = re.sub('[ ]+', ' ', line[2].strip()).split(' ')

    assert int(fields[0]) == 1
    assert fields[1] == 'ETH/BTC'
    assert msg_mock.call_count == 1


def test_daily_handle(default_conf, update, ticker, limit_buy_order, fee,
                      limit_sell_order, markets, mocker) -> None:
    """
    Test _daily() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch(
        'freqtrade.fiat_convert.CryptoToFiatConverter._find_price',
        return_value=15000.0
    )
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    freqtradebot.create_trade()
    trade = Trade.query.first()
    assert trade

    # Simulate fulfilled LIMIT_BUY order for trade
    trade.update(limit_buy_order)

    # Simulate fulfilled LIMIT_SELL order for trade
    trade.update(limit_sell_order)

    trade.close_date = datetime.utcnow()
    trade.is_open = False

    # Try valid data
    update.message.text = '/daily 2'
    telegram._daily(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'Daily' in msg_mock.call_args_list[0][0][0]
    assert str(datetime.utcnow().date()) in msg_mock.call_args_list[0][0][0]
    assert str('  0.00006217 BTC') in msg_mock.call_args_list[0][0][0]
    assert str('  0.933 USD') in msg_mock.call_args_list[0][0][0]
    assert str('  1 trade') in msg_mock.call_args_list[0][0][0]
    assert str('  0 trade') in msg_mock.call_args_list[0][0][0]

    # Reset msg_mock
    msg_mock.reset_mock()
    # Add two other trades
    freqtradebot.create_trade()
    freqtradebot.create_trade()

    trades = Trade.query.all()
    for trade in trades:
        trade.update(limit_buy_order)
        trade.update(limit_sell_order)
        trade.close_date = datetime.utcnow()
        trade.is_open = False

    update.message.text = '/daily 1'

    telegram._daily(bot=MagicMock(), update=update)
    assert str('  0.00018651 BTC') in msg_mock.call_args_list[0][0][0]
    assert str('  2.798 USD') in msg_mock.call_args_list[0][0][0]
    assert str('  3 trades') in msg_mock.call_args_list[0][0][0]


def test_daily_wrong_input(default_conf, update, ticker, mocker) -> None:
    """
    Test _daily() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker
    )
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Try invalid data
    msg_mock.reset_mock()
    freqtradebot.state = State.RUNNING
    update.message.text = '/daily -2'
    telegram._daily(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'must be an integer greater than 0' in msg_mock.call_args_list[0][0][0]

    # Try invalid data
    msg_mock.reset_mock()
    freqtradebot.state = State.RUNNING
    update.message.text = '/daily today'
    telegram._daily(bot=MagicMock(), update=update)
    assert str('Daily Profit over the last 7 days') in msg_mock.call_args_list[0][0][0]


def test_profit_handle(default_conf, update, ticker, ticker_sell_up, fee,
                       limit_buy_order, limit_sell_order, markets, mocker) -> None:
    """
    Test _profit() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.fiat_convert.CryptoToFiatConverter._find_price', return_value=15000.0)
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    telegram._profit(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'no closed trade' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()

    # Create some test data
    freqtradebot.create_trade()
    trade = Trade.query.first()

    # Simulate fulfilled LIMIT_BUY order for trade
    trade.update(limit_buy_order)

    telegram._profit(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'no closed trade' in msg_mock.call_args_list[-1][0][0]
    msg_mock.reset_mock()

    # Update the ticker with a market going up
    mocker.patch('freqtrade.exchange.Exchange.get_ticker', ticker_sell_up)
    trade.update(limit_sell_order)

    trade.close_date = datetime.utcnow()
    trade.is_open = False

    telegram._profit(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert '*ROI:* Close trades' in msg_mock.call_args_list[-1][0][0]
    assert '∙ `0.00006217 BTC (6.20%)`' in msg_mock.call_args_list[-1][0][0]
    assert '∙ `0.933 USD`' in msg_mock.call_args_list[-1][0][0]
    assert '*ROI:* All trades' in msg_mock.call_args_list[-1][0][0]
    assert '∙ `0.00006217 BTC (6.20%)`' in msg_mock.call_args_list[-1][0][0]
    assert '∙ `0.933 USD`' in msg_mock.call_args_list[-1][0][0]

    assert '*Best Performing:* `ETH/BTC: 6.20%`' in msg_mock.call_args_list[-1][0][0]


def test_telegram_balance_handle(default_conf, update, mocker) -> None:
    """
    Test _balance() method
    """

    mock_balance = {
        'BTC': {
            'total': 12.0,
            'free': 12.0,
            'used': 0.0
        },
        'ETH': {
            'total': 0.0,
            'free': 0.0,
            'used': 0.0
        },
        'USDT': {
            'total': 10000.0,
            'free': 10000.0,
            'used': 0.0
        },
        'LTC': {
            'total': 10.0,
            'free': 10.0,
            'used': 0.0
        }
    }

    def mock_ticker(symbol, refresh):
        """
        Mock Bittrex.get_ticker() response
        """
        if symbol == 'BTC/USDT':
            return {
                'bid': 10000.00,
                'ask': 10000.00,
                'last': 10000.00,
            }

        return {
            'bid': 0.1,
            'ask': 0.1,
            'last': 0.1,
        }

    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.exchange.Exchange.get_balances', return_value=mock_balance)
    mocker.patch('freqtrade.exchange.Exchange.get_ticker', side_effect=mock_ticker)

    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    telegram._balance(bot=MagicMock(), update=update)
    result = msg_mock.call_args_list[0][0][0]
    assert msg_mock.call_count == 1
    assert '*BTC:*' in result
    assert '*ETH:*' not in result
    assert '*USDT:*' in result
    assert 'Balance:' in result
    assert 'Est. BTC:' in result
    assert 'BTC:  14.00000000' in result


def test_zero_balance_handle(default_conf, update, mocker) -> None:
    """
    Test _balance() method when the Exchange platform returns nothing
    """
    patch_get_signal(mocker, (True, False))
    mocker.patch('freqtrade.exchange.Exchange.get_balances', return_value={})

    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    telegram._balance(bot=MagicMock(), update=update)
    result = msg_mock.call_args_list[0][0][0]
    assert msg_mock.call_count == 1
    assert 'all balances are zero' in result


def test_start_handle(default_conf, update, mocker) -> None:
    """
    Test _start() method
    """
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.STOPPED
    assert freqtradebot.state == State.STOPPED
    telegram._start(bot=MagicMock(), update=update)
    assert freqtradebot.state == State.RUNNING
    assert msg_mock.call_count == 1


def test_start_handle_already_running(default_conf, update, mocker) -> None:
    """
    Test _start() method
    """
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.RUNNING
    assert freqtradebot.state == State.RUNNING
    telegram._start(bot=MagicMock(), update=update)
    assert freqtradebot.state == State.RUNNING
    assert msg_mock.call_count == 1
    assert 'already running' in msg_mock.call_args_list[0][0][0]


def test_stop_handle(default_conf, update, mocker) -> None:
    """
    Test _stop() method
    """
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.RUNNING
    assert freqtradebot.state == State.RUNNING
    telegram._stop(bot=MagicMock(), update=update)
    assert freqtradebot.state == State.STOPPED
    assert msg_mock.call_count == 1
    assert 'stopping trader' in msg_mock.call_args_list[0][0][0]


def test_stop_handle_already_stopped(default_conf, update, mocker) -> None:
    """
    Test _stop() method
    """
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.STOPPED
    assert freqtradebot.state == State.STOPPED
    telegram._stop(bot=MagicMock(), update=update)
    assert freqtradebot.state == State.STOPPED
    assert msg_mock.call_count == 1
    assert 'already stopped' in msg_mock.call_args_list[0][0][0]


def test_reload_conf_handle(default_conf, update, mocker) -> None:
    """ Test _reload_conf() method """
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )

    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.RUNNING
    assert freqtradebot.state == State.RUNNING
    telegram._reload_conf(bot=MagicMock(), update=update)
    assert freqtradebot.state == State.RELOAD_CONF
    assert msg_mock.call_count == 1
    assert 'reloading config' in msg_mock.call_args_list[0][0][0]


def test_forcesell_handle(default_conf, update, ticker, fee,
                          ticker_sell_up, markets, mocker) -> None:
    """
    Test _forcesell() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.fiat_convert.CryptoToFiatConverter._find_price', return_value=15000.0)
    rpc_mock = mocker.patch('freqtrade.rpc.telegram.Telegram.send_msg', MagicMock())
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    freqtradebot.create_trade()

    trade = Trade.query.first()
    assert trade

    # Increase the price and sell it
    mocker.patch('freqtrade.exchange.Exchange.get_ticker', ticker_sell_up)

    update.message.text = '/forcesell 1'
    telegram._forcesell(bot=MagicMock(), update=update)

    assert rpc_mock.call_count == 2
    last_msg = rpc_mock.call_args_list[-1][0][0]
    assert {
        'type': RPCMessageType.SELL_NOTIFICATION,
        'exchange': 'Bittrex',
        'pair': 'ETH/BTC',
        'gain': 'profit',
        'market_url': 'https://bittrex.com/Market/Index?MarketName=BTC-ETH',
        'limit': 1.172e-05,
        'amount': 90.99181073703367,
        'open_rate': 1.099e-05,
        'current_rate': 1.172e-05,
        'profit_amount': 6.126e-05,
        'profit_percent': 0.06110514,
        'profit_fiat': 0.9189,
        'stake_currency': 'BTC',
        'fiat_currency': 'USD',
    } == last_msg


def test_forcesell_down_handle(default_conf, update, ticker, fee,
                               ticker_sell_down, markets, mocker) -> None:
    """
    Test _forcesell() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.fiat_convert.CryptoToFiatConverter._find_price', return_value=15000.0)
    rpc_mock = mocker.patch('freqtrade.rpc.telegram.Telegram.send_msg', MagicMock())
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    freqtradebot.create_trade()

    # Decrease the price and sell it
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker_sell_down
    )

    trade = Trade.query.first()
    assert trade

    update.message.text = '/forcesell 1'
    telegram._forcesell(bot=MagicMock(), update=update)

    assert rpc_mock.call_count == 2

    last_msg = rpc_mock.call_args_list[-1][0][0]
    assert {
        'type': RPCMessageType.SELL_NOTIFICATION,
        'exchange': 'Bittrex',
        'pair': 'ETH/BTC',
        'gain': 'loss',
        'market_url': 'https://bittrex.com/Market/Index?MarketName=BTC-ETH',
        'limit': 1.044e-05,
        'amount': 90.99181073703367,
        'open_rate': 1.099e-05,
        'current_rate': 1.044e-05,
        'profit_amount': -5.492e-05,
        'profit_percent': -0.05478343,
        'profit_fiat': -0.8238000000000001,
        'stake_currency': 'BTC',
        'fiat_currency': 'USD',
    } == last_msg


def test_forcesell_all_handle(default_conf, update, ticker, fee, markets, mocker) -> None:
    """
    Test _forcesell() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.fiat_convert.CryptoToFiatConverter._find_price', return_value=15000.0)
    rpc_mock = mocker.patch('freqtrade.rpc.telegram.Telegram.send_msg', MagicMock())
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())
    mocker.patch('freqtrade.exchange.Exchange.get_pair_detail_url', MagicMock())
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    for _ in range(4):
        freqtradebot.create_trade()
    rpc_mock.reset_mock()

    update.message.text = '/forcesell all'
    telegram._forcesell(bot=MagicMock(), update=update)

    assert rpc_mock.call_count == 4
    msg = rpc_mock.call_args_list[0][0][0]
    assert {
        'type': RPCMessageType.SELL_NOTIFICATION,
        'exchange': 'Bittrex',
        'pair': 'ETH/BTC',
        'gain': 'loss',
        'market_url': ANY,
        'limit': 1.098e-05,
        'amount': 90.99181073703367,
        'open_rate': 1.099e-05,
        'current_rate': 1.098e-05,
        'profit_amount': -5.91e-06,
        'profit_percent': -0.00589292,
        'profit_fiat': -0.08865,
        'stake_currency': 'BTC',
        'fiat_currency': 'USD',
    } == msg


def test_forcesell_handle_invalid(default_conf, update, mocker) -> None:
    """
    Test _forcesell() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker, value={'price_usd': 15000.0})
    mocker.patch('freqtrade.fiat_convert.CryptoToFiatConverter._find_price', return_value=15000.0)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.exchange.Exchange.validate_pairs', MagicMock())

    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Trader is not running
    freqtradebot.state = State.STOPPED
    update.message.text = '/forcesell 1'
    telegram._forcesell(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'not running' in msg_mock.call_args_list[0][0][0]

    # No argument
    msg_mock.reset_mock()
    freqtradebot.state = State.RUNNING
    update.message.text = '/forcesell'
    telegram._forcesell(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'invalid argument' in msg_mock.call_args_list[0][0][0]

    # Invalid argument
    msg_mock.reset_mock()
    freqtradebot.state = State.RUNNING
    update.message.text = '/forcesell 123456'
    telegram._forcesell(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'invalid argument' in msg_mock.call_args_list[0][0][0]


def test_performance_handle(default_conf, update, ticker, fee,
                            limit_buy_order, limit_sell_order, markets, mocker) -> None:
    """
    Test _performance() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        get_fee=fee,
        get_markets=markets
    )
    mocker.patch('freqtrade.freqtradebot.RPCManager', MagicMock())
    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Create some test data
    freqtradebot.create_trade()
    trade = Trade.query.first()
    assert trade

    # Simulate fulfilled LIMIT_BUY order for trade
    trade.update(limit_buy_order)

    # Simulate fulfilled LIMIT_SELL order for trade
    trade.update(limit_sell_order)

    trade.close_date = datetime.utcnow()
    trade.is_open = False
    telegram._performance(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'Performance' in msg_mock.call_args_list[0][0][0]
    assert '<code>ETH/BTC\t6.20% (1)</code>' in msg_mock.call_args_list[0][0][0]


def test_performance_handle_invalid(default_conf, update, mocker) -> None:
    """
    Test _performance() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch('freqtrade.exchange.Exchange.validate_pairs', MagicMock())
    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    # Trader is not running
    freqtradebot.state = State.STOPPED
    telegram._performance(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'not running' in msg_mock.call_args_list[0][0][0]


def test_count_handle(default_conf, update, ticker, fee, markets, mocker) -> None:
    """
    Test _count() method
    """
    patch_get_signal(mocker, (True, False))
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    mocker.patch.multiple(
        'freqtrade.exchange.Exchange',
        validate_pairs=MagicMock(),
        get_ticker=ticker,
        buy=MagicMock(return_value={'id': 'mocked_order_id'}),
        get_markets=markets
    )
    mocker.patch('freqtrade.exchange.Exchange.get_fee', fee)
    freqtradebot = FreqtradeBot(default_conf)
    telegram = Telegram(freqtradebot)

    freqtradebot.state = State.STOPPED
    telegram._count(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert 'not running' in msg_mock.call_args_list[0][0][0]
    msg_mock.reset_mock()
    freqtradebot.state = State.RUNNING

    # Create some test data
    freqtradebot.create_trade()
    msg_mock.reset_mock()
    telegram._count(bot=MagicMock(), update=update)

    msg = '<pre>  current    max    total stake\n---------  -----  -------------\n' \
          '        1      {}          {}</pre>'\
        .format(
            default_conf['max_open_trades'],
            default_conf['stake_amount']
        )
    assert msg in msg_mock.call_args_list[0][0][0]


def test_help_handle(default_conf, update, mocker) -> None:
    """
    Test _help() method
    """
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    freqtradebot = get_patched_freqtradebot(mocker, default_conf)

    telegram = Telegram(freqtradebot)

    telegram._help(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert '*/help:* `This help message`' in msg_mock.call_args_list[0][0][0]


def test_version_handle(default_conf, update, mocker) -> None:
    """
    Test _version() method
    """
    patch_coinmarketcap(mocker)
    msg_mock = MagicMock()
    mocker.patch.multiple(
        'freqtrade.rpc.telegram.Telegram',
        _init=MagicMock(),
        _send_msg=msg_mock
    )
    freqtradebot = get_patched_freqtradebot(mocker, default_conf)
    telegram = Telegram(freqtradebot)

    telegram._version(bot=MagicMock(), update=update)
    assert msg_mock.call_count == 1
    assert '*Version:* `{}`'.format(__version__) in msg_mock.call_args_list[0][0][0]


def test_send_msg_buy_notification() -> None:
    # TODO: implement me
    pass


def test_send_msg_sell_notification() -> None:
    # TODO: implement me
    pass


def test_send_msg_status_notification() -> None:
    # TODO: implement me
    pass


def test__send_msg(default_conf, mocker) -> None:
    """
    Test send_msg() method
    """
    patch_coinmarketcap(mocker)
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())
    conf = deepcopy(default_conf)
    bot = MagicMock()
    freqtradebot = get_patched_freqtradebot(mocker, conf)
    telegram = Telegram(freqtradebot)

    telegram._config['telegram']['enabled'] = True
    telegram._send_msg('test', bot)
    assert len(bot.method_calls) == 1


def test__send_msg_network_error(default_conf, mocker, caplog) -> None:
    """
    Test send_msg() method
    """
    patch_coinmarketcap(mocker)
    mocker.patch('freqtrade.rpc.telegram.Telegram._init', MagicMock())
    conf = deepcopy(default_conf)
    bot = MagicMock()
    bot.send_message = MagicMock(side_effect=NetworkError('Oh snap'))
    freqtradebot = get_patched_freqtradebot(mocker, conf)
    telegram = Telegram(freqtradebot)

    telegram._config['telegram']['enabled'] = True
    telegram._send_msg('test', bot)

    # Bot should've tried to send it twice
    assert len(bot.method_calls) == 2
    assert log_has(
        'Telegram NetworkError: Oh snap! Trying one more time.',
        caplog.record_tuples
    )
