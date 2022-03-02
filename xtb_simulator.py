import datetime
import sys

import numpy as np
import pandas as pd
import talib  # for patterns, https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib

from XTBApi.api import Client, PERIOD
from utils import credentials

CLOSE = 'close'
OPEN = 'open'
RATE_INFO = 'rateInfos'
LOW = 'low'
HIGH = 'high'
CTM = 'ctm'
CTM_STRING = 'ctmString'

BUY = 'buy'
FIXED_RISK = 0.02
SUPPORTS = 'supports'
RESISTANCES = 'resistances'

BALANCE = 300

client = None


def apply_pivots(df_daily, df_1min):
    df_1min['day'] = [int(datetime.datetime.fromtimestamp(x / 1000).strftime("%d")) for x in df_1min.ctm]
    df_1min[SUPPORTS] = np.nan
    df_1min[RESISTANCES] = np.nan

    for _, day in df_daily.iterrows():
        df_pivots_high = day.high
        df_pivots_low = day.low
        df_pivots_close = day.close
        decimals = 3
        pivot = round((df_pivots_high + df_pivots_low + df_pivots_close) / 3, decimals)
        resistance_1 = round(2 * pivot - df_pivots_low, decimals)
        resistance_2 = round(pivot + (df_pivots_high - df_pivots_low), decimals)
        resistance_3 = round(pivot + 2 * (df_pivots_high - df_pivots_low), decimals)
        resistances = sorted([pivot, resistance_1, resistance_2, resistance_3])
        support_1 = round(2 * pivot - df_pivots_high, decimals)
        support_2 = round(pivot - (df_pivots_high - df_pivots_low), decimals)
        support_3 = round(pivot - 2 * (df_pivots_high - df_pivots_low), decimals)
        supports = sorted([pivot, support_1, support_2, support_3], reverse=True)
        week_day = datetime.datetime.fromtimestamp(day.ctm / 1000).weekday()

        if day.ctm == df_daily[CTM].iloc[-1]:
            break

        days = 1
        if week_day == 4:
            days = 3
        elif week_day == 6:
            continue
        ctm_day = int((datetime.datetime.fromtimestamp(day.ctm / 1000) + datetime.timedelta(days=days)).strftime("%d"))

        minutes_index = df_1min.index[df_1min["day"] == ctm_day].tolist()
        for i in minutes_index:
            df_1min.at[i, SUPPORTS] = str(supports)
            df_1min.at[i, RESISTANCES] = str(resistances)
    df_1min = df_1min.drop(['day'], axis=1)
    return df_1min
    # ONLY FOR DEBUG
    # print(df_1min[SUPPORTS].iloc[int(len(df_1min)/2)], df_1min[CTM_STRING].iloc[int(len(df_1min)/2)])


def apply_so(df):
    """
    https://school.stockcharts.com/doku.php?id=technical_indicators:stochastic_oscillator_fast_slow_and_full
    """
    try:
        slow_k, slow_d = talib.STOCH(df.high, df.low, df.close, fastk_period=30, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        # df['t'] = [str(datetime.datetime.fromtimestamp(x / 1000).day) + '_' + str(datetime.datetime.fromtimestamp(x / 1000).hour) for x in df.ctm]
        df['slow_k'] = round(slow_k, 2)
        df['slow_d'] = round(slow_d, 2)
        df[BUY] = np.where((df['slow_k'] < 20) & (df['slow_d'] < 20) & (df['slow_k'] < df['slow_d']), df.close, False)  # (abs(df['slow_k'] - df['slow_d']) < 2)
        # df = df.drop(['t'], axis=1)
        return df
    except Exception as ex:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print('Fail in so:', ex.args, 'line:', exc_tb.tb_lineno)


def strategy_a(df, pip_value, symbol):
    """
    Indecision Candle (CDLLONGLEGGEDDOJI) + Fixed Risk 2% +  Amount variable(ATR, N Units...) but closing half of position
    + when expenses touches EMA, close >= 0
    BUY / SELL Based on ADX
    :param symbol:
    :param df:
    :param pip_value:
    :return:
    """
    try:
        decimals = 3
        last_buys = []
        my_balance = BALANCE
        opened_trades = 0
        closed_trades = 0
        wins = 0
        gains = 0
        losses = 0
        order_id = 0
        min_amount = 0.01
        margin = client.get_margin_trade(symbol=symbol, volume=(1 * min_amount))['margin']
        spread_raw = client.get_symbol(symbol=symbol)['spreadTable']
        for i, row in df.iterrows():
            # Running out of money
            if my_balance <= 0:
                return "RIP", round(my_balance, 2), row.ctmString

            # STRATEGY
            if isinstance(row.supports, str) and row.buy != 0:
                amount = FIXED_RISK * my_balance * min_amount * 100
                if 0 < amount < my_balance and my_balance > (min_amount * row.close) and my_balance > (BALANCE * 0.20):
                    amount = 12 if amount >= 12 else amount
                    min_margin = round(margin * amount, 2)
                    actual_margin = sum([li[6] for li in last_buys])
                    actual_profit = sum([round((row.buy - li[0]) * pip_value, 2) for li in last_buys])
                    free_margin = (my_balance - actual_margin) - actual_profit
                    if free_margin >= min_margin:
                        row.buy = round((spread_raw * pip_value) + row.buy, decimals)
                        half_amount = int(amount / 2)
                        final_amount = int(abs(amount - half_amount)) if amount > 1 else 1
                        sl = round(row.buy - (FIXED_RISK * row.buy), decimals)
                        res = list(map(float, row.resistances.replace('[', '').replace(']', '').split(",")))
                        tp = round(row.buy + 0.01, decimals) if not any(ele > row.buy for ele in res) else next(x[1] for x in enumerate(res) if x[1] > row.buy)
                        last_buys.append((row.buy, final_amount, sl, tp, order_id, row.ctmString, round(margin * final_amount, 2)))
                        opened_trades += 1

                        if amount > 1:
                            if tp in res:
                                res.remove(tp)
                            sl = round(row.buy - (FIXED_RISK * row.buy), decimals)
                            tp = round(row.buy + 0.01, decimals) if not any(ele > row.buy for ele in res) else next(x[1] for x in enumerate(res) if x[1] > row.buy)
                            last_buys.append((row.buy, half_amount, sl, tp, order_id, row.ctmString, round(margin * half_amount, 2)))
                            opened_trades += 1
                        order_id += 1

            for e, lb in enumerate(last_buys):
                last_buy = lb[0]
                contracts = lb[1]
                stop_price = lb[2]
                tp = lb[3]
                entry_id = lb[4]
                amount = (pip_value * contracts)
                if row.low <= stop_price <= row.high:
                    result = round((stop_price - last_buy) * amount, 2)
                    if result < 0:
                        losses += result
                    elif result > 0:
                        wins += result
                    my_balance += result
                    gains += result
                    print(last_buys[e])
                    del last_buys[e]
                    closed_trades += 1
                    continue
                if row.low <= tp <= row.high:
                    result = round((tp - last_buy) * amount, 2)
                    my_balance += result
                    gains += result
                    wins += result
                    print(last_buys[e])
                    del last_buys[e]
                    closed_trades += 1

                    # A second entry exists, update it
                    index = next((i for i, item in enumerate(last_buys) if item[4] == entry_id), None)
                    if index is not None and len(last_buys) >= index:
                        new_stop_loss = round(last_buy + ((last_buy - tp) / 2), decimals)
                        last_buys[index] = (last_buy, contracts, new_stop_loss, last_buys[index][3], last_buys[index][4], last_buys[index][5], last_buys[index][6])

        return 'A', 'Real:', round(my_balance, 2), "Profit:", round(gains, 2), "Wins:", round(wins, 2), "Losses:", round(losses, 2), "OT:", opened_trades, "CT:", closed_trades
    except Exception as ex:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print('Fail in strategy:', ex.args, 'line:', exc_tb.tb_lineno)


def prepare_data(symbol, pip_value=0.0):
    try:
        end = datetime.datetime.today().timestamp()
        start = datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(weeks=2))
        chart_min = client.get_chart_range_request(symbol, PERIOD.ONE_MINUTE.value, start, end, 0)
        chart_day = client.get_chart_range_request(symbol, PERIOD.ONE_DAY.value, start, end, 0)

        digits = int('1' + ('0' * chart_min['digits']))
        for rate in chart_min[RATE_INFO]:
            rate[CLOSE] = (rate[OPEN] + rate[CLOSE]) / digits
            rate[HIGH] = (rate[OPEN] + rate[HIGH]) / digits
            rate[LOW] = (rate[OPEN] + rate[LOW]) / digits
            rate[OPEN] = (rate[OPEN] / digits)

        for rate in chart_day[RATE_INFO]:
            rate[CLOSE] = (rate[OPEN] + rate[CLOSE]) / digits
            rate[HIGH] = (rate[OPEN] + rate[HIGH]) / digits
            rate[LOW] = (rate[OPEN] + rate[LOW]) / digits
            rate[OPEN] = (rate[OPEN] / digits)

        df_1min = pd.DataFrame(chart_min[RATE_INFO])
        df_daily = pd.DataFrame(chart_day[RATE_INFO])

        df_1min = apply_so(df_1min)

        # Pivots
        df_1min = apply_pivots(df_daily, df_1min)

        print(symbol, strategy_a(df_1min, pip_value, symbol))

    except Exception as ex:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print('Fail in Simulator:', ex.args, 'line:', exc_tb.tb_lineno)


if __name__ == '__main__':
    client = Client()
    client.login(credentials.XTB_DEMO_ID, credentials.XTB_PASS_KEY, mode='demo')

    prepare_data('CADJPY', 0.08)
    # prepare_data('OIL', 8.87)
    # prepare_data('OIL.WTI', 8.87)
    # prepare_data('GASOLINE', 1.86)
    # prepare_data('LSGASOIL', 0.89)
    # prepare_data('SUGAR', 9.92)
    # prepare_data('SOYBEAN', 2.66)
    # prepare_data('CORN', 4.43)
    # prepare_data('WHEAT', 3.54)
    # prepare_data('COCOA', 0.09)
    # prepare_data('COFFEE', 17.72)
    # prepare_data('COTTON', 4.43)
    # prepare_data('COPPER', 0.27)
    # prepare_data('NICKEL', 0.09)
    # prepare_data('ALUMINIUM', 0.44)
    # prepare_data('ZINC', 0.44)
    # prepare_data('PALLADIUM', 0.88)
    # prepare_data('PLATINUM', 1.33)
    # prepare_data('GOLD', 0.89)
    # prepare_data('SILVER', 44.30)
    # prepare_data('BITCOIN', 0.01)
