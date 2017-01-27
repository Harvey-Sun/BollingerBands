# -*- coding:utf-8 -*-

from CloudQuant import MiniSimulator
import numpy as np
import pandas as pd

username = 'Harvey_Sun'
password = 'P948894dgmcsy'
Strategy_Name = 'BollingerBands_parity'

INIT_CAP = 100000000
START_DATE = '20130101'
END_DATE = '20161231'
Fee_Rate = 0.001
window = 10
program_path = 'C:/cStrategy/'


def initial(sdk):
    # 下载日度最高价、最低价和中证500成分股
    sdk.prepareData(['LZ_GPA_QUOTE_TCLOSE', 'LZ_GPA_INDEX_CSI500MEMBER',
                     'LZ_GPA_SLCIND_STOP_FLAG'])


def init_per_day(sdk):
    sdk.clearGlobal()
	today = sdk.getNowDate()
    # 获取当天中证500成分股
    in_zz500 = pd.Series(sdk.getFieldData('LZ_GPA_INDEX_CSI500MEMBER')[-1]) == 1
    stock_list = sdk.getStockList()
    zz500 = list(pd.Series(stock_list)[in_zz500])
    sdk.setGlobal('zz500', zz500)
    # 获取仓位信息
    positions = sdk.getPositions()
    stock_with_position = [i.code for i in positions]
    # 找到中证500外的有仓位的股票
    out_zz500_stock = list(set(stock_with_position) - set(zz500))
    # 以下代码获取当天未停牌未退市的股票，即可交易股票
    # not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-1])  # 当日没有停牌的股票
    not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-(window + 1):]).all(axis=0)  # 当日和前10日均没有停牌的股票
    zz500_available = list(pd.Series(stock_list)[np.logical_and(in_zz500, not_stop)])
    sdk.setGlobal('zz500_available', zz500_available)
    # 以下代码获取当天被移出中证500的有仓位的股票中可交易的股票
    out_zz500_available = list(set(pd.Series(stock_list)[not_stop]).intersection(set(out_zz500_stock)))
    sdk.setGlobal('out_zz500_available', out_zz500_available)
    # 订阅所有可交易的股票
    stock_available = list(set(zz500_available + out_zz500_available))
    sdk.subscribeQuote(stock_available)
    # 找到所有可交易股票的收盘价,并计算MA和上轨
    close = pd.DataFrame(sdk.getFieldData('LZ_GPA_QUOTE_TCLOSE')[-window:], columns=stock_list)[stock_available]
    mid_line = close.mean(axis=0)
    band_width = close.std(axis=0)
    up_line = mid_line + band_width * 2
    # 记录
    sdk.sdklog(today, '=======================================日期')
    sdk.sdklog(len(sdk.getPositions()), '持有股票数量')
    sdk.sdklog(len(stock_available), '订阅股票数量')
    # 全局变量
    sdk.setGlobal('mid_line', mid_line)
    sdk.setGlobal('up_line', up_line)
    # 建立一个列表，来记录当天有过交易的股票
    traded_stock = []
    sdk.setGlobal('traded_stock', traded_stock)


def strategy(sdk):
    if (sdk.getNowTime() >= '093000') & (sdk.getNowTime() < '150000'):
        # 每分钟开始时，加载今日已交易股票、上中轨
        traded_stock = sdk.getGlobal('traded_stock')
        up_line = sdk.getGlobal('up_line')
        mid_line = sdk.getGlobal('mid_line')
        # 获取仓位信息及有仓位的股票
        positions = sdk.getPositions()
        position_dict = dict([[i.code, i.optPosition] for i in positions])
        stock_with_position = [i.code for i in positions]
        number = len(stock_with_position)
        # 找到中证500外的有仓位的股票
        zz500 = sdk.getGlobal('zz500')
        out_zz500_stock = list(set(stock_with_position) - set(zz500))
        out_num = len(out_zz500_stock)
        # 找到目前有仓位且可交易的中证500外的股票
        out_zz500_available = sdk.getGlobal('out_zz500_available')
        out_zz500_tradable = list(set(out_zz500_stock).intersection(set(out_zz500_available)))
        # 获得中证500当日可交易的股票
        zz500_available = sdk.getGlobal('zz500_available')
        # 去除今天已经有交易的股票，获得当下还可交易的股票
        zz500_tradable = list(set(zz500_available) - set(traded_stock))
        # 取得盘口数据
        quotes = sdk.getQuotes(zz500_tradable + out_zz500_tradable)

        # 考虑被移出中证500的那些股票
        sell_orders_out500 = []
        if out_zz500_tradable:
            for stock in out_zz500_tradable:
                position = position_dict[stock]
                current_price = quotes[stock].current
                mid = mid_line[stock]
                if current_price < mid:  # 判断是否卖出
                    order = [stock, current_price, position, -1]
                    sell_orders_out500.append(order)
        sdk.makeOrders(sell_orders_out500)
        # 考虑当日中证500可交易的股票
        buy_orders = []
        sell_orders = []
        for stock in zz500_tradable:
            available_cash = sdk.getAccountInfo().availableCash / (500 - number)
            # 如果当时买入股票超过了500-number？
            current_price = quotes[stock].current
            up = up_line[stock]
            mid = mid_line[stock]
            if (current_price > up) & (stock not in stock_with_position):
                volume = 100 * np.floor(available_cash / (100 * current_price))
                if volume > 0:
                    order = [stock, current_price, volume, 1]
                    buy_orders.append(order)
                    traded_stock.append(stock)  # 这里有待考虑，下单后不一定会成交,现假设都能成交
            elif (current_price < mid) & (stock in stock_with_position):
                volume = position_dict[stock]
                order = [stock, current_price, volume, -1]
                sell_orders.append(order)
                traded_stock.append(stock)
            else:
                pass
        sdk.makeOrders(buy_orders)
        sdk.makeOrders(sell_orders)
        # 记录下单数据
        if buy_orders or sell_orders or sell_orders_out500:
            sdk.sdklog(sdk.getNowTime(), '=================时间')
            if buy_orders:
                sdk.sdklog('Buy orders')
                sdk.sdklog(np.array(buy_orders))
            if sell_orders:
                sdk.sdklog('Sell orders')
                sdk.sdklog(np.array(sell_orders))
            if sell_orders_out500:
                sdk.sdklog('Sell removed stocks')
                sdk.sdklog(np.array(sell_orders_out500))
        
        sdk.setGlobal('traded_stock', traded_stock)


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
    'rootpath': program_path,
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
