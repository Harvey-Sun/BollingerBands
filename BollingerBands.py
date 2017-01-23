# -*- coding:utf-8 -*-

from CloudQuant import MiniSimulator
import numpy as np
import pandas as pd

username = 'Harvey_Sun'
password = 'P948894dgmcsy'
Strategy_Name = 'BollingerBands'

INIT_CAP = 100000000
START_DATE = '20130101'
END_DATE = '20161231'
Fee_Rate = 0.001


def initial(sdk):
    # 下载日度最高价、最低价和中证500成分股
    sdk.prepareData(['LZ_GPA_QUOTE_TCLOSE', 'LZ_GPA_INDEX_CSI500MEMBER',
                     'LZ_GPA_SLCIND_STOP_FLAG'])
    # 下面获取close数据是为了判断某些股票当天是否已退市
    close = pd.read_csv('C:\cStrategy\Factor\LZ_GPA_QUOTE_TCLOSE.csv', index_col=0)
    close.index = [str(i) for i in close.index]
    sdk.setGlobal('close', close)
    # 获取股票代码
    stock_list = sdk.getStockList()
    sdk.setGlobal('stock_list', stock_list)
    # 找到中证500成分股
    in_zz500 = pd.Series(sdk.getFieldData('LZ_GPA_INDEX_CSI500MEMBER')[-1]) == 1
    sdk.setGlobal('in_zz500', in_zz500)
    zz500 = list(pd.Series(stock_list)[in_zz500])
    sdk.setGlobal('zz500', zz500)
    # 建立一个字典来管理每只股票的仓位信息
    cash_for_each_stock = INIT_CAP / 500
    position_of_stock = {}
    for stock in zz500:
        position_of_stock[stock] = {}
        position_of_stock[stock]['position'] = 0
        position_of_stock[stock]['cash'] = cash_for_each_stock
        # position_of_stock[stock]['last_trade_day'] = str(int(START_DATE) - 1)
    sdk.setGlobal('position_of_stock', position_of_stock)


def init_per_day(sdk):
    close = sdk.getGlobal('close')
    today = sdk.getNowDate()
    # 选出当天可交易的中证500成分股
    # in_zz500 = bool(sdk.getFieldData('LZ_GPA_INDEX_CSI500MEMBER')[-1])
    stock_list = sdk.getGlobal('stock_list')
    in_zz500 = sdk.getGlobal('in_zz500')
    # not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-1])  # 当日没有停牌的股票
    not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-11:]).all(axis=0)  # 当日和前10日均没有停牌的股票
    on_list = pd.notnull(close.ix[today])  # 存在于市场上的股票
    zz500_not_stop = list(pd.Series(stock_list)[np.logical_and(np.logical_and(in_zz500, not_stop), on_list)])
    sdk.setGlobal('zz500_not_stop', zz500_not_stop)
    sdk.subscribeQuote(zz500_not_stop)
    # 找到中证500成分股前前10天收盘价,并计算MA和上轨
    close = pd.DataFrame(sdk.getFieldData('LZ_GPA_QUOTE_TCLOSE')[-10:], columns=stock_list)[zz500_not_stop]
    mid_line = close.mean(axis=0)
    band_width = close.std(axis=0)
    up_line = mid_line + band_width * 2
    sdk.sdklog(sdk.getNowDate(), '=======================================日期')
    sdk.setGlobal('mid_line', mid_line)
    sdk.setGlobal('up_line', up_line)
    # 建立一个列表，来记录当天有过交易的股票
    traded_stock = []
    sdk.setGlobal('traded_stock', traded_stock)


def strategy(sdk):
    if (sdk.getNowTime() >= '093000') & (sdk.getNowTime() < '150000'):
        # today = sdk.getNowDate()
        zz500_not_stop = sdk.getGlobal('zz500_not_stop')
        traded_stock = sdk.getGlobal('traded_stock')
        mid_line = sdk.getGlobal('mid_line')
        up_line = sdk.getGlobal('up_line')
        # 获取当天仓位信息
        position_of_stock = sdk.getGlobal('position_of_stock')
        # 获得当日还可以买入或卖出的股票代码
        available_stock = list(set(zz500_not_stop) - set(traded_stock))
        quotes = sdk.getQuotes(available_stock)
        buy_orders = []
        sell_orders = []
        for stock in available_stock:
            cash = position_of_stock[stock]['cash']
            position = position_of_stock[stock]['position']
            current_price = quotes[stock].current
            up = up_line[stock]
            mid = mid_line[stock]
            if current_price > up:
                volume = 100 * np.floor(cash / (100 * current_price))
                order = [stock, current_price, volume, 1]
                buy_orders.append(order)
                traded_stock.append(stock)  # 这里有待考虑，下单后不一定会成交,现假设都能成交
                # 计算交易后的仓位变化，并记录在position_of_stock中
                cash_payed = volume * current_price * (1 + Fee_Rate)
                position_of_stock[stock]['cash'] = cash - cash_payed
                position_of_stock[stock]['position'] = position + volume
                # position_of_stock[stock]['last_trade_day'] = today
            elif (current_price < mid) & (position > 0):
                volume = position
                order = [stock, current_price, volume, -1]
                sell_orders.append(order)
                traded_stock.append(stock)
                # 计算交易后的仓位变化，并记录在position_of_stock中
                cash_received = volume * current_price * (1 - Fee_Rate)
                position_of_stock[stock]['cash'] = cash + cash_received
                position_of_stock[stock]['position'] = 0
                # position_of_stock[stock]['last_trade_day'] = today
            else:
                pass
        sdk.makeOrders(buy_orders)
        sdk.makeOrders(sell_orders)
        if buy_orders or sell_orders:
            sdk.sdklog(sdk.getNowTime(), '=================时间')
            sdk.sdklog('Buy orders')
            sdk.sdklog(np.array(buy_orders))
            sdk.sdklog('Sell orders')
            sdk.sdklog(np.array(sell_orders))
        sdk.setGlobal('traded_stock', traded_stock)
        sdk.setGlobal('position_of_stock', position_of_stock)

config = {
    'username': username,
    'password': password,
    'initCapital': INIT_CAP,
    'startDate': START_DATE,
    'endDate': END_DATE,
    'strategy': strategy,
    'initial': initial,
    'preparePerDay': init_per_day,
    'feeRate': Fee_Rate,
    'strategyName': Strategy_Name,
    'logfile': '%s.log' % Strategy_Name,
    'rootpath': 'C:/cStrategy/',
    'executeMode': 'M',
    'feeLimit': 5,
    'cycle': 1,
    'playBackTime': 1,
    'allowfortodayfactor': ['LZ_GPA_INDEX_CSI500MEMBER', 'LZ_GPA_SLCIND_STOP_FLAG']
}

if __name__ == "__main__":
    # 在线运行所需代码
    import os
    config['strategyID'] = os.path.splitext(os.path.split(__file__)[1])[0]
    MiniSimulator(**config).run()
